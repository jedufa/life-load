"""Mobile web payloads backed by the canonical health-observability SQLite store."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from life_load.drift import drift_payload as _drift_payload, rebuild_drift_snapshots
from life_load.extraction import analyze_diary_entry, validate_proposal
from life_load.contracts import contract_payload as _contract_payload
from life_load.scoring import (
    SCORING_CONTRACT_VERSION,
    activity_rollup as _activity_rollup,
    formula_settings_hash as _formula_settings_hash,
    formula_settings_snapshot as _formula_settings_snapshot,
    group_activity_by_date as _group_activity_by_date,
    normalize_activity_type as _normalize_activity_type,
    score_entry as _score_entry,
)
from life_load.sqlite_core import DEFAULT_ROOT_REL, HealthObservabilityStore, utc_now_iso
from life_load.trends import rebuild_trend_features, trend_payload as _trend_payload

DATE_FMT = "%Y-%m-%d"


def platform_contract_payload() -> Dict[str, Any]:
    return _contract_payload()


def _today_vienna() -> dt.date:
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo("Europe/Vienna")).date()
    except Exception:
        return dt.date.today()


def _yesterday_default() -> dt.date:
    return _today_vienna() - dt.timedelta(days=1)


def _parse_date(value: str | None) -> dt.date:
    text = str(value or "").strip()
    if not text:
        return _yesterday_default()
    try:
        return dt.datetime.strptime(text, DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"invalid date '{text}'; expected YYYY-MM-DD") from exc


def _iso_date(value: dt.date) -> str:
    return value.strftime(DATE_FMT)


def _week_start(value: dt.date) -> dt.date:
    return value - dt.timedelta(days=value.weekday())


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "home"}


def _as_optional_bool(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    return _as_bool(value)


def _normalize_alcohol(value: Any) -> str:
    if isinstance(value, bool):
        return "home" if value else "none"
    if isinstance(value, (int, float)):
        if int(value) == 2:
            return "social"
        return "home" if bool(value) else "none"
    text = str(value or "").strip().lower()
    if text in {"home", "at_home", "at home", "true", "yes", "y", "on", "1"}:
        return "home"
    if text in {"social", "outside", "out"}:
        return "social"
    return "none"


def _alcohol_storage_value(value: Any) -> int:
    normalized = _normalize_alcohol(value)
    if normalized == "home":
        return 1
    if normalized == "social":
        return 2
    return 0


def _as_optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _clamp_int(value: Any, *, minimum: int = 0, maximum: int = 10, default: int | None = None) -> int | None:
    parsed = _as_optional_int(value)
    if parsed is None:
        return default
    return max(minimum, min(maximum, parsed))


def _normalize_tags(value: Any) -> List[str]:
    raw: List[Any] = []
    pending: List[Any] = list(value) if isinstance(value, list) else [value]
    while pending:
        item = pending.pop(0)
        if item is None:
            continue
        if isinstance(item, list):
            pending = list(item) + pending
            continue
        text = str(item or "").strip()
        if not text:
            continue
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                pending = list(parsed) + pending
                continue
        raw.extend(text.replace(";", ",").split(","))
    tags: List[str] = []
    for item in raw:
        tag = str(item or "").strip().lower().replace(" ", "-")
        if tag and tag not in tags:
            tags.append(tag[:48])
    return tags


def _parse_json_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        loaded = json.loads(text)
    except Exception:
        return [text]
    if not isinstance(loaded, list):
        return []
    return [str(item or "").strip() for item in loaded if str(item or "").strip()]


def _normalize_activity_types(value: Any, *, fallback: Any = "") -> List[str]:
    raw_items: List[Any]
    if isinstance(value, (list, tuple)):
        raw_items = list(value)
    elif isinstance(value, str) and value.strip().startswith("["):
        try:
            loaded = json.loads(value)
        except Exception:
            loaded = []
        raw_items = loaded if isinstance(loaded, list) else []
    elif isinstance(value, str) and "," in value:
        raw_items = value.split(",")
    elif value:
        raw_items = [value]
    elif fallback:
        raw_items = [fallback]
    else:
        raw_items = []
    normalized: List[str] = []
    for item in raw_items:
        activity_type = _normalize_activity_type(item)
        if activity_type and activity_type not in normalized:
            normalized.append(activity_type)
    return normalized[:6]


def _default_entry(day: dt.date) -> Dict[str, Any]:
    return {
        "date": _iso_date(day),
        "diary_text": "",
        "diary_summary": "",
        "tags": [],
        "sleep_ok": None,
        "nutrition_ok": None,
        "alcohol": False,
        "binge": False,
        "mood": None,
        "stress": None,
        "energy": None,
        "coffee_cups": None,
        "foot_pain": None,
        "shoulder_pain": None,
        "migraine_warning": False,
        "decompression_done": None,
        "shutdown_done": None,
        "phone_after_21": None,
        "project_overrun": None,
        "primary_activity_type": "",
        "activity_types": [],
        "activity_duration_min": None,
        "rehab_done": None,
        "other_symptoms": "",
        "work_intensity": "normal",
        "family_stress": None,
        "home_office": None,
        "alone_home": None,
        "homework_done": None,
        "after_work_decompression_done": None,
        "evening_chain_broken": None,
        "wife_conflict_count": None,
        "wife_conflict_school": None,
        "wife_conflict_chores": None,
        "wife_conflict_other": None,
    }


def _entry_fields_equal(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> bool:
    return dict(left or {}) == dict(right or {})


def _entry_has_usable_signal(entry: Mapping[str, Any] | None) -> bool:
    """Whether an approved row contains user supplied evidence to score."""
    if not isinstance(entry, Mapping):
        return False
    if any(str(entry.get(key) or "").strip() for key in ("diary_text", "diary_summary", "other_symptoms")):
        return True
    if _normalize_alcohol(entry.get("alcohol")) != "none" or entry.get("binge") is True or entry.get("migraine_warning") is True:
        return True
    if entry.get("tags") or entry.get("activity_types") or entry.get("primary_activity_type"):
        return True
    if str(entry.get("work_intensity") or "").strip().lower() not in {"", "normal"}:
        return True
    signal_keys = (
        "sleep_ok", "nutrition_ok", "mood", "stress", "energy", "coffee_cups", "foot_pain", "shoulder_pain",
        "decompression_done", "shutdown_done", "phone_after_21", "project_overrun", "activity_duration_min",
        "rehab_done", "family_stress", "home_office", "alone_home", "homework_done",
        "after_work_decompression_done", "evening_chain_broken", "wife_conflict_count",
        "wife_conflict_school", "wife_conflict_chores", "wife_conflict_other",
    )
    return any(entry.get(key) is not None for key in signal_keys)


def _entry_has_evaluable_signal(
    entry: Mapping[str, Any] | None,
    *,
    garmin_passive: Mapping[str, Any] | None = None,
    activity_rows: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    """Whether a day has manual or imported data from which to calculate guidance."""
    return _entry_has_usable_signal(entry) or bool(garmin_passive) or bool(activity_rows)


def _merge_entry(base: Mapping[str, Any], updates: Mapping[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if key == "tags" and value is not None:
            merged[key] = _normalize_tags(value)
        elif key in {
            "sleep_ok",
            "nutrition_ok",
            "decompression_done",
            "shutdown_done",
            "phone_after_21",
            "project_overrun",
            "home_office",
            "alone_home",
            "homework_done",
            "rehab_done",
            "after_work_decompression_done",
            "evening_chain_broken",
            "wife_conflict_school",
            "wife_conflict_chores",
            "wife_conflict_other",
        }:
            merged[key] = _as_optional_bool(value)
        elif key == "alcohol":
            merged[key] = _normalize_alcohol(value)
        elif key in {"binge", "migraine_warning"}:
            merged[key] = _as_bool(value)
        elif key in {"mood", "stress", "energy", "foot_pain", "shoulder_pain", "family_stress"}:
            merged[key] = _clamp_int(value, default=None)
        elif key == "coffee_cups":
            merged[key] = _clamp_int(value, maximum=8, default=None)
        elif key == "wife_conflict_count":
            merged[key] = _clamp_int(value, maximum=12, default=None)
        elif key == "activity_duration_min":
            merged[key] = _as_optional_int(value)
        elif key == "activity_types":
            merged[key] = _normalize_activity_types(value, fallback=merged.get("primary_activity_type"))
        elif key == "primary_activity_type":
            merged[key] = str(value or "").strip().lower().replace(" ", "_")[:32]
        elif key == "other_symptoms":
            merged[key] = str(value or "").strip()[:240]
        elif key == "work_intensity":
            intensity = str(value or "").strip().lower()
            merged[key] = intensity if intensity in {"normal", "heavy"} else merged.get("work_intensity", "normal")
        elif key in {"diary_text", "diary_summary"}:
            merged[key] = str(value or "").strip()
        else:
            merged[key] = value
    return _clean_entry(merged, day=_parse_date(str(base.get("date") or merged.get("date") or "")))


def _clean_entry(raw: Mapping[str, Any], *, day: dt.date | None = None) -> Dict[str, Any]:
    target_day = day or _parse_date(raw.get("date"))
    entry = _default_entry(target_day)
    entry["diary_text"] = str(raw.get("diary_text") or "").strip()
    entry["diary_summary"] = str(raw.get("diary_summary") or "").strip()[:140]
    entry["tags"] = _normalize_tags(raw.get("tags"))
    entry["sleep_ok"] = _as_optional_bool(raw.get("sleep_ok"))
    entry["nutrition_ok"] = _as_optional_bool(raw.get("nutrition_ok"))
    entry["alcohol"] = _normalize_alcohol(raw.get("alcohol"))
    entry["binge"] = _as_bool(raw.get("binge"))
    entry["mood"] = _clamp_int(raw.get("mood"), default=None)
    entry["stress"] = _clamp_int(raw.get("stress"), default=None)
    entry["energy"] = _clamp_int(raw.get("energy"), default=None)
    entry["coffee_cups"] = _clamp_int(raw.get("coffee_cups"), maximum=8, default=None)
    entry["foot_pain"] = _clamp_int(raw.get("foot_pain"), default=None)
    entry["shoulder_pain"] = _clamp_int(raw.get("shoulder_pain"), default=None)
    entry["migraine_warning"] = _as_bool(raw.get("migraine_warning"))
    entry["decompression_done"] = _as_optional_bool(raw.get("decompression_done"))
    entry["shutdown_done"] = _as_optional_bool(raw.get("shutdown_done"))
    entry["phone_after_21"] = _as_optional_bool(raw.get("phone_after_21"))
    entry["project_overrun"] = _as_optional_bool(raw.get("project_overrun"))
    entry["activity_types"] = _normalize_activity_types(raw.get("activity_types"), fallback=raw.get("primary_activity_type"))
    entry["primary_activity_type"] = (
        entry["activity_types"][0]
        if entry["activity_types"]
        else str(raw.get("primary_activity_type") or "").strip().lower().replace(" ", "_")[:32]
    )
    entry["activity_duration_min"] = _as_optional_int(raw.get("activity_duration_min"))
    entry["rehab_done"] = _as_optional_bool(raw.get("rehab_done"))
    entry["other_symptoms"] = str(raw.get("other_symptoms") or "").strip()[:240]
    intensity = str(raw.get("work_intensity") or "normal").strip().lower()
    entry["work_intensity"] = intensity if intensity in {"normal", "heavy"} else "normal"
    entry["family_stress"] = _clamp_int(raw.get("family_stress"), default=None)
    entry["home_office"] = _as_optional_bool(raw.get("home_office"))
    entry["alone_home"] = _as_optional_bool(raw.get("alone_home"))
    entry["homework_done"] = _as_optional_bool(raw.get("homework_done"))
    entry["after_work_decompression_done"] = _as_optional_bool(raw.get("after_work_decompression_done"))
    entry["evening_chain_broken"] = _as_optional_bool(raw.get("evening_chain_broken"))
    entry["wife_conflict_count"] = _clamp_int(raw.get("wife_conflict_count"), maximum=12, default=None)
    entry["wife_conflict_school"] = _as_optional_bool(raw.get("wife_conflict_school"))
    entry["wife_conflict_chores"] = _as_optional_bool(raw.get("wife_conflict_chores"))
    entry["wife_conflict_other"] = _as_optional_bool(raw.get("wife_conflict_other"))
    return entry


def _sqlite_daily_row(entry: Mapping[str, Any], *, approved_at: str | None) -> Dict[str, Any]:
    summary = str(entry.get("diary_summary") or "").strip()
    diary_text = str(entry.get("diary_text") or "").strip()
    if not summary and diary_text:
        summary = diary_text[:120].strip()
    return {
        "date": str(entry["date"]),
        "completed": 1 if approved_at else 0,
        "diary_text": diary_text,
        "diary_summary": summary,
        "tags": list(entry.get("tags") or []),
        "sleep_ok": _sqlite_bool(entry.get("sleep_ok")),
        "nutrition_ok": _sqlite_bool(entry.get("nutrition_ok")),
        "alcohol": _alcohol_storage_value(entry.get("alcohol")),
        "binge": 1 if _as_bool(entry.get("binge")) else 0,
        "mood": _clamp_int(entry.get("mood"), default=None),
        "stress": _clamp_int(entry.get("stress"), default=None),
        "energy": _clamp_int(entry.get("energy"), default=None),
        "coffee_cups": _clamp_int(entry.get("coffee_cups"), maximum=8, default=None),
        "foot_pain": _clamp_int(entry.get("foot_pain"), default=None),
        "shoulder_pain": _clamp_int(entry.get("shoulder_pain"), default=None),
        "migraine_warning": 1 if _as_bool(entry.get("migraine_warning")) else 0,
        "decompression_done": _sqlite_bool(entry.get("decompression_done")),
        "shutdown_done": _sqlite_bool(entry.get("shutdown_done")),
        "phone_after_21": _sqlite_bool(entry.get("phone_after_21")),
        "project_overrun": _sqlite_bool(entry.get("project_overrun")),
        "primary_activity_type": str(entry.get("primary_activity_type") or "").strip().lower().replace(" ", "_")[:32],
        "activity_types": _normalize_activity_types(entry.get("activity_types"), fallback=entry.get("primary_activity_type")),
        "activity_duration_min": _as_optional_int(entry.get("activity_duration_min")),
        "rehab_done": _sqlite_bool(entry.get("rehab_done")),
        "other_symptoms": str(entry.get("other_symptoms") or "").strip()[:240],
        "work_intensity": str(entry.get("work_intensity") or "normal"),
        "family_stress": _clamp_int(entry.get("family_stress"), default=None),
        "home_office": _sqlite_bool(entry.get("home_office")),
        "alone_home": _sqlite_bool(entry.get("alone_home")),
        "homework_done": _sqlite_bool(entry.get("homework_done")),
        "after_work_decompression_done": _sqlite_bool(entry.get("after_work_decompression_done")),
        "evening_chain_broken": _sqlite_bool(entry.get("evening_chain_broken")),
        "wife_conflict_count": _clamp_int(entry.get("wife_conflict_count"), maximum=12, default=None),
        "wife_conflict_school": _sqlite_bool(entry.get("wife_conflict_school")),
        "wife_conflict_chores": _sqlite_bool(entry.get("wife_conflict_chores")),
        "wife_conflict_other": _sqlite_bool(entry.get("wife_conflict_other")),
        "user_approved_at": approved_at,
    }


def _sqlite_bool(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return 1 if _as_bool(value) else 0


def _from_daily_row(row: Mapping[str, Any], *, day: dt.date | None = None) -> Dict[str, Any]:
    if not row:
        return _default_entry(day or _yesterday_default())
    target_day = day or _parse_date(str(row.get("date") or ""))
    return _clean_entry(
        {
            "date": str(row.get("date") or _iso_date(target_day)),
            "diary_text": row.get("diary_text"),
            "diary_summary": row.get("diary_summary"),
            "tags": row.get("tags") if isinstance(row.get("tags"), list) else row.get("tags") or [],
            "sleep_ok": row.get("sleep_ok"),
            "nutrition_ok": row.get("nutrition_ok"),
            "alcohol": row.get("alcohol"),
            "binge": row.get("binge"),
            "mood": row.get("mood"),
            "stress": row.get("stress"),
            "energy": row.get("energy"),
            "coffee_cups": row.get("coffee_cups"),
            "foot_pain": row.get("foot_pain"),
            "shoulder_pain": row.get("shoulder_pain"),
            "migraine_warning": row.get("migraine_warning"),
            "decompression_done": row.get("decompression_done"),
            "shutdown_done": row.get("shutdown_done"),
            "phone_after_21": row.get("phone_after_21"),
            "project_overrun": row.get("project_overrun"),
            "primary_activity_type": row.get("primary_activity_type"),
            "activity_types": row.get("activity_types"),
            "activity_duration_min": row.get("activity_duration_min"),
            "rehab_done": row.get("rehab_done"),
            "other_symptoms": row.get("other_symptoms"),
            "work_intensity": row.get("work_intensity"),
            "family_stress": row.get("family_stress"),
            "home_office": row.get("home_office"),
            "alone_home": row.get("alone_home"),
            "homework_done": row.get("homework_done"),
            "after_work_decompression_done": row.get("after_work_decompression_done"),
            "evening_chain_broken": row.get("evening_chain_broken"),
            "wife_conflict_count": row.get("wife_conflict_count"),
            "wife_conflict_school": row.get("wife_conflict_school"),
            "wife_conflict_chores": row.get("wife_conflict_chores"),
            "wife_conflict_other": row.get("wife_conflict_other"),
        },
        day=target_day,
    )


def _list_dates(start: dt.date, end: dt.date) -> List[str]:
    return [_iso_date(start + dt.timedelta(days=offset)) for offset in range((end - start).days + 1)]


def _fetch_activity_rows(store: HealthObservabilityStore, *, start: dt.date, end: dt.date) -> List[Dict[str, Any]]:
    return store.fetch_all(
        """
        SELECT date, activity_type, duration_min, intensity, hard_session, recovery_activity, notes, source
        FROM activity_log
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC, id ASC
        """,
        (_iso_date(start), _iso_date(end)),
    )


def _as_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _activity_raw_json(row: Mapping[str, Any]) -> Dict[str, Any]:
    value = row.get("raw_json")
    if isinstance(value, Mapping):
        return dict(value)
    try:
        loaded = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return dict(loaded) if isinstance(loaded, Mapping) else {}


def _activity_start_hour(row: Mapping[str, Any]) -> int | None:
    text = str(row.get("start_time_local_iso") or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return int(parsed.hour)


def _elapsed_minutes(row: Mapping[str, Any], raw: Mapping[str, Any]) -> float | None:
    for key in ("elapsed_duration_min", "elapsedDuration"):
        value = raw.get(key)
        parsed = _as_float(value)
        if parsed is None:
            continue
        return parsed / 60.0 if key == "elapsedDuration" and parsed > 360.0 else parsed
    return _as_float(row.get("duration_min"))


def _infer_garmin_activity_type(row: Mapping[str, Any]) -> str:
    activity_type = _normalize_activity_type(row.get("activity_type") or row.get("sport_type") or "")
    if activity_type != "bike":
        return activity_type
    raw = _activity_raw_json(row)
    name_text = " ".join(
        str(value or "")
        for value in (
            row.get("name"),
            raw.get("activityName"),
            raw.get("name"),
            raw.get("eventType", {}).get("typeKey") if isinstance(raw.get("eventType"), Mapping) else "",
        )
    ).lower()
    if any(marker in name_text for marker in ("commute", "to work", "bike to work", "cycling to work")):
        return "bike_commute"

    distance = _as_float(row.get("distance_km"))
    moving = _as_float(row.get("moving_duration_min")) or _as_float(row.get("duration_min"))
    aerobic = _as_float(row.get("aerobic_training_effect")) or _as_float(raw.get("aerobicTrainingEffect")) or 0.0
    elapsed = _elapsed_minutes(row, raw)
    start_hour = _activity_start_hour(row)
    date_text = str(row.get("date") or "")
    weekday = True
    try:
        weekday = dt.datetime.strptime(date_text, DATE_FMT).date().weekday() < 5
    except Exception:
        pass
    if distance is None or moving is None:
        return activity_type

    commute_window = start_hour is not None and (5 <= start_hour <= 9 or 15 <= start_hour <= 19)
    single_leg = weekday and commute_window and 7.0 <= distance <= 11.5 and 18.0 <= moving <= 45.0
    round_trip = weekday and commute_window and 15.0 <= distance <= 22.5 and 40.0 <= moving <= 80.0
    all_day_recording = (
        elapsed is not None
        and moving > 0
        and elapsed / moving >= 2.5
        and 14.0 <= distance <= 35.0
    )
    if aerobic <= 2.8 and (single_leg or round_trip or all_day_recording):
        return "bike_commute"
    return activity_type


def _fetch_garmin_activity_rows(store: HealthObservabilityStore, *, start: dt.date, end: dt.date) -> List[Dict[str, Any]]:
    rows = store.fetch_all(
        """
        SELECT date, activity_type, sport_type, duration_min, moving_duration_min,
               time_on_feet_min_est, hard_session_est, avg_hr, aerobic_training_effect,
               anaerobic_training_effect, name, start_time_local_iso, distance_km, raw_json
        FROM garmin_activity
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC, start_time_local_iso ASC, activity_id ASC
        """,
        (_iso_date(start), _iso_date(end)),
    )
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        duration = row.get("moving_duration_min") or row.get("duration_min") or row.get("time_on_feet_min_est")
        activity_type = _infer_garmin_activity_type(row)
        intensity = _garmin_intensity(row, activity_type=activity_type)
        normalized.append(
            {
                "date": row.get("date"),
                "activity_type": activity_type,
                "duration_min": duration,
                "intensity": intensity,
                "hard_session": _garmin_hard_session(row, activity_type=activity_type, intensity=intensity),
                "recovery_activity": False,
                "notes": row.get("name") or "",
                "source": "garmin_activity",
                "avg_hr": row.get("avg_hr"),
                "aerobic_training_effect": row.get("aerobic_training_effect"),
                "anaerobic_training_effect": row.get("anaerobic_training_effect"),
            }
        )
    return normalized


def _fetch_garmin_passive_rows(store: HealthObservabilityStore, *, start: dt.date, end: dt.date) -> Dict[str, Dict[str, Any]]:
    rows = store.fetch_all(
        """
        SELECT *
        FROM garmin_daily_passive_summary
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC
        """,
        (_iso_date(start), _iso_date(end)),
    )
    return {str(row.get("date") or ""): dict(row) for row in rows}


def _garmin_intensity(row: Mapping[str, Any], *, activity_type: str | None = None) -> str:
    normalized_type = _normalize_activity_type(activity_type or row.get("activity_type") or row.get("sport_type") or "")
    aerobic = float(row.get("aerobic_training_effect") or 0.0)
    anaerobic = float(row.get("anaerobic_training_effect") or 0.0)
    if normalized_type == "bike_commute":
        return "moderate" if max(aerobic, anaerobic) >= 1.5 else "light"
    if max(aerobic, anaerobic) >= 3.0:
        return "hard"
    if max(aerobic, anaerobic) >= 1.5:
        return "moderate"
    return "light"


def _garmin_hard_session(row: Mapping[str, Any], *, activity_type: str, intensity: str) -> bool:
    normalized_type = _normalize_activity_type(activity_type)
    if normalized_type == "bike_commute":
        return False
    if intensity == "hard":
        return True
    if normalized_type in {"run", "crossfit"}:
        return _as_bool(row.get("hard_session_est"))
    if normalized_type in {"strength", "swim", "hike"}:
        duration = _as_float(row.get("moving_duration_min")) or _as_float(row.get("duration_min")) or 0.0
        aerobic = _as_float(row.get("aerobic_training_effect")) or 0.0
        anaerobic = _as_float(row.get("anaerobic_training_effect")) or 0.0
        return _as_bool(row.get("hard_session_est")) and duration >= 25.0 and max(aerobic, anaerobic) >= 1.5
    return False


def _recent_training_loads(store: HealthObservabilityStore, *, day: dt.date, lookback_days: int = 42) -> List[float]:
    start = day - dt.timedelta(days=lookback_days)
    end = day - dt.timedelta(days=1)
    if end < start:
        return []
    date_keys = _list_dates(start, end)
    summary_rows = store.fetch_all(
        """
        SELECT date, training_load
        FROM derived_daily_summary
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC
        """,
        (_iso_date(start), _iso_date(end)),
    )
    summary_by_date = {str(row.get("date") or ""): float(row.get("training_load") or 0.0) for row in summary_rows}
    activity_by_date = _group_activity_by_date(
        [
            *_fetch_activity_rows(store, start=start, end=end),
            *_fetch_garmin_activity_rows(store, start=start, end=end),
        ]
    )
    loads: List[float] = []
    for date_text in date_keys:
        if date_text in summary_by_date:
            loads.append(summary_by_date[date_text])
        else:
            loads.append(float(_activity_rollup(activity_by_date.get(date_text, []))["training_load"]))
    return loads


def _recalculate_for_date(
    store: HealthObservabilityStore,
    *,
    day: dt.date,
    persist: bool = True,
    canonical_row_override: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    from life_load.settings import load_settings

    date_text = _iso_date(day)
    settings = load_settings(store.repo_root)
    canonical_row = dict(canonical_row_override) if canonical_row_override is not None else store.fetch_one("SELECT * FROM daily_log WHERE date = ?", (date_text,))
    entry = _from_daily_row(canonical_row or {"date": date_text}, day=day)
    daily_activity_rows = [
        *_fetch_activity_rows(store, start=day, end=day),
        *_fetch_garmin_activity_rows(store, start=day, end=day),
    ]
    daily_passive = store.fetch_garmin_passive_summary(date_text)
    daily = _score_entry(
        entry,
        activity_rows=daily_activity_rows,
        garmin_passive=daily_passive,
        prior_training_loads=_recent_training_loads(store, day=day),
        formula_settings=settings,
    )
    daily_row = {
        "date": date_text,
        "life_load_score": daily["life_load_score"],
        "training_load": daily["training_load"],
        "recovery_score": daily["recovery_score"],
        "strain_score": daily["strain_score"],
        "red_flags": daily["red_flags"],
        "zone": daily["zone"],
        "next_action": daily["next_action"],
        "scoring_version": SCORING_CONTRACT_VERSION,
        "formula_settings_json": _formula_settings_snapshot(settings),
        "formula_settings_hash": _formula_settings_hash(settings),
    }
    if persist:
        store.upsert_derived_daily_summary(daily_row)

    week_start = _week_start(day)
    week_end = week_start + dt.timedelta(days=6)
    rows = store.fetch_all(
        "SELECT * FROM daily_log WHERE date >= ? AND date <= ? ORDER BY date ASC",
        (_iso_date(week_start), _iso_date(week_end)),
    )
    if canonical_row_override is not None:
        rows = [row for row in rows if str(row.get("date") or "") != date_text]
        rows.append(dict(canonical_row_override))
        rows.sort(key=lambda row: str(row.get("date") or ""))
    weekly_activity_rows = _fetch_activity_rows(store, start=week_start, end=week_end)
    weekly_garmin_activity_rows = _fetch_garmin_activity_rows(store, start=week_start, end=week_end)
    activity_by_date = _group_activity_by_date(weekly_activity_rows)
    for date_key, rows_for_day in _group_activity_by_date(weekly_garmin_activity_rows).items():
        activity_by_date.setdefault(date_key, []).extend(rows_for_day)
    passive_by_date = _fetch_garmin_passive_rows(store, start=week_start, end=week_end)
    entries = []
    for row in rows:
        date_key = str(row.get("date") or "")
        entry = _from_daily_row(row)
        if str(row.get("user_approved_at") or "").strip() and _entry_has_evaluable_signal(
            entry,
            garmin_passive=passive_by_date.get(date_key),
            activity_rows=activity_by_date.get(date_key, []),
        ):
            entries.append(entry)
    scores = [
        _score_entry(
            row,
            activity_rows=activity_by_date.get(str(row["date"]), []),
            garmin_passive=passive_by_date.get(str(row["date"])),
            prior_training_loads=_recent_training_loads(store, day=_parse_date(str(row["date"]))),
            formula_settings=settings,
        )
        for row in entries
    ]
    warnings = {flag for row in scores for flag in row.get("warnings", [])}
    red_flags = {flag for row in scores for flag in row.get("red_flags", [])}
    zone = "green"
    total_load = sum(float(row["life_load_score"]) for row in scores)
    total_recovery = sum(float(row["recovery_score"]) for row in scores)
    net = round(total_load - total_recovery, 2)
    hard_sessions = sum(int(row.get("hard_sessions", 0) or 0) for row in scores)
    rehab_sessions = sum(int(row.get("rehab_sessions", 0) or 0) for row in scores)
    if not entries:
        zone = "yellow"
        next_action = "Approve at least one day before using this weekly view."
    else:
        if red_flags or net >= 18 or hard_sessions >= 4:
            zone = "red"
        elif net >= 10 or hard_sessions >= 3:
            zone = "orange"
        elif net >= 4 or warnings:
            zone = "yellow"
        next_action = (
            "Use a recovery-first week: reduce load, protect sleep, and avoid catch-up pressure."
            if zone == "red"
            else "Keep the next days simple; let recovery catch up."
            if zone == "orange"
            else "Fill missing fields and keep the baseline steady."
            if warnings
            else "Continue the current baseline."
        )
    weekly_row = {
        "week_start": _iso_date(week_start),
        "week_end": _iso_date(week_end),
        "completed_days": len(entries),
        "sleep_nights": sum(1 for row in entries if row.get("sleep_ok") is True),
        "nutrition_clean_days": sum(1 for row in entries if row.get("nutrition_ok") is True),
        "alcohol_home_count": sum(1 for row in entries if _as_bool(row.get("alcohol"))),
        "binge_count": sum(1 for row in entries if _as_bool(row.get("binge"))),
        "training_load": sum(float(row["training_load"]) for row in scores),
        "hard_sessions": hard_sessions,
        "rehab_sessions": rehab_sessions,
        "homework_sessions": sum(1 for row in entries if row.get("homework_done") is True),
        "net_life_load": net,
        "zone": zone,
        "success_score": round((len(entries) / 7.0) if entries else 0.0, 2),
        "next_action": next_action,
    }
    if persist:
        store.upsert_derived_weekly_summary(weekly_row)
    return {
        "daily": daily,
        "daily_row": daily_row,
        "weekly_row": weekly_row,
        "weekly": {
            "week_start": _iso_date(week_start),
            "week_end": _iso_date(week_end),
            "zone": zone,
            "net_life_load": net,
            "next_action": next_action,
            "hard_sessions": hard_sessions,
            "rehab_sessions": rehab_sessions,
            "warnings": sorted(warnings),
            "red_flags": sorted(red_flags),
        },
    }


def _refresh_derived_read_models(store: HealthObservabilityStore, *, day: dt.date) -> Dict[str, Any]:
    derived = _recalculate_for_date(store, day=day)
    future_rows = store.fetch_all(
        """
        SELECT date
        FROM daily_log
        WHERE date > ? AND user_approved_at IS NOT NULL AND TRIM(user_approved_at) <> ''
        ORDER BY date ASC
        """,
        (_iso_date(day),),
    )
    # Training context is chronological. Recompute every later approved day so
    # a backfill cannot leave materialized ratios and guidance stale.
    for row in future_rows:
        _recalculate_for_date(store, day=_parse_date(str(row["date"])))
    rebuild_trend_features(store)
    rebuild_drift_snapshots(store)
    return {
        "daily": derived["daily"],
        "weekly": derived["weekly"],
        "trend": _trend_payload(store, date_value=_iso_date(day), days=30),
        "drift": _drift_payload(store, date_value=_iso_date(day)),
    }


def _ensure_derived_current(store: HealthObservabilityStore, settings: Mapping[str, Any]) -> None:
    current_hash = _formula_settings_hash(settings)
    stale_rows = store.fetch_all(
        """
        SELECT d.date, s.scoring_version, s.formula_settings_hash
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE d.user_approved_at IS NOT NULL AND TRIM(d.user_approved_at) <> ''
          AND (s.date IS NULL OR s.scoring_version <> ? OR s.formula_settings_hash <> ?)
        ORDER BY d.date ASC
        """,
        (SCORING_CONTRACT_VERSION, current_hash),
    )
    if not stale_rows:
        return
    all_dates = store.fetch_all(
        """
        SELECT date
        FROM daily_log
        WHERE user_approved_at IS NOT NULL AND TRIM(user_approved_at) <> ''
        ORDER BY date ASC
        """,
    )
    for row in all_dates:
        _recalculate_for_date(store, day=_parse_date(str(row["date"])))
    rebuild_trend_features(store)
    rebuild_drift_snapshots(store)


def refresh_derived_for_date(store: HealthObservabilityStore, date_value: str) -> Dict[str, Any]:
    return _refresh_derived_read_models(store, day=_parse_date(date_value))


def _fetch_derived_daily_rows(store: HealthObservabilityStore, *, start: dt.date, end: dt.date) -> List[Dict[str, Any]]:
    return store.fetch_all(
        """
        SELECT date, life_load_score, training_load, recovery_score, strain_score, red_flags, zone, next_action, calculated_at
        FROM derived_daily_summary
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC
        """,
        (_iso_date(start), _iso_date(end)),
    )


def _weekly_dashboard_state(
    store: HealthObservabilityStore,
    *,
    week_start: dt.date,
    week_end: dt.date,
    weekly_row: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    if not weekly_row:
        return None
    approved_rows = store.fetch_all(
        """
        SELECT *
        FROM daily_log
        WHERE date >= ? AND date <= ? AND user_approved_at IS NOT NULL AND TRIM(user_approved_at) != ''
        ORDER BY date ASC
        """,
        (_iso_date(week_start), _iso_date(week_end)),
    )
    week_activity_rows = [
        *_fetch_activity_rows(store, start=week_start, end=week_end),
        *_fetch_garmin_activity_rows(store, start=week_start, end=week_end),
    ]
    activity_by_date = _group_activity_by_date(week_activity_rows)
    passive_by_date = _fetch_garmin_passive_rows(store, start=week_start, end=week_end)
    usable_approved_dates = {
        str(row.get("date") or "")
        for row in approved_rows
        if _entry_has_evaluable_signal(
            _from_daily_row(row),
            garmin_passive=passive_by_date.get(str(row.get("date") or "")),
            activity_rows=activity_by_date.get(str(row.get("date") or ""), []),
        )
    }
    daily_rows = [
        row
        for row in _fetch_derived_daily_rows(store, start=week_start, end=week_end)
        if str(row.get("date") or "") in usable_approved_dates
    ]
    daily_by_date = {str(row.get("date") or ""): row for row in daily_rows}
    dates = _list_dates(week_start, week_end)
    red_flag_days: List[Dict[str, Any]] = []
    highest_load_day: Dict[str, Any] | None = None
    for date_text in dates:
        if date_text not in usable_approved_dates:
            continue
        daily_row = daily_by_date.get(date_text)
        if not daily_row:
            continue
        life_load = float(daily_row.get("life_load_score") or 0.0)
        if highest_load_day is None or life_load > float(highest_load_day["life_load_score"]):
            highest_load_day = {"date": date_text, "life_load_score": life_load, "zone": str(daily_row.get("zone") or "")}
        for flag in _parse_json_list(daily_row.get("red_flags")):
            red_flag_days.append({"date": date_text, "flag": flag})
    recent_reviews = store.fetch_all(
        """
        SELECT date, review_type, period_start, period_end, what_worked, what_failed, highest_risk_day, next_adjustment, notes, created_at
        FROM review_snapshot
        WHERE period_start = ? AND period_end = ?
        ORDER BY created_at DESC, id DESC
        """,
        (_iso_date(week_start), _iso_date(week_end)),
    )
    return {
        "week_start": _iso_date(week_start),
        "week_end": _iso_date(week_end),
        "zone": str(weekly_row.get("zone") or ""),
        "net_life_load": float(weekly_row.get("net_life_load") or 0.0),
        "success_score": float(weekly_row.get("success_score") or 0.0),
        "sleep_compliance": {
            "completed": int(weekly_row.get("sleep_nights") or 0),
            "target": 7,
        },
        "nutrition_compliance": {
            "completed": int(weekly_row.get("nutrition_clean_days") or 0),
            "target": 7,
        },
        "hard_sessions": int(weekly_row.get("hard_sessions") or 0),
        "recovery_score": round(sum(float(row.get("recovery_score") or 0.0) for row in daily_rows), 2),
        "red_flags": red_flag_days,
        "next_action": str(weekly_row.get("next_action") or ""),
        "highest_load_day": highest_load_day,
        "approved_days": [
            str(row.get("date") or "")
            for row in approved_rows
            if str(row.get("date") or "") in usable_approved_dates
        ],
        "daily_summary_dates": [str(row.get("date") or "") for row in daily_rows],
        "latest_review": dict(recent_reviews[0]) if recent_reviews else None,
    }


def _dashboard_week_for_date(
    store: HealthObservabilityStore,
    *,
    requested_week_start: dt.date,
) -> tuple[dt.date, dt.date, Mapping[str, Any] | None]:
    weekly = store.fetch_one("SELECT * FROM derived_weekly_summary WHERE week_start = ?", (_iso_date(requested_week_start),))
    if weekly:
        week_start = requested_week_start
        return week_start, week_start + dt.timedelta(days=6), weekly
    weekly = store.fetch_one(
        """
        SELECT *
        FROM derived_weekly_summary
        WHERE week_start <= ?
        ORDER BY week_start DESC
        LIMIT 1
        """,
        (_iso_date(requested_week_start),),
    )
    if not weekly:
        week_start = requested_week_start
        return week_start, week_start + dt.timedelta(days=6), None
    week_start = _parse_date(str(weekly.get("week_start") or _iso_date(requested_week_start)))
    week_end = _parse_date(str(weekly.get("week_end") or _iso_date(week_start + dt.timedelta(days=6))))
    return week_start, week_end, weekly


def _review_period(review_type: str, day: dt.date) -> tuple[dt.date, dt.date]:
    if review_type == "monthly":
        start = day.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1) - dt.timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1) - dt.timedelta(days=1)
        return start, end
    start = _week_start(day)
    return start, start + dt.timedelta(days=6)


def _reviews_payload_for_period(
    store: HealthObservabilityStore,
    *,
    day: dt.date,
) -> Dict[str, Any]:
    week_start, week_end = _review_period("weekly", day)
    month_start, month_end = _review_period("monthly", day)
    weekly_row = store.fetch_one(
        "SELECT * FROM derived_weekly_summary WHERE week_start = ?",
        (_iso_date(week_start),),
    )
    week_daily_rows = _fetch_derived_daily_rows(store, start=week_start, end=week_end)
    highest_risk_row = max(
        week_daily_rows,
        key=lambda row: float(row.get("life_load_score") or 0.0),
        default=None,
    )
    recent_reviews = store.fetch_all(
        """
        SELECT date, review_type, period_start, period_end, what_worked, what_failed, highest_risk_day, next_adjustment, notes, created_at
        FROM review_snapshot
        ORDER BY created_at DESC, id DESC
        LIMIT 12
        """
    )
    current_week_review = store.fetch_one(
        """
        SELECT date, review_type, period_start, period_end, what_worked, what_failed, highest_risk_day, next_adjustment, notes, created_at
        FROM review_snapshot
        WHERE review_type = 'weekly' AND period_start = ? AND period_end = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (_iso_date(week_start), _iso_date(week_end)),
    )
    return {
        "schema_version": "life_load_mobile_reviews_v1",
        "date": _iso_date(day),
        "current_week_review": dict(current_week_review) if current_week_review else None,
        "weekly_review_form": {
            "review_type": "weekly",
            "period_start": _iso_date(week_start),
            "period_end": _iso_date(week_end),
            "current_zone": str((weekly_row or {}).get("zone") or ""),
            "success_score": float((weekly_row or {}).get("success_score") or 0.0),
            "training_load": float((weekly_row or {}).get("training_load") or 0.0),
            "highest_risk_day": str((highest_risk_row or {}).get("date") or ""),
            "suggested_next_adjustment": str((weekly_row or {}).get("next_action") or ""),
        },
        "monthly_review_placeholder": {
            "review_type": "monthly",
            "period_start": _iso_date(month_start),
            "period_end": _iso_date(month_end),
            "status": "placeholder",
            "notes": "Monthly trend synthesis is not implemented yet.",
        },
        "recent_reviews": [dict(row) for row in recent_reviews],
    }


