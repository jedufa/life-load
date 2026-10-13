"""Optional Garmin Connect probe using the third-party ``garminconnect`` package.

This is intentionally not part of the Life Load ingestion pipeline.  It is a
thin experiment to check whether live Garmin account access is viable before we
decide whether to promote it into durable imports.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_TOKENSTORE = "~/.garminconnect"
DEFAULT_OUTPUT_REL = Path("runtime/state/life_load/garmin_connect_probe")
LIVE_IMPORT_SCHEMA_VERSION = "life_load_garminconnect_import_v1"


class GarminConnectProbeError(RuntimeError):
    """Raised when the optional Garmin Connect probe cannot run."""


@dataclass(frozen=True)
class ProbeConfig:
    date: str
    email: str | None
    password: str | None
    tokenstore: str
    output_dir: Path
    write_raw: bool


def today_text() -> str:
    return dt.date.today().isoformat()


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_now_precise_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_date_text(value: str | None) -> str:
    if not value:
        return today_text()
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise GarminConnectProbeError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def import_garmin_class() -> Any:
    try:
        from garminconnect import Garmin
    except ImportError as exc:
        raise GarminConnectProbeError(
            "Optional dependency missing. Install only for this experiment with: "
            "python -m pip install --upgrade garminconnect curl_cffi"
        ) from exc
    return Garmin


def prompt_mfa() -> str:
    if not sys.stdin.isatty():
        raise GarminConnectProbeError("Garmin MFA is required, but stdin is not interactive.")
    return input("Garmin MFA code: ")


def login_client(config: ProbeConfig) -> Any:
    token_path = Path(config.tokenstore).expanduser()
    if not token_path.exists() and not (config.email and config.password):
        raise GarminConnectProbeError(
            f"No Garmin token store found at {token_path}. Run the CLI probe once with GARMIN_EMAIL/GARMIN_PASSWORD."
        )
    Garmin = import_garmin_class()
    client = Garmin(config.email, config.password, prompt_mfa=prompt_mfa)
    client.login(config.tokenstore)
    harden_private_path(token_path)
    return client


def _safe_call(client: Any, method_name: str, *args: Any) -> dict[str, Any]:
    method = getattr(client, method_name, None)
    if not callable(method):
        return {
            "ok": False,
            "skipped": True,
            "method": method_name,
            "error": "method not available in installed garminconnect version",
        }
    try:
        return {"ok": True, "method": method_name, "data": method(*args)}
    except Exception as exc:
        return {
            "ok": False,
            "method": method_name,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def fetch_day_bundle(client: Any, date_text: str) -> dict[str, Any]:
    """Fetch a conservative Garmin daily bundle.

    Each endpoint is isolated.  The probe should still produce useful evidence
    if Garmin changes one response shape, one endpoint is empty, or the
    installed library version lacks a method.
    """

    calls = {
        "stats": _safe_call(client, "get_stats", date_text),
        "user_summary": _safe_call(client, "get_user_summary", date_text),
        "heart_rates": _safe_call(client, "get_heart_rates", date_text),
        "resting_heart_rate": _safe_call(client, "get_resting_heart_rate", date_text),
        "sleep": _safe_call(client, "get_sleep_data", date_text),
        "all_day_stress": _safe_call(client, "get_all_day_stress", date_text),
        "stress": _safe_call(client, "get_stress_data", date_text),
        "body_battery": _safe_call(client, "get_body_battery", date_text, date_text),
        "activities": _safe_call(client, "get_activities_by_date", date_text, date_text),
        "activities_for_day": _safe_call(client, "get_activities_fordate", date_text),
        "steps_data": _safe_call(client, "get_steps_data", date_text),
        "intensity_minutes": _safe_call(client, "get_intensity_minutes_data", date_text),
    }
    return {"date": date_text, "fetched_at": utc_now_iso(), "source": "garminconnect_probe", "calls": calls}


def fetch_days_bundle(client: Any, *, end_date: str, days: int) -> list[dict[str, Any]]:
    if days < 1 or days > 31:
        raise GarminConnectProbeError("days must be between 1 and 31")
    end = dt.date.fromisoformat(parse_date_text(end_date))
    start = end - dt.timedelta(days=days - 1)
    return [fetch_day_bundle(client, (start + dt.timedelta(days=offset)).isoformat()) for offset in range(days)]


def date_range_texts(*, end_date: str, days: int) -> list[str]:
    if days < 1 or days > 31:
        raise GarminConnectProbeError("days must be between 1 and 31")
    end = dt.date.fromisoformat(parse_date_text(end_date))
    start = end - dt.timedelta(days=days - 1)
    return [(start + dt.timedelta(days=offset)).isoformat() for offset in range(days)]


def _first_number(mapping: Mapping[str, Any] | None, keys: tuple[str, ...]) -> float | int | None:
    if not isinstance(mapping, Mapping):
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                number = float(value)
            except ValueError:
                continue
            return int(number) if number.is_integer() else number
    return None


def _call_data(bundle: Mapping[str, Any], name: str) -> Any:
    call = bundle.get("calls", {}).get(name, {}) if isinstance(bundle.get("calls"), Mapping) else {}
    if isinstance(call, Mapping) and call.get("ok"):
        return call.get("data")
    return None


def _call_items(bundle: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    calls = bundle.get("calls")
    if not isinstance(calls, Mapping):
        return []
    return [(str(name), call) for name, call in calls.items() if isinstance(call, Mapping)]


def _first_mapping(*values: Any) -> Mapping[str, Any] | None:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return None


def _nested_mapping(mapping: Mapping[str, Any] | None, *keys: str) -> Mapping[str, Any] | None:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, Mapping) else None


def _sleep_minutes(sleep_data: Any) -> int | None:
    sleep = sleep_data if isinstance(sleep_data, Mapping) else None
    candidates = [
        sleep,
        _nested_mapping(sleep, "dailySleepDTO"),
        _nested_mapping(sleep, "sleepData"),
    ]
    for candidate in candidates:
        seconds = _first_number(
            candidate,
            ("sleepTimeSeconds", "totalSleepSeconds", "durationInSeconds", "sleepDurationSeconds"),
        )
        if seconds is not None:
            return int(round(float(seconds) / 60))
        millis = _first_number(candidate, ("sleepTimeMillis", "totalSleepMillis", "durationInMillis"))
        if millis is not None:
            return int(round(float(millis) / 60000))
    return None


def summarize_day_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    stats = _first_mapping(_call_data(bundle, "stats"), _call_data(bundle, "user_summary"))
    heart_rates = _call_data(bundle, "heart_rates")
    resting_hr = _call_data(bundle, "resting_heart_rate")
    stress = _first_mapping(_call_data(bundle, "all_day_stress"), _call_data(bundle, "stress"))
    activities = _call_data(bundle, "activities")
    activities_for_day = _call_data(bundle, "activities_for_day")
    steps_data = _call_data(bundle, "steps_data")
    intensity_minutes = _first_mapping(_call_data(bundle, "intensity_minutes"))

    stats_steps = _first_number(stats, ("totalSteps", "steps", "stepCount", "wellnessSteps"))
    interval_steps = _steps_from_intervals(steps_data)
    steps = interval_steps if interval_steps is not None else stats_steps
    steps_source = "steps_data" if interval_steps is not None else "stats" if stats_steps is not None else ""

    resting_hr_value = _first_number(
        _first_mapping(heart_rates),
        ("restingHeartRate", "restingHR", "restingHr", "resting_heart_rate"),
    )
    if resting_hr_value is None:
        resting_hr_value = _first_number(_first_mapping(resting_hr), ("value", "restingHeartRate"))
    if resting_hr_value is None and isinstance(resting_hr, (int, float)):
        resting_hr_value = resting_hr

    call_items = _call_items(bundle)
    successful_calls = [name for name, call in call_items if call.get("ok")]
    failed_calls = {
        name: call.get("error") or call.get("error_type") or "unknown error"
        for name, call in call_items
        if not call.get("ok") and not call.get("skipped")
    }
    skipped_calls = [
        name
        for name, call in call_items
        if isinstance(call, Mapping) and call.get("skipped")
    ]

    return {
        "date": bundle.get("date"),
        "steps": steps,
        "steps_source": steps_source,
        "stats_steps": stats_steps,
        "interval_steps": interval_steps,
        "active_kcal": _first_number(stats, ("activeKilocalories", "activeCalories", "wellnessActiveKcal")),
        "resting_hr": resting_hr_value,
        "avg_stress": _first_number(
            stress,
            ("avgStressLevel", "averageStressLevel", "stressAvg", "wellnessAvgStress"),
        ),
        "sleep_total_min": _sleep_minutes(_call_data(bundle, "sleep")),
        "activity_count": len(activities) if isinstance(activities, list) else None,
        "activities_for_day_count": _activities_for_day_count(activities_for_day),
        "moderate_minutes": _first_number(intensity_minutes, ("moderateMinutes", "weeklyModerate")),
        "vigorous_minutes": _first_number(intensity_minutes, ("vigorousMinutes", "weeklyVigorous")),
        "intensity_minutes_total": _first_number(intensity_minutes, ("dailyTotal", "endDayMinutes", "weeklyTotal")),
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "skipped_calls": skipped_calls,
    }


def _steps_from_intervals(value: Any) -> int | None:
    if not isinstance(value, list):
        return None
    total = 0
    found = False
    for row in value:
        if not isinstance(row, Mapping):
            continue
        steps = _number(row.get("steps"))
        if steps is None:
            continue
        total += int(steps)
        found = True
    return total if found else None


def _activities_for_day_count(value: Any) -> int | None:
    if isinstance(value, Mapping):
        section = value.get("ActivitiesForDay")
        if isinstance(section, Mapping) and isinstance(section.get("payload"), list):
            return len(section["payload"])
    return None


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_source_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in bundle.items() if key != "fetched_at"}


def _source_confidence(summary: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    steps_source = str(summary.get("steps_source") or "")
    return {
        "steps": {
            "source": steps_source,
            "confidence": "high" if steps_source == "steps_data" else "medium" if steps_source == "stats" else "missing",
        },
        "sleep": {
            "source": "sleep",
            "confidence": "high" if summary.get("sleep_total_min") is not None else "missing",
        },
        "stress": {
            "source": "all_day_stress_or_stress",
            "confidence": "medium" if summary.get("avg_stress") is not None else "missing",
        },
        "activities": {
            "source": "activities",
            "confidence": "high" if summary.get("activity_count") is not None else "missing",
        },
        "intensity_minutes": {
            "source": "intensity_minutes",
            "confidence": "medium" if summary.get("intensity_minutes_total") is not None else "missing",
        },
    }


def _activity_type_key(activity: Mapping[str, Any], key: str) -> str:
    value = activity.get(key)
    if isinstance(value, Mapping):
        return str(value.get("typeKey") or value.get("sportTypeKey") or value.get("name") or "").strip()
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_utc_iso(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _utc_now_datetime() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def dates_needing_import(
    store: Any,
    *,
    end_date: str,
    days: int,
    max_age_minutes: int,
    now: dt.datetime | None = None,
) -> list[str]:
    dates = date_range_texts(end_date=end_date, days=days)
    rows = store.fetch_all(
        f"SELECT date, updated_at FROM garmin_daily_passive_summary WHERE date IN ({','.join(['?'] * len(dates))})",
        dates,
    )
    updated_by_date = {str(row["date"]): _parse_utc_iso(row.get("updated_at")) for row in rows}
    reference = (now or _utc_now_datetime()).astimezone(dt.timezone.utc)
    max_age = dt.timedelta(minutes=max_age_minutes)
    stale: list[str] = []
    for date_text in dates:
        updated_at = updated_by_date.get(date_text)
        if updated_at is None or reference - updated_at > max_age:
            stale.append(date_text)
    return stale


def _minutes_from_seconds(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return round(number / 60.0, 2)


def _km_from_meters(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return round(number / 1000.0, 3)


def _activity_id(activity: Mapping[str, Any], source_sha256: str, index: int) -> str:
    for key in ("activityId", "activity_id", "activityUUID", "uuid"):
        value = str(activity.get(key) or "").strip()
        if value:
            return value
    return f"garminconnect:{source_sha256}:{index}"


def _activity_date(activity: Mapping[str, Any], fallback_date: str) -> str:
    for key in ("startTimeLocal", "startTimeGMT", "beginTimestamp", "date"):
        value = str(activity.get(key) or "").strip()
        if len(value) >= 10:
            return value[:10]
    return fallback_date


def _activity_duration_min(activity: Mapping[str, Any]) -> float | None:
    for key in ("duration", "elapsedDuration", "movingDuration", "durationInSeconds"):
        minutes = _minutes_from_seconds(activity.get(key))
        if minutes is not None:
            return minutes
    return _number(activity.get("duration_min"))


def _activity_moving_duration_min(activity: Mapping[str, Any]) -> float | None:
    for key in ("movingDuration", "movingDurationInSeconds"):
        minutes = _minutes_from_seconds(activity.get(key))
        if minutes is not None:
            return minutes
    return None


def _activity_distance_km(activity: Mapping[str, Any]) -> float | None:
    for key in ("distance", "distanceMeters"):
        km = _km_from_meters(activity.get(key))
        if km is not None:
            return km
    return _number(activity.get("distance_km"))


def _normalized_activity_rows(bundle: Mapping[str, Any], source_sha256: str) -> list[tuple[Any, ...]]:
    activities = _call_data(bundle, "activities")
    if not isinstance(activities, list):
        return []
    rows: list[tuple[Any, ...]] = []
    fallback_date = str(bundle.get("date") or "")
    for index, activity in enumerate(activities):
        if not isinstance(activity, Mapping):
            continue
        duration_min = _activity_duration_min(activity)
        moving_min = _activity_moving_duration_min(activity)
        distance_km = _activity_distance_km(activity)
        aerobic = _number(activity.get("aerobicTrainingEffect") or activity.get("aerobic_training_effect"))
        anaerobic = _number(activity.get("anaerobicTrainingEffect") or activity.get("anaerobic_training_effect"))
        hard = 1 if max(aerobic or 0.0, anaerobic or 0.0) >= 3.0 or (duration_min or 0.0) >= 45.0 else 0
        rows.append(
            (
                _activity_id(activity, source_sha256, index),
                _activity_date(activity, fallback_date),
                str(activity.get("startTimeLocal") or activity.get("startTimeGMT") or ""),
                str(activity.get("activityName") or activity.get("name") or ""),
                _activity_type_key(activity, "activityType"),
                _activity_type_key(activity, "sportType"),
                duration_min,
                moving_min,
                distance_km,
                moving_min or duration_min,
                None,
                hard,
                _number(activity.get("calories") or activity.get("activeKilocalories")),
                _number(activity.get("averageHR") or activity.get("avgHR") or activity.get("avg_hr")),
                _number(activity.get("maxHR") or activity.get("max_hr")),
                aerobic,
                anaerobic,
                "garminconnect_live",
                "live_api",
                source_sha256,
                json.dumps(dict(activity), sort_keys=True, ensure_ascii=False, default=str),
            )
        )
    return rows


def _passive_summary_row(bundle: Mapping[str, Any], source_sha256: str, imported_at: str) -> tuple[Any, ...]:
    summary = summarize_day_bundle(bundle)
    activities = _normalized_activity_rows(bundle, source_sha256)
    raw_payload = {
        "bundle": bundle,
        "summary": summary,
        "source_confidence": _source_confidence(summary),
    }
    return (
        summary.get("date"),
        int(summary.get("steps")) if summary.get("steps") is not None else None,
        summary.get("resting_hr"),
        summary.get("avg_stress"),
        summary.get("active_kcal"),
        summary.get("activity_count"),
        round(sum(float(row[6] or 0.0) for row in activities), 2),
        round(sum(float(row[8] or 0.0) for row in activities), 3),
        round(sum(float(row[9] or 0.0) for row in activities), 2),
        sum(int(row[11] or 0) for row in activities),
        summary.get("sleep_total_min"),
        None,
        "",
        "",
        None,
        None,
        source_sha256,
        json.dumps(raw_payload, sort_keys=True, ensure_ascii=False, default=str),
        imported_at,
    )


def import_day_bundle(store: Any, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Upsert one Garmin live bundle into existing passive/activity tables."""

    store.migrate()
    source_sha256 = _sha256_json(_stable_source_bundle(bundle))
    imported_at = utc_now_iso()
    activity_rows = _normalized_activity_rows(bundle, source_sha256)
    passive_row = _passive_summary_row(bundle, source_sha256, imported_at)
    date_text = str(passive_row[0] or "")
    existing_passive = store.fetch_one(
        "SELECT source_sha256 FROM garmin_daily_passive_summary WHERE date = ?",
        (date_text,),
    )
    activity_ids = [str(row[0]) for row in activity_rows]
    existing_activity_rows = (
        store.fetch_all(
            f"SELECT activity_id, raw_json FROM garmin_activity WHERE activity_id IN ({','.join(['?'] * len(activity_ids))})",
            activity_ids,
        )
        if activity_ids
        else []
    )
    existing_activity_raw = {str(row["activity_id"]): str(row["raw_json"] or "") for row in existing_activity_rows}
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, wellness_steps, wellness_resting_hr,
                wellness_avg_stress, wellness_active_kcal, activity_count,
                activity_total_duration_min, activity_total_distance_km,
                activity_total_time_on_feet_min_est, activity_hard_session_count_est,
                sleep_total_sleep_min, sleep_time_in_bed_min, sleep_start_gmt,
                sleep_end_gmt, body_weight_kg_est_from_bmi, body_bmi,
                source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                has_garmin_data=1,
                wellness_steps=excluded.wellness_steps,
                wellness_resting_hr=excluded.wellness_resting_hr,
                wellness_avg_stress=excluded.wellness_avg_stress,
                wellness_active_kcal=excluded.wellness_active_kcal,
                activity_count=excluded.activity_count,
                activity_total_duration_min=excluded.activity_total_duration_min,
                activity_total_distance_km=excluded.activity_total_distance_km,
                activity_total_time_on_feet_min_est=excluded.activity_total_time_on_feet_min_est,
                activity_hard_session_count_est=excluded.activity_hard_session_count_est,
                sleep_total_sleep_min=excluded.sleep_total_sleep_min,
                sleep_time_in_bed_min=excluded.sleep_time_in_bed_min,
                sleep_start_gmt=excluded.sleep_start_gmt,
                sleep_end_gmt=excluded.sleep_end_gmt,
                body_weight_kg_est_from_bmi=excluded.body_weight_kg_est_from_bmi,
                body_bmi=excluded.body_bmi,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            passive_row,
        )
        conn.executemany(
            """
            INSERT INTO garmin_activity(
                activity_id, date, start_time_local_iso, name, activity_type, sport_type,
                duration_min, moving_duration_min, distance_km, time_on_feet_min_est,
                impact_load_est, hard_session_est, calories, avg_hr, max_hr,
                aerobic_training_effect, anaerobic_training_effect, source_file,
                quality_flag, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                date=excluded.date,
                start_time_local_iso=excluded.start_time_local_iso,
                name=excluded.name,
                activity_type=excluded.activity_type,
                sport_type=excluded.sport_type,
                duration_min=excluded.duration_min,
                moving_duration_min=excluded.moving_duration_min,
                distance_km=excluded.distance_km,
                time_on_feet_min_est=excluded.time_on_feet_min_est,
                impact_load_est=excluded.impact_load_est,
                hard_session_est=excluded.hard_session_est,
                calories=excluded.calories,
                avg_hr=excluded.avg_hr,
                max_hr=excluded.max_hr,
                aerobic_training_effect=excluded.aerobic_training_effect,
                anaerobic_training_effect=excluded.anaerobic_training_effect,
                source_file=excluded.source_file,
                quality_flag=excluded.quality_flag,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            activity_rows,
        )
    passive_action = (
        "created"
        if not existing_passive
        else "unchanged"
        if str(existing_passive.get("source_sha256") or "") == source_sha256
        else "updated"
    )
    activity_created = 0
    activity_updated = 0
    activity_unchanged = 0
    for row in activity_rows:
        activity_id = str(row[0])
        raw_json = str(row[-1] or "")
        if activity_id not in existing_activity_raw:
            activity_created += 1
        elif existing_activity_raw[activity_id] == raw_json:
            activity_unchanged += 1
        else:
            activity_updated += 1
    summary = summarize_day_bundle(bundle)
    return {
        "date": summary.get("date"),
        "passive_action": passive_action,
        "passive_created": 1 if passive_action == "created" else 0,
        "passive_updated": 1 if passive_action == "updated" else 0,
        "passive_unchanged": 1 if passive_action == "unchanged" else 0,
        "passive_upserted": 1,
        "activity_created": activity_created,
        "activity_updated": activity_updated,
        "activity_unchanged": activity_unchanged,
        "activity_upserted": len(activity_rows),
        "source_sha256": source_sha256,
        "summary": summary,
    }


def _batch_id(*, started_at: str, mode: str, end_date: str, days: int, stale_dates: list[str]) -> str:
    payload = {
        "started_at": started_at,
        "mode": mode,
        "end_date": end_date,
        "days": days,
        "stale_dates": stale_dates,
        "attempt_nonce": uuid.uuid4().hex,
    }
    return "glive_" + _sha256_json(payload)[:20]


def _endpoint_status(imported: list[Mapping[str, Any]]) -> dict[str, Any]:
    status: dict[str, Any] = {}
    for row in imported:
        date_text = str(row.get("date") or "")
        summary = row.get("summary") if isinstance(row.get("summary"), Mapping) else {}
        status[date_text] = {
            "successful_calls": list(summary.get("successful_calls") or []),
            "failed_calls": dict(summary.get("failed_calls") or {}),
            "skipped_calls": list(summary.get("skipped_calls") or []),
            "source_confidence": _source_confidence(summary),
        }
    return status


def _with_batch_audit(
    store: Any,
    result: dict[str, Any],
    *,
    started_at: str,
    completed_at: str,
    mode: str,
    requested_end_date: str,
) -> dict[str, Any]:
    imported = [row for row in result.get("imported", []) if isinstance(row, Mapping)]
    stale_dates = [str(value) for value in result.get("stale_dates", [])]
    requested_start_date = str(result.get("start_date") or "")
    source_hashes = [str(row.get("source_sha256")) for row in imported if row.get("source_sha256")]
    batch_id = _batch_id(
        started_at=started_at,
        mode=mode,
        end_date=requested_end_date,
        days=int(result.get("days_requested", 0) or 0),
        stale_dates=stale_dates or [str(row.get("date")) for row in imported if row.get("date")],
    )
    audited = {
        **result,
        "batch_id": batch_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "endpoint_status": _endpoint_status(imported),
        "source_hashes": source_hashes,
    }
    inserter = getattr(store, "insert_garmin_live_import_batch", None)
    if callable(inserter):
        inserter(
            {
                **audited,
                "mode": mode,
                "requested_start_date": requested_start_date,
                "requested_end_date": requested_end_date,
                "result": audited,
            }
        )
    return audited


def import_day_from_client(store: Any, client: Any, date_text: str) -> dict[str, Any]:
    return import_day_bundle(store, fetch_day_bundle(client, parse_date_text(date_text)))


def import_recent_days_from_client(store: Any, client: Any, *, end_date: str, days: int) -> dict[str, Any]:
    started_at = utc_now_precise_iso()
    bundles = fetch_days_bundle(client, end_date=end_date, days=days)
    imported = [import_day_bundle(store, bundle) for bundle in bundles]
    result = {
        "schema_version": LIVE_IMPORT_SCHEMA_VERSION,
        "ok": True,
        "skipped": False,
        "skipped_reason": "",
        "start_date": imported[0]["date"] if imported else None,
        "end_date": imported[-1]["date"] if imported else None,
        "days_requested": days,
        "days_imported": len(imported),
        "activity_upserted": sum(int(row["activity_upserted"]) for row in imported),
        "activity_created": sum(int(row["activity_created"]) for row in imported),
        "activity_updated": sum(int(row["activity_updated"]) for row in imported),
        "activity_unchanged": sum(int(row["activity_unchanged"]) for row in imported),
        "passive_upserted": sum(int(row["passive_upserted"]) for row in imported),
        "passive_created": sum(int(row["passive_created"]) for row in imported),
        "passive_updated": sum(int(row["passive_updated"]) for row in imported),
        "passive_unchanged": sum(int(row["passive_unchanged"]) for row in imported),
        "imported": imported,
        "stale_dates": [str(row["date"]) for row in imported if row.get("date")],
    }
    return _with_batch_audit(
        store,
        result,
        started_at=started_at,
        completed_at=utc_now_precise_iso(),
        mode="manual",
        requested_end_date=parse_date_text(end_date),
    )


def _empty_import_result(*, end_date: str, days: int, skipped_reason: str) -> dict[str, Any]:
    dates = date_range_texts(end_date=end_date, days=days)
    return {
        "schema_version": LIVE_IMPORT_SCHEMA_VERSION,
        "ok": True,
        "skipped": True,
        "skipped_reason": skipped_reason,
        "start_date": dates[0] if dates else None,
        "end_date": dates[-1] if dates else None,
        "days_requested": days,
        "days_imported": 0,
        "activity_upserted": 0,
        "activity_created": 0,
        "activity_updated": 0,
        "activity_unchanged": 0,
        "passive_upserted": 0,
        "passive_created": 0,
        "passive_updated": 0,
        "passive_unchanged": 0,
        "imported": [],
        "stale_dates": [],
    }


def import_recent_days_if_stale(
    store: Any,
    *,
    end_date: str,
    days: int,
    tokenstore: str = DEFAULT_TOKENSTORE,
    max_age_minutes: int = 180,
) -> dict[str, Any]:
    started_at = utc_now_precise_iso()
    parsed_end = parse_date_text(end_date)
    stale_dates = dates_needing_import(store, end_date=parsed_end, days=days, max_age_minutes=max_age_minutes)
    if not stale_dates:
        return _with_batch_audit(
            store,
            _empty_import_result(end_date=parsed_end, days=days, skipped_reason="fresh"),
            started_at=started_at,
            completed_at=utc_now_precise_iso(),
            mode="auto",
            requested_end_date=parsed_end,
        )
    if not Path(tokenstore).expanduser().exists():
        result = _empty_import_result(end_date=parsed_end, days=days, skipped_reason="missing_tokenstore")
        result["stale_dates"] = stale_dates
        return _with_batch_audit(
            store,
            result,
            started_at=started_at,
            completed_at=utc_now_precise_iso(),
            mode="auto",
            requested_end_date=parsed_end,
        )

    config = ProbeConfig(
        date=parsed_end,
        email=None,
        password=None,
        tokenstore=tokenstore,
        output_dir=Path(os.getcwd()) / DEFAULT_OUTPUT_REL,
        write_raw=False,
    )
    client = login_client(config)
    imported = [import_day_bundle(store, fetch_day_bundle(client, date_text)) for date_text in stale_dates]
    result = {
        "schema_version": LIVE_IMPORT_SCHEMA_VERSION,
        "ok": True,
        "skipped": False,
        "skipped_reason": "",
        "start_date": stale_dates[0] if stale_dates else parsed_end,
        "end_date": stale_dates[-1] if stale_dates else parsed_end,
        "days_requested": days,
        "days_imported": len(imported),
        "activity_upserted": sum(int(row["activity_upserted"]) for row in imported),
        "activity_created": sum(int(row["activity_created"]) for row in imported),
        "activity_updated": sum(int(row["activity_updated"]) for row in imported),
        "activity_unchanged": sum(int(row["activity_unchanged"]) for row in imported),
        "passive_upserted": sum(int(row["passive_upserted"]) for row in imported),
        "passive_created": sum(int(row["passive_created"]) for row in imported),
        "passive_updated": sum(int(row["passive_updated"]) for row in imported),
        "passive_unchanged": sum(int(row["passive_unchanged"]) for row in imported),
        "imported": imported,
        "stale_dates": stale_dates,
    }
    return _with_batch_audit(
        store,
        result,
        started_at=started_at,
        completed_at=utc_now_precise_iso(),
        mode="auto",
        requested_end_date=parsed_end,
    )


def import_recent_days(store: Any, *, end_date: str, days: int, tokenstore: str = DEFAULT_TOKENSTORE) -> dict[str, Any]:
    config = ProbeConfig(
        date=parse_date_text(end_date),
        email=None,
        password=None,
        tokenstore=tokenstore,
        output_dir=Path(os.getcwd()) / DEFAULT_OUTPUT_REL,
        write_raw=False,
    )
    client = login_client(config)
    return import_recent_days_from_client(store, client, end_date=config.date, days=days)


def write_probe_artifact(output_dir: Path, date_text: str, artifact: Mapping[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    output_path = output_dir / f"{date_text}.json"
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    output_path.chmod(0o600)
    return output_path


def harden_private_path(path: Path) -> None:
    """Best-effort permissions hardening for local token/raw health data files."""

    if not path.exists():
        return
    if path.is_file():
        path.chmod(0o600)
        return
    path.chmod(0o700)
    for child in path.rglob("*"):
        if child.is_dir():
            child.chmod(0o700)
        elif child.is_file():
            child.chmod(0o600)


def run_probe(config: ProbeConfig, client_factory: Callable[[ProbeConfig], Any] = login_client) -> dict[str, Any]:
    client = client_factory(config)
    raw_bundle = fetch_day_bundle(client, config.date)
    summary = summarize_day_bundle(raw_bundle)
    artifact = {
        "summary": summary,
        "raw_bundle": raw_bundle if config.write_raw else None,
    }
    output_path = write_probe_artifact(config.output_dir, config.date, artifact) if config.write_raw else None
    return {"summary": summary, "output_path": str(output_path) if output_path else None}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Garmin Connect daily data without importing it into Life Load.")
    parser.add_argument("--date", default=None, help="Date to fetch as YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--email", default=os.getenv("GARMIN_EMAIL") or os.getenv("EMAIL"))
    parser.add_argument("--password", default=os.getenv("GARMIN_PASSWORD") or os.getenv("PASSWORD"))
    parser.add_argument("--tokenstore", default=os.getenv("GARMINTOKENS") or DEFAULT_TOKENSTORE)
    parser.add_argument("--output-dir", type=Path, default=Path(os.getcwd()) / DEFAULT_OUTPUT_REL)
    parser.add_argument("--summary-only", action="store_true", help="Do not write the raw endpoint bundle to disk.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = ProbeConfig(
        date=parse_date_text(args.date),
        email=args.email,
        password=args.password,
        tokenstore=args.tokenstore,
        output_dir=args.output_dir,
        write_raw=not args.summary_only,
    )
    result = run_probe(config)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
