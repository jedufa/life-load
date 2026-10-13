"""Life Load filesystem DB, scoring, summaries, and API payloads.

Canonical storage is deliberately boring: one editable JSON file per date under
``data/json_entries/entries/YYYY/MM/YYYY-MM-DD.json`` plus an append-only
``events.jsonl`` audit log.  The Android/mobile web UI is an input/display
surface only; this module owns scoring truth so row-number spreadsheet nonsense
can stop breeding in the walls.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

DEFAULT_DB_REL = Path("data/json_entries")
SCHEMA_VERSION = "life_load_v0.1"
DATE_FMT = "%Y-%m-%d"

YES_VALUES = {"yes", "true", "1", "y", "on"}
NO_VALUES = {"no", "false", "0", "n", "off", ""}

DEFAULT_RULES: Dict[str, Any] = {
    "training_points": {
        "bike_commute": 1.0,
        "crossfit": 2.0,
        "run": 2.0,
        "rehab": 0.5,
        "home_strength_mobility": 0.5,
    },
    "weekly_targets": {
        "sleep_nights": 5,
        "clean_nutrition_days": 5,
        "bike_commute_days": 3,
        "rehab_sessions": 5,
        "homework_sessions": 2,
        "structured_training_sessions": 3,
    },
    "caps": {
        "max_run_sessions_per_week": 2,
        "orange_run_sessions": 3,
        "red_run_sessions": 4,
        "max_run_distance_km": 5.0,
        "max_hard_sessions_per_week": 3,
    },
    "zones": {
        "green_max": 10.0,
        "yellow_max": 20.0,
        "orange_max": 35.0,
    },
}

ENTRY_DEFAULTS: Dict[str, Any] = {
    "completed": False,
    "sleep_on_time": None,
    "bedtime": "",
    "nutrition_clean": None,
    "alcohol": "None",  # None, Social, Home
    "binge": False,
    "bike_commute": False,
    "crossfit": False,
    "run": False,
    "run_distance_km": 0.0,
    "rehab": False,
    "home_strength_mobility": False,
    "homework_done": "N/A",  # Yes, No, N/A
    "weekly_review": False,
    "work_intensity": "Normal",  # Normal, Heavy, Very heavy
    "home_office": False,
    "decompression": "None",  # None, Walk, Meditation, Cooking, Other
    "morning_reset": False,
    "shutdown_done": None,
    "phone_after_21": False,
    "project_after_2045": False,
    "injury_pain": 0,
    "foot_pain_next_day": 0,
    "migraine_warning": False,
    "on_fire": "Normal",  # Normal, High, Dangerous
    "mood": None,
    "stress": None,
    "weekend_prep_adventure": False,
    "diary": "",
    "tags": [],
}

ENTRY_FIELDS: List[str] = ["date", *ENTRY_DEFAULTS.keys()]


def _today_vienna() -> dt.date:
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo("Europe/Vienna")).date()
    except Exception:
        return dt.date.today()


def parse_date(value: str) -> dt.date:
    txt = str(value or "").strip()
    if not txt:
        raise ValueError("date is required in YYYY-MM-DD format")
    try:
        return dt.datetime.strptime(txt, DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"invalid date '{txt}'; expected YYYY-MM-DD") from exc


def iso_date(value: dt.date) -> str:
    return value.strftime(DATE_FMT)


def week_start(value: dt.date) -> dt.date:
    return value - dt.timedelta(days=value.weekday())


def week_end(value: dt.date) -> dt.date:
    return week_start(value) + dt.timedelta(days=6)


def boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    txt = str(value).strip().lower()
    if txt in YES_VALUES:
        return True
    if txt in NO_VALUES:
        return False
    return default


def nullable_bool(value: Any) -> Optional[bool]:
    if value is None or str(value).strip() == "":
        return None
    return boolish(value)


def number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def int_0_10(value: Any, default: int = 0) -> int:
    try:
        return max(0, min(10, int(round(float(value)))))
    except Exception:
        return default


def normalize_choice(value: Any, allowed: Iterable[str], default: str) -> str:
    lookup = {str(item).strip().lower(): str(item) for item in allowed}
    key = str(value or default).strip().lower()
    return lookup.get(key, default)


def normalize_tags(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(";", ",").split(",")
    tags: List[str] = []
    for item in raw:
        tag = str(item or "").strip().lower().replace(" ", "-")
        if tag and tag not in tags:
            tags.append(tag[:48])
    return tags


def normalize_entry(raw: Mapping[str, Any], *, default_date: Optional[dt.date] = None) -> Dict[str, Any]:
    date_value = raw.get("date") or (iso_date(default_date) if default_date else iso_date(_today_vienna()))
    day = parse_date(str(date_value))
    is_weekend = day.weekday() >= 5

    entry: Dict[str, Any] = {"schema_version": SCHEMA_VERSION, "date": iso_date(day)}
    entry.update(ENTRY_DEFAULTS)
    entry.update({k: v for k, v in raw.items() if k in ENTRY_DEFAULTS})

    entry["completed"] = boolish(entry.get("completed"), default=False)
    entry["sleep_on_time"] = nullable_bool(entry.get("sleep_on_time"))
    entry["bedtime"] = str(entry.get("bedtime") or "").strip()[:32]
    entry["nutrition_clean"] = nullable_bool(entry.get("nutrition_clean"))
    entry["alcohol"] = normalize_choice(entry.get("alcohol"), ["None", "Social", "Home"], "None")
    entry["binge"] = boolish(entry.get("binge"))
    entry["bike_commute"] = boolish(entry.get("bike_commute"))
    entry["crossfit"] = boolish(entry.get("crossfit"))
    entry["run"] = boolish(entry.get("run"))
    entry["run_distance_km"] = round(max(0.0, number(entry.get("run_distance_km"))), 2) if entry["run"] else 0.0
    entry["rehab"] = boolish(entry.get("rehab"))
    entry["home_strength_mobility"] = boolish(entry.get("home_strength_mobility"))
    homework_default = "N/A" if is_weekend else "No"
    entry["homework_done"] = normalize_choice(entry.get("homework_done"), ["Yes", "No", "N/A"], homework_default)
    if is_weekend and entry["homework_done"] == "No":
        entry["homework_done"] = "N/A"
    entry["weekly_review"] = boolish(entry.get("weekly_review"))
    entry["work_intensity"] = normalize_choice(entry.get("work_intensity"), ["Normal", "Heavy", "Very heavy"], "Normal")
    entry["home_office"] = boolish(entry.get("home_office"))
    entry["decompression"] = normalize_choice(
        entry.get("decompression"), ["None", "Walk", "Meditation", "Cooking", "Other"], "None"
    )
    entry["morning_reset"] = boolish(entry.get("morning_reset"))
    entry["shutdown_done"] = nullable_bool(entry.get("shutdown_done"))
    entry["phone_after_21"] = boolish(entry.get("phone_after_21"))
    entry["project_after_2045"] = boolish(entry.get("project_after_2045"))
    entry["injury_pain"] = int_0_10(entry.get("injury_pain"))
    entry["foot_pain_next_day"] = int_0_10(entry.get("foot_pain_next_day"))
    entry["migraine_warning"] = boolish(entry.get("migraine_warning"))
    entry["on_fire"] = normalize_choice(entry.get("on_fire"), ["Normal", "High", "Dangerous"], "Normal")
    entry["mood"] = None if entry.get("mood") in (None, "") else int_0_10(entry.get("mood"), default=5)
    entry["stress"] = None if entry.get("stress") in (None, "") else int_0_10(entry.get("stress"), default=5)
    entry["weekend_prep_adventure"] = boolish(entry.get("weekend_prep_adventure"))
    entry["diary"] = str(entry.get("diary") or "").strip()
    entry["tags"] = normalize_tags(entry.get("tags"))
    return entry


@dataclass
class LifeLoadStore:
    """Filesystem-backed Life Load storage rooted under local data/."""

    repo_root: Path
    db_rel: Path = DEFAULT_DB_REL

    @property
    def db_root(self) -> Path:
        return (self.repo_root / self.db_rel).resolve()

    @property
    def entries_root(self) -> Path:
        return self.db_root / "entries"

    @property
    def generated_root(self) -> Path:
        return self.db_root / "generated"

    @property
    def events_path(self) -> Path:
        return self.db_root / "events.jsonl"

    @property
    def rules_path(self) -> Path:
        return self.db_root / "rules.json"

    def ensure(self) -> None:
        self.entries_root.mkdir(parents=True, exist_ok=True)
        self.generated_root.mkdir(parents=True, exist_ok=True)
        if not self.rules_path.exists():
            atomic_write_json(self.rules_path, DEFAULT_RULES)

    def load_rules(self) -> Dict[str, Any]:
        self.ensure()
        try:
            with self.rules_path.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                return merge_rules(DEFAULT_RULES, loaded)
        except Exception:
            pass
        return DEFAULT_RULES

    def entry_path(self, day: dt.date) -> Path:
        return self.entries_root / f"{day.year:04d}" / f"{day.month:02d}" / f"{iso_date(day)}.json"

    def get_entry(self, day: dt.date) -> Dict[str, Any]:
        path = self.entry_path(day)
        if not path.exists():
            return normalize_entry({"date": iso_date(day), "homework_done": "N/A" if day.weekday() >= 5 else "No"})
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError(f"entry is not an object: {path}")
        return normalize_entry(raw, default_date=day)

    def entry_exists(self, day: dt.date) -> bool:
        return self.entry_path(day).exists()

    def save_entry(self, raw: Mapping[str, Any]) -> Dict[str, Any]:
        self.ensure()
        entry = normalize_entry(raw)
        day = parse_date(entry["date"])
        path = self.entry_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        had_previous = path.exists()
        previous = self.get_entry(day) if had_previous else None
        atomic_write_json(path, entry)
        self.append_event(
            "entry_updated" if had_previous else "entry_created",
            {
                "date": entry["date"],
                "previous_completed": bool(previous and previous.get("completed")),
                "completed": bool(entry.get("completed")),
            },
        )
        return entry

    def append_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self.db_root.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": SCHEMA_VERSION,
            "event_type": event_type,
            "utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "payload": dict(payload),
        }
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    def iter_entries(self, start: dt.date, end: dt.date) -> Iterable[Dict[str, Any]]:
        day = start
        while day <= end:
            yield self.get_entry(day)
            day += dt.timedelta(days=1)


def merge_rules(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key].update(value)
        else:
            out[key] = value
    return out


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def score_entry(entry: Mapping[str, Any], rules: Mapping[str, Any]) -> Dict[str, Any]:
    day = parse_date(str(entry["date"]))
    is_weekend = day.weekday() >= 5
    training_points = rules.get("training_points", {}) if isinstance(rules.get("training_points"), dict) else {}
    caps = rules.get("caps", {}) if isinstance(rules.get("caps"), dict) else {}
    max_run_km = float(caps.get("max_run_distance_km", 5.0))

    bike = boolish(entry.get("bike_commute"))
    crossfit = boolish(entry.get("crossfit"))
    run = boolish(entry.get("run"))
    rehab = boolish(entry.get("rehab"))
    home_strength = boolish(entry.get("home_strength_mobility"))
    run_km = number(entry.get("run_distance_km")) if run else 0.0

    training_load = 0.0
    training_load += float(training_points.get("bike_commute", 1.0)) if bike else 0.0
    training_load += float(training_points.get("crossfit", 2.0)) if crossfit else 0.0
    training_load += float(training_points.get("run", 2.0)) if run else 0.0
    training_load += float(training_points.get("rehab", 0.5)) if rehab else 0.0
    training_load += float(training_points.get("home_strength_mobility", 0.5)) if home_strength else 0.0

    strain = 0.0
    recovery = 0.0
    red_flags: List[str] = []
    warnings: List[str] = []

    sleep_on_time = entry.get("sleep_on_time")
    if sleep_on_time is True:
        recovery += 2.0
    elif sleep_on_time is False:
        strain += 2.0
        warnings.append("Sleep missed")

    nutrition_clean = entry.get("nutrition_clean")
    if nutrition_clean is True:
        recovery += 1.0
    elif nutrition_clean is False:
        strain += 2.0
        warnings.append("Nutrition drift")

    alcohol = str(entry.get("alcohol") or "None")
    if alcohol == "Home":
        strain += 8.0
        red_flags.append("Alcohol at home")
    elif alcohol == "Social":
        strain += 3.0
        warnings.append("Social alcohol")

    if boolish(entry.get("binge")):
        strain += 6.0
        warnings.append("Binge episode")

    work_intensity = str(entry.get("work_intensity") or "Normal")
    if work_intensity == "Heavy":
        strain += 2.0
    elif work_intensity == "Very heavy":
        strain += 3.0

    if boolish(entry.get("home_office")):
        strain += 1.0

    decompression = str(entry.get("decompression") or "None")
    if decompression in {"Walk", "Meditation", "Cooking"}:
        recovery += 2.0
    elif decompression == "Other":
        recovery += 1.0
    else:
        strain += 2.0

    shutdown = entry.get("shutdown_done")
    if shutdown is True:
        recovery += 3.0
    elif shutdown is False:
        strain += 3.0
        warnings.append("Shutdown missed")

    if boolish(entry.get("phone_after_21")):
        strain += 3.0
        warnings.append("Phone/videos after 21:00")
    else:
        recovery += 2.0

    if boolish(entry.get("project_after_2045")):
        strain += 3.0
        warnings.append("Project after 20:45")

    if boolish(entry.get("morning_reset")):
        recovery += 2.0

    if rehab:
        recovery += 1.0

    if boolish(entry.get("weekend_prep_adventure")):
        if is_weekend:
            recovery += 2.0
        else:
            recovery += 1.0

    injury = int_0_10(entry.get("injury_pain"))
    foot_next = int_0_10(entry.get("foot_pain_next_day"))
    if injury >= 7:
        strain += 5.0
        red_flags.append("High injury pain")
    elif injury >= 4:
        strain += 3.0
        warnings.append("Injury pain elevated")
    if foot_next >= 6:
        strain += 5.0
        red_flags.append("Foot pain next day")
    elif foot_next >= 4:
        strain += 3.0
        warnings.append("Foot pain elevated")

    if boolish(entry.get("migraine_warning")):
        strain += 4.0
        warnings.append("Migraine/dehydration warning")

    on_fire = str(entry.get("on_fire") or "Normal")
    on_fire_score = 0
    if on_fire == "High":
        on_fire_score = 2
        warnings.append("On-fire risk high")
    elif on_fire == "Dangerous":
        on_fire_score = 5
        red_flags.append("On-fire risk dangerous")

    if run and run_km > max_run_km:
        red_flags.append(f"Run distance cap violated ({run_km:g} km > {max_run_km:g} km)")

    if boolish(entry.get("binge")) and shutdown is False:
        warnings.append("Binge plus missed shutdown")

    net = training_load + strain - recovery
    zone = classify_daily_zone(net, red_flags)
    next_action = next_action_for(zone, red_flags, warnings)
    return {
        "schema_version": SCHEMA_VERSION,
        "date": entry["date"],
        "day_type": "Weekend" if is_weekend else "Weekday",
        "training_load": round(training_load, 2),
        "life_strain": round(strain, 2),
        "recovery_score": round(recovery, 2),
        "net_life_load": round(net, 2),
        "hard_session": bool(crossfit or run),
        "on_fire_score": on_fire_score,
        "zone": zone,
        "next_action": next_action,
        "warnings": warnings,
        "red_flags": red_flags,
        "field_status": field_status(entry, rules),
    }


def classify_daily_zone(net: float, red_flags: List[str]) -> str:
    if red_flags:
        return "Red"
    if net <= 3:
        return "Green"
    if net <= 8:
        return "Yellow"
    if net <= 14:
        return "Orange"
    return "Red"


def field_status(entry: Mapping[str, Any], rules: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    """Return field-level color/target/help metadata for mobile UI highlighting."""
    max_run = float(((rules.get("caps") or {}).get("max_run_distance_km", 5.0)))
    is_weekend = parse_date(str(entry["date"])).weekday() >= 5

    statuses: Dict[str, Dict[str, str]] = {
        "sleep_on_time": {"target": "Yes, in bed by 21:45", "level": "neutral", "help": "Sleep is priority 1."},
        "nutrition_clean": {"target": "Yes, keto-ish whole food day", "level": "neutral", "help": "Target: 5 clean days/week."},
        "alcohol": {"target": "None; Home is red", "level": "neutral", "help": "Alcohol at home is a red flag."},
        "run_distance_km": {"target": f"<= {max_run:g} km", "level": "neutral", "help": "First block cap."},
        "homework_done": {"target": "Tue/Thu protected; weekend N/A", "level": "neutral", "help": "No weekend penalty."},
        "shutdown_done": {"target": "Yes, shutdown by 20:45", "level": "neutral", "help": "Protect 21:00 collapse zone."},
        "phone_after_21": {"target": "No", "level": "neutral", "help": "Late solo phone/video is a trigger."},
        "project_after_2045": {"target": "No", "level": "neutral", "help": "Project work stops at 20:45."},
        "injury_pain": {"target": "0-3", "level": "neutral", "help": "5+ is elevated, 7+ red."},
        "foot_pain_next_day": {"target": "0-3", "level": "neutral", "help": "5+ is elevated, 6+ red."},
        "on_fire": {"target": "Normal", "level": "neutral", "help": "High motivation triggers caps, not expansion."},
    }
    if entry.get("sleep_on_time") is True:
        statuses["sleep_on_time"]["level"] = "good"
    elif entry.get("sleep_on_time") is False:
        statuses["sleep_on_time"]["level"] = "warn"
    if entry.get("nutrition_clean") is True:
        statuses["nutrition_clean"]["level"] = "good"
    elif entry.get("nutrition_clean") is False:
        statuses["nutrition_clean"]["level"] = "warn"
    if str(entry.get("alcohol")) == "Home":
        statuses["alcohol"]["level"] = "red"
    elif str(entry.get("alcohol")) == "Social":
        statuses["alcohol"]["level"] = "warn"
    else:
        statuses["alcohol"]["level"] = "good"
    if boolish(entry.get("run")):
        statuses["run_distance_km"]["level"] = "red" if number(entry.get("run_distance_km")) > max_run else "good"
    if is_weekend:
        statuses["homework_done"]["level"] = "neutral"
    elif str(entry.get("homework_done")) == "Yes":
        statuses["homework_done"]["level"] = "good"
    elif str(entry.get("homework_done")) == "No":
        statuses["homework_done"]["level"] = "warn"
    if entry.get("shutdown_done") is True:
        statuses["shutdown_done"]["level"] = "good"
    elif entry.get("shutdown_done") is False:
        statuses["shutdown_done"]["level"] = "warn"
    statuses["phone_after_21"]["level"] = "red" if boolish(entry.get("phone_after_21")) else "good"
    statuses["project_after_2045"]["level"] = "red" if boolish(entry.get("project_after_2045")) else "good"
    injury = int_0_10(entry.get("injury_pain"))
    statuses["injury_pain"]["level"] = "red" if injury >= 7 else "warn" if injury >= 5 else "good"
    foot = int_0_10(entry.get("foot_pain_next_day"))
    statuses["foot_pain_next_day"]["level"] = "red" if foot >= 6 else "warn" if foot >= 5 else "good"
    statuses["on_fire"]["level"] = "red" if str(entry.get("on_fire")) == "Dangerous" else "warn" if str(entry.get("on_fire")) == "High" else "good"
    return statuses


def _scaled_week_target(full_target: int, elapsed_days: int) -> int:
    if elapsed_days <= 0:
        return 0
    return max(0, min(full_target, int(math.floor((full_target * elapsed_days) / 7.0))))


def _elapsed_homework_slots(start: dt.date, anchor: dt.date) -> int:
    count = 0
    day = start
    while day <= anchor:
        if day.weekday() in {1, 3}:  # Tuesday / Thursday
            count += 1
        day += dt.timedelta(days=1)
    return count


def summarize_week(
    entries: List[Dict[str, Any]],
    rules: Mapping[str, Any],
    *,
    start: dt.date,
    anchor: Optional[dt.date] = None,
) -> Dict[str, Any]:
    caps = rules.get("caps", {}) if isinstance(rules.get("caps"), dict) else {}
    zones = rules.get("zones", {}) if isinstance(rules.get("zones"), dict) else {}
    weekly_targets = rules.get("weekly_targets", {}) if isinstance(rules.get("weekly_targets"), dict) else {}
    completed = [e for e in entries if boolish(e.get("completed"))]
    scored = [score_entry(e, rules) for e in completed]

    sleep = sum(1 for e in completed if e.get("sleep_on_time") is True)
    clean = sum(1 for e in completed if e.get("nutrition_clean") is True)
    alcohol_home = sum(1 for e in completed if str(e.get("alcohol")) == "Home")
    binge = sum(1 for e in completed if boolish(e.get("binge")))
    run_entries = [e for e in completed if boolish(e.get("run"))]
    run_sessions = len(run_entries)
    max_run_km = max([number(e.get("run_distance_km")) for e in run_entries] or [0.0])
    weekly_run_km = sum(number(e.get("run_distance_km")) for e in run_entries)
    crossfit = sum(1 for e in completed if boolish(e.get("crossfit")))
    hard_sessions = run_sessions + crossfit
    bike = sum(1 for e in completed if boolish(e.get("bike_commute")))
    rehab = sum(1 for e in completed if boolish(e.get("rehab")))
    homework = sum(1 for e in completed if str(e.get("homework_done")) == "Yes")
    weekly_review = sum(1 for e in completed if boolish(e.get("weekly_review")))
    net = round(sum(number(s.get("net_life_load")) for s in scored), 2)
    training_load = round(sum(number(s.get("training_load")) for s in scored), 2)
    recovery_score = round(sum(number(s.get("recovery_score")) for s in scored), 2)
    red_flags: List[str] = []
    warnings: List[str] = []
    for s in scored:
        red_flags.extend(str(x) for x in s.get("red_flags", []))
        warnings.extend(str(x) for x in s.get("warnings", []))

    run_cap_status = "OK - within run cap"
    max_runs = int(caps.get("max_run_sessions_per_week", 2))
    orange_runs = int(caps.get("orange_run_sessions", 3))
    red_runs = int(caps.get("red_run_sessions", 4))
    max_run_distance = float(caps.get("max_run_distance_km", 5.0))
    if run_sessions >= red_runs:
        run_cap_status = "RED - too many run sessions"
        red_flags.append("Running session cap violated")
    elif run_sessions >= orange_runs:
        run_cap_status = "ORANGE - running cap exceeded"
        warnings.append("Running session cap exceeded")
    elif run_sessions > max_runs:
        run_cap_status = "ORANGE - running cap exceeded"
        warnings.append("Running session cap exceeded")
    if max_run_km > max_run_distance:
        run_cap_status = "RED - run distance cap violated"
        red_flags.append("Run distance cap violated")

    hard_cap = int(caps.get("max_hard_sessions_per_week", 3))
    if hard_sessions > hard_cap:
        red_flags.append("Hard session cap violated")

    status = weekly_zone(net, red_flags, zones)
    if run_sessions >= orange_runs and run_sessions < red_runs:
        status = _elevate_weekly_status(status, "Orange")
    if any("pain elevated" in warning.lower() for warning in warnings):
        status = _elevate_weekly_status(status, "Orange")
    next_action = next_action_for(status, red_flags, warnings)
    sleep_target = int(weekly_targets.get("sleep_nights", 5) or 5)
    clean_target = int(weekly_targets.get("clean_nutrition_days", 5) or 5)
    bike_target = int(weekly_targets.get("bike_commute_days", 3) or 3)
    rehab_target = int(weekly_targets.get("rehab_sessions", 5) or 5)
    homework_target = int(weekly_targets.get("homework_sessions", 2) or 2)
    review_target = 1
    training_min_target = 2
    elapsed_days = 7
    if anchor and start <= anchor <= start + dt.timedelta(days=6):
        elapsed_days = (anchor - start).days + 1
        sleep_target = _scaled_week_target(sleep_target, elapsed_days)
        clean_target = _scaled_week_target(clean_target, elapsed_days)
        bike_target = _scaled_week_target(bike_target, elapsed_days)
        rehab_target = _scaled_week_target(rehab_target, elapsed_days)
        homework_target = _elapsed_homework_slots(start, anchor)
        review_target = 1 if elapsed_days >= 7 else 0
        training_min_target = _scaled_week_target(2, elapsed_days)
    success_items = {
        "sleep": sleep >= sleep_target,
        "nutrition": clean >= clean_target,
        "alcohol": alcohol_home == 0,
        "training": hard_sessions >= training_min_target and hard_sessions <= hard_cap,
        "bike": bike >= bike_target,
        "rehab": rehab >= rehab_target,
        "homework": homework >= homework_target,
        "review": weekly_review >= review_target,
    }
    if not completed:
        success_items = {key: False for key in success_items}
        warnings.append("No completed days recorded")
        next_action = "Complete one real day first. Treat blank weeks as missing data, not success."
    success_score = round(100.0 * sum(1 for ok in success_items.values() if ok) / max(1, len(success_items)), 1)
    return {
        "schema_version": SCHEMA_VERSION,
        "week_start": iso_date(start),
        "week_end": iso_date(start + dt.timedelta(days=6)),
        "completed_days": len(completed),
        "sleep_nights": sleep,
        "clean_nutrition_days": clean,
        "alcohol_at_home": alcohol_home,
        "binge_count": binge,
        "run_sessions": run_sessions,
        "max_run_km": round(max_run_km, 2),
        "weekly_run_km": round(weekly_run_km, 2),
        "crossfit_sessions": crossfit,
        "hard_sessions": hard_sessions,
        "bike_commute_days": bike,
        "rehab_sessions": rehab,
        "homework_done": homework,
        "weekly_review": weekly_review,
        "training_load": training_load,
        "recovery_score": recovery_score,
        "net_life_load": net,
        "success_score": success_score,
        "success_items": success_items,
        "targets_applied": {
            "sleep_nights": sleep_target,
            "clean_nutrition_days": clean_target,
            "bike_commute_days": bike_target,
            "rehab_sessions": rehab_target,
            "homework_sessions": homework_target,
            "training_min_sessions": training_min_target,
            "weekly_review": review_target,
            "elapsed_days": elapsed_days,
        },
        "running_cap_status": run_cap_status,
        "status": status,
        "next_action": next_action,
        "red_flags": sorted(set(red_flags)),
        "warnings": sorted(set(warnings)),
    }


def weekly_zone(net: float, red_flags: List[str], zones: Mapping[str, Any]) -> str:
    if red_flags:
        return "Red"
    if net <= float(zones.get("green_max", 10.0)):
        return "Green"
    if net <= float(zones.get("yellow_max", 20.0)):
        return "Yellow"
    if net <= float(zones.get("orange_max", 35.0)):
        return "Orange"
    return "Red"


def _elevate_weekly_status(current: str, minimum: str) -> str:
    order = {"Green": 0, "Yellow": 1, "Orange": 2, "Red": 3}
    names = {value: key for key, value in order.items()}
    return names[max(order.get(current, 0), order.get(minimum, 0))]


def next_action_for(status: str, red_flags: List[str], warnings: List[str]) -> str:
    if status == "Red":
        if any("Alcohol at home" in x for x in red_flags):
            return "Stabilization week. Remove alcohol exposure and protect sleep."
        if any("Run" in x or "Running" in x for x in red_flags):
            return "Stabilization week. Freeze running progression and keep rehab."
        if any("Hard session" in x for x in red_flags):
            return "Stabilization week. Reduce hard sessions and protect deload."
        return "Stabilization week. Do minimum plan, no punishment workout."
    if status == "Orange":
        return "Reduce ambition. Hold progression, add decompression, protect shutdown."
    if status == "Yellow":
        return "Load building. Keep plan flat, protect sleep and decompression."
    return "Continue. No heroic expansion."


def dashboard_payload(store: LifeLoadStore, *, date_value: Optional[str] = None, weeks: int = 8) -> Dict[str, Any]:
    anchor = parse_date(date_value) if date_value else _today_vienna()
    current_start = week_start(anchor)
    rules = store.load_rules()
    summaries: List[Dict[str, Any]] = []
    for idx in range(max(1, weeks)):
        start = current_start - dt.timedelta(days=7 * (weeks - idx - 1))
        entries = list(store.iter_entries(start, start + dt.timedelta(days=6)))
        summaries.append(summarize_week(entries, rules, start=start))
    current_week = summarize_week(
        list(store.iter_entries(current_start, current_start + dt.timedelta(days=6))),
        rules,
        start=current_start,
        anchor=anchor,
    )
    result = {
        "schema_version": "life_load_dashboard_v0.1",
        "utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "db_root": str(store.db_root),
        "date": iso_date(anchor),
        "current_week": current_week,
        "weeks": summaries,
    }
    atomic_write_json(store.generated_root / "dashboard_state.json", result)
    write_exports(store, summaries)
    return result


def get_entry_payload(store: LifeLoadStore, *, date_value: str) -> Dict[str, Any]:
    day = parse_date(date_value)
    rules = store.load_rules()
    exists = store.entry_exists(day)
    entry = store.get_entry(day)
    return {
        "schema_version": "life_load_entry_v0.1",
        "entry": entry,
        "entry_exists": exists,
        "entry_state": "saved" if exists else "draft",
        "score": score_entry(entry, rules),
        "previous_date": iso_date(day - dt.timedelta(days=1)),
        "next_date": iso_date(day + dt.timedelta(days=1)),
    }


def save_entry_payload(store: LifeLoadStore, obj: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, Mapping):
        raise ValueError("entry body must be a JSON object")
    raw = obj.get("entry") if isinstance(obj.get("entry"), dict) else obj
    if not isinstance(raw, Mapping):
        raise ValueError("entry body must be a JSON object")
    existing = store.entry_exists(parse_date(str(raw.get("date") or "")))
    entry = store.save_entry(raw)
    rules = store.load_rules()
    score = score_entry(entry, rules)
    dashboard_payload(store, date_value=str(entry["date"]), weeks=8)
    return {
        "schema_version": "life_load_entry_saved_v0.1",
        "ok": True,
        "entry": entry,
        "entry_exists": True,
        "entry_state": "saved",
        "save_action": "updated" if existing else "created",
        "score": score,
    }


def range_payload(store: LifeLoadStore, *, start_value: str, end_value: str) -> Dict[str, Any]:
    start = parse_date(start_value)
    end = parse_date(end_value)
    if end < start:
        raise ValueError("end must be >= start")
    if (end - start).days > 370:
        raise ValueError("range too large; max 370 days")
    rules = store.load_rules()
    entries = []
    for entry in store.iter_entries(start, end):
        entries.append({"entry": entry, "score": score_entry(entry, rules)})
    return {"schema_version": "life_load_range_v0.1", "start": start_value, "end": end_value, "entries": entries}


def write_exports(store: LifeLoadStore, weekly: List[Dict[str, Any]]) -> None:
    exports_root = store.generated_root / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    weekly_path = exports_root / "weekly_summaries.csv"
    if weekly:
        with weekly_path.open("w", newline="", encoding="utf-8") as fh:
            fields = [
                "week_start", "week_end", "completed_days", "sleep_nights", "clean_nutrition_days",
                "alcohol_at_home", "binge_count", "run_sessions", "max_run_km", "weekly_run_km",
                "crossfit_sessions", "hard_sessions", "bike_commute_days", "rehab_sessions", "homework_done",
                "weekly_review", "training_load", "recovery_score", "net_life_load", "success_score",
                "running_cap_status", "status", "next_action",
            ]
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in weekly:
                writer.writerow({key: row.get(key, "") for key in fields})


def load_daily_entry(store: LifeLoadStore, date_value: str) -> Dict[str, Any]:
    return store.get_entry(parse_date(date_value))


def save_daily_entry(store: LifeLoadStore, raw: Mapping[str, Any]) -> Dict[str, Any]:
    return store.save_entry(raw)


def calculate_daily_score(entry: Mapping[str, Any], rules: Mapping[str, Any]) -> Dict[str, Any]:
    return score_entry(entry, rules)


def calculate_weekly_summary(
    entries: List[Dict[str, Any]],
    rules: Mapping[str, Any],
    *,
    start: dt.date,
    anchor: Optional[dt.date] = None,
) -> Dict[str, Any]:
    return summarize_week(entries, rules, start=start, anchor=anchor)


def calculate_dashboard_state(store: LifeLoadStore, *, date_value: Optional[str] = None, weeks: int = 8) -> Dict[str, Any]:
    return dashboard_payload(store, date_value=date_value, weeks=weeks)


def export_weekly_summaries_csv(store: LifeLoadStore, weekly: List[Dict[str, Any]]) -> None:
    write_exports(store, weekly)


def api_store(repo_root: Path) -> LifeLoadStore:
    store = LifeLoadStore(repo_root=repo_root)
    store.ensure()
    return store