def reviews_payload(store: HealthObservabilityStore, *, date_value: str | None = None) -> Dict[str, Any]:
    return _reviews_payload_for_period(store, day=_parse_date(date_value))


def weekly_replay_payload(
    store: HealthObservabilityStore,
    *,
    date_value: str | None = None,
    weeks: int = 8,
) -> Dict[str, Any]:
    day = _parse_date(date_value)
    week_start = _week_start(day)
    capped_weeks = max(1, min(int(weeks), 16))
    weekly_rows = store.fetch_all(
        """
        SELECT *
        FROM derived_weekly_summary
        WHERE week_start <= ?
        ORDER BY week_start DESC
        LIMIT ?
        """,
        (_iso_date(week_start), capped_weeks),
    )
    reports: List[Dict[str, Any]] = []
    for row in weekly_rows:
        start = _parse_date(str(row.get("week_start") or ""))
        end = _parse_date(str(row.get("week_end") or "")) if row.get("week_end") else start + dt.timedelta(days=6)
        approved_days = store.fetch_all(
            """
            SELECT d.date, s.zone, s.life_load_score, s.next_action
            FROM daily_log d
            LEFT JOIN derived_daily_summary s ON s.date = d.date
            WHERE d.date >= ? AND d.date <= ?
              AND d.user_approved_at IS NOT NULL AND TRIM(d.user_approved_at) != ''
            ORDER BY d.date ASC
            """,
            (_iso_date(start), _iso_date(end)),
        )
        highest = max(approved_days, key=lambda item: float(item.get("life_load_score") or 0.0), default=None)
        drift_row = store.fetch_one(
            """
            SELECT date, risk_level, mode, contributing_signals, next_action, evidence_note
            FROM drift_detection_snapshot
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (_iso_date(start), _iso_date(end)),
        )
        signals = _parse_json_list((drift_row or {}).get("contributing_signals"))[:3]
        one_correction = _concrete_weekly_correction(
            [
                str((drift_row or {}).get("next_action") or ""),
                str(row.get("next_action") or ""),
                str((highest or {}).get("next_action") or ""),
            ],
            signals,
        )
        reports.append(
            {
                "week_start": _iso_date(start),
                "week_end": _iso_date(end),
                "approved_day_count": len(approved_days),
                "zone": str((drift_row or {}).get("risk_level") or row.get("zone") or ""),
                "mode": str((drift_row or {}).get("mode") or ""),
                "highest_load_day": str((highest or {}).get("date") or ""),
                "highest_load_zone": str((highest or {}).get("zone") or ""),
                "signals": signals,
                "one_correction": one_correction,
                "review_exists": bool((row.get("week_start") and store.fetch_one(
                    """
                    SELECT id FROM review_snapshot
                    WHERE review_type = 'weekly' AND period_start = ? AND period_end = ?
                    LIMIT 1
                    """,
                    (_iso_date(start), _iso_date(end)),
                ))),
            }
        )
    return {
        "schema_version": "life_load_weekly_replay_report_v1",
        "date": _iso_date(day),
        "weeks_requested": capped_weeks,
        "weeks_replayed": len(reports),
        "approved_day_total": sum(int(item["approved_day_count"]) for item in reports),
        "reports": reports,
        "privacy": {
            "contains_diary_text": False,
            "contains_diary_summary": False,
            "contains_raw_payload": False,
        },
    }


def _concrete_weekly_correction(candidates: Sequence[str], signals: Sequence[str]) -> str:
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and not _is_vague_weekly_action(text):
            return text
    normalized = [str(signal or "").lower() for signal in signals]
    if any("project" in signal for signal in normalized):
        return "No project work after 20:45 for the next two evenings."
    if any("late phone" in signal or "phone" in signal for signal in normalized):
        return "Put the phone away by 21:00 tonight."
    if any("sleep" in signal for signal in normalized):
        return "Set a fixed shutdown alarm tonight."
    if any("nutrition" in signal or "food" in signal for signal in normalized):
        return "Plan the next normal dinner before 17:00."
    return "Pick one recovery-protecting boundary for the next 48 hours."


def _is_vague_weekly_action(value: str) -> bool:
    normalized = value.strip().lower().rstrip(".!?")
    if len(normalized.split()) <= 2:
        return True
    return normalized in {
        "protect sleep",
        "protect shutdown",
        "protect shutdown tonight",
        "recover first",
        "take it easy",
        "be careful",
        "hold the line",
        "no recommendation yet",
    }


def save_review_payload(store: HealthObservabilityStore, obj: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, Mapping):
        raise ValueError("review body must be a JSON object")
    raw_review = obj.get("review") if isinstance(obj.get("review"), Mapping) else obj
    if not isinstance(raw_review, Mapping):
        raise ValueError("review body must be a JSON object")
    review_type = str(raw_review.get("review_type") or "weekly").strip().lower()
    if review_type not in {"weekly", "monthly"}:
        raise ValueError("review_type must be 'weekly' or 'monthly'")
    day = _parse_date(str(raw_review.get("date") or ""))
    period_start, period_end = _review_period(review_type, day)
    default_payload = _reviews_payload_for_period(store, day=day)
    weekly_form = default_payload["weekly_review_form"]
    notes = str(raw_review.get("notes") or "").strip()
    if review_type == "monthly" and not notes:
        notes = "Monthly review placeholder only; trend synthesis is not implemented yet."
    snapshot = {
        "date": _iso_date(day),
        "review_type": review_type,
        "period_start": _iso_date(period_start),
        "period_end": _iso_date(period_end),
        "what_worked": str(raw_review.get("what_worked") or ""),
        "what_failed": str(raw_review.get("what_failed") or ""),
        "highest_risk_day": str(raw_review.get("highest_risk_day") or weekly_form.get("highest_risk_day") or ""),
        "next_adjustment": str(
            raw_review.get("next_adjustment")
            or weekly_form.get("suggested_next_adjustment")
            or ("Review the monthly trends before changing the mode." if review_type == "monthly" else "")
        ),
        "notes": notes,
    }
    store.insert_review_snapshot(snapshot)
    return {
        "schema_version": "life_load_mobile_review_saved_v1",
        "ok": True,
        "review": snapshot,
        "reviews": _reviews_payload_for_period(store, day=day),
    }


def get_entry_payload(store: HealthObservabilityStore, *, date_value: str | None = None) -> Dict[str, Any]:
    from life_load.settings import load_settings

    day = _parse_date(date_value)
    date_text = _iso_date(day)
    approved_row = store.fetch_one("SELECT * FROM daily_log WHERE date = ?", (date_text,))
    draft_row = store.fetch_daily_log_draft(date_text)
    garmin_passive = store.fetch_garmin_passive_summary(date_text)
    daily_activity_rows = [
        *_fetch_activity_rows(store, start=day, end=day),
        *_fetch_garmin_activity_rows(store, start=day, end=day),
    ]
    approved_entry = _from_daily_row(approved_row, day=day) if approved_row else _default_entry(day)
    draft_entry = _clean_entry(draft_row["draft_payload"], day=day) if draft_row else None
    active_entry = draft_entry or approved_entry
    entry_state = "draft" if draft_row else "approved" if approved_row else "garmin_only" if garmin_passive or daily_activity_rows else "blank"
    active_score = (
        _score_entry(
            active_entry,
            activity_rows=daily_activity_rows,
            garmin_passive=garmin_passive,
            prior_training_loads=_recent_training_loads(store, day=day),
            formula_settings=load_settings(store.repo_root),
        )
        if entry_state != "blank"
        else {}
    )
    latest_proposal = store.fetch_latest_ai_proposal_for_date(date_text)
    return {
        "schema_version": "life_load_mobile_entry_v1",
        "date": date_text,
        "default_date": _iso_date(_yesterday_default()),
        "entry": active_entry,
        "approved_entry": approved_entry if approved_row else None,
        "entry_exists": bool(approved_row or draft_row or garmin_passive),
        "entry_state": entry_state,
        "has_draft": bool(draft_row),
        "has_garmin_passive": bool(garmin_passive),
        "garmin_passive": garmin_passive,
        "garmin_live_import_latest": store.fetch_latest_garmin_live_import_batch(),
        "approved_at": str((approved_row or {}).get("user_approved_at") or ""),
        "draft_updated_at": str((draft_row or {}).get("updated_at") or ""),
        "score": active_score,
        "score_available": bool(active_score) and _entry_has_evaluable_signal(
            active_entry,
            garmin_passive=garmin_passive,
            activity_rows=daily_activity_rows,
        ),
        "latest_proposal": latest_proposal,
        "previous_date": _iso_date(day - dt.timedelta(days=1)),
        "next_date": _iso_date(day + dt.timedelta(days=1)),
    }


def save_entry_payload(store: HealthObservabilityStore, obj: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, Mapping):
        raise ValueError("entry body must be a JSON object")
    raw_entry = obj.get("entry") if isinstance(obj.get("entry"), Mapping) else obj
    if not isinstance(raw_entry, Mapping):
        raise ValueError("entry body must be a JSON object")
    action = str(obj.get("action") or "draft").strip().lower()
    if action not in {"draft", "approve"}:
        raise ValueError("action must be 'draft' or 'approve'")
    entry = _clean_entry(raw_entry)
    day = _parse_date(entry["date"])
    date_text = _iso_date(day)
    existing_approved = store.fetch_one("SELECT * FROM daily_log WHERE date = ?", (date_text,))
    existing_draft = store.fetch_daily_log_draft(date_text)
    if action == "draft":
        store.upsert_daily_log_draft(date=date_text, draft_payload=entry)
        payload = get_entry_payload(store, date_value=date_text)
        return {
            "schema_version": "life_load_mobile_entry_saved_v1",
            "ok": True,
            "action": "draft",
            "save_action": "updated" if existing_approved or existing_draft else "created",
            **payload,
        }

    approved_at = utc_now_iso()
    canonical_row = _sqlite_daily_row(entry, approved_at=approved_at)
    # Calculate before opening the write transaction. The store then commits
    # canonical data, draft removal, and the target summaries as one unit.
    calculated = _recalculate_for_date(
        store,
        day=day,
        persist=False,
        canonical_row_override=canonical_row,
    )
    store.approve_daily_log_with_derived(
        canonical_row,
        daily_summary=calculated["daily_row"],
        weekly_summary=calculated["weekly_row"],
    )
    try:
        derived = _refresh_derived_read_models(store, day=day)
    except Exception as exc:
        # The approval transaction is already durable and internally
        # consistent. Keep returning the saved state while exposing that a
        # secondary trend rebuild needs a later retry.
        derived = {
            "daily": calculated["daily"],
            "weekly": calculated["weekly"],
            "refresh_error": str(exc),
        }
    payload = get_entry_payload(store, date_value=date_text)
    return {
        "schema_version": "life_load_mobile_entry_saved_v1",
        "ok": True,
        "action": "approve",
        "save_action": "updated" if existing_approved else "created",
        "approved_at": approved_at,
        "derived": derived,
        **payload,
    }


def analyze_diary_payload(store: HealthObservabilityStore, obj: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, Mapping):
        raise ValueError("entry body must be a JSON object")
    raw_entry = obj.get("entry") if isinstance(obj.get("entry"), Mapping) else obj
    if not isinstance(raw_entry, Mapping):
        raise ValueError("entry body must be a JSON object")
    requested_date = str(raw_entry.get("date") or obj.get("date") or "").strip()
    day = _parse_date(requested_date)
    date_text = _iso_date(day)
    current = get_entry_payload(store, date_value=date_text)
    existing_entry = dict(current["entry"])
    diary_text = str(raw_entry.get("diary_text") or existing_entry.get("diary_text") or "").strip()
    if not diary_text:
        raise ValueError("diary_text is required for analyze-diary")
    proposal = analyze_diary_entry(
        date=date_text,
        diary_text=diary_text,
        existing_entry=existing_entry,
        week_context=dict(current.get("score") or {}),
        repo_root=store.repo_root,
    )
    validated = validate_proposal(request_date=date_text, proposal=proposal)
    for key in ("extractor_model", "extractor_timeout_s"):
        if key in proposal:
            validated[key] = proposal[key]
    fallback_error = str(proposal.get("fallback_error") or "").strip()
    if fallback_error:
        validated["fallback_error"] = fallback_error
    store.upsert_ai_proposal(
        {
            "proposal_id": validated["proposal_id"],
            "date": date_text,
            "diary_text_hash": validated["diary_text_hash"],
            "extractor_version": validated["extractor_version"],
            "raw_json": validated,
            "status": "applied_to_draft",
            "accepted_at": None,
            "error": "",
        }
    )
    updates = dict(validated["fields"])
    if validated.get("summary"):
        updates["diary_summary"] = validated["summary"]
    if validated.get("fields", {}).get("tags"):
        updates["tags"] = validated["fields"]["tags"]
    merged_entry = _merge_entry(existing_entry, {"diary_text": diary_text, **updates})
    if current["entry_state"] == "approved" and _entry_fields_equal(merged_entry, current["approved_entry"]):
        store.delete_daily_log_draft(date_text)
    else:
        store.upsert_daily_log_draft(date=date_text, draft_payload=merged_entry)
    payload = get_entry_payload(store, date_value=date_text)
    return {
        "schema_version": "life_load_mobile_diary_analysis_v1",
        "ok": True,
        "date": date_text,
        "extractor_version": str(validated.get("extractor_version") or ""),
        "extractor_model": str(validated.get("extractor_model") or ""),
        "extractor_timeout_s": int(validated.get("extractor_timeout_s") or 0),
        "proposal": validated,
        **payload,
    }


def history_payload(store: HealthObservabilityStore, *, limit: int = 60, selected_date: str | None = None) -> Dict[str, Any]:
    from life_load.settings import load_settings

    capped = max(1, min(int(limit), 180))
    settings = load_settings(store.repo_root)
    _ensure_derived_current(store, settings)
    approved_rows = store.fetch_all(
        """
        SELECT d.*, s.zone, s.next_action
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        ORDER BY d.date DESC
        LIMIT ?
        """,
        (capped,),
    )
    approved_by_date = {str(row.get("date") or ""): row for row in approved_rows}
    draft_rows = store.list_daily_log_drafts(limit=capped)
    draft_by_date = {str(row.get("date") or ""): row for row in draft_rows}
    passive_rows = store.fetch_all(
        """
        SELECT date, wellness_steps, activity_count, sleep_total_sleep_min, updated_at
        FROM garmin_daily_passive_summary
        ORDER BY date DESC
        LIMIT ?
        """,
        (capped,),
    )
    passive_by_date = {str(row.get("date") or ""): row for row in passive_rows}
    all_dates = sorted({*approved_by_date.keys(), *draft_by_date.keys(), *passive_by_date.keys()}, reverse=True)[:capped]
    rows: List[Dict[str, Any]] = []
    for date_text in all_dates:
        approved = approved_by_date.get(date_text)
        draft = draft_by_date.get(date_text)
        passive = passive_by_date.get(date_text)
        draft_entry = _clean_entry(draft["draft_payload"], day=_parse_date(date_text)) if draft else None
        canonical_entry = _from_daily_row(approved, day=_parse_date(date_text)) if approved else None
        active = draft_entry or canonical_entry or _default_entry(_parse_date(date_text))
        state = "draft_over_approved" if draft and approved else "draft" if draft else "approved" if approved else "garmin_only"
        day = _parse_date(date_text)
        activity_rows = [
            *_fetch_activity_rows(store, start=day, end=day),
            *_fetch_garmin_activity_rows(store, start=day, end=day),
        ]
        passive_data = store.fetch_garmin_passive_summary(date_text) if passive else None
        evaluable = _entry_has_evaluable_signal(active, garmin_passive=passive_data, activity_rows=activity_rows)
        score = _score_entry(
            active,
            activity_rows=activity_rows,
            garmin_passive=passive_data,
            prior_training_loads=_recent_training_loads(store, day=day),
            formula_settings=settings,
        )
        rows.append(
            {
                "date": date_text,
                "state": state,
                "approved_at": str((approved or {}).get("user_approved_at") or ""),
                "updated_at": str((draft or approved or passive or {}).get("updated_at") or ""),
                "zone": (
                    str(score.get("zone") or "")
                    if state == "approved" and evaluable
                    else str((approved or {}).get("zone") or "")
                    if approved and _entry_has_evaluable_signal(canonical_entry, garmin_passive=passive_data, activity_rows=activity_rows)
                    else ""
                ),
                "next_action": (
                    str(score.get("next_action") or "")
                    if state == "approved" and evaluable
                    else str((approved or {}).get("next_action") or "")
                    if approved and _entry_has_evaluable_signal(canonical_entry, garmin_passive=passive_data, activity_rows=activity_rows)
                    else ""
                ),
                "diary_summary": str(active.get("diary_summary") or ""),
                "diary_text": str(active.get("diary_text") or ""),
                "tags": list(active.get("tags") or []),
                "mood": active.get("mood"),
                "stress": active.get("stress"),
                "energy": active.get("energy"),
                "canonical_completed": bool(approved and str(approved.get("user_approved_at") or "").strip()),
                "score_available": bool(approved and evaluable and score),
                "has_garmin_passive": bool(passive),
                "garmin_hint": {
                    "steps": passive.get("wellness_steps") if passive else None,
                    "activity_count": passive.get("activity_count") if passive else None,
                    "sleep_total_sleep_min": passive.get("sleep_total_sleep_min") if passive else None,
                },
            }
        )
    target = selected_date or (rows[0]["date"] if rows else _iso_date(_yesterday_default()))
    selected = next((row for row in rows if row["date"] == target), None)
    if selected is None and store.fetch_garmin_passive_summary(target):
        selected = get_entry_payload(store, date_value=target)
    return {
        "schema_version": "life_load_mobile_history_v1",
        "selected_date": target,
        "entries": rows,
        "selected_entry": selected,
    }


def dashboard_payload(store: HealthObservabilityStore, *, date_value: Optional[str] = None, weeks: int = 8) -> Dict[str, Any]:
    from life_load.settings import load_settings

    capped_weeks = max(1, min(int(weeks), 16))
    day = _parse_date(date_value)
    _ensure_derived_current(store, load_settings(store.repo_root))
    requested_week_start = _week_start(day)
    week_start, week_end, weekly = _dashboard_week_for_date(store, requested_week_start=requested_week_start)
    recent_weeks = store.fetch_all(
        """
        SELECT * FROM derived_weekly_summary
        WHERE week_start <= ?
        ORDER BY week_start DESC
        LIMIT ?
        """,
        (_iso_date(requested_week_start), capped_weeks),
    )
    dashboard_state = _weekly_dashboard_state(store, week_start=week_start, week_end=week_end, weekly_row=weekly)
    history = history_payload(store, limit=35, selected_date=_iso_date(day))
    trend = _trend_payload(store, date_value=_iso_date(day), days=56)
    trend_rows = trend.get("rows") if isinstance(trend, dict) else []
    latest_features = dict(((trend_rows or [])[-1] or {}).get("features") or {}) if trend_rows else {}
    if trend_rows and "chronic_capacity_42d" not in latest_features:
        rebuild_trend_features(store)
        rebuild_drift_snapshots(store)
        trend = _trend_payload(store, date_value=_iso_date(day), days=56)
    return {
        "schema_version": "life_load_mobile_dashboard_v1",
        "date": _iso_date(day),
        "db_root": str(store.db_root.resolve()),
        "current_week": dict(weekly) if weekly else None,
        "dashboard_state": dashboard_state,
        "trend": trend,
        "drift": _drift_payload(store, date_value=_iso_date(day)),
        "reviews": _reviews_payload_for_period(store, day=day),
        "recent_weeks": [dict(row) for row in recent_weeks],
        "history": history["entries"],
        "selected_entry": history["selected_entry"],
    }


def _range_score(
    store: HealthObservabilityStore,
    row: Mapping[str, Any] | None,
    date_text: str,
    passive: Mapping[str, Any] | None,
    settings: Mapping[str, Any],
) -> Dict[str, Any]:
    if not row or not str(row.get("user_approved_at") or "").strip():
        return {}
    day = _parse_date(date_text)
    entry = _from_daily_row(row, day=day)
    activity_rows = [
        *_fetch_activity_rows(store, start=day, end=day),
        *_fetch_garmin_activity_rows(store, start=day, end=day),
    ]
    passive_data = store.fetch_garmin_passive_summary(date_text) if passive else None
    if not _entry_has_evaluable_signal(entry, garmin_passive=passive_data, activity_rows=activity_rows):
        return {}
    return _score_entry(
        entry,
        activity_rows=activity_rows,
        garmin_passive=passive_data,
        prior_training_loads=_recent_training_loads(store, day=day),
        formula_settings=settings,
    )


def range_payload(store: HealthObservabilityStore, *, start_value: str, end_value: str) -> Dict[str, Any]:
    from life_load.settings import load_settings

    start = _parse_date(start_value)
    end = _parse_date(end_value)
    if end < start:
        raise ValueError("end must be >= start")
    if (end - start).days > 370:
        raise ValueError("range too large; max 370 days")
    rows = store.fetch_all(
        """
        SELECT d.*, s.zone, s.next_action
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE d.date >= ? AND d.date <= ?
        ORDER BY d.date ASC
        """,
        (_iso_date(start), _iso_date(end)),
    )
    passive_by_date = {
        str(row.get("date") or ""): row
        for row in store.fetch_all(
            """
            SELECT *
            FROM garmin_daily_passive_summary
            WHERE date >= ? AND date <= ?
            ORDER BY date ASC
            """,
            (_iso_date(start), _iso_date(end)),
        )
    }
    row_by_date = {str(row.get("date") or ""): row for row in rows}
    all_dates = sorted({*row_by_date.keys(), *passive_by_date.keys()})
    settings = load_settings(store.repo_root)
    _ensure_derived_current(store, settings)
    entries: List[Dict[str, Any]] = []
    for date_text in all_dates:
        row = row_by_date.get(date_text)
        computed = _range_score(store, row, date_text, passive_by_date.get(date_text), settings) if row else {}
        entries.append(
            {
                "entry": _from_daily_row(row) if row else _default_entry(_parse_date(date_text)),
                "approved_at": str((row or {}).get("user_approved_at") or ""),
                "zone": computed.get("zone", ""),
                "next_action": computed.get("next_action", ""),
                "score_available": bool(row and computed),
                "entry_state": "approved" if row else "garmin_only",
                "has_garmin_passive": date_text in passive_by_date,
                "garmin_passive": store.fetch_garmin_passive_summary(date_text) if date_text in passive_by_date else None,
            }
        )
    return {
        "schema_version": "life_load_mobile_range_v1",
        "start": _iso_date(start),
        "end": _iso_date(end),
        "entries": entries,
    }


def api_store(repo_root: Path) -> HealthObservabilityStore:
    store = HealthObservabilityStore(repo_root=repo_root, root_rel=DEFAULT_ROOT_REL)
    store.ensure_layout()
    store.migrate()
    return store
