"""Rule-based drift detection over derived trend features."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from life_load.sqlite_core import HealthObservabilityStore, utc_now_iso

RULES_VERSION = "drift_detector_v0_2"


def _latest_feature_rows(store: HealthObservabilityStore) -> List[Dict[str, Any]]:
    rows = store.fetch_all("SELECT date FROM derived_trend_feature ORDER BY date ASC")
    output: List[Dict[str, Any]] = []
    for row in rows:
        loaded = store.fetch_derived_trend_feature(str(row["date"]))
        if loaded:
            output.append(loaded)
    return output


def _float_feature(features: Mapping[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(features.get(name) if features.get(name) is not None else default)
    except (TypeError, ValueError):
        return default


def _int_feature(features: Mapping[str, Any], name: str, default: int = 0) -> int:
    try:
        return int(features.get(name) if features.get(name) is not None else default)
    except (TypeError, ValueError):
        return default


def _classify(features: Mapping[str, Any]) -> Dict[str, Any]:
    signals: List[str] = []
    severity = 0
    sleep_7 = _float_feature(features, "sleep_compliance_7d")
    nutrition_7 = _float_feature(features, "nutrition_compliance_7d")
    project_count = _int_feature(features, "project_overrun_count_7d")
    project_weighted = _float_feature(features, "project_overrun_weighted_7d", float(project_count))
    project_recent = _int_feature(features, "project_overrun_recent_count_3d", project_count)
    project_older = _int_feature(features, "project_overrun_older_count_4_to_7d")
    late_phone_count = _int_feature(features, "phone_after_21_count_7d")
    late_phone_weighted = _float_feature(features, "phone_after_21_weighted_7d", float(late_phone_count))
    late_phone_recent = _int_feature(features, "phone_after_21_recent_count_3d", late_phone_count)
    late_phone_older = _int_feature(features, "phone_after_21_older_count_4_to_7d")
    pain_7 = _float_feature(features, "pain_avg_7d")
    stress_7 = _float_feature(features, "stress_avg_7d")
    energy_7 = _float_feature(features, "energy_avg_7d")
    binge_30 = _int_feature(features, "binge_count_30d")
    alcohol_30 = _int_feature(features, "alcohol_home_count_30d")
    recovery_7 = _float_feature(features, "recovery_compliance_7d")
    life_load_7 = _float_feature(features, "life_load_rolling_avg_7d")
    red_flags_7 = _int_feature(features, "red_flag_count_7d")
    drift_risk_score = _float_feature(features, "drift_risk_score")
    life_margin = _float_feature(features, "life_margin_7d")
    recommended_mode = str(features.get("recommended_mode") or "")
    weight_change_7d = float(features.get("weight_change_7d") or 0.0) if features.get("weight_change_7d_usable") is True else 0.0
    weight_change_14d = float(features.get("weight_change_14d") or 0.0) if features.get("weight_change_14d_usable") is True else 0.0
    weight_change_30d = float(features.get("weight_change_30d") or 0.0) if features.get("weight_change_30d_usable") is True else 0.0
    weight_pressure = max(weight_change_7d, weight_change_14d, weight_change_30d)

    if sleep_7 and sleep_7 < 0.5:
        severity += 2
        signals.append("sleep compliance falling")
    if nutrition_7 and nutrition_7 < 0.5:
        severity += 2
        signals.append("nutrition support pattern")
    project_active = project_recent >= 1 or project_weighted >= 1.35
    project_fading = project_recent == 0 and project_older > 0
    late_phone_active = late_phone_recent >= 1 or late_phone_weighted >= 1.15
    late_phone_fading = late_phone_recent == 0 and late_phone_older > 0

    if project_active:
        severity += 2
        signals.append("project spillover active")
    elif project_fading:
        severity += 1
        signals.append("project spillover fading")
    if late_phone_active:
        severity += 1
        signals.append("late phone active")
    elif late_phone_fading and severity > 0:
        signals.append("late phone fading")
    if pain_7 >= 5:
        severity += 2
        signals.append("pain trend elevated")
    if stress_7 >= 7:
        severity += 2
        signals.append("stress elevated")
    if 0 < energy_7 <= 4:
        severity += 1
        signals.append("energy suppressed")
    if binge_30 >= 1:
        severity += 2
        signals.append("recent eating episode")
    if alcohol_30 >= 1 and (sleep_7 < 0.5 or recovery_7 < 0.4 or binge_30 >= 1 or red_flags_7 > 0):
        severity += 1
        signals.append("alcohol recovery context")
    if recovery_7 and recovery_7 < 0.4:
        severity += 2
        signals.append("recovery compliance falling")
    if life_load_7 >= 14:
        severity += 2
        signals.append("life load rising")
    if red_flags_7 >= 2:
        severity += 1
        signals.append("support signals stacking")
    if life_margin <= -8:
        severity += 3
        signals.append("negative life margin")
    elif life_margin <= -4:
        severity += 2
        signals.append("life margin narrowing")
    if drift_risk_score >= 75:
        severity += 3
        signals.append("historical risk score high")
    elif drift_risk_score >= 50:
        severity += 2
        signals.append("historical risk score elevated")
    if weight_pressure >= 2.0:
        severity += 3
        signals.append("weight reset signal")
    elif weight_pressure >= 1.0:
        severity += 2
        signals.append("weight trend rising")

    if severity >= 12 or recommended_mode == "stabilize" or drift_risk_score >= 75:
        risk_level = "red"
        mode = "stabilize"
        next_action = "Use a stabilization block: protect sleep, reduce optional load, and keep the next three days simple."
    elif severity >= 5 or recommended_mode == "hold":
        risk_level = "orange"
        mode = "hold"
        next_action = (
            "Run a three-day reset: clean food, no alcohol at home, protect sleep, and pause optional progression."
            if weight_pressure >= 1.0
            else "Pause progression and protect evening recovery for the next three days."
        )
    elif severity >= 2 or recommended_mode == "caution":
        risk_level = "yellow"
        mode = "caution"
        next_action = (
            "Treat the weight uptick as an early signal: clean meals, no snacks, and shutdown protected for 48 hours."
            if weight_pressure >= 1.0
            else "Protect shutdown and recovery before adding more load."
        )
    else:
        risk_level = "green"
        mode = "normal"
        next_action = "Continue the baseline."

    evidence_note = "No strong drift pattern detected." if not signals else f"Signals noticed: {', '.join(signals[:4])}."
    return {
        "risk_level": risk_level,
        "mode": mode,
        "contributing_signals": signals,
        "next_action": next_action,
        "evidence_note": evidence_note,
        "rules_version": RULES_VERSION,
    }


def rebuild_drift_snapshots(store: HealthObservabilityStore) -> List[Dict[str, Any]]:
    rows = _latest_feature_rows(store)
    built: List[Dict[str, Any]] = []
    for row in rows:
        features = dict(row.get("features_json") or {})
        classified = _classify(features)
        payload = {
            "date": str(row["date"]),
            "risk_level": classified["risk_level"],
            "mode": classified["mode"],
            "contributing_signals": classified["contributing_signals"],
            "next_action": classified["next_action"],
            "evidence_note": classified["evidence_note"],
            "rules_version": RULES_VERSION,
            "calculated_at": utc_now_iso(),
        }
        store.upsert_drift_detection_snapshot(payload)
        built.append({"date": str(row["date"]), **classified})
    return built


def drift_payload(store: HealthObservabilityStore, *, date_value: str | None = None) -> Dict[str, Any]:
    if date_value:
        snapshot = store.fetch_drift_detection_snapshot(date_value)
        if snapshot is None:
            row = store.fetch_one(
                "SELECT date FROM drift_detection_snapshot WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (date_value,),
            )
            snapshot = store.fetch_drift_detection_snapshot(str(row["date"])) if row else None
    else:
        rows = store.fetch_all("SELECT date FROM drift_detection_snapshot ORDER BY date DESC LIMIT 1")
        snapshot = store.fetch_drift_detection_snapshot(str(rows[0]["date"])) if rows else None
    return {
        "schema_version": "life_load_drift_v1",
        "snapshot": snapshot,
    }
