"""Rolling feature derivation and trend exports for health observability."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from life_load.sqlite_core import HealthObservabilityStore, utc_now_iso

DATE_FMT = "%Y-%m-%d"
RULES_VERSION = "trend_features_v0_3"


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(str(value), DATE_FMT).date()


def _iso_date(value: dt.date) -> str:
    return value.strftime(DATE_FMT)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _days_ago(row: Mapping[str, Any], target_date: dt.date) -> int:
    return (target_date - _parse_date(str(row["date"]))).days


def _recency_weight(days_ago: int) -> float:
    weights = {
        0: 1.00,
        1: 0.85,
        2: 0.70,
        3: 0.55,
        4: 0.40,
        5: 0.28,
        6: 0.18,
    }
    return weights.get(days_ago, 0.0)


def _signal_recency_features(rows: List[Mapping[str, Any]], target_date: dt.date, field_name: str) -> Dict[str, Any]:
    matching: List[int] = []
    for row in rows:
        if _safe_bool(row.get(field_name)):
            days_ago = _days_ago(row, target_date)
            if 0 <= days_ago <= 6:
                matching.append(days_ago)

    count_7d = len(matching)
    weighted_count_7d = round(sum(_recency_weight(days) for days in matching), 2)
    recent_count_3d = sum(1 for days in matching if days <= 2)
    older_count_4_to_7d = sum(1 for days in matching if days >= 3)
    most_recent_days_ago = min(matching) if matching else -1
    if recent_count_3d == 0 and older_count_4_to_7d > 0:
        trend = "fading"
    elif recent_count_3d > 0 and older_count_4_to_7d > 0:
        trend = "persistent"
    elif recent_count_3d > 0:
        trend = "recent"
    else:
        trend = "none"

    return {
        f"{field_name}_count_7d": count_7d,
        f"{field_name}_weighted_7d": weighted_count_7d,
        f"{field_name}_recent_count_3d": recent_count_3d,
        f"{field_name}_older_count_4_to_7d": older_count_4_to_7d,
        f"{field_name}_most_recent_days_ago": most_recent_days_ago,
        f"{field_name}_trend": trend,
    }


def _mean(values: Iterable[float]) -> float:
    seq = [float(item) for item in values]
    return round(sum(seq) / len(seq), 2) if seq else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _window_rows(rows: List[Mapping[str, Any]], *, end_date: dt.date, days: int) -> List[Mapping[str, Any]]:
    start_date = end_date - dt.timedelta(days=days - 1)
    return [row for row in rows if start_date <= _parse_date(str(row["date"])) <= end_date]


def _approved_daily_rows(store: HealthObservabilityStore) -> List[Dict[str, Any]]:
    return store.fetch_all(
        """
        SELECT d.date, d.sleep_ok, d.nutrition_ok, d.alcohol, d.binge, d.mood, d.stress, d.energy,
               d.foot_pain, d.shoulder_pain, d.migraine_warning, d.decompression_done, d.shutdown_done,
               d.phone_after_21, d.project_overrun, d.work_intensity, d.family_stress, d.home_office, d.alone_home,
               d.homework_done, s.life_load_score, s.training_load, s.recovery_score, s.strain_score, s.red_flags, s.zone
        FROM daily_log d
        LEFT JOIN derived_daily_summary s ON s.date = d.date
        WHERE d.user_approved_at IS NOT NULL AND TRIM(d.user_approved_at) != ''
          AND (
            TRIM(COALESCE(d.diary_text, '')) != ''
            OR TRIM(COALESCE(d.diary_summary, '')) != ''
            OR TRIM(COALESCE(d.tags, '')) NOT IN ('', '[]')
            OR TRIM(COALESCE(d.activity_types, '')) NOT IN ('', '[]')
            OR TRIM(COALESCE(d.primary_activity_type, '')) != ''
            OR d.sleep_ok IS NOT NULL
            OR d.nutrition_ok IS NOT NULL
            OR COALESCE(d.alcohol, 0) != 0
            OR COALESCE(d.binge, 0) = 1
            OR d.mood IS NOT NULL
            OR d.stress IS NOT NULL
            OR d.energy IS NOT NULL
            OR d.coffee_cups IS NOT NULL
            OR d.foot_pain IS NOT NULL
            OR d.shoulder_pain IS NOT NULL
            OR COALESCE(d.migraine_warning, 0) = 1
            OR d.decompression_done IS NOT NULL
            OR d.shutdown_done IS NOT NULL
            OR d.phone_after_21 IS NOT NULL
            OR d.project_overrun IS NOT NULL
            OR d.activity_duration_min IS NOT NULL
            OR d.rehab_done IS NOT NULL
            OR TRIM(COALESCE(d.other_symptoms, '')) != ''
            OR d.family_stress IS NOT NULL
            OR d.home_office IS NOT NULL
            OR d.alone_home IS NOT NULL
            OR d.homework_done IS NOT NULL
            OR d.after_work_decompression_done IS NOT NULL
            OR d.evening_chain_broken IS NOT NULL
            OR d.wife_conflict_count IS NOT NULL
            OR d.wife_conflict_school IS NOT NULL
            OR d.wife_conflict_chores IS NOT NULL
            OR d.wife_conflict_other IS NOT NULL
            OR EXISTS (SELECT 1 FROM activity_log a WHERE a.date = d.date)
            OR EXISTS (SELECT 1 FROM garmin_activity ga WHERE ga.date = d.date)
            OR EXISTS (SELECT 1 FROM garmin_daily_passive_summary gp WHERE gp.date = d.date)
          )
        ORDER BY d.date ASC
        """
    )


def _garmin_weight_rows(store: HealthObservabilityStore) -> List[Dict[str, Any]]:
    rows = store.fetch_all(
        """
        SELECT date, body_weight_kg_est_from_bmi AS weight_kg, 'daily_passive' AS source
        FROM garmin_daily_passive_summary
        WHERE date != '' AND body_weight_kg_est_from_bmi IS NOT NULL
        UNION ALL
        SELECT date, weight_kg_est_from_bmi AS weight_kg, 'body_measurement' AS source
        FROM garmin_body_measurement
        WHERE date != '' AND weight_kg_est_from_bmi IS NOT NULL
        ORDER BY date ASC
        """
    )
    by_date: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        date_text = str(row.get("date") or "")
        weight = float(row.get("weight_kg") or 0.0)
        if not date_text or weight <= 0:
            continue
        # Prefer the daily passive joined row when both sources exist.
        if date_text not in by_date or row.get("source") == "daily_passive":
            by_date[date_text] = {"date": date_text, "weight_kg": round(weight, 2)}
    return [by_date[key] for key in sorted(by_date)]


def _latest_weight_at_or_before(weight_rows: List[Mapping[str, Any]], target_date: dt.date) -> Dict[str, Any] | None:
    latest: Dict[str, Any] | None = None
    for row in weight_rows:
        row_date = _parse_date(str(row["date"]))
        weight = float(row.get("weight_kg") or 0.0)
        if row_date <= target_date and weight > 0:
            latest = {"date": row_date, "weight_kg": weight}
        else:
            break
    return latest


def _weight_change(weight_rows: List[Mapping[str, Any]], *, target_date: dt.date, days: int) -> Dict[str, Any]:
    latest = _latest_weight_at_or_before(weight_rows, target_date)
    latest_stale = latest is None or (target_date - latest["date"]).days > 14
    baseline = _latest_weight_at_or_before(weight_rows, target_date - dt.timedelta(days=days))
    baseline_date: dt.date | None = baseline["date"] if baseline is not None else None
    if baseline is None:
        window_start = target_date - dt.timedelta(days=days)
        for row in weight_rows:
            row_date = _parse_date(str(row["date"]))
            if window_start <= row_date < target_date:
                candidate = float(row.get("weight_kg") or 0.0)
                if candidate > 0:
                    baseline = {"date": row_date, "weight_kg": candidate}
                    baseline_date = row_date
                    break
    enough_span = bool(latest and baseline_date and (latest["date"] - baseline_date).days >= min(7, days))
    usable = bool(latest and baseline and not latest_stale and enough_span)
    change = round(float(latest["weight_kg"]) - float(baseline["weight_kg"]), 2) if usable else 0.0
    return {
        "change": change,
        "usable": usable,
        "latest_days_old": (target_date - latest["date"]).days if latest else None,
        "baseline_days_old": (target_date - baseline_date).days if baseline_date else None,
    }


def _daily_capacity(row: Mapping[str, Any]) -> float:
    recovery = float(row.get("recovery_score") or 0.0)
    sleep = 1.5 if row.get("sleep_ok") == 1 else 0.0
    nutrition = 1.5 if row.get("nutrition_ok") == 1 else 0.0
    shutdown = 1.0 if _safe_bool(row.get("shutdown_done")) else 0.0
    decompression = 0.75 if _safe_bool(row.get("decompression_done")) else 0.0
    energy = (float(row.get("energy") or 0.0) * 0.2) if row.get("energy") is not None else 0.0
    mood = (float(row.get("mood") or 0.0) * 0.15) if row.get("mood") is not None else 0.0
    pain = max(float(row.get("foot_pain") or 0.0), float(row.get("shoulder_pain") or 0.0))
    stress = float(row.get("stress") or 0.0)
    red_flag_count = _red_flag_count(row)
    penalty = pain * 0.45 + stress * 0.22 + red_flag_count * 1.5
    return round(_clamp(recovery + sleep + nutrition + shutdown + decompression + energy + mood - penalty, 0.0, 20.0), 2)


def _red_flag_count(row: Mapping[str, Any]) -> int:
    raw = str(row.get("red_flags") or "[]")
    if not raw.startswith("["):
        return 0
    try:
        loaded = json.loads(raw)
    except Exception:
        return 0
    return len(loaded) if isinstance(loaded, list) else 0


def _risk_mode(score: float, margin: float) -> str:
    if score >= 75 or margin <= -8:
        return "stabilize"
    if score >= 50 or margin <= -4:
        return "hold"
    if score >= 25 or margin <= 0:
        return "caution"
    return "normal"


def _feature_row(rows: List[Mapping[str, Any]], *, target_date: dt.date, weight_rows: List[Mapping[str, Any]] | None = None) -> Dict[str, Any]:
    rows_7 = _window_rows(rows, end_date=target_date, days=7)
    rows_14 = _window_rows(rows, end_date=target_date, days=14)
    rows_30 = _window_rows(rows, end_date=target_date, days=30)
    rows_42 = _window_rows(rows, end_date=target_date, days=42)
    acute_life_load_7d = _mean((float(row.get("life_load_score") or 0) for row in rows_7))
    acute_strain_7d = _mean((float(row.get("strain_score") or 0) for row in rows_7))
    acute_training_load_7d = _mean((float(row.get("training_load") or 0) for row in rows_7))
    chronic_life_load_42d = _mean((float(row.get("life_load_score") or 0) for row in rows_42))
    chronic_training_load_42d = _mean((float(row.get("training_load") or 0) for row in rows_42))
    chronic_capacity_42d = _mean((_daily_capacity(row) for row in rows_42))
    life_margin_7d = round(chronic_capacity_42d - acute_life_load_7d, 2)
    training_margin_7d = round(chronic_training_load_42d - acute_training_load_7d, 2)
    weight_history = list(weight_rows or [])
    latest_weight_row = _latest_weight_at_or_before(weight_history, target_date)
    latest_weight = float(latest_weight_row["weight_kg"]) if latest_weight_row else None
    latest_weight_days_old = (target_date - latest_weight_row["date"]).days if latest_weight_row else None
    weight_7 = _weight_change(weight_history, target_date=target_date, days=7)
    weight_14 = _weight_change(weight_history, target_date=target_date, days=14)
    weight_30 = _weight_change(weight_history, target_date=target_date, days=30)
    weight_change_7d = float(weight_7["change"])
    weight_change_14d = float(weight_14["change"])
    weight_change_30d = float(weight_30["change"])
    red_flags_7d = sum(_red_flag_count(row) for row in rows_7)
    project_features = _signal_recency_features(rows_7, target_date, "project_overrun")
    phone_features = _signal_recency_features(rows_7, target_date, "phone_after_21")
    binge_features = _signal_recency_features(rows_7, target_date, "binge")
    project_signal_score = float(project_features["project_overrun_weighted_7d"]) * 4.0
    if project_features["project_overrun_recent_count_3d"] == 0 and project_features["project_overrun_older_count_4_to_7d"] > 0:
        project_signal_score *= 0.65
    phone_signal_score = float(phone_features["phone_after_21_weighted_7d"]) * 3.0
    if phone_features["phone_after_21_recent_count_3d"] == 0 and phone_features["phone_after_21_older_count_4_to_7d"] > 0:
        phone_signal_score *= 0.65
    weight_reset_pressure = max(
        weight_change_7d if weight_7["usable"] else 0.0,
        weight_change_14d if weight_14["usable"] else 0.0,
        weight_change_30d if weight_30["usable"] else 0.0,
    )
    drift_risk_score = round(
        _clamp(
            50.0
            + max(0.0, -life_margin_7d) * 4.0
            + max(0.0, acute_life_load_7d - chronic_life_load_42d) * 2.0
            + max(0.0, acute_strain_7d - 5.0) * 2.0
            + red_flags_7d * 6.0
            + project_signal_score
            + phone_signal_score
            + max(0.0, weight_reset_pressure - 0.75) * 8.0
            - max(0.0, life_margin_7d) * 2.5,
            0.0,
            100.0,
        ),
        1,
    )
    features = {
        "sleep_compliance_7d": round(sum(1 for row in rows_7 if row.get("sleep_ok") == 1) / len(rows_7), 2) if rows_7 else 0.0,
        "sleep_compliance_14d": round(sum(1 for row in rows_14 if row.get("sleep_ok") == 1) / len(rows_14), 2) if rows_14 else 0.0,
        "nutrition_compliance_7d": round(sum(1 for row in rows_7 if row.get("nutrition_ok") == 1) / len(rows_7), 2) if rows_7 else 0.0,
        "nutrition_compliance_14d": round(sum(1 for row in rows_14 if row.get("nutrition_ok") == 1) / len(rows_14), 2) if rows_14 else 0.0,
        **project_features,
        **phone_features,
        "alone_home_count_7d": sum(1 for row in rows_7 if _safe_bool(row.get("alone_home"))),
        "pain_avg_7d": _mean((max(float(row.get("foot_pain") or 0), float(row.get("shoulder_pain") or 0)) for row in rows_7)),
        "foot_pain_avg_7d": _mean((float(row.get("foot_pain") or 0) for row in rows_7)),
        "shoulder_pain_avg_7d": _mean((float(row.get("shoulder_pain") or 0) for row in rows_7)),
        "mood_avg_7d": _mean((float(row.get("mood") or 0) for row in rows_7 if row.get("mood") is not None)),
        "stress_avg_7d": _mean((float(row.get("stress") or 0) for row in rows_7 if row.get("stress") is not None)),
        "energy_avg_7d": _mean((float(row.get("energy") or 0) for row in rows_7 if row.get("energy") is not None)),
        "binge_count_30d": sum(1 for row in rows_30 if _safe_bool(row.get("binge"))),
        **binge_features,
        "alcohol_home_count_30d": sum(1 for row in rows_30 if int(row.get("alcohol") or 0) == 1),
        "recovery_compliance_7d": round(sum(1 for row in rows_7 if _safe_bool(row.get("shutdown_done")) and _safe_bool(row.get("decompression_done"))) / len(rows_7), 2) if rows_7 else 0.0,
        "life_load_rolling_avg_7d": acute_life_load_7d,
        "red_flag_count_7d": red_flags_7d,
        "acute_load_7d": acute_life_load_7d,
        "acute_strain_7d": acute_strain_7d,
        "acute_training_load_7d": acute_training_load_7d,
        "chronic_life_load_42d": chronic_life_load_42d,
        "chronic_training_load_42d": chronic_training_load_42d,
        "chronic_capacity_42d": chronic_capacity_42d,
        "life_margin_7d": life_margin_7d,
        "training_margin_7d": training_margin_7d,
        "weight_kg_latest": round(latest_weight, 2) if latest_weight is not None else 0.0,
        "weight_latest_days_old": latest_weight_days_old if latest_weight_days_old is not None else -1,
        "weight_change_7d": weight_change_7d,
        "weight_change_14d": weight_change_14d,
        "weight_change_30d": weight_change_30d,
        "weight_change_7d_usable": bool(weight_7["usable"]),
        "weight_change_14d_usable": bool(weight_14["usable"]),
        "weight_change_30d_usable": bool(weight_30["usable"]),
        "drift_risk_score": drift_risk_score,
        "recommended_mode": _risk_mode(drift_risk_score, life_margin_7d),
        "missed_review_count_30d": 0,
        "days_in_window_7d": len(rows_7),
        "days_in_window_14d": len(rows_14),
        "days_in_window_30d": len(rows_30),
        "days_in_window_42d": len(rows_42),
    }
    return features


def rebuild_trend_features(store: HealthObservabilityStore) -> List[Dict[str, Any]]:
    rows = _approved_daily_rows(store)
    weight_rows = _garmin_weight_rows(store)
    derived: List[Dict[str, Any]] = []
    for row in rows:
        target_date = _parse_date(str(row["date"]))
        features = _feature_row(rows, target_date=target_date, weight_rows=weight_rows)
        payload = {
            "date": str(row["date"]),
            "features_json": features,
            "rules_version": RULES_VERSION,
            "calculated_at": utc_now_iso(),
        }
        store.upsert_derived_trend_feature(payload)
        derived.append({"date": str(row["date"]), **features})
    export_rows = [
        {"date": row["date"], **row["features_json"]}
        for row in (
            store.fetch_derived_trend_feature(item["date"]) or {}
            for item in derived
        )
        if row
    ]
    _write_trend_csv(store.root / "generated" / "exports" / "derived_trend_features.csv", export_rows)
    return derived


def _write_trend_csv(path: Path, rows: List[Mapping[str, Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["date"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def trend_payload(store: HealthObservabilityStore, *, date_value: str | None = None, days: int = 90) -> Dict[str, Any]:
    approved_rows = _approved_daily_rows(store)
    if approved_rows and date_value:
        target_date = _parse_date(date_value)
    elif approved_rows:
        target_date = _parse_date(str(approved_rows[-1]["date"]))
    else:
        target_date = dt.date.today()
    capped_days = max(7, min(int(days), 365))
    start_date = target_date - dt.timedelta(days=capped_days - 1)
    trend_rows = store.fetch_all(
        "SELECT date, features_json, rules_version, calculated_at FROM derived_trend_feature WHERE date >= ? AND date <= ? ORDER BY date ASC",
        (_iso_date(start_date), _iso_date(target_date)),
    )
    parsed_rows: List[Dict[str, Any]] = []
    for row in trend_rows:
        features = {}
        raw = row.get("features_json")
        if isinstance(raw, str) and raw.strip():
            try:
                features = json.loads(raw)
            except Exception:
                features = {}
        parsed_rows.append(
            {
                "date": str(row.get("date") or ""),
                "features": features,
                "rules_version": str(row.get("rules_version") or ""),
                "calculated_at": str(row.get("calculated_at") or ""),
            }
        )
    return {
        "schema_version": "life_load_trends_v1",
        "date": _iso_date(target_date),
        "days": capped_days,
        "rows": parsed_rows,
        "export_path": str((store.root / "generated" / "exports" / "derived_trend_features.csv").resolve()),
    }
