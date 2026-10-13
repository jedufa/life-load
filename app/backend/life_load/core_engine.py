"""SQLite-backed Life Load core engine.

This module owns the PIS-style backend contract:

- diary analysis writes draft state only
- approval explicitly promotes a draft into canonical daily_log truth
- deterministic scoring and weekly/drift summaries are derived from approved
  entries only

It intentionally does not import Garmin, Android, browser, or the broader
platform control-surface modules.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

DB_REL = Path("data/health.sqlite")
DATE_FMT = "%Y-%m-%d"
SCHEMA_VERSION = "life_load_core_v1"
EXTRACTOR_VERSION = "life_load_fast_extractor_v1"
CORE_SCORING_VERSION = "life_load_core_scoring_v1"
FORMULA_REPLAY_REPORT_VERSION = "life_load_formula_replay_report_v1"
FORMULA_SETTING_KEYS = (
    "include_training_trend_brake",
    "include_garmin_recovery",
    "include_relationship_stress",
    "include_alone_home",
    "include_after_work_decompression",
    "include_project_overrun",
    "include_late_phone",
    "include_home_office",
)

BOOL_FIELDS = {
    "sleep_ok",
    "nutrition_ok",
    "binge",
    "migraine_warning",
    "decompression_done",
    "after_work_decompression_done",
    "evening_chain_broken",
    "shutdown_done",
    "phone_after_21",
    "project_overrun",
    "home_office",
    "alone_home",
    "rehab_done",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
}
INT_FIELDS = {
    "mood",
    "stress",
    "energy",
    "foot_pain",
    "shoulder_pain",
    "activity_duration_min",
    "wife_conflict_count",
}
ENTRY_FIELDS = [
    "date",
    "completed",
    "diary_text",
    "diary_summary",
    "tags",
    "sleep_ok",
    "nutrition_ok",
    "alcohol",
    "binge",
    "mood",
    "stress",
    "energy",
    "foot_pain",
    "shoulder_pain",
    "migraine_warning",
    "decompression_done",
    "shutdown_done",
    "phone_after_21",
    "project_overrun",
    "primary_activity_type",
    "activity_duration_min",
    "rehab_done",
    "other_symptoms",
    "work_intensity",
    "family_stress",
    "home_office",
    "alone_home",
    "homework_done",
    "after_work_decompression_done",
    "evening_chain_broken",
    "wife_conflict_count",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
    "zone",
    "mode",
    "next_action",
    "approved_at",
    "created_at",
    "updated_at",
]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("date is required in YYYY-MM-DD format")
    try:
        return dt.datetime.strptime(text, DATE_FMT).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid date '{text}'; expected YYYY-MM-DD") from exc


def week_start(date_text: str) -> str:
    day = dt.datetime.strptime(date_text, DATE_FMT).date()
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def week_end(date_text: str) -> str:
    start = dt.datetime.strptime(week_start(date_text), DATE_FMT).date()
    return (start + dt.timedelta(days=6)).isoformat()


def is_weekend(date_text: str) -> bool:
    return dt.datetime.strptime(date_text, DATE_FMT).date().weekday() >= 5


def _json_dump(value: Any, default: Any) -> str:
    try:
        return json.dumps(value if value is not None else default, sort_keys=True)
    except Exception:
        return json.dumps(default, sort_keys=True)


def _json_load(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _bool(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _bool_db(value: Any) -> int | None:
    parsed = _bool(value)
    if parsed is None:
        return None
    return 1 if parsed else 0


def _int_0_10(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return max(0, min(10, int(float(str(value).split("/")[0].strip()))))
    except Exception:
        return None


def _tags(value: Any) -> List[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    tags: List[str] = []
    for item in raw:
        tag = str(item or "").strip().lower().replace("_", "-").replace(" ", "-")
        if tag and tag not in tags:
            tags.append(tag[:48])
    return tags


def _alcohol(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in {"false", "0", "no", "none", "na", "n/a"}:
        return "none"
    if text in {"true", "1", "yes", "home", "at_home", "at-home"}:
        return "home"
    if text in {"social", "out", "outside"}:
        return "social"
    return None


def _family_stress(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in {"low", "normal", "heavy"}:
        return text
    if text in {"high", "extreme", "very heavy", "overloaded"}:
        return "heavy"
    if text in {"0", "1", "2", "3"}:
        return "low"
    if text in {"4", "5", "6"}:
        return "normal"
    return "heavy"


def _activity_type(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "none": "",
        "walking": "walk",
        "cycling": "bike",
        "biking": "bike",
        "jog": "run",
        "jogging": "run",
        "running": "run",
        "cross_fit": "crossfit",
        "strength": "crossfit",
        "physio": "rehab",
        "mobility": "rehab",
        "bike_commute": "bike",
    }
    normalized = aliases.get(text, text)
    if normalized in {"", "walk", "bike", "run", "crossfit", "rehab", "meditation", "other"}:
        return normalized
    return None


def _minutes(value: Any) -> int | None:
    parsed = _int_0_10(value)
    if parsed is not None and str(value).strip() == str(parsed):
        return parsed
    if value is None or str(value).strip() == "":
        return None
    try:
        return max(0, min(24 * 60, int(float(str(value).split("/")[0].strip()))))
    except Exception:
        return None


def _count_0_12(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return max(0, min(12, int(float(str(value).strip()))))
    except Exception:
        return None


def _diary_text(entry: Mapping[str, Any]) -> str:
    return str(entry.get("diary_text") or "").lower()


def _text_has_any(text: str, tokens: Iterable[str]) -> bool:
    return any(token in text for token in tokens)


def _diary_says_no_alcohol(text: str) -> bool:
    lowered = str(text or "").lower()
    negative_patterns = (
        "no alcohol",
        "no beer",
        "no wine",
        "didn't have alcohol",
        "did not have alcohol",
        "didn't drink",
        "did not drink",
        "without alcohol",
        "alcohol free",
        "alcohol-free",
        "zero alcohol",
    )
    positive_patterns = (
        "had alcohol",
        "drank alcohol",
        "drank beer",
        "drank wine",
        "beer at home",
        "wine at home",
        "alcohol at home",
    )
    return any(pattern in lowered for pattern in negative_patterns) and not any(pattern in lowered for pattern in positive_patterns)


def _homework(value: Any, *, date_text: str) -> str | None:
    if is_weekend(date_text):
        return "na"
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in {"na", "n/a", "none"}:
        return "na"
    parsed = _bool(text)
    if parsed is None:
        return None
    return "yes" if parsed else "no"


def normalize_structured_fields(fields: Mapping[str, Any], *, date_text: str, reject_unknown: bool = False) -> Dict[str, Any]:
    allowed = {
        "diary_text",
        "diary_summary",
        "summary",
        "tags",
        "alcohol",
        "work_intensity",
        "family_stress",
        "homework_done",
        "primary_activity_type",
        "other_symptoms",
        *BOOL_FIELDS,
        *INT_FIELDS,
    }
    unknown = sorted(set(fields) - allowed)
    if reject_unknown and unknown:
        raise ValueError(f"unknown fields: {', '.join(unknown)}")
    clean: Dict[str, Any] = {}
    for key in BOOL_FIELDS:
        if key in fields:
            clean[key] = _bool(fields.get(key))
    for key in INT_FIELDS:
        if key in fields:
            if key == "activity_duration_min":
                clean[key] = _minutes(fields.get(key))
            elif key == "wife_conflict_count":
                clean[key] = _count_0_12(fields.get(key))
            else:
                clean[key] = _int_0_10(fields.get(key))
    if "alcohol" in fields:
        clean["alcohol"] = _alcohol(fields.get("alcohol"))
    if "work_intensity" in fields:
        text = str(fields.get("work_intensity") or "").strip().lower()
        if text in {"low", "normal", "heavy", "extreme"}:
            clean["work_intensity"] = text
        else:
            clean["work_intensity"] = None
    if "family_stress" in fields:
        clean["family_stress"] = _family_stress(fields.get("family_stress"))
    if "homework_done" in fields:
        clean["homework_done"] = _homework(fields.get("homework_done"), date_text=date_text)
    if "tags" in fields:
        clean["tags"] = _tags(fields.get("tags"))
    if "primary_activity_type" in fields:
        clean["primary_activity_type"] = _activity_type(fields.get("primary_activity_type"))
    if "other_symptoms" in fields:
        clean["other_symptoms"] = str(fields.get("other_symptoms") or "").strip()[:240]
    if "diary_summary" in fields or "summary" in fields:
        clean["diary_summary"] = str(fields.get("diary_summary") or fields.get("summary") or "").strip()[:180]
    if "diary_text" in fields:
        clean["diary_text"] = str(fields.get("diary_text") or "").strip()
    return {key: value for key, value in clean.items() if value is not None}


@dataclass
class LifeLoadCore:
    repo_root: Path
    db_rel: Path = DB_REL

    @property
    def db_path(self) -> Path:
        return (self.repo_root / self.db_rel).resolve()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS daily_log (
                date TEXT PRIMARY KEY,
                completed INTEGER NOT NULL DEFAULT 0,
                diary_text TEXT NOT NULL DEFAULT '',
                diary_summary TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                sleep_ok INTEGER,
                nutrition_ok INTEGER,
                alcohol TEXT,
                binge INTEGER,
                mood INTEGER,
                stress INTEGER,
                energy INTEGER,
                foot_pain INTEGER,
                shoulder_pain INTEGER,
                migraine_warning INTEGER,
                decompression_done INTEGER,
                shutdown_done INTEGER,
                phone_after_21 INTEGER,
                project_overrun INTEGER,
                primary_activity_type TEXT NOT NULL DEFAULT '',
                activity_duration_min INTEGER,
                rehab_done INTEGER,
                other_symptoms TEXT NOT NULL DEFAULT '',
                work_intensity TEXT,
                family_stress TEXT,
                home_office INTEGER,
                alone_home INTEGER,
                homework_done TEXT,
                after_work_decompression_done INTEGER,
                evening_chain_broken INTEGER,
                wife_conflict_count INTEGER,
                wife_conflict_school INTEGER,
                wife_conflict_chores INTEGER,
                wife_conflict_other INTEGER,
                zone TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                approved_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS draft_entry (
                date TEXT PRIMARY KEY,
                diary_text TEXT NOT NULL DEFAULT '',
                structured_json TEXT NOT NULL DEFAULT '{}',
                summary TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_proposal (
                proposal_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                diary_text_hash TEXT NOT NULL,
                extractor_version TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS derived_daily_summary (
                date TEXT PRIMARY KEY,
                life_load_score REAL NOT NULL DEFAULT 0,
                base_score REAL NOT NULL DEFAULT 0,
                profile_adjusted_score REAL NOT NULL DEFAULT 0,
                strain_score REAL NOT NULL DEFAULT 0,
                recovery_score REAL NOT NULL DEFAULT 0,
                training_load REAL NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                red_flags_json TEXT NOT NULL DEFAULT '[]',
                next_action TEXT NOT NULL DEFAULT '',
                why_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0,
                guidance_thresholds_json TEXT NOT NULL DEFAULT '{}',
                profile_modifiers_json TEXT NOT NULL DEFAULT '[]',
                profile_effects_json TEXT NOT NULL DEFAULT '[]',
                scoring_version TEXT NOT NULL DEFAULT '',
                formula_settings_json TEXT NOT NULL DEFAULT '{}',
                formula_settings_hash TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS derived_weekly_summary (
                week_start TEXT PRIMARY KEY,
                week_end TEXT NOT NULL,
                approved_days INTEGER NOT NULL DEFAULT 0,
                sleep_count INTEGER NOT NULL DEFAULT 0,
                nutrition_count INTEGER NOT NULL DEFAULT 0,
                alcohol_home_count INTEGER NOT NULL DEFAULT 0,
                binge_count INTEGER NOT NULL DEFAULT 0,
                late_phone_count INTEGER NOT NULL DEFAULT 0,
                project_overrun_count INTEGER NOT NULL DEFAULT 0,
                pain_warning_count INTEGER NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                top_drift_signals_json TEXT NOT NULL DEFAULT '[]',
                next_action TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """,
        ]
        with self.connect() as conn, conn:
            for statement in statements:
                conn.execute(statement)
            self._add_missing_columns(conn)

    def _add_missing_columns(self, conn: sqlite3.Connection) -> None:
        def existing_columns(table: str) -> set[str]:
            return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}

        def add_columns(table: str, columns: Mapping[str, str]) -> None:
            present = existing_columns(table)
            for name, definition in columns.items():
                if name not in present:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

        add_columns(
            "daily_log",
            {
                "completed": "INTEGER NOT NULL DEFAULT 0",
                "diary_text": "TEXT NOT NULL DEFAULT ''",
                "diary_summary": "TEXT NOT NULL DEFAULT ''",
                "tags": "TEXT NOT NULL DEFAULT '[]'",
                "sleep_ok": "INTEGER",
                "nutrition_ok": "INTEGER",
                "alcohol": "TEXT",
                "binge": "INTEGER",
                "mood": "INTEGER",
                "stress": "INTEGER",
                "energy": "INTEGER",
                "foot_pain": "INTEGER",
                "shoulder_pain": "INTEGER",
                "migraine_warning": "INTEGER",
                "decompression_done": "INTEGER",
                "shutdown_done": "INTEGER",
                "phone_after_21": "INTEGER",
                "project_overrun": "INTEGER",
                "primary_activity_type": "TEXT NOT NULL DEFAULT ''",
                "activity_duration_min": "INTEGER",
                "rehab_done": "INTEGER",
                "other_symptoms": "TEXT NOT NULL DEFAULT ''",
                "work_intensity": "TEXT",
                "family_stress": "TEXT",
                "home_office": "INTEGER",
                "alone_home": "INTEGER",
                "homework_done": "TEXT",
                "after_work_decompression_done": "INTEGER",
                "evening_chain_broken": "INTEGER",
                "wife_conflict_count": "INTEGER",
                "wife_conflict_school": "INTEGER",
                "wife_conflict_chores": "INTEGER",
                "wife_conflict_other": "INTEGER",
                "zone": "TEXT NOT NULL DEFAULT ''",
                "mode": "TEXT NOT NULL DEFAULT ''",
                "next_action": "TEXT NOT NULL DEFAULT ''",
                "approved_at": "TEXT NOT NULL DEFAULT ''",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            },
        )
        add_columns(
            "derived_daily_summary",
            {
                "life_load_score": "REAL NOT NULL DEFAULT 0",
                "base_score": "REAL NOT NULL DEFAULT 0",
                "profile_adjusted_score": "REAL NOT NULL DEFAULT 0",
                "strain_score": "REAL NOT NULL DEFAULT 0",
                "recovery_score": "REAL NOT NULL DEFAULT 0",
                "training_load": "REAL NOT NULL DEFAULT 0",
                "zone": "TEXT NOT NULL DEFAULT ''",
                "mode": "TEXT NOT NULL DEFAULT ''",
                "red_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "next_action": "TEXT NOT NULL DEFAULT ''",
                "why_json": "TEXT NOT NULL DEFAULT '[]'",
                "confidence": "REAL NOT NULL DEFAULT 0",
                "guidance_thresholds_json": "TEXT NOT NULL DEFAULT '{}'",
                "profile_modifiers_json": "TEXT NOT NULL DEFAULT '[]'",
                "profile_effects_json": "TEXT NOT NULL DEFAULT '[]'",
                "scoring_version": "TEXT NOT NULL DEFAULT ''",
                "formula_settings_json": "TEXT NOT NULL DEFAULT '{}'",
                "formula_settings_hash": "TEXT NOT NULL DEFAULT ''",
                "calculated_at": "TEXT NOT NULL DEFAULT ''",
            },
        )
        add_columns(
            "derived_weekly_summary",
            {
                "week_end": "TEXT NOT NULL DEFAULT ''",
                "approved_days": "INTEGER NOT NULL DEFAULT 0",
                "sleep_count": "INTEGER NOT NULL DEFAULT 0",
                "nutrition_count": "INTEGER NOT NULL DEFAULT 0",
                "alcohol_home_count": "INTEGER NOT NULL DEFAULT 0",
                "binge_count": "INTEGER NOT NULL DEFAULT 0",
                "late_phone_count": "INTEGER NOT NULL DEFAULT 0",
                "project_overrun_count": "INTEGER NOT NULL DEFAULT 0",
                "pain_warning_count": "INTEGER NOT NULL DEFAULT 0",
                "zone": "TEXT NOT NULL DEFAULT ''",
                "mode": "TEXT NOT NULL DEFAULT ''",
                "top_drift_signals_json": "TEXT NOT NULL DEFAULT '[]'",
                "next_action": "TEXT NOT NULL DEFAULT ''",
                "calculated_at": "TEXT NOT NULL DEFAULT ''",
            },
        )

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> Dict[str, Any] | None:
        self.migrate()
        with self.connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        self.migrate()
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def core_store(repo_root: Path | str) -> LifeLoadCore:
    store = LifeLoadCore(repo_root=Path(repo_root))
    store.migrate()
    return store


