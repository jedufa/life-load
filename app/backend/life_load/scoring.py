"""Pure Life Load scoring engine.

This module intentionally has no SQLite, web route, Android, or browser
knowledge. Callers provide a normalized daily entry, activity rows, optional
Garmin passive context, and prior training loads; the engine returns score
numbers, warnings, zone, and next action.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Sequence, Set

SCORING_CONTRACT_VERSION = "life_load_scoring_contract_v1"
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

SCORING_INPUT_KEYS = ("entry", "activity_rows", "garmin_passive", "prior_training_loads")

SCORING_OUTPUT_KEYS = (
    "date",
    "life_load_score",
    "training_load",
    "recovery_score",
    "strain_score",
    "red_flags",
    "warnings",
    "unknown_fields",
    "zone",
    "next_action",
    "hard_sessions",
    "rehab_sessions",
    "acute_training_load",
    "chronic_training_load",
    "training_load_ratio",
    "training_ramp",
)

SCORING_CONTRACT = {
    "version": SCORING_CONTRACT_VERSION,
    "input_keys": SCORING_INPUT_KEYS,
    "output_keys": SCORING_OUTPUT_KEYS,
    "notes": (
        "Pure deterministic scoring contract. Implementations must not read a database, "
        "HTTP state, Android state, wall-clock time, or developer-server state."
    ),
}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def as_optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def clamp_int(value: Any, *, minimum: int = 0, maximum: int = 10, default: int | None = None) -> int | None:
    parsed = as_optional_int(value)
    if parsed is None:
        return default
    return max(minimum, min(maximum, parsed))


def normalize_activity_type(value: Any) -> str:
    activity_type = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "running": "run",
        "street_running": "run",
        "trail_running": "run",
        "treadmill_running": "run",
        "cycling": "bike",
        "commute": "bike_commute",
        "bike_commute": "bike_commute",
        "commute_bike": "bike_commute",
        "bike_to_work": "bike_commute",
        "road_biking": "bike",
        "mountain_biking": "bike",
        "indoor_cycling": "bike",
        "walking": "walk",
        "hiking": "hike",
        "strength_training": "strength",
        "lap_swimming": "swim",
        "open_water_swimming": "swim",
        "swimming": "swim",
        "breathwork": "meditation",
        "physio": "rehab",
        "mobility": "rehab",
    }
    return aliases.get(activity_type, activity_type)


def duration_minutes(row: Mapping[str, Any]) -> float:
    for key in ("duration_min", "moving_duration_min", "time_on_feet_min_est"):
        value = row.get(key)
        if value is None or str(value).strip() == "":
            continue
        try:
            minutes = float(value)
        except Exception:
            continue
        if minutes > 0:
            return min(minutes, 360.0)
    return 0.0


def activity_training_points(row: Mapping[str, Any]) -> float:
    activity_type = normalize_activity_type(row.get("activity_type"))
    intensity = str(row.get("intensity") or "").strip().lower()
    duration = duration_minutes(row)
    per_30_min = {
        "run": 2.0,
        "crossfit": 2.4,
        "strength": 1.6,
        "bike": 1.1,
        "bike_commute": 0.55,
        "swim": 1.2,
        "hike": 0.9,
        "walk": 0.35,
        "rehab": 0.25,
        "meditation": 0.0,
    }.get(activity_type)
    fallback = {
        "run": 2.0,
        "crossfit": 2.5,
        "strength": 1.5,
        "bike": 1.1,
        "bike_commute": 0.8,
        "swim": 1.2,
        "hike": 1.0,
        "walk": 0.5,
        "rehab": 0.3,
        "meditation": 0.0,
    }.get(activity_type)
    if per_30_min is None:
        if intensity in {"hard", "heavy"}:
            per_30_min, fallback = 1.6, 2.0
        elif intensity == "moderate":
            per_30_min, fallback = 1.0, 1.0
        elif intensity == "light":
            per_30_min, fallback = 0.4, 0.5
        else:
            return 0.0
    if not duration:
        return float(fallback if fallback is not None else per_30_min)
    intensity_multiplier = 1.25 if intensity in {"hard", "heavy"} else 1.0 if intensity == "moderate" else 0.8 if intensity == "light" else 1.0
    cap = (
        8.0
        if activity_type in {"run", "crossfit"}
        else 6.0
        if activity_type in {"bike", "strength", "swim", "hike"}
        else 4.0
        if activity_type == "bike_commute"
        else 3.0
    )
    return round(min(cap, (duration / 30.0) * per_30_min * intensity_multiplier), 2)


def activity_rollup(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    training_load = 0.0
    progression_load = 0.0
    commute_load = 0.0
    hard_sessions = 0
    rehab_sessions = 0
    recovery_bonus = 0.0
    for row in rows:
        activity_type = normalize_activity_type(row.get("activity_type"))
        points = activity_training_points(row)
        training_load += points
        if activity_type == "bike_commute":
            commute_load += points
        else:
            progression_load += points
        duration = duration_minutes(row)
        if activity_type == "rehab":
            rehab_sessions += 1
        if as_bool(row.get("recovery_activity")) or activity_type in {"walk", "rehab", "meditation"}:
            recovery_bonus += min(1.25, 0.35 + (duration / 60.0) * 0.4) if duration else 0.5
        if as_bool(row.get("hard_session")) or activity_type in {"crossfit"} or (activity_type == "run" and duration >= 25) or (activity_type != "bike_commute" and points >= 3.0):
            hard_sessions += 1
    return {
        "training_load": round(training_load, 2),
        "progression_load": round(progression_load, 2),
        "commute_load": round(commute_load, 2),
        "hard_sessions": hard_sessions,
        "rehab_sessions": rehab_sessions,
        "recovery_bonus": round(recovery_bonus, 2),
    }


def formula_toggle(settings: Mapping[str, Any] | None, key: str, default: bool = True) -> bool:
    formula = settings.get("formula") if isinstance(settings, Mapping) and isinstance(settings.get("formula"), Mapping) else settings
    if not isinstance(formula, Mapping) or key not in formula:
        return default
    return as_bool(formula.get(key))


PROFILE_MODIFIER_KEYS = {"balanced", "protective", "sports_light"}


def profile_modifiers(settings: Mapping[str, Any] | None) -> Set[str]:
    formula = settings.get("formula") if isinstance(settings, Mapping) and isinstance(settings.get("formula"), Mapping) else settings
    if not isinstance(formula, Mapping):
        return set()
    raw_modifiers = formula.get("profile_modifiers")
    modifiers: Set[str] = set()
    if isinstance(raw_modifiers, list):
        modifiers = {str(item) for item in raw_modifiers if str(item) in PROFILE_MODIFIER_KEYS and str(item) != "balanced"}
    if not modifiers:
        legacy = str(formula.get("profile") or "")
        if legacy in PROFILE_MODIFIER_KEYS and legacy != "balanced":
            modifiers.add(legacy)
    return modifiers


def has_profile_modifier(settings: Mapping[str, Any] | None, name: str) -> bool:
    return name in profile_modifiers(settings)


def formula_settings_snapshot(settings: Mapping[str, Any] | None) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {key: formula_toggle(settings, key) for key in FORMULA_SETTING_KEYS}
    snapshot["profile_modifiers"] = sorted(profile_modifiers(settings))
    return snapshot


def formula_settings_hash(settings: Mapping[str, Any] | None) -> str:
    payload = json.dumps(formula_settings_snapshot(settings), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _entry_activity_types(entry: Mapping[str, Any]) -> List[str]:
    raw_types = entry.get("activity_types")
    if isinstance(raw_types, str) and raw_types.strip().startswith("["):
        try:
            loaded = json.loads(raw_types)
        except Exception:
            loaded = []
        raw_types = loaded if isinstance(loaded, list) else []
    elif isinstance(raw_types, str) and "," in raw_types:
        raw_types = raw_types.split(",")
    elif isinstance(raw_types, str) and raw_types.strip():
        raw_types = [raw_types]
    elif not isinstance(raw_types, (list, tuple)):
        raw_types = []
    normalized: List[str] = []
    for item in raw_types:
        activity_type = normalize_activity_type(item)
        if activity_type and activity_type not in normalized:
            normalized.append(activity_type)
    if not normalized:
        primary = normalize_activity_type(entry.get("primary_activity_type"))
        if primary:
            normalized.append(primary)
    return normalized


def entry_activity_rows(entry: Mapping[str, Any]) -> List[Dict[str, Any]]:
    activity_types = _entry_activity_types(entry)
    duration_min = as_optional_int(entry.get("activity_duration_min")) or 0
    rehab_done = entry.get("rehab_done")
    if not activity_types and rehab_done is True:
        activity_types = ["rehab"]
    if not activity_types:
        return []
    per_activity_duration = int(duration_min / len(activity_types)) if duration_min and len(activity_types) > 1 else duration_min
    return [
        {
            "date": str(entry.get("date") or ""),
            "activity_type": activity_type,
            "duration_min": per_activity_duration,
            "intensity": "moderate" if activity_type in {"run", "crossfit", "strength", "bike"} else "light",
            "hard_session": activity_type == "crossfit" or (activity_type == "run" and per_activity_duration >= 25),
            "recovery_activity": activity_type in {"walk", "rehab", "meditation"},
            "notes": "",
            "source": "daily_log",
        }
        for activity_type in activity_types
    ]


def entry_activity_row(entry: Mapping[str, Any]) -> Dict[str, Any] | None:
    rows = entry_activity_rows(entry)
    return rows[0] if rows else None


def group_activity_by_date(rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("date") or ""), []).append(dict(row))
    return grouped


def _activity_types_match(left: str, right: str) -> bool:
    if left == right:
        return True
    return {left, right} in ({"crossfit", "strength"}, {"bike", "bike_commute"})


def _duplicate_activity_match(candidate: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    candidate_type = normalize_activity_type(candidate.get("activity_type"))
    row_type = normalize_activity_type(row.get("activity_type"))
    if not candidate_type or not _activity_types_match(candidate_type, row_type):
        return False
    source = str(row.get("source") or "").strip().lower()
    if source not in {"garmin_activity", "activity_log"}:
        return False
    candidate_duration = duration_minutes(candidate)
    row_duration = duration_minutes(row)
    return not candidate_duration or not row_duration or abs(candidate_duration - row_duration) <= 45


def _manual_activity_overrides(candidate: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    candidate_type = normalize_activity_type(candidate.get("activity_type"))
    row_type = normalize_activity_type(row.get("activity_type"))
    return (
        candidate_type == "crossfit"
        and row_type == "strength"
    ) or (
        {candidate_type, row_type} == {"bike", "bike_commute"}
    )


def activity_already_represented(candidate: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    return any(_duplicate_activity_match(candidate, row) for row in rows)


def combine_activity_rows(
    rows: Sequence[Mapping[str, Any]],
    synthetic_activity: Mapping[str, Any] | None,
) -> List[Dict[str, Any]]:
    combined = [dict(row) for row in rows]
    if synthetic_activity is None:
        return combined
    matched_indices = [
        index
        for index, row in enumerate(combined)
        if _duplicate_activity_match(synthetic_activity, row)
    ]
    if not matched_indices:
        combined.append(dict(synthetic_activity))
        return combined
    override_indices = [
        index
        for index in matched_indices
        if _manual_activity_overrides(synthetic_activity, combined[index])
    ]
    if override_indices:
        combined = [row for index, row in enumerate(combined) if index not in set(override_indices)]
        combined.append(dict(synthetic_activity))
    return combined


def ewma_load(values: Sequence[float], *, tau_days: float) -> float:
    if not values:
        return 0.0
    current = float(values[0] or 0.0)
    alpha = 1.0 - pow(2.718281828459045, -1.0 / tau_days)
    for value in values[1:]:
        current = current + alpha * (float(value or 0.0) - current)
    return round(current, 2)


def load_context_from_history(
    prior_training_loads: Sequence[float] | None,
    *,
    today_training_load: float,
) -> Dict[str, Any]:
    history = [float(value or 0.0) for value in (prior_training_loads or [])][-42:]
    with_today = [*history, float(today_training_load or 0.0)]
    acute = ewma_load(with_today, tau_days=7.0)
    chronic = ewma_load(with_today, tau_days=42.0)
    prior_chronic = ewma_load(history, tau_days=42.0) if history else 0.0
    ratio = round(acute / chronic, 2) if chronic >= 1.0 else None
    ramp = round(chronic - prior_chronic, 2)
    spike_penalty = 0.0
    warnings: List[str] = []
    if today_training_load >= 3.0 and chronic < 1.0:
        spike_penalty += 2.0
        warnings.append("training spike from low base")
    elif ratio is not None and ratio >= 1.5:
        spike_penalty += 2.0
        warnings.append("acute training spike")
    elif ratio is not None and ratio >= 1.3:
        spike_penalty += 1.0
        warnings.append("training load rising fast")
    if ramp > 1.0:
        warnings.append("chronic load ramp")
    return {
        "acute_training_load": acute,
        "chronic_training_load": chronic,
        "training_load_ratio": ratio,
        "training_ramp": ramp,
        "spike_penalty": spike_penalty,
        "warnings": warnings,
    }


def garmin_sleep_risk(sleep_min: float | int | None) -> Dict[str, Any]:
    """Classify Garmin sleep duration as a next-day decision-risk signal."""

    try:
        minutes = float(sleep_min or 0.0)
    except Exception:
        minutes = 0.0
    if minutes <= 0:
        return {"minutes": None, "level": "unknown", "strain": 0.0, "recovery": 0.0, "warning": ""}
    if minutes < 240:
        return {
            "minutes": minutes,
            "level": "red",
            "strain": 5.0,
            "recovery": 0.0,
            "warning": "garmin critical short sleep",
        }
    if minutes < 300:
        return {
            "minutes": minutes,
            "level": "orange",
            "strain": 6.0,
            "recovery": 0.0,
            "warning": "garmin very short sleep",
        }
    if minutes < 360:
        return {
            "minutes": minutes,
            "level": "yellow",
            "strain": 2.0,
            "recovery": 0.0,
            "warning": "garmin short sleep",
        }
    if minutes >= 420:
        return {"minutes": minutes, "level": "good", "strain": 0.0, "recovery": 1.5, "warning": ""}
    return {"minutes": minutes, "level": "borderline", "strain": 0.5, "recovery": 0.0, "warning": "garmin borderline sleep"}


def score_entry(
    entry: Mapping[str, Any],
    *,
    activity_rows: Sequence[Mapping[str, Any]] | None = None,
    garmin_passive: Mapping[str, Any] | None = None,
    prior_training_loads: Sequence[float] | None = None,
    formula_settings: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    modifiers = profile_modifiers(formula_settings)
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
    recovery = 0.0
    strain = 0.0
    combined_activity_rows = [dict(row) for row in (activity_rows or [])]
    for manual_activity in entry_activity_rows(entry):
        combined_activity_rows = combine_activity_rows(combined_activity_rows, manual_activity)
    activity_summary = activity_rollup(combined_activity_rows)
    training = float(activity_summary["training_load"])
    load_context = load_context_from_history(
        prior_training_loads,
        today_training_load=float(activity_summary["progression_load"]),
    )
    red_flags: List[str] = []
    warnings: List[str] = []
    unknown_fields: List[str] = []
    passive_sleep_risk: Dict[str, Any] | None = None

    if entry.get("sleep_ok") is True:
        recovery += 2.0
    elif entry.get("sleep_ok") is False:
        strain += 2.0
        warnings.append("sleep drift")
    elif garmin_passive and formula_toggle(formula_settings, "include_garmin_recovery"):
        passive_sleep_risk = garmin_sleep_risk(garmin_passive.get("sleep_total_sleep_min"))
        recovery += float(passive_sleep_risk["recovery"])
        strain += float(passive_sleep_risk["strain"])
        if passive_sleep_risk["warning"]:
            warnings.append(str(passive_sleep_risk["warning"]))
        if passive_sleep_risk["level"] == "red":
            red_flags.append("critical short sleep")

    if entry.get("nutrition_ok") is True:
        recovery += 2.0
    elif entry.get("nutrition_ok") is False:
        strain += 2.0
        warnings.append("nutrition drift")

    if as_bool(entry.get("alcohol")):
        strain += 4.0
        red_flags.append("alcohol")

    if as_bool(entry.get("binge")):
        strain += 5.0
        red_flags.append("binge")

    stress_value = clamp_int(entry.get("stress"), default=None)
    energy_value = clamp_int(entry.get("energy"), default=None)
    mood_value = clamp_int(entry.get("mood"), default=None)
    stress = stress_value or 0
    energy = energy_value or 0
    mood = mood_value or 0
    foot_pain = clamp_int(entry.get("foot_pain"), default=0) or 0
    shoulder_pain = clamp_int(entry.get("shoulder_pain"), default=0) or 0
    family_stress = clamp_int(entry.get("family_stress"), default=0) or 0
    wife_conflict_count = clamp_int(entry.get("wife_conflict_count"), maximum=12, default=0) or 0

    strain += round(stress * 0.7, 2)
    recovery += round(energy * 0.4, 2)
    recovery += round(mood * 0.3, 2)
    strain += round(foot_pain * 0.5, 2)
    strain += round(shoulder_pain * 0.4, 2)
    strain += round(family_stress * 0.5, 2)
    include_relationship = formula_toggle(formula_settings, "include_relationship_stress")
    if wife_conflict_count and include_relationship:
        strain += min(7.0, wife_conflict_count * 2.0)
        warnings.append("relationship conflict")
    if wife_conflict_count >= 2 and include_relationship:
        strain += 1.5
        warnings.append("repeated relationship conflict")
    if entry.get("wife_conflict_school") is True and include_relationship:
        strain += 1.0
        warnings.append("school conflict")
    if entry.get("wife_conflict_chores") is True and include_relationship:
        strain += 0.5
    if entry.get("wife_conflict_other") is True and include_relationship:
        strain += 0.5
    recovery += float(activity_summary["recovery_bonus"])
    if formula_toggle(formula_settings, "include_training_trend_brake"):
        spike_penalty = float(load_context["spike_penalty"])
        if sports_light and spike_penalty:
            original_spike_penalty = spike_penalty
            non_training_recovery_priority = bool(red_flags) or (strain + training - recovery) * 10 >= guidance_thresholds["high"]
            migraine_signal = as_bool(entry.get("migraine_warning"))
            sleep_disrupted = entry.get("sleep_ok") is False
            pain_blocks_softening = foot_pain >= 5 or shoulder_pain >= 5
            low_energy_blocks_softening = energy_value is not None and energy_value <= 3
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
                spike_penalty = round(spike_penalty * 0.8, 2)
                profile_score_delta += spike_penalty - original_spike_penalty
                profile_effects.append("sports_light softened training spike penalty")
        strain += spike_penalty
        warnings.extend(load_context["warnings"])
    if garmin_passive and formula_toggle(formula_settings, "include_garmin_recovery"):
        steps = int(float(garmin_passive.get("wellness_steps") or 0))
        avg_stress = float(garmin_passive.get("wellness_avg_stress") or 0.0)
        active_kcal = float(garmin_passive.get("wellness_active_kcal") or 0.0)
        hard_sessions_est = int(float(garmin_passive.get("activity_hard_session_count_est") or 0))
        if steps >= 6000:
            recovery += 0.5
        if steps >= 12000:
            strain += 0.5
        if steps >= 20000:
            strain += 1.0
            warnings.append("very high steps")
        if active_kcal >= 900 and not training:
            strain += 1.0
            warnings.append("high active calories")
        if avg_stress >= 70:
            strain += 3.0
            warnings.append("garmin high stress")
        elif avg_stress >= 55:
            strain += 1.5
            warnings.append("garmin elevated stress")
        if hard_sessions_est >= 2 and (not combined_activity_rows or int(activity_summary["hard_sessions"]) >= 2):
            warnings.append("multiple hard sessions")

    if as_bool(entry.get("migraine_warning")):
        strain += 4.0
        red_flags.append("migraine warning")
    if foot_pain >= 6 or shoulder_pain >= 6:
        red_flags.append("pain flare")
    if entry.get("shutdown_done") is True:
        recovery += 2.0
    elif entry.get("shutdown_done") is False:
        shutdown_delta = 0.5 if protective else 0.0
        strain += 2.5 + shutdown_delta
        profile_score_delta += shutdown_delta
        if protective:
            profile_effects.append("protective increased shutdown-missed strain")
        warnings.append("shutdown missed")
    if entry.get("decompression_done") is True:
        recovery += 1.75
    elif entry.get("decompression_done") is False:
        strain += 2.0
        warnings.append("decompression missed")
    if entry.get("after_work_decompression_done") is True and formula_toggle(formula_settings, "include_after_work_decompression"):
        recovery += 1.25
    elif entry.get("after_work_decompression_done") is False and formula_toggle(formula_settings, "include_after_work_decompression"):
        decompression_delta = 0.5 if protective else 0.0
        strain += 3.0 + decompression_delta
        profile_score_delta += decompression_delta
        if protective:
            profile_effects.append("protective increased after-work decompression strain")
        warnings.append("after-work decompression missed")
    if entry.get("rehab_done") is True:
        recovery += 0.5
    if entry.get("phone_after_21") is True and formula_toggle(formula_settings, "include_late_phone"):
        late_phone_delta = 0.5 if protective else 0.0
        strain += 2.0 + late_phone_delta
        profile_score_delta += late_phone_delta
        if protective:
            profile_effects.append("protective increased late-phone strain")
        warnings.append("late phone")
    if entry.get("project_overrun") is True and formula_toggle(formula_settings, "include_project_overrun"):
        project_delta = 0.5 if protective else 0.0
        strain += 2.0 + project_delta
        profile_score_delta += project_delta
        if protective:
            profile_effects.append("protective increased project-overrun strain")
        warnings.append("project spillover")
    if entry.get("evening_chain_broken") is True:
        strain += 3.0
        warnings.append("evening chain broken")
    if str(entry.get("work_intensity") or "") == "heavy":
        strain += 2.0

    emotional_pressure = 0
    if stress >= 7:
        emotional_pressure += 1
    if family_stress >= 7:
        emotional_pressure += 1
    if wife_conflict_count >= 1 and include_relationship:
        emotional_pressure += 1
    if wife_conflict_count >= 2 and include_relationship:
        emotional_pressure += 1
    if energy_value is not None and energy_value <= 3:
        emotional_pressure += 1
    if mood_value is not None and mood_value <= 3:
        emotional_pressure += 1
    if entry.get("decompression_done") is False:
        emotional_pressure += 1
    if entry.get("after_work_decompression_done") is False and formula_toggle(formula_settings, "include_after_work_decompression"):
        emotional_pressure += 2
    if entry.get("shutdown_done") is False:
        emotional_pressure += 1
    if entry.get("evening_chain_broken") is True:
        emotional_pressure += 2
    if entry.get("project_overrun") is True and formula_toggle(formula_settings, "include_project_overrun"):
        emotional_pressure += 1
    if entry.get("phone_after_21") is True and formula_toggle(formula_settings, "include_late_phone"):
        emotional_pressure += 1
    if str(entry.get("work_intensity") or "") == "heavy":
        emotional_pressure += 1
    if entry.get("alone_home") is True and formula_toggle(formula_settings, "include_alone_home"):
        emotional_pressure += 1
    emotional_high_threshold = 5 if protective else 6
    emotional_medium_threshold = 3 if protective else 4
    if emotional_pressure >= emotional_high_threshold:
        strain += 4.0
        if protective and emotional_pressure == 5:
            profile_score_delta += 2.0
            profile_effects.append("protective lowered emotional-overload threshold")
        warnings.append("emotional overload")
    elif emotional_pressure >= emotional_medium_threshold:
        strain += 2.0
        if protective and emotional_pressure == 3:
            profile_score_delta += 2.0
            profile_effects.append("protective lowered accumulated-emotional-load threshold")
        warnings.append("accumulated emotional load")

    if entry.get("home_office") is True and formula_toggle(formula_settings, "include_home_office"):
        strain += 0.5
    if entry.get("alone_home") is True and formula_toggle(formula_settings, "include_alone_home"):
        strain += 2.5
        warnings.append("alone at home trigger")
        if entry.get("nutrition_ok") is False or entry.get("binge") is True:
            strain += 1.0
            warnings.append("alone home food risk")
    if entry.get("homework_done") is True:
        recovery += 0.5
    for field_name in ("sleep_ok", "nutrition_ok", "stress", "energy", "shutdown_done"):
        if entry.get(field_name) is None:
            unknown_fields.append(field_name)
    if len(unknown_fields) >= 3:
        warnings.append("missing structured data")

    profile_adjusted_score = round(strain + training - recovery, 2)
    base_score = round(profile_adjusted_score - profile_score_delta, 2)
    zone = "green"
    risk_basis = profile_adjusted_score * 10
    if red_flags or profile_adjusted_score >= 10:
        zone = "red"
    elif risk_basis >= guidance_thresholds["high"]:
        zone = "orange"
    elif risk_basis >= guidance_thresholds["medium"]:
        zone = "yellow"

    if "missing structured data" in warnings and not red_flags:
        zone = "yellow" if zone == "green" else zone
    caution_floor_warnings = {
        "garmin very short sleep",
        "training spike from low base",
        "acute training spike",
        "decompression missed",
        "after-work decompression missed",
        "shutdown missed",
        "late phone",
        "project spillover",
        "accumulated emotional load",
    }
    if not red_flags and zone == "green" and caution_floor_warnings.intersection(warnings):
        zone = "yellow"
    if not red_flags and "garmin very short sleep" in warnings and zone in {"green", "yellow"}:
        zone = "orange"

    if zone == "red":
        next_action = (
            "Treat today as impaired by short sleep: no ambitious decisions, no extra training, and protect tonight."
            if "critical short sleep" in red_flags
            else
            "Make tomorrow a stabilization day: decompress, close one loop, and protect sleep."
            if "emotional overload" in warnings or "accumulated emotional load" in warnings
            else "Make tomorrow recovery-first: reduce optional load and protect sleep."
        )
    elif zone == "orange":
        next_action = (
            "Hold progression today: protect sleep tonight and avoid stacking training or project work."
            if "garmin very short sleep" in warnings
            else
            "Pause extra demands today: decompress, close one loop, and restart shutdown."
            if "emotional overload" in warnings or "accumulated emotional load" in warnings
            else "Keep ambition flat today and protect sleep/shutdown."
        )
    elif zone == "yellow":
        next_action = (
            "A few fields are missing; add them before relying on this score."
            if "missing structured data" in warnings
            else "Hold progression today: protect sleep tonight and avoid stacking training or project work."
            if "garmin very short sleep" in warnings or "training spike from low base" in warnings or "acute training spike" in warnings
            else "Keep decisions small today and protect tonight's sleep."
            if "garmin short sleep" in warnings or "garmin borderline sleep" in warnings
            else "Release pressure first: one decompression step before adding ambition."
            if "accumulated emotional load" in warnings or "decompression missed" in warnings
            else "Keep the next step simple and repeatable."
        )
    else:
        next_action = "Keep the steady baseline."

    return {
        "date": str(entry["date"]),
        "life_load_score": profile_adjusted_score,
        "base_score": base_score,
        "profile_adjusted_score": profile_adjusted_score,
        "guidance_thresholds": guidance_thresholds,
        "profile_modifiers": sorted(modifiers),
        "profile_effects": sorted(set(profile_effects)),
        "training_load": training,
        "recovery_score": round(recovery, 2),
        "strain_score": round(strain, 2),
        "red_flags": sorted(set(red_flags)),
        "warnings": sorted(set(warnings)),
        "unknown_fields": sorted(set(unknown_fields)),
        "zone": zone,
        "next_action": next_action,
        "hard_sessions": int(activity_summary["hard_sessions"]),
        "rehab_sessions": int(activity_summary["rehab_sessions"]),
        "acute_training_load": float(load_context["acute_training_load"]),
        "chronic_training_load": float(load_context["chronic_training_load"]),
        "training_load_ratio": load_context["training_load_ratio"],
        "training_ramp": float(load_context["training_ramp"]),
    }