def _draft_from_row(row: Mapping[str, Any] | None, *, date_text: str) -> Dict[str, Any] | None:
    if not row:
        return None
    structured = _json_load(row.get("structured_json"), {})
    return {
        "date": date_text,
        "diary_text": row.get("diary_text") or "",
        "structured": structured,
        "summary": row.get("summary") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _entry_from_row(row: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not row:
        return None
    entry = dict(row)
    entry["tags"] = _json_load(entry.get("tags"), [])
    for key in BOOL_FIELDS:
        if key in entry:
            entry[key] = None if entry[key] is None else bool(entry[key])
    entry["completed"] = bool(entry.get("completed"))
    return entry


def legacy_entry_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    approved = payload.get("entry") if isinstance(payload.get("entry"), Mapping) else None
    draft = payload.get("draftEntry") if isinstance(payload.get("draftEntry"), Mapping) else None
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    entry = dict(approved or {})
    if not entry and draft:
        structured = dict(draft.get("structured") or {})
        entry = {
            "date": payload.get("date"),
            "diary_text": draft.get("diary_text") or "",
            "diary_summary": draft.get("summary") or structured.get("diary_summary") or "",
            **structured,
        }
    entry_state = "approved" if approved else "draft" if draft else "blank"
    compat = {
        **dict(payload),
        "entry": entry or {"date": payload.get("date")},
        "approved_entry": dict(approved) if approved else None,
        "score": dict(summary),
        "entry_state": entry_state,
        "has_draft": bool(draft),
        "entry_exists": bool(approved),
        "approved_at": str((approved or {}).get("approved_at") or ""),
        "draft_updated_at": str((draft or {}).get("updated_at") or ""),
        "latest_proposal": payload.get("proposal"),
    }
    return compat


def _week_context(store: LifeLoadCore, date_text: str) -> Dict[str, Any]:
    start, end = week_start(date_text), week_end(date_text)
    row = store.fetch_one("SELECT * FROM derived_weekly_summary WHERE week_start = ?", (start,))
    return dict(row) if row else {"week_start": start, "week_end": end, "approved_days": 0}


def get_entry_payload(store: LifeLoadCore, *, date_value: str) -> Dict[str, Any]:
    date_text = parse_date(date_value)
    approved = _entry_from_row(store.fetch_one("SELECT * FROM daily_log WHERE date = ?", (date_text,)))
    draft = _draft_from_row(store.fetch_one("SELECT * FROM draft_entry WHERE date = ?", (date_text,)), date_text=date_text)
    summary = store.fetch_one("SELECT * FROM derived_daily_summary WHERE date = ?", (date_text,))
    if summary:
        summary["red_flags"] = _json_load(summary.pop("red_flags_json", "[]"), [])
        summary["why"] = _json_load(summary.pop("why_json", "[]"), [])
        summary["guidance_thresholds"] = _json_load(summary.pop("guidance_thresholds_json", "{}"), {})
        summary["profile_modifiers"] = _json_load(summary.pop("profile_modifiers_json", "[]"), [])
        summary["profile_effects"] = _json_load(summary.pop("profile_effects_json", "[]"), [])
    return {
        "schema_version": "life_load_entry_payload_v1",
        "date": date_text,
        "entry": approved,
        "draftEntry": draft,
        "summary": summary,
        "week_context": _week_context(store, date_text),
    }


def update_draft_payload(store: LifeLoadCore, payload: Mapping[str, Any]) -> Dict[str, Any]:
    date_text = parse_date(str(payload.get("date") or ""))
    current = store.fetch_one("SELECT * FROM draft_entry WHERE date = ?", (date_text,))
    structured = _json_load((current or {}).get("structured_json"), {})
    updates = payload.get("fields") if isinstance(payload.get("fields"), Mapping) else payload
    clean = normalize_structured_fields(updates, date_text=date_text)
    structured.update(clean)
    diary_text = str(payload.get("diary_text") or (current or {}).get("diary_text") or structured.get("diary_text") or "")
    summary = str(payload.get("summary") or structured.get("diary_summary") or (current or {}).get("summary") or "")[:180]
    now = utc_now_iso()
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO draft_entry(date, diary_text, structured_json, summary, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              diary_text=excluded.diary_text,
              structured_json=excluded.structured_json,
              summary=excluded.summary,
              updated_at=excluded.updated_at
            """,
            (date_text, diary_text, _json_dump(structured, {}), summary, now),
        )
    return get_entry_payload(store, date_value=date_text)


def fast_codex_extract(
    *,
    repo_root: Path,
    date_text: str,
    diary_text: str,
    approved_entry: Mapping[str, Any] | None,
    current_draft: Mapping[str, Any] | None,
    week_context: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    from life_load.extraction import analyze_diary_entry

    return analyze_diary_entry(
        date=date_text,
        diary_text=diary_text,
        existing_entry={
            "approved": dict(approved_entry or {}),
            "draft": dict(current_draft or {}),
        },
        week_context=week_context,
        repo_root=repo_root,
    )


def validate_proposal(request_date: str, raw: Mapping[str, Any]) -> Dict[str, Any]:
    if parse_date(str(raw.get("date") or "")) != request_date:
        raise ValueError("proposal date does not match request date")
    fields = raw.get("fields")
    if not isinstance(fields, Mapping):
        raise ValueError("proposal fields must be an object")
    clean_fields = normalize_structured_fields(fields, date_text=request_date)
    red_flags = raw.get("red_flags") if isinstance(raw.get("red_flags"), list) else []
    valid_flags = []
    for item in red_flags:
        if not isinstance(item, Mapping):
            continue
        severity = str(item.get("severity") or "").lower()
        if severity not in {"green", "yellow", "orange", "red"}:
            continue
        valid_flags.append(
            {
                "type": str(item.get("type") or "")[:64],
                "severity": severity,
                "evidence": str(item.get("evidence") or "")[:240],
            }
        )
    return {
        "date": request_date,
        "fields": clean_fields,
        "summary": str(raw.get("summary") or "")[:180],
        "red_flags": valid_flags,
        "next_action": str(raw.get("next_action") or "")[:240],
        "extractor_version": str(raw.get("extractor_version") or EXTRACTOR_VERSION)[:80],
        "extractor_model": str(raw.get("extractor_model") or "")[:80],
        "extractor_timeout_s": int(raw.get("extractor_timeout_s") or 0),
    }


def _apply_diary_safety_overrides(proposal: Mapping[str, Any], *, diary_text: str) -> Dict[str, Any]:
    clean = dict(proposal)
    fields = dict(clean.get("fields") or {})
    red_flags = [dict(item) for item in clean.get("red_flags") or [] if isinstance(item, Mapping)]
    if _diary_says_no_alcohol(diary_text):
        fields["alcohol"] = "none"
        tags = [tag for tag in _tags(fields.get("tags")) if tag != "alcohol"]
        if tags:
            fields["tags"] = tags
        elif "tags" in fields:
            fields["tags"] = []
        red_flags = [flag for flag in red_flags if str(flag.get("type") or "").lower() != "alcohol"]
        summary = str(clean.get("summary") or "")
        if summary.strip().lower() == "alcohol":
            clean["summary"] = "No alcohol."
    clean["fields"] = fields
    clean["red_flags"] = red_flags
    return clean


Extractor = Callable[..., Mapping[str, Any] | str]


def analyze_diary_payload(store: LifeLoadCore, payload: Mapping[str, Any], *, extractor: Extractor | None = None) -> Dict[str, Any]:
    date_text = parse_date(str(payload.get("date") or ""))
    diary_text = str(payload.get("diary_text") or "").strip()
    if not diary_text:
        raise ValueError("diary_text is required")
    now = utc_now_iso()
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO draft_entry(date, diary_text, structured_json, summary, updated_at)
            VALUES (?, ?, COALESCE((SELECT structured_json FROM draft_entry WHERE date = ?), '{}'), COALESCE((SELECT summary FROM draft_entry WHERE date = ?), ''), ?)
            ON CONFLICT(date) DO UPDATE SET diary_text=excluded.diary_text, updated_at=excluded.updated_at
            """,
            (date_text, diary_text, date_text, date_text, now),
        )
    proposal_id = f"llp_{uuid.uuid4().hex[:16]}"
    raw_result: Mapping[str, Any] | str
    try:
        extractor_fn = extractor
        if extractor_fn is None:
            extractor_fn = lambda **kwargs: fast_codex_extract(repo_root=store.repo_root, **kwargs)
        raw_result = extractor_fn(
            date_text=date_text,
            diary_text=diary_text,
            approved_entry=_entry_from_row(store.fetch_one("SELECT * FROM daily_log WHERE date = ?", (date_text,))),
            current_draft=_draft_from_row(store.fetch_one("SELECT * FROM draft_entry WHERE date = ?", (date_text,)), date_text=date_text),
            week_context=_week_context(store, date_text),
        )
        if isinstance(raw_result, str):
            raw_result = json.loads(raw_result)
        if not isinstance(raw_result, Mapping):
            raise ValueError("extractor result must be JSON object")
        proposal = _apply_diary_safety_overrides(validate_proposal(date_text, raw_result), diary_text=diary_text)
    except Exception as exc:
        with store.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO ai_proposal(proposal_id, date, diary_text_hash, extractor_version, raw_json, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    date_text,
                    hashlib.sha256(diary_text.encode()).hexdigest(),
                    EXTRACTOR_VERSION,
                    "{}",
                    "error",
                    str(exc),
                    utc_now_iso(),
                ),
            )
        return {**get_entry_payload(store, date_value=date_text), "proposal": None, "warnings": [str(exc)]}

    with store.connect() as conn, conn:
        current = conn.execute("SELECT structured_json FROM draft_entry WHERE date = ?", (date_text,)).fetchone()
        structured = _json_load(current["structured_json"] if current else "{}", {})
        structured.update(proposal["fields"])
        if proposal.get("summary"):
            structured["diary_summary"] = proposal["summary"]
        conn.execute(
            "UPDATE draft_entry SET structured_json = ?, summary = ?, updated_at = ? WHERE date = ?",
            (_json_dump(structured, {}), proposal.get("summary") or "", utc_now_iso(), date_text),
        )
        conn.execute(
            """
            INSERT INTO ai_proposal(proposal_id, date, diary_text_hash, extractor_version, raw_json, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, '', ?)
            """,
            (
                proposal_id,
                date_text,
                hashlib.sha256(diary_text.encode()).hexdigest(),
                str(proposal.get("extractor_version") or EXTRACTOR_VERSION),
                _json_dump(proposal, {}),
                "applied_to_draft",
                utc_now_iso(),
            ),
        )
    return {
        **get_entry_payload(store, date_value=date_text),
        "proposal": proposal,
        "warnings": [],
        "extractor_version": proposal.get("extractor_version") or EXTRACTOR_VERSION,
        "extractor_model": proposal.get("extractor_model") or "",
        "extractor_timeout_s": int(proposal.get("extractor_timeout_s") or 0),
    }


def _family_stress_points(value: str | None) -> float:
    return {"low": 0.0, "normal": 0.5, "heavy": 2.0}.get(str(value or ""), 0.0)


def _zone_rank(zone: str | None) -> int:
    return {"green": 0, "yellow": 1, "orange": 2, "red": 3}.get(str(zone or "").lower(), 0)


def _zone_from_rank(rank: int) -> str:
    return {0: "green", 1: "yellow", 2: "orange", 3: "red"}[max(0, min(3, rank))]


def _recent_context_from_rows(rows: Iterable[Mapping[str, Any]], *, lookback_days: int = 6) -> Dict[str, Any]:
    rows = list(rows)
    signals: List[str] = []
    late_phone_count = sum(1 for row in rows if row.get("phone_after_21") == 1)
    project_count = sum(1 for row in rows if row.get("project_overrun") == 1)
    sleep_fail_count = sum(1 for row in rows if row.get("sleep_ok") == 0)
    nutrition_fail_count = sum(1 for row in rows if row.get("nutrition_ok") == 0)
    binge_count = sum(1 for row in rows if row.get("binge") == 1)
    alcohol_home_count = sum(1 for row in rows if row.get("alcohol") == "home")
    pain_warning_count = sum(1 for row in rows if max(row.get("foot_pain") or 0, row.get("shoulder_pain") or 0) >= 5)
    relationship_count = sum(int(row.get("wife_conflict_count") or 0) for row in rows)
    alone_count = sum(1 for row in rows if row.get("alone_home") == 1)
    decompression_miss_count = sum(1 for row in rows if row.get("after_work_decompression_done") == 0 or row.get("decompression_done") == 0)
    orange_red_count = sum(1 for row in rows if _zone_rank(row.get("summary_zone")) >= 2)
    yellow_plus_count = sum(1 for row in rows if _zone_rank(row.get("summary_zone")) >= 1)
    training_7d = round(sum(float(row.get("training_load") or 0.0) for row in rows), 2)

    if late_phone_count >= 2:
        signals.append("repeated late phone")
    if project_count >= 2:
        signals.append("repeated project overrun")
    if sleep_fail_count >= 2:
        signals.append("sleep drift repeated")
    if nutrition_fail_count >= 2:
        signals.append("nutrition drift repeated")
    if decompression_miss_count >= 2:
        signals.append("decompression missed repeatedly")
    if relationship_count >= 3:
        signals.append("relationship stress accumulating")
    if alone_count >= 2:
        signals.append("alone-at-home trigger repeated")
    if pain_warning_count >= 1:
        signals.append("recent pain warning")
    if binge_count:
        signals.append("recent eating episode")
    if alcohol_home_count:
        signals.append("recent alcohol at home")
    if orange_red_count >= 2:
        signals.append("repeated hold/stabilize days")
    elif yellow_plus_count >= 3:
        signals.append("repeated protect days")
    if training_7d >= 8.0 and (sleep_fail_count or pain_warning_count or decompression_miss_count):
        signals.append("activity load with weak recovery")

    risk_rank = 0
    if alcohol_home_count or orange_red_count >= 2 or len(signals) >= 5:
        risk_rank = 3
    elif binge_count or pain_warning_count or len(signals) >= 3 or yellow_plus_count >= 3:
        risk_rank = 2
    elif signals:
        risk_rank = 1
    return {
        "lookback_days": lookback_days,
        "approved_days": len(rows),
        "risk_zone": _zone_from_rank(risk_rank),
        "signals": signals[:6],
        "counts": {
            "late_phone": late_phone_count,
            "project_overrun": project_count,
            "sleep_fail": sleep_fail_count,
            "nutrition_fail": nutrition_fail_count,
            "binge": binge_count,
            "alcohol_home": alcohol_home_count,
            "pain_warning": pain_warning_count,
            "relationship_stress": relationship_count,
            "alone_home": alone_count,
            "decompression_missed": decompression_miss_count,
            "yellow_plus_days": yellow_plus_count,
            "orange_red_days": orange_red_count,
        },
        "training_load_7d": training_7d,
    }


def _recent_context(store: LifeLoadCore, date_text: str, *, lookback_days: int = 6) -> Dict[str, Any]:
    day = dt.datetime.strptime(date_text, DATE_FMT).date()
    start = (day - dt.timedelta(days=lookback_days)).isoformat()
    end = (day - dt.timedelta(days=1)).isoformat()
    rows = store.fetch_all(
        """
        SELECT d.*, s.zone AS summary_zone, s.life_load_score, s.training_load, s.why_json
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE d.date >= ? AND d.date <= ? AND d.approved_at != ''
        ORDER BY d.date ASC
        """,
        (start, end),
    )
    return _recent_context_from_rows(rows, lookback_days=lookback_days)


def _formula_toggle(settings: Mapping[str, Any] | None, key: str, default: bool = True) -> bool:
    formula = settings.get("formula") if isinstance(settings, Mapping) and isinstance(settings.get("formula"), Mapping) else settings
    if not isinstance(formula, Mapping) or key not in formula:
        return default
    return _bool(formula.get(key)) is True


PROFILE_MODIFIER_KEYS = {"balanced", "protective", "sports_light"}


def _profile_modifiers(settings: Mapping[str, Any] | None) -> set[str]:
    formula = settings.get("formula") if isinstance(settings, Mapping) and isinstance(settings.get("formula"), Mapping) else settings
    if not isinstance(formula, Mapping):
        return set()
    raw_modifiers = formula.get("profile_modifiers")
    modifiers: set[str] = set()
    if isinstance(raw_modifiers, list):
        modifiers = {str(item) for item in raw_modifiers if str(item) in PROFILE_MODIFIER_KEYS and str(item) != "balanced"}
    if not modifiers:
        legacy = str(formula.get("profile") or "")
        if legacy in PROFILE_MODIFIER_KEYS and legacy != "balanced":
            modifiers.add(legacy)
    return modifiers


def _formula_settings_snapshot(settings: Mapping[str, Any] | None) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {key: _formula_toggle(settings, key) for key in FORMULA_SETTING_KEYS}
    snapshot["profile_modifiers"] = sorted(_profile_modifiers(settings))
    return snapshot


def _formula_settings_hash(settings: Mapping[str, Any] | None) -> str:
    payload = _json_dump(_formula_settings_snapshot(settings), {})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def score_entry(entry: Mapping[str, Any], *, formula_settings: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    modifiers = _profile_modifiers(formula_settings)
    protective = "protective" in modifiers
    sports_light = "sports_light" in modifiers
    profile_effects: List[str] = []
    guidance_thresholds = {
        "medium": 32 if protective else 35,
        "high": 65 if protective else 70,
    }
    if protective:
        profile_effects.append("protective lowered medium-risk threshold to 32")
        profile_effects.append("protective lowered high-risk threshold to 65")
    profile_score_delta = 0.0
    strain = 0.0
    recovery = 0.0
    red_flags: List[str] = []
    why: List[str] = []
    missing = 0
    diary_text = _diary_text(entry)
    sleep_fragmented = _text_has_any(
        diary_text,
        (
            "couldn't sleep",
            "could not sleep",
            "couldn't fall asleep",
            "could not fall asleep",
            "woke up at midnight",
            "awake for 2 hours",
            "awake for two hours",
            "couldn't sleep again",
            "could not sleep again",
        ),
    )
    project_rumination = "project" in diary_text and _text_has_any(
        diary_text,
        ("head full", "mind full", "couldn't fall asleep", "could not fall asleep", "ruminat", "couldn't switch off", "could not switch off"),
    )

    def known_bool(key: str) -> bool | None:
        nonlocal missing
        value = entry.get(key)
        if value is None:
            missing += 1
            return None
        return bool(value)

    sleep = known_bool("sleep_ok")
    if sleep is True:
        recovery += 2.0
    elif sleep is False:
        strain += 2.0
        why.append("Sleep drift")
    if sleep_fragmented and sleep is not False:
        strain += 2.0
        why.append("Sleep fragmentation")

    nutrition = known_bool("nutrition_ok")
    if nutrition is True:
        recovery += 2.0
    elif nutrition is False:
        strain += 2.0
        why.append("Nutrition drift")

    alcohol = _alcohol(entry.get("alcohol"))
    if alcohol == "home":
        strain += 6.0
        red_flags.append("alcohol at home")
        why.append("Alcohol at home")
    elif alcohol == "social":
        strain += 2.0
        why.append("Alcohol exposure")

    binge = known_bool("binge")
    shutdown = known_bool("shutdown_done")
    late_phone = known_bool("phone_after_21")
    project_overrun = known_bool("project_overrun")
    include_late_phone = _formula_toggle(formula_settings, "include_late_phone")
    include_project_overrun = _formula_toggle(formula_settings, "include_project_overrun")
    if binge is True:
        strain += 5.0
        why.append("Binge")
        if shutdown is False or late_phone is True:
            red_flags.append("binge plus evening drift")

    for key, label, points in (
        ("migraine_warning", "Migraine warning", 3.0),
    ):
        value = known_bool(key)
        if value is True:
            strain += points
            why.append(label)
    if late_phone is True and include_late_phone:
        late_phone_delta = 0.5 if protective else 0.0
        strain += 2.0 + late_phone_delta
        profile_score_delta += late_phone_delta
        if protective:
            profile_effects.append("protective increased late-phone strain")
        why.append("Late phone")
    if project_overrun is True and include_project_overrun:
        project_delta = 0.5 if protective else 0.0
        strain += 2.5 + project_delta
        profile_score_delta += project_delta
        if protective:
            profile_effects.append("protective increased project-overrun strain")
        why.append("Project overrun")

    if shutdown is False:
        shutdown_delta = 0.5 if protective else 0.0
        strain += 2.5 + shutdown_delta
        profile_score_delta += shutdown_delta
        if protective:
            profile_effects.append("protective increased shutdown-missed strain")
        why.append("Shutdown missed")
    decompression = known_bool("decompression_done")
    if decompression is True:
        recovery += 1.5
    elif decompression is False:
        strain += 2.0
        why.append("Decompression missed")

    foot_pain_value = _int_0_10(entry.get("foot_pain"))
    shoulder_pain_value = _int_0_10(entry.get("shoulder_pain"))
    for value, label in ((foot_pain_value, "Foot pain"), (shoulder_pain_value, "Shoulder pain")):
        if value is None:
            missing += 1
            continue
        strain += value * 0.45
        if value >= 5:
            why.append(f"{label} {value}")

    energy_value = _int_0_10(entry.get("energy"))
    for key, label, recovery_factor, strain_factor in (
        ("mood", "Mood", 0.25, 0.0),
        ("energy", "Energy", 0.35, 0.0),
        ("stress", "Stress", 0.0, 0.6),
    ):
        value = _int_0_10(entry.get(key))
        if value is None:
            missing += 1
            continue
        recovery += value * recovery_factor
        strain += value * strain_factor
        if key == "stress" and value >= 7:
            why.append(f"Stress {value}")

    strain += _family_stress_points(_family_stress(entry.get("family_stress")))
    if entry.get("work_intensity") == "heavy":
        strain += 1.5
        why.append("Heavy work")
    elif entry.get("work_intensity") == "extreme":
        strain += 2.5
        why.append("Extreme work")
    if _bool(entry.get("home_office")) is True and _formula_toggle(formula_settings, "include_home_office"):
        strain += 0.5
    if _bool(entry.get("alone_home")) is True and _formula_toggle(formula_settings, "include_alone_home"):
        strain += 1.5
        why.append("Alone at home")
    if _bool(entry.get("after_work_decompression_done")) is True and _formula_toggle(formula_settings, "include_after_work_decompression"):
        recovery += 1.0
    elif _bool(entry.get("after_work_decompression_done")) is False and _formula_toggle(formula_settings, "include_after_work_decompression"):
        after_work_delta = 0.5 if protective else 0.0
        strain += 3.0 + after_work_delta
        profile_score_delta += after_work_delta
        if protective:
            profile_effects.append("protective increased after-work decompression strain")
        why.append("After-work decompression missed")
    if _bool(entry.get("evening_chain_broken")) is True:
        strain += 2.5
        why.append("Evening chain broken")
    wife_conflicts = _count_0_12(entry.get("wife_conflict_count")) or 0
    include_relationship = _formula_toggle(formula_settings, "include_relationship_stress")
    if wife_conflicts and include_relationship:
        strain += min(7.0, wife_conflicts * 2.0)
        why.append(f"Relationship stress x{wife_conflicts}")
    if _bool(entry.get("wife_conflict_school")) is True and include_relationship:
        strain += 1.0
    if _bool(entry.get("wife_conflict_chores")) is True and include_relationship:
        strain += 0.5

    training_load = 0.0
    activity_type = _activity_type(entry.get("primary_activity_type")) or ""
    duration = _minutes(entry.get("activity_duration_min")) or 0
    late_training = _text_has_any(diary_text, ("late training", "late session", "ending at 20:30", "ended at 20:30", "20:30", "8:30"))
    if activity_type:
        per_30 = {
            "walk": 0.4,
            "bike": 0.6,
            "run": 1.6,
            "crossfit": 2.0,
            "rehab": 0.2,
            "meditation": -0.3,
            "other": 0.8,
        }.get(activity_type, 0.0)
        training_load += max(0.0, per_30 * max(0.5, duration / 30.0 if duration else 1.0))
        if activity_type == "meditation":
            recovery += 0.5
    if late_training and activity_type in {"run", "crossfit", "other"}:
        strain += 1.5
        why.append("Late hard training")
    if project_rumination:
        strain += 2.5
        why.append("Project rumination")
    if _bool(entry.get("rehab_done")) is True:
        recovery += 0.8
        if not activity_type:
            training_load += 0.2
    # PIS rule: a completed day is not a hard session. Training is not inferred
    # from completed alone in this backend core.

    if sports_light and training_load:
        pain_blocks_softening = (foot_pain_value is not None and foot_pain_value >= 5) or (shoulder_pain_value is not None and shoulder_pain_value >= 5)
        low_energy_blocks_softening = energy_value is not None and energy_value <= 3
        migraine_signal = _bool(entry.get("migraine_warning")) is True
        sleep_disrupted = sleep is False
        non_training_recovery_priority = bool(red_flags) or (strain - recovery) * 10 >= guidance_thresholds["high"]
        if pain_blocks_softening:
            profile_effects.append("sports_light not applied because pain >= 5")
        elif low_energy_blocks_softening:
            profile_effects.append("sports_light not applied because energy <= 3")
        elif migraine_signal:
            profile_effects.append("sports_light not applied because migraine signal is active")
        elif sleep_disrupted:
            profile_effects.append("sports_light not applied because sleep was disrupted")
        elif non_training_recovery_priority:
            profile_effects.append("sports_light not applied because non-training risk already needs recovery priority")
        else:
            original_training_load = training_load
            training_load = round(training_load * 0.8, 2)
            profile_score_delta += training_load - original_training_load
            profile_effects.append("sports_light softened training load")

    red_override = 8.0 if "alcohol at home" in red_flags else 4.0 if red_flags else 0.0
    profile_adjusted_score = round(strain + training_load - recovery + red_override, 2)
    base_score = round(profile_adjusted_score - profile_score_delta, 2)
    life_load = profile_adjusted_score
    zone = "green"
    if "alcohol at home" in red_flags or life_load >= 10:
        zone = "red"
    elif binge is True or life_load * 10 >= guidance_thresholds["high"] or any("pain" in item.lower() for item in why):
        zone = "orange"
    elif (late_phone is True and include_late_phone) or (project_overrun is True and include_project_overrun) or life_load * 10 >= guidance_thresholds["medium"]:
        zone = "yellow"
    sleep_project_training_combo = (
        (sleep is False or sleep_fragmented)
        and (project_rumination or (project_overrun is True and include_project_overrun))
        and (late_training or training_load >= 2.0)
    )
    if sleep_project_training_combo:
        zone = _zone_from_rank(max(_zone_rank(zone), 2))
        red_flags.append("sleep disrupted after late training/project rumination")
        why.insert(0, "Sleep disrupted after project/training")
    mode = {"green": "continue", "yellow": "protect", "orange": "hold", "red": "stabilize"}[zone]
    confidence = round(max(0.25, 1.0 - min(0.75, missing * 0.08)), 2)
    why = why[:5] or ["No major drift signals"]
    next_action = next_action_card(mode=mode, why=why, entry=entry)
    return {
        "life_load_score": life_load,
        "base_score": base_score,
        "profile_adjusted_score": profile_adjusted_score,
        "guidance_thresholds": guidance_thresholds,
        "profile_modifiers": sorted(modifiers),
        "profile_effects": sorted(set(profile_effects)),
        "strain_score": round(strain, 2),
        "recovery_score": round(recovery, 2),
        "training_load": training_load,
        "zone": zone,
        "mode": mode,
        "red_flags": sorted(set(red_flags)),
        "next_action": next_action,
        "why": why,
        "confidence": confidence,
        "missingness_note": f"{missing} unknown field(s)" if missing else "complete enough",
    }


def score_entry_with_context(
    entry: Mapping[str, Any],
    recent_context: Mapping[str, Any] | None = None,
    *,
    formula_settings: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    score = score_entry(entry, formula_settings=formula_settings)
    context = dict(recent_context or {})
    signals = [str(item) for item in context.get("signals") or [] if str(item).strip()]
    if not signals:
        score["recent_context"] = context
        return score

    risk_zone = str(context.get("risk_zone") or "green")
    risk_rank = _zone_rank(risk_zone)
    current_rank = _zone_rank(score["zone"])
    context_strain = {1: 1.0, 2: 2.5, 3: 4.0}.get(risk_rank, 0.0)
    adjusted_rank = max(current_rank, min(3, risk_rank))
    if current_rank == 0 and risk_rank >= 2:
        # A green-looking day after several drift days should still be protect,
        # not hold, unless today's own data also shows strain.
        adjusted_rank = 1

    why = list(dict.fromkeys([*signals[:3], *score["why"]]))[:5]
    score["strain_score"] = round(float(score["strain_score"]) + context_strain, 2)
    score["life_load_score"] = round(float(score["life_load_score"]) + context_strain, 2)
    score["zone"] = _zone_from_rank(adjusted_rank)
    score["mode"] = {"green": "continue", "yellow": "protect", "orange": "hold", "red": "stabilize"}[score["zone"]]
    score["why"] = why or score["why"]
    score["red_flags"] = sorted(set([*score["red_flags"], *(signals if risk_rank >= 2 else [])]))
    score["next_action"] = next_action_card(mode=score["mode"], why=score["why"], entry=entry)
    score["recent_context"] = context
    return score


def next_action_card(*, mode: str, why: List[str], entry: Mapping[str, Any]) -> Dict[str, Any]:
    why_text = " ".join(str(item).lower() for item in why)
    if "sleep disrupted after project/training" in why_text:
        primary = "Take it easy today: no hard training and no project work."
        minimum = "Do one low-friction recovery action: 20-minute walk or quiet decompression."
        avoid = "Do not touch the project today; park ideas in one note if needed."
    elif mode == "stabilize":
        primary = "No hard training tomorrow. Walk 20 minutes only."
        minimum = "10 minutes outside after work."
        avoid = "No project work after 20:45."
    elif mode == "hold":
        primary = "Keep training easy tomorrow and protect shutdown."
        minimum = "10 minutes outside after work."
        avoid = "No catch-up workout."
    elif mode == "protect":
        primary = "Phone outside bedroom by 21:00 tonight."
        minimum = "One decompression step before dinner."
        avoid = "No project work after 20:45."
    else:
        primary = "Repeat the baseline; do not add extra ambition."
        minimum = "Short shutdown check at 20:45."
        avoid = "No heroic add-ons."
    return {
        "mode": mode,
        "primary_action": primary,
        "minimum_action": minimum,
        "avoid": avoid,
        "why": why,
        "check_tomorrow": "Foot pain and energy",
    }


def _canonical_from_draft(date_text: str, draft: Mapping[str, Any]) -> Dict[str, Any]:
    structured = dict(draft.get("structured") or {})
    return {
        "date": date_text,
        "completed": 1,
        "diary_text": str(draft.get("diary_text") or structured.get("diary_text") or ""),
        "diary_summary": str(draft.get("summary") or structured.get("diary_summary") or "")[:180],
        "tags": _json_dump(_tags(structured.get("tags")), []),
        "sleep_ok": _bool_db(structured.get("sleep_ok")),
        "nutrition_ok": _bool_db(structured.get("nutrition_ok")),
        "alcohol": _alcohol(structured.get("alcohol")),
        "binge": _bool_db(structured.get("binge")),
        "mood": _int_0_10(structured.get("mood")),
        "stress": _int_0_10(structured.get("stress")),
        "energy": _int_0_10(structured.get("energy")),
        "foot_pain": _int_0_10(structured.get("foot_pain")),
        "shoulder_pain": _int_0_10(structured.get("shoulder_pain")),
        "migraine_warning": _bool_db(structured.get("migraine_warning")),
        "decompression_done": _bool_db(structured.get("decompression_done")),
        "shutdown_done": _bool_db(structured.get("shutdown_done")),
        "phone_after_21": _bool_db(structured.get("phone_after_21")),
        "project_overrun": _bool_db(structured.get("project_overrun")),
        "primary_activity_type": _activity_type(structured.get("primary_activity_type")) or "",
        "activity_duration_min": _minutes(structured.get("activity_duration_min")),
        "rehab_done": _bool_db(structured.get("rehab_done")),
        "other_symptoms": str(structured.get("other_symptoms") or "")[:240],
        "work_intensity": structured.get("work_intensity"),
        "family_stress": _family_stress(structured.get("family_stress")),
        "home_office": _bool_db(structured.get("home_office")),
        "alone_home": _bool_db(structured.get("alone_home")),
        "homework_done": _homework(structured.get("homework_done"), date_text=date_text) or ("na" if is_weekend(date_text) else None),
        "after_work_decompression_done": _bool_db(structured.get("after_work_decompression_done")),
        "evening_chain_broken": _bool_db(structured.get("evening_chain_broken")),
        "wife_conflict_count": _count_0_12(structured.get("wife_conflict_count")),
        "wife_conflict_school": _bool_db(structured.get("wife_conflict_school")),
        "wife_conflict_chores": _bool_db(structured.get("wife_conflict_chores")),
        "wife_conflict_other": _bool_db(structured.get("wife_conflict_other")),
    }


def _insert_daily(
    store: LifeLoadCore,
    entry: Mapping[str, Any],
    score: Mapping[str, Any],
    approved_at: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    now = utc_now_iso()
    row = {
        **entry,
        "zone": score["zone"],
        "mode": score["mode"],
        "next_action": _json_dump(score["next_action"], {}),
        "approved_at": approved_at,
        "created_at": now,
        "updated_at": now,
    }
    for key, fallback in {
        "diary_summary": "",
        "tags": "[]",
        "alcohol": "none",
        "binge": 0,
        "migraine_warning": 0,
        "work_intensity": "",
        "other_symptoms": "",
    }.items():
        if row.get(key) is None:
            row[key] = fallback
    columns = ENTRY_FIELDS
    assignments = ", ".join(f"{col}=excluded.{col}" for col in columns if col not in {"date", "created_at"})
    sql = f"""
        INSERT INTO daily_log({', '.join(columns)})
        VALUES ({', '.join('?' for _ in columns)})
        ON CONFLICT(date) DO UPDATE SET {assignments}
    """
    values = tuple(row.get(col) for col in columns)
    if conn is not None:
        conn.execute(sql, values)
        return
    with store.connect() as connection, connection:
        connection.execute(sql, values)


def _upsert_daily_summary(
    store: LifeLoadCore,
    date_text: str,
    score: Mapping[str, Any],
    *,
    formula_settings: Mapping[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    settings_snapshot = _formula_settings_snapshot(formula_settings)
    settings_hash = _formula_settings_hash(formula_settings)
    values = (
        date_text,
        score["life_load_score"],
        score.get("base_score", score["life_load_score"]),
        score.get("profile_adjusted_score", score["life_load_score"]),
        score["strain_score"],
        score["recovery_score"],
        score["training_load"],
        score["zone"],
        score["mode"],
        _json_dump(score["red_flags"], []),
        _json_dump(score["next_action"], {}),
        _json_dump(score["why"], []),
        score["confidence"],
        _json_dump(score.get("guidance_thresholds") or {}, {}),
        _json_dump(score.get("profile_modifiers") or [], []),
        _json_dump(score.get("profile_effects") or [], []),
        CORE_SCORING_VERSION,
        _json_dump(settings_snapshot, {}),
        settings_hash,
        utc_now_iso(),
    )
    sql = """
            INSERT INTO derived_daily_summary(
                date, life_load_score, base_score, profile_adjusted_score, strain_score, recovery_score, training_load,
                zone, mode, red_flags_json, next_action, why_json, confidence,
                guidance_thresholds_json, profile_modifiers_json, profile_effects_json,
                scoring_version, formula_settings_json, formula_settings_hash, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              life_load_score=excluded.life_load_score,
              base_score=excluded.base_score,
              profile_adjusted_score=excluded.profile_adjusted_score,
              strain_score=excluded.strain_score,
              recovery_score=excluded.recovery_score,
              training_load=excluded.training_load,
              zone=excluded.zone,
              mode=excluded.mode,
              red_flags_json=excluded.red_flags_json,
              next_action=excluded.next_action,
              why_json=excluded.why_json,
              confidence=excluded.confidence,
              guidance_thresholds_json=excluded.guidance_thresholds_json,
              profile_modifiers_json=excluded.profile_modifiers_json,
              profile_effects_json=excluded.profile_effects_json,
              scoring_version=excluded.scoring_version,
              formula_settings_json=excluded.formula_settings_json,
              formula_settings_hash=excluded.formula_settings_hash,
              calculated_at=excluded.calculated_at
            """
    if conn is not None:
        conn.execute(sql, values)
        return
    with store.connect() as connection, connection:
        connection.execute(
            sql,
            values,
        )


def recompute_weekly_summary(
    store: LifeLoadCore,
    date_text: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> Dict[str, Any]:
    start, end = week_start(date_text), week_end(date_text)
    query = """
        SELECT d.*, s.zone AS summary_zone, s.mode AS summary_mode, s.why_json
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE d.date >= ? AND d.date <= ? AND d.approved_at != ''
        ORDER BY d.date ASC
        """
    if conn is None:
        rows = store.fetch_all(query, (start, end))
    else:
        rows = [dict(row) for row in conn.execute(query, (start, end)).fetchall()]
    approved_days = len(rows)
    signals: List[str] = []
    late_phone_count = sum(1 for row in rows if row.get("phone_after_21") == 1)
    project_count = sum(1 for row in rows if row.get("project_overrun") == 1)
    sleep_count = sum(1 for row in rows if row.get("sleep_ok") == 1)
    nutrition_count = sum(1 for row in rows if row.get("nutrition_ok") == 1)
    pain_count = sum(1 for row in rows if max(row.get("foot_pain") or 0, row.get("shoulder_pain") or 0) >= 5)
    if late_phone_count >= 2:
        signals.append("repeated late phone")
    if project_count >= 2:
        signals.append("repeated project overrun")
    if approved_days and sleep_count / approved_days < 0.6:
        signals.append("sleep compliance falling")
    if approved_days and nutrition_count / approved_days < 0.6:
        signals.append("nutrition compliance falling")
    if pain_count:
        signals.append("pain warning")
    if sum(1 for row in rows if row.get("binge") == 1):
        signals.append("binge signal")
    if sum(1 for row in rows if row.get("alcohol") == "home"):
        signals.append("alcohol signal")
    if approved_days < max(1, (dt.datetime.strptime(date_text, DATE_FMT).date() - dt.datetime.strptime(start, DATE_FMT).date()).days + 1):
        signals.append("missed approvals")
    worst = "green"
    for zone in ("red", "orange", "yellow"):
        if any(row.get("summary_zone") == zone for row in rows):
            worst = zone
            break
    if signals and worst == "green":
        worst = "yellow"
    mode = {"green": "continue", "yellow": "protect", "orange": "hold", "red": "stabilize"}[worst]
    next_action = next_action_card(mode=mode, why=signals[:5] or ["Week stable"], entry={})
    payload = {
        "week_start": start,
        "week_end": end,
        "approved_days": approved_days,
        "sleep_count": sleep_count,
        "nutrition_count": nutrition_count,
        "alcohol_home_count": sum(1 for row in rows if row.get("alcohol") == "home"),
        "binge_count": sum(1 for row in rows if row.get("binge") == 1),
        "late_phone_count": late_phone_count,
        "project_overrun_count": project_count,
        "pain_warning_count": pain_count,
        "zone": worst,
        "mode": mode,
        "top_drift_signals": signals[:5],
        "next_action": next_action,
    }
    write_sql = """
            INSERT INTO derived_weekly_summary(
                week_start, week_end, approved_days, sleep_count, nutrition_count,
                alcohol_home_count, binge_count, late_phone_count, project_overrun_count,
                pain_warning_count, zone, mode, top_drift_signals_json, next_action, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
              week_end=excluded.week_end,
              approved_days=excluded.approved_days,
              sleep_count=excluded.sleep_count,
              nutrition_count=excluded.nutrition_count,
              alcohol_home_count=excluded.alcohol_home_count,
              binge_count=excluded.binge_count,
              late_phone_count=excluded.late_phone_count,
              project_overrun_count=excluded.project_overrun_count,
              pain_warning_count=excluded.pain_warning_count,
              zone=excluded.zone,
              mode=excluded.mode,
              top_drift_signals_json=excluded.top_drift_signals_json,
              next_action=excluded.next_action,
              calculated_at=excluded.calculated_at
            """
    values = (
        start,
        end,
        payload["approved_days"],
        payload["sleep_count"],
        payload["nutrition_count"],
        payload["alcohol_home_count"],
        payload["binge_count"],
        payload["late_phone_count"],
        payload["project_overrun_count"],
        payload["pain_warning_count"],
        payload["zone"],
        payload["mode"],
        _json_dump(payload["top_drift_signals"], []),
        _json_dump(payload["next_action"], {}),
        utc_now_iso(),
    )
    if conn is not None:
        conn.execute(write_sql, values)
    else:
        with store.connect() as connection, connection:
            connection.execute(write_sql, values)
    return payload


def _replay_materialized_row(entry: Mapping[str, Any], score: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        **dict(entry),
        "summary_zone": score.get("zone") or "",
        "life_load_score": float(score.get("life_load_score") or 0.0),
        "training_load": float(score.get("training_load") or 0.0),
    }


def _primary_action(value: Any) -> str:
    parsed = _json_load(value, {})
    if isinstance(parsed, Mapping):
        return str(parsed.get("primary_action") or "")
    return ""


def replay_approved_days(
    store: LifeLoadCore,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Dict[str, Any]:
    from life_load.settings import load_settings

    settings = load_settings(store.repo_root)
    current_formula_hash = _formula_settings_hash(settings)
    where = ["d.approved_at != ''"]
    params: List[Any] = []
    parsed_start = parse_date(start_date) if start_date else ""
    parsed_end = parse_date(end_date) if end_date else ""
    warmup_start = ""
    if parsed_start:
        warmup_start = (
            dt.datetime.strptime(parsed_start, DATE_FMT).date() - dt.timedelta(days=6)
        ).isoformat()
        where.append("d.date >= ?")
        params.append(warmup_start)
    if parsed_end:
        where.append("d.date <= ?")
        params.append(parsed_end)
    rows = store.fetch_all(
        f"""
        SELECT d.*,
               s.life_load_score AS stored_life_load_score,
               s.strain_score AS stored_strain_score,
               s.recovery_score AS stored_recovery_score,
               s.training_load AS stored_training_load,
               s.zone AS stored_zone,
               s.mode AS stored_mode,
               s.next_action AS stored_next_action,
               s.scoring_version AS stored_scoring_version,
               s.formula_settings_hash AS stored_formula_settings_hash
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE {' AND '.join(where)}
        ORDER BY d.date ASC
        """,
        params,
    )

    replayed_rows: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    for row in rows:
        date_text = str(row.get("date") or "")
        day = dt.datetime.strptime(date_text, DATE_FMT).date()
        start = (day - dt.timedelta(days=6)).isoformat()
        prior_rows = [item for item in replayed_rows if start <= str(item.get("date") or "") < date_text]
        entry = _entry_from_row(row) or {}
        score = score_entry_with_context(
            entry,
            _recent_context_from_rows(prior_rows),
            formula_settings=settings,
        )
        current = {
            "scoring_version": CORE_SCORING_VERSION,
            "formula_settings_hash": current_formula_hash,
            "life_load_score": float(score.get("life_load_score") or 0.0),
            "zone": score.get("zone") or "",
            "mode": score.get("mode") or "",
            "primary_action": str((score.get("next_action") or {}).get("primary_action") or ""),
        }
        stored = {
            "scoring_version": row.get("stored_scoring_version") or "",
            "formula_settings_hash": row.get("stored_formula_settings_hash") or "",
            "life_load_score": float(row.get("stored_life_load_score") or 0.0),
            "zone": row.get("stored_zone") or "",
            "mode": row.get("stored_mode") or "",
            "primary_action": _primary_action(row.get("stored_next_action")),
        }
        is_reported_day = not parsed_start or date_text >= parsed_start
        changed_fields = [
            key
            for key in ("scoring_version", "formula_settings_hash", "zone", "mode", "primary_action")
            if stored[key] != current[key]
        ]
        if abs(float(stored["life_load_score"]) - float(current["life_load_score"])) > 0.01:
            changed_fields.append("life_load_score")
        if is_reported_day and changed_fields:
            changes.append(
                {
                    "date": date_text,
                    "changed_fields": changed_fields,
                    "stored": stored,
                    "current": current,
                }
            )
        replayed_rows.append(_replay_materialized_row(entry, score))

    return {
        "schema_version": FORMULA_REPLAY_REPORT_VERSION,
        "scoring_version_current": CORE_SCORING_VERSION,
        "formula_settings_hash_current": current_formula_hash,
        "start_date": parsed_start,
        "end_date": parsed_end,
        "total_days": sum(1 for row in rows if not parsed_start or str(row.get("date") or "") >= parsed_start),
        "changed_days": len(changes),
        "changes": changes,
    }


def approve_payload(store: LifeLoadCore, payload: Mapping[str, Any]) -> Dict[str, Any]:
    from life_load.settings import load_settings

    date_text = parse_date(str(payload.get("date") or ""))
    draft = _draft_from_row(store.fetch_one("SELECT * FROM draft_entry WHERE date = ?", (date_text,)), date_text=date_text)
    if not draft:
        raise ValueError("no draftEntry exists for approval")
    canonical = _canonical_from_draft(date_text, draft)
    settings = load_settings(store.repo_root)
    score = score_entry_with_context(canonical, _recent_context(store, date_text), formula_settings=settings)
    approved_at = utc_now_iso()
    # Canonical promotion, its daily projection, weekly projection, and draft
    # removal are one unit. A failed derived write must leave the prior draft
    # available for retry instead of exposing mixed canonical/history state.
    with store.connect() as conn, conn:
        _insert_daily(store, canonical, score, approved_at, conn=conn)
        _upsert_daily_summary(store, date_text, score, formula_settings=settings, conn=conn)
        weekly = recompute_weekly_summary(store, date_text, conn=conn)
        conn.execute("DELETE FROM draft_entry WHERE date = ?", (date_text,))
    return {
        "schema_version": "life_load_approval_v1",
        "date": date_text,
        "entry": get_entry_payload(store, date_value=date_text)["entry"],
        "summary": {**score, "next_action": score["next_action"]},
        "decision_card": score["next_action"],
        "weekly_summary": weekly,
    }


def _core_history_days(store: LifeLoadCore, date_text: str, *, days: int = 14) -> List[Dict[str, Any]]:
    day = dt.datetime.strptime(date_text, DATE_FMT).date()
    start = (day - dt.timedelta(days=days - 1)).isoformat()
    rows = store.fetch_all(
        """
        SELECT d.date, d.diary_summary, d.diary_text, d.mood, d.stress, d.energy,
               s.zone, s.life_load_score, s.next_action
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE d.date >= ? AND d.date <= ? AND d.approved_at != ''
        ORDER BY d.date ASC
        """,
        (start, date_text),
    )
    history = []
    for row in rows:
        history.append(
            {
                "date": row.get("date"),
                "state": "approved",
                "zone": row.get("zone") or "",
                "next_action": _json_load(row.get("next_action"), {}).get("primary_action", ""),
                "life_load_score": float(row.get("life_load_score") or 0.0),
                "diary_summary": row.get("diary_summary") or str(row.get("diary_text") or "")[:80],
                "mood": row.get("mood"),
                "stress": row.get("stress"),
                "energy": row.get("energy"),
            }
        )
    return history


def _core_trend_points(store: LifeLoadCore, date_text: str, *, days: int = 14) -> List[Dict[str, Any]]:
    day = dt.datetime.strptime(date_text, DATE_FMT).date()
    start = day - dt.timedelta(days=days - 1)
    rows = store.fetch_all(
        """
        SELECT date, life_load_score, training_load, recovery_score, strain_score, red_flags_json, zone
        FROM derived_daily_summary
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC
        """,
        (start.isoformat(), date_text),
    )
    by_date = {str(row.get("date") or ""): row for row in rows}
    points: List[Dict[str, Any]] = []
    dates: List[str] = []
    for offset in range(days):
        date_key = (start + dt.timedelta(days=offset)).isoformat()
        row = by_date.get(date_key)
        if not row:
            continue
        dates.append(date_key)
        recent_keys = dates[-7:]
        chronic_keys = dates[-42:]
        recent_rows = [by_date[key] for key in recent_keys if key in by_date]
        chronic_rows = [by_date[key] for key in chronic_keys if key in by_date]

        def avg(key: str, source: List[Mapping[str, Any]]) -> float:
            if not source:
                return 0.0
            return round(sum(float(item.get(key) or 0.0) for item in source) / len(source), 2)

        life_7d = avg("life_load_score", recent_rows)
        acute_7d = life_7d
        acute_training_7d = round(sum(float(item.get("training_load") or 0.0) for item in recent_rows), 2)
        recovery_7d = avg("recovery_score", recent_rows)
        chronic_capacity = max(1.0, avg("recovery_score", chronic_rows) + avg("training_load", chronic_rows))
        red_count = sum(len(_json_load(item.get("red_flags_json"), [])) for item in recent_rows)
        pain_risk = 1 if any(str(item.get("zone") or "") in {"orange", "red"} for item in recent_rows) else 0
        drift_risk = min(10.0, life_7d + red_count + pain_risk)
        points.append(
            {
                "date": date_key,
                "features": {
                    "life_load_rolling_avg_7d": life_7d,
                    "sleep_compliance_7d": 0.0,
                    "nutrition_compliance_7d": 0.0,
                    "project_overrun_count_7d": 0,
                    "phone_after_21_count_7d": 0,
                    "pain_avg_7d": 0.0,
                    "red_flag_count_7d": red_count,
                    "acute_load_7d": acute_7d,
                    "acute_training_load_7d": acute_training_7d,
                    "chronic_capacity_42d": round(chronic_capacity, 2),
                    "life_margin_7d": round(chronic_capacity - life_7d, 2),
                    "drift_risk_score": round(drift_risk, 2),
                    "recommended_mode": {"green": "continue", "yellow": "protect", "orange": "hold", "red": "stabilize"}.get(str(row.get("zone") or ""), ""),
                    "recovery_score_7d": recovery_7d,
                },
            }
        )
    return points


def dashboard_payload(store: LifeLoadCore, *, date_value: str) -> Dict[str, Any]:
    date_text = parse_date(date_value)
    entry_payload = get_entry_payload(store, date_value=date_text)
    summary = entry_payload["summary"]
    weekly = _week_context(store, date_text)
    recent = _recent_context(store, date_text)
    risk_level = (weekly or {}).get("zone") or (summary or {}).get("zone") or recent.get("risk_zone") or "green"
    if _zone_rank(str(recent.get("risk_zone") or "")) > _zone_rank(str(risk_level or "")):
        risk_level = recent["risk_zone"]
    drift = {
        "risk_level": risk_level,
        "top_contributing_signals": _json_load((weekly or {}).get("top_drift_signals_json"), []) or recent.get("signals", []),
        "recommended_mode": (weekly or {}).get("mode") or (summary or {}).get("mode") or {"green": "continue", "yellow": "protect", "orange": "hold", "red": "stabilize"}.get(str(risk_level), "continue"),
        "next_action": _json_load((weekly or {}).get("next_action"), {}) or (summary or {}).get("next_action"),
        "recent_context": recent,
    }
    return {
        "schema_version": "life_load_dashboard_v1",
        "date": date_text,
        "daily_zone": (summary or {}).get("zone") or risk_level,
        "mode": (summary or {}).get("mode") or drift["recommended_mode"],
        "next_action": _json_load((summary or {}).get("next_action"), {}) if summary else None,
        "why": (summary or {}).get("why") or recent.get("signals", []),
        "weekly_context": weekly,
        "drift_signals": drift,
        "trend": {"rows": _core_trend_points(store, date_text)},
        "history": _core_history_days(store, date_text),
    }
