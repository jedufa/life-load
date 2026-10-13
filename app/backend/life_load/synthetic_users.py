"""Synthetic Life Load user histories for profile/guidance validation.

The harness uses fake, deterministic data only. It is intended to catch
profile, copy, missingness, and temporal-response regressions before beta
review. It does not change production scoring and does not claim real-world
efficacy.
"""

from __future__ import annotations

import csv
import json
import random
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Literal, Mapping

from life_load.guidance_bridge import build_guidance_bridge_from_signal_entries
from life_load.profile_templates import PROFILE_TEMPLATE_METADATA
from life_load.signal_registry import SIGNALS_BY_ID


GuidanceLabel = Literal["Push", "Maintain", "Recover", "Simplify", "Protect Sleep"]
OracleStatus = Literal["pass", "warning", "fail"]
GuidanceVariant = Literal[
    "baseline_092_pre_ac_promotion",
    "shadow_guidance_v1_confidence_action_quality",
    "shadow_formula_body_signal_v1",
    "shadow_formula_general_balance_stress_energy_v1",
    "shadow_formula_training_recovery_push_v1",
    "shadow_formula_combined_v1",
]
BASELINE_092_PRE_AC_PROMOTION: GuidanceVariant = "baseline_092_pre_ac_promotion"
SHADOW_GUIDANCE_V1: GuidanceVariant = "shadow_guidance_v1_confidence_action_quality"
SHADOW_FORMULA_BODY_SIGNAL_V1: GuidanceVariant = "shadow_formula_body_signal_v1"
SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1: GuidanceVariant = "shadow_formula_general_balance_stress_energy_v1"
SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1: GuidanceVariant = "shadow_formula_training_recovery_push_v1"
SHADOW_FORMULA_COMBINED_V1: GuidanceVariant = "shadow_formula_combined_v1"
SHADOW_FORMULA_VARIANTS = (
    SHADOW_FORMULA_BODY_SIGNAL_V1,
    SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
    SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1,
)

ACTION_FAMILIES = (
    "protect_sleep",
    "reduce_optional_load",
    "simplify_evening",
    "keep_training_easy",
    "take_recovery_break",
    "maintain_plan",
    "use_good_capacity",
    "small_start",
    "stabilize_routine",
    "check_in_first",
    "avoid_extra_commitment",
    "recover_body_signal",
    "protect_private_pattern",
    "no_action_needed",
)

FORBIDDEN_SENSITIVE_TERMS = (
    "addiction",
    "bulimia",
    "eating disorder",
    "relapse",
    "treatment",
    "diagnosis",
    "disorder",
    "medical device",
    "therapy",
    "cure",
    "prevent",
    "failure",
    "failed",
    "shame",
)

PROFILE_FORBIDDEN_DRIVER_TERMS: Mapping[str, tuple[str, ...]] = {
    "general_balance": (
        "foot",
        "shoulder",
        "relationship",
        "homework",
        "alcohol",
        "eating episode",
        "primary activity",
        "crossfit",
    ),
    "work_stress": ("relationship", "homework", "foot", "shoulder", "body-part"),
    "training_recovery": ("relationship", "homework"),
    "body_signal_awareness": ("foot", "shoulder", "diagnosis", "treatment"),
}

LABEL_SEVERITY: Mapping[str, int] = {
    "Push": 0,
    "Maintain": 1,
    "Recover": 2,
    "Simplify": 3,
    "Protect Sleep": 4,
}


@dataclass(frozen=True)
class SyntheticPhase:
    name: str
    start_day: int
    end_day: int
    tendencies: Mapping[str, Any]
    expected_guidance: str

    def contains(self, day_index: int) -> bool:
        return self.start_day <= day_index <= self.end_day


@dataclass(frozen=True)
class GuidanceExpectation:
    scenario_id: str
    phase_name: str
    allowed_labels: tuple[str, ...]
    discouraged_labels: tuple[str, ...] = ()
    required_driver_any_of: tuple[str, ...] = ()
    forbidden_driver_any_of: tuple[str, ...] = ()
    expected_action_families: tuple[str, ...] = ()
    expected_confidence_behavior: str = "normal"
    required_copy_traits: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = FORBIDDEN_SENSITIVE_TERMS
    recency_expectation: str = ""
    profile_leakage_forbidden: bool = True


@dataclass(frozen=True)
class SyntheticUserModel:
    id: str
    name: str
    profile_id: str
    optional_packs: tuple[str, ...]
    duration_days: int
    baseline_traits: Mapping[str, Any]
    missingness_pattern: Mapping[str, Any]
    event_schedule: tuple[SyntheticPhase, ...]
    expectations: tuple[GuidanceExpectation, ...]
    expected_behavior_notes: str


@dataclass(frozen=True)
class SyntheticDay:
    date: str
    profile_id: str
    inputs: Mapping[str, Any]
    missing_inputs: tuple[str, ...]
    tags: tuple[str, ...]
    phase_name: str
    notes: str = ""


@dataclass(frozen=True)
class GuidanceOutput:
    date: str
    profile_id: str
    label: GuidanceLabel
    top_drivers: tuple[str, ...]
    confidence: str
    confidence_note: str
    primary_action: str
    action_family: str
    recent_change: str
    warning_sensitive_text: str
    missing_signal_ids: tuple[str, ...]
    bridge_inputs: Mapping[str, Any]


@dataclass(frozen=True)
class OracleResult:
    oracle: str
    status: OracleStatus
    affected_days: tuple[str, ...]
    explanation: str
    suggested_review_sample: tuple[str, ...] = ()
    classification: str = ""


@dataclass(frozen=True)
class SimulationResult:
    user_model_id: str
    duration_days: int
    generated_days: tuple[SyntheticDay, ...]
    guidance_outputs: tuple[GuidanceOutput, ...]
    summary_metrics: Mapping[str, Any]
    anomalies: tuple[OracleResult, ...]
    oracle_results: tuple[OracleResult, ...] = ()
    review_samples: tuple[Mapping[str, Any], ...] = ()


def required_synthetic_user_models() -> tuple[SyntheticUserModel, ...]:
    return (
        _general_balance_stable(),
        _general_balance_overload_drift(),
        _work_stress_project_crunch(),
        _training_recovery_recreational_athlete(),
        _body_signal_awareness_recurring_signal(),
        _pattern_awareness_private_pull(),
        _sparse_low_compliance_user(),
        _long_term_inconsistent_user(),
    )


def simulate_user(
    model: SyntheticUserModel,
    *,
    seed: int = 20260518,
    duration_days: int | None = None,
    start_date: date = date(2026, 1, 1),
    guidance_variant: GuidanceVariant | None = None,
) -> SimulationResult:
    days_count = duration_days or model.duration_days
    rng = random.Random(f"life-load:{seed}:{model.id}:{days_count}")
    days = tuple(_generate_day(model, day_index, rng, start_date) for day_index in range(days_count))
    outputs = tuple(
        _guidance_for_day(day, model.optional_packs, days[: index + 1], guidance_variant=guidance_variant)
        for index, day in enumerate(days)
    )
    metrics = compute_metrics(days, outputs)
    oracle_results = tuple(run_all_oracles(days, outputs, model, metrics))
    samples = tuple(generate_review_samples(days, outputs, oracle_results, model, seed=seed))
    anomalies = tuple(result for result in oracle_results if result.status in {"warning", "fail"})
    return SimulationResult(
        user_model_id=model.id,
        duration_days=days_count,
        generated_days=days,
        guidance_outputs=outputs,
        summary_metrics=metrics,
        anomalies=anomalies,
        oracle_results=oracle_results,
        review_samples=samples,
    )


def simulate_required_models(
    *,
    seed: int = 20260518,
    durations: tuple[int, ...] = (14, 30, 90),
) -> tuple[SimulationResult, ...]:
    results: list[SimulationResult] = []
    for model in required_synthetic_user_models():
        if model.id == "long_term_inconsistent_user":
            results.append(simulate_user(model, seed=seed, duration_days=730))
            continue
        for duration in durations:
            results.append(simulate_user(model, seed=seed, duration_days=duration))
    return tuple(results)


def guidance_for_synthetic_day(
    day: SyntheticDay,
    *,
    optional_packs: tuple[str, ...] = (),
    history: tuple[SyntheticDay, ...] | None = None,
    guidance_variant: GuidanceVariant | None = None,
) -> GuidanceOutput:
    """Evaluate one synthetic day through the shadow guidance bridge."""

    return _guidance_for_day(day, optional_packs, history or (day,), guidance_variant=guidance_variant)


def compute_metrics(days: Iterable[SyntheticDay], outputs: Iterable[GuidanceOutput]) -> Mapping[str, Any]:
    day_list = tuple(days)
    output_list = tuple(outputs)
    label_distribution = Counter(output.label for output in output_list)
    confidence_distribution = Counter(output.confidence for output in output_list)
    driver_frequency = Counter(driver for output in output_list for driver in output.top_drivers)
    action_family_distribution = Counter(output.action_family for output in output_list)
    total_fields = sum(len(day.inputs) + len(day.missing_inputs) for day in day_list) or 1
    missing_fields = sum(len(day.missing_inputs) for day in day_list)
    profile_leakage_count = _profile_leakage_count(output_list)
    sensitive_word_violation_count = sum(_contains_forbidden(_guidance_text(output)) for output in output_list)
    stuck_state_count = _stuck_state_count(output_list)
    recency_mismatch_count = _recency_mismatch_count(day_list, output_list)
    overconfidence_sparse_count = sum(
        1
        for day, output in zip(day_list, output_list)
        if len(day.inputs) <= 2 and output.confidence == "normal"
    )
    push_on_severe_day_count = sum(
        1
        for day, output in zip(day_list, output_list)
        if output.label == "Push" and _day_severity(day) >= 3
    )
    total_outputs = len(output_list) or 1
    return {
        "guidance_label_distribution": dict(label_distribution),
        "confidence_distribution": dict(confidence_distribution),
        "missing_data_rate": round(missing_fields / total_fields, 3),
        "driver_frequency": dict(driver_frequency),
        "action_family_distribution": dict(action_family_distribution),
        "profile_leakage_count": profile_leakage_count,
        "sensitive_word_violation_count": sensitive_word_violation_count,
        "stuck_state_count": stuck_state_count,
        "recency_mismatch_count": recency_mismatch_count,
        "overconfidence_sparse_count": overconfidence_sparse_count,
        "push_on_severe_day_count": push_on_severe_day_count,
        "protect_sleep_rate": round(label_distribution["Protect Sleep"] / total_outputs, 3),
        "simplify_rate": round(label_distribution["Simplify"] / total_outputs, 3),
        "recover_rate": round(label_distribution["Recover"] / total_outputs, 3),
        "maintain_rate": round(label_distribution["Maintain"] / total_outputs, 3),
        "push_rate": round(label_distribution["Push"] / total_outputs, 3),
        "recent_recovery_responsiveness": _recent_recovery_responsiveness(day_list, output_list),
        "old_drift_overweighting": _old_drift_overweighting(day_list, output_list),
    }


def compute_life_rhythm_metrics(
    days: Iterable[SyntheticDay],
    outputs: Iterable[GuidanceOutput],
) -> Mapping[str, Any]:
    day_list = tuple(days)
    output_list = tuple(outputs)
    gap_lengths = _gap_lengths(day_list)
    post_gap_dates = set(_post_gap_dates(day_list, min_gap=30, window=3))
    post_gap_outputs = tuple(output for output in output_list if output.date in post_gap_dates)
    post_gap_confidence = Counter(output.confidence for output in post_gap_outputs)
    return {
        "max_gap_days": max(gap_lengths, default=0),
        "days_since_last_checkin": _days_since_last_checkin(day_list),
        "post_gap_confidence_distribution": dict(post_gap_confidence),
        "stale_history_influence_count": _stale_history_influence_count(day_list, output_list),
        "phase_transition_response_days": _phase_transition_response_days(day_list, output_list),
        "bad_day_sampling_bias_score": _sampling_bias_score(day_list, "biased_bad_logging"),
        "good_day_sampling_bias_score": _sampling_bias_score(day_list, "biased_good_logging"),
        "gap_return_guidance_labels": [output.label for output in post_gap_outputs],
        "long_gap_stuck_state_count": len(_classified_stuck_state_days(day_list, output_list, max_run=10)[0]),
        "return_after_gap_limited_confidence_rate": _limited_confidence_rate(post_gap_outputs),
        "stale_good_push_count": sum(
            1
            for day, output in zip(day_list, output_list)
            if day.phase_name == "return_after_gap" and output.label == "Push"
        ),
        "stale_bad_simplify_or_protect_count": sum(
            1
            for day, output in zip(day_list, output_list)
            if day.phase_name == "return_after_gap" and output.label in {"Simplify", "Protect Sleep"} and not day.inputs
        ),
    }


def run_all_oracles(
    days: tuple[SyntheticDay, ...],
    outputs: tuple[GuidanceOutput, ...],
    model: SyntheticUserModel,
    metrics: Mapping[str, Any] | None = None,
) -> tuple[OracleResult, ...]:
    metrics = metrics or compute_metrics(days, outputs)
    return (
        ProfileLeakageOracle().evaluate(days, outputs, model, metrics),
        MissingDataOracle().evaluate(days, outputs, model, metrics),
        RecencyOracle().evaluate(days, outputs, model, metrics),
        SeverityOracle().evaluate(days, outputs, model, metrics),
        MessageRelevanceOracle().evaluate(days, outputs, model, metrics),
        ActionQualityOracle().evaluate(days, outputs, model, metrics),
        SensitiveCopyOracle().evaluate(days, outputs, model, metrics),
        StuckStateOracle().evaluate(days, outputs, model, metrics),
        NoDataGuidanceOracle().evaluate(days, outputs, model, metrics),
    )


class ProfileLeakageOracle:
    name = "ProfileLeakageOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        forbidden = PROFILE_FORBIDDEN_DRIVER_TERMS.get(model.profile_id, ())
        affected = tuple(
            output.date
            for output in outputs
            if any(term in " ".join(output.top_drivers).lower() for term in forbidden)
        )
        return _oracle_result(
            self.name,
            affected,
            "Drivers stayed within active profile boundaries.",
            "Drivers mention inactive or personal-legacy concepts.",
        )


class MissingDataOracle:
    name = "MissingDataOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected = tuple(
            output.date
            for day, output in zip(days, outputs)
            if len(day.inputs) <= 2 and output.confidence != "limited"
        )
        if model.id != "sparse_low_compliance_user":
            affected = ()
        return _oracle_result(
            self.name,
            affected,
            "Sparse days are marked with limited confidence.",
            "Sparse days appear overconfident.",
        )


class RecencyOracle:
    name = "RecencyOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected = tuple(
            output.date
            for day, output in zip(days, outputs)
            if day.phase_name == "recovery" and _day_severity(day) <= 1 and output.label == "Protect Sleep"
        )
        return _oracle_result(
            self.name,
            affected,
            "Recent recovery softens older overload.",
            "Older overload appears to dominate despite recent recovery.",
        )


class SeverityOracle:
    name = "SeverityOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected = tuple(
            output.date
            for day, output in zip(days, outputs)
            if _day_severity(day) >= 3 and output.label == "Push"
        )
        return _oracle_result(
            self.name,
            affected,
            "Severe input days do not receive aggressive guidance.",
            "Severe input days received Push.",
        )


class MessageRelevanceOracle:
    name = "MessageRelevanceOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected: list[str] = []
        for day, output in zip(days, outputs):
            expected = _expected_driver_terms(day)
            driver_text = " ".join(output.top_drivers).lower()
            if expected and not any(term in driver_text for term in expected):
                affected.append(output.date)
        return _oracle_result(
            self.name,
            tuple(affected),
            "Top drivers align with dominant inputs.",
            "Top drivers miss dominant input signals.",
            warning_limit=3,
        )


class ActionQualityOracle:
    name = "ActionQualityOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        vague = {"be mindful", "do better", "try harder", "fix it", "improve"}
        affected = tuple(output.date for output in outputs if output.primary_action.lower() in vague)
        return _oracle_result(
            self.name,
            affected,
            "Primary actions are concrete enough for review.",
            "Primary action is vague.",
        )


class SensitiveCopyOracle:
    name = "SensitiveCopyOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected = tuple(output.date for output in outputs if _contains_forbidden(_guidance_text(output)))
        return _oracle_result(
            self.name,
            affected,
            "Guidance copy avoids forbidden sensitive wording.",
            "Guidance copy contains forbidden sensitive wording.",
        )


class StuckStateOracle:
    name = "StuckStateOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected, classification = _classified_stuck_state_days(days, outputs, max_run=10)
        if classification == "stable_maintain_ok":
            return OracleResult(
                oracle=self.name,
                status="pass",
                affected_days=(),
                explanation="Repeated Maintain matches stable inputs.",
                classification=classification,
            )
        return _oracle_result(
            self.name,
            affected,
            "Guidance responds to meaningful input changes.",
            "Guidance appears stuck relative to the input trend.",
            warning_limit=1,
            classification=classification,
        )


class NoDataGuidanceOracle:
    name = "NoDataGuidanceOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected: list[str] = []
        consecutive_empty = 0
        for day, output in zip(days, outputs):
            if not day.inputs:
                consecutive_empty += 1
                text = _guidance_text(output).lower()
                if output.confidence != "limited":
                    affected.append(day.date)
                if "check-in" not in text and "check in" not in text:
                    affected.append(day.date)
                if any(key in output.bridge_inputs for key in ("mental_load_high", "energy_low", "private_pattern_active")):
                    affected.append(day.date)
                if consecutive_empty > 7 and output.action_family != "check_in_first":
                    affected.append(day.date)
            else:
                consecutive_empty = 0
        return _oracle_result(
            self.name,
            tuple(dict.fromkeys(affected)),
            "Empty-input days remain limited-confidence check-in prompts.",
            "Empty-input days imply known load or do not invite check-in.",
            classification="missing_data_loop" if affected else "",
        )


class StaleHistoryOracle:
    name = "StaleHistoryOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected: list[str] = []
        for date_value in _post_gap_dates(days, min_gap=30, window=3):
            output = _output_by_date(outputs, date_value)
            day = _day_by_date(days, date_value)
            if output is None or day is None:
                continue
            if output.label == "Push":
                affected.append(date_value)
            if (
                output.label in {"Protect Sleep", "Simplify"}
                and output.confidence == "normal"
                and _day_severity(day) <= 1
                and len(day.inputs) <= 2
                and "Missing data" not in output.top_drivers
            ):
                affected.append(date_value)
        return _oracle_result(
            self.name,
            tuple(dict.fromkeys(affected)),
            "Long-gap returns are not dominated by stale history.",
            "Long-gap return guidance appears dominated by stale history.",
            classification="stale_history_overweighting" if affected else "pass",
        )


class ReturnAfterGapOracle:
    name = "ReturnAfterGapOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected: list[str] = []
        for date_value in _post_gap_dates(days, min_gap=30, window=3):
            output = _output_by_date(outputs, date_value)
            if output is None:
                continue
            text = _guidance_text(output).lower()
            if output.confidence != "limited":
                affected.append(date_value)
            if (
                "check-in" not in text
                and "missing data" not in text
                and output.action_family != "check_in_first"
            ):
                affected.append(date_value)
        return _oracle_result(
            self.name,
            tuple(dict.fromkeys(affected)),
            "Return-after-gap check-ins stay cautious and limited-confidence.",
            "Return-after-gap guidance is overconfident or lacks a check-in reset.",
            classification="return_after_gap_overconfidence" if affected else "pass",
        )


class SamplingBiasOracle:
    name = "SamplingBiasOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        if not any(day.phase_name in {"biased_bad_logging", "biased_good_logging"} for day in days):
            return OracleResult(self.name, "pass", (), "No biased logging phase in this model.", classification="pass")
        affected: list[str] = []
        for day, output in zip(days, outputs):
            if day.phase_name == "biased_bad_logging" and output.label in {"Protect Sleep", "Simplify"} and output.confidence == "normal":
                affected.append(output.date)
            if day.phase_name == "biased_good_logging" and output.label == "Push" and output.confidence == "normal":
                affected.append(output.date)
        return _oracle_result(
            self.name,
            tuple(affected),
            "Biased logging remains uncertainty-aware.",
            "Biased logging produces overconfident conclusions.",
            warning_limit=5,
            classification="biased_sampling_overconfidence" if affected else "pass",
        )


class PhaseTransitionOracle:
    name = "PhaseTransitionOracle"

    def evaluate(
        self,
        days: tuple[SyntheticDay, ...],
        outputs: tuple[GuidanceOutput, ...],
        model: SyntheticUserModel,
        metrics: Mapping[str, Any],
    ) -> OracleResult:
        affected: list[str] = []
        for index in range(1, len(days)):
            if days[index].phase_name == days[index - 1].phase_name:
                continue
            previous = outputs[index - 1]
            current = outputs[index]
            previous_severity = _day_severity(days[index - 1])
            current_severity = _day_severity(days[index])
            if current_severity >= previous_severity + 2 and LABEL_SEVERITY[current.label] < LABEL_SEVERITY[previous.label]:
                affected.append(current.date)
            if current_severity <= previous_severity - 2 and LABEL_SEVERITY[current.label] > LABEL_SEVERITY[previous.label] + 1:
                affected.append(current.date)
        return _oracle_result(
            self.name,
            tuple(affected),
            "Phase transitions are reflected by guidance direction.",
            "A high/low phase transition appears ignored.",
            classification="transition_ignored" if affected else "pass",
        )


def mutation_checks(seed: int = 20260518) -> Mapping[str, bool]:
    base = SyntheticDay(
        date="2026-05-18",
        profile_id="general_balance",
        inputs={
            "core.sleep_ok": True,
            "core.nutrition_ok": True,
            "mental.stress": 3,
            "energy.energy": 7,
            "recovery.shutdown_done": True,
        },
        missing_inputs=(),
        tags=("mutation",),
        phase_name="baseline",
    )

    def label(day: SyntheticDay, optional_packs: tuple[str, ...] = ()) -> GuidanceOutput:
        return _guidance_for_day(day, optional_packs, (day,))

    sleep_good = label(base)
    sleep_poor = label(_replace_input(base, "core.sleep_ok", False))
    energy_high = label(base)
    energy_low = label(_replace_input(base, "energy.energy", 2))
    training_low = label(
        SyntheticDay(
            **{
                **asdict(base),
                "profile_id": "training_recovery",
                "inputs": {
                    "core.sleep_ok": True,
                    "core.nutrition_ok": True,
                    "mental.stress": 2,
                    "energy.energy": 8,
                    "training.activity_duration_min": 20,
                    "training.primary_activity_type": "walk",
                },
            }
        )
    )
    training_high = label(
        SyntheticDay(
            **{
                **asdict(base),
                "profile_id": "training_recovery",
                "inputs": {
                    "core.sleep_ok": False,
                    "core.nutrition_ok": True,
                    "mental.stress": 6,
                    "energy.energy": 3,
                    "training.activity_duration_min": 70,
                    "training.primary_activity_type": "run",
                },
            }
        )
    )
    pattern_disabled = label(
        _replace_many(base, {"evening.phone_after_21": True, "work.project_overrun": True}),
        optional_packs=(),
    )
    pattern_enabled = label(
        _replace_many(base, {"evening.phone_after_21": True, "work.project_overrun": True}),
        optional_packs=("pattern_awareness_pack",),
    )
    protective_absent = label(_replace_input(base, "recovery.shutdown_done", False))
    protective_present = label(_replace_input(base, "recovery.shutdown_done", True))
    return {
        "worsening_sleep_does_not_make_guidance_more_aggressive": _severity(sleep_poor) >= _severity(sleep_good),
        "improving_energy_does_not_make_guidance_more_severe": _severity(energy_high) <= _severity(energy_low),
        "training_load_high_is_not_more_aggressive": _severity(training_high) >= _severity(training_low),
        "pattern_awareness_off_removes_private_pattern_driver": "Private pattern" not in pattern_disabled.top_drivers
        and "Private pattern" in pattern_enabled.top_drivers,
        "protective_behavior_softens_guidance_or_support_text": _severity(protective_present) <= _severity(protective_absent)
        or "Protective behavior" in protective_present.top_drivers,
    }


def advanced_synthetic_user_models() -> tuple[SyntheticUserModel, ...]:
    return (
        _general_balance_high_baseline_stress_stable(),
        _general_balance_low_baseline_sudden_spike(),
        _general_balance_good_sleep_high_life_load(),
        _general_balance_poor_sleep_low_demand(),
        _work_stress_weekend_recovery(),
        _training_recovery_overenthusiastic_athlete(),
        _custom_avoidance_risk_small_start(),
        _family_load_carrier(),
    )


def all_synthetic_user_models() -> tuple[SyntheticUserModel, ...]:
    return required_synthetic_user_models() + advanced_synthetic_user_models()


def life_rhythm_synthetic_user_models() -> tuple[SyntheticUserModel, ...]:
    return (
        _high_to_recovery_transition(),
        _stable_to_sudden_spike(),
        _repeated_load_waves(),
        _bad_phase_then_long_gap(),
        _good_phase_then_long_gap(),
        _bad_day_only_logger(),
        _good_day_only_logger(),
        _partial_after_gap_user(),
    )


def all_extended_synthetic_user_models() -> tuple[SyntheticUserModel, ...]:
    return all_synthetic_user_models() + life_rhythm_synthetic_user_models()


def generate_review_samples(
    days: tuple[SyntheticDay, ...],
    outputs: tuple[GuidanceOutput, ...],
    oracle_results: tuple[OracleResult, ...],
    model: SyntheticUserModel,
    *,
    seed: int,
    max_random_samples: int = 12,
) -> tuple[Mapping[str, Any], ...]:
    selected: dict[str, str] = {}
    seen_phases: set[str] = set()
    previous_label = None
    previous_has_inputs = True
    empty_run = 0
    for day, output in zip(days, outputs):
        if not day.inputs:
            empty_run += 1
        elif empty_run >= 30:
            selected[day.date] = f"first check-in after {empty_run}-day gap"
            empty_run = 0
        elif day.inputs:
            empty_run = 0
        if day.phase_name not in seen_phases:
            selected[day.date] = f"first day of phase {day.phase_name}"
            seen_phases.add(day.phase_name)
        if previous_label is not None and output.label != previous_label:
            selected.setdefault(day.date, f"label transition from {previous_label} to {output.label}")
        if day.phase_name == "recovery" and _day_severity(day) <= 1:
            selected.setdefault(day.date, "recent recovery transition")
        if "pattern" in " ".join(day.tags):
            selected.setdefault(day.date, "Pattern Awareness sample")
        if previous_has_inputs is False and day.inputs:
            selected.setdefault(day.date, "return after missing-data run")
        if day.phase_name in {"return_after_gap", "biased_bad_logging", "biased_good_logging"}:
            selected.setdefault(day.date, f"life-rhythm phase sample: {day.phase_name}")
        previous_label = output.label
        previous_has_inputs = bool(day.inputs)
    for result in oracle_results:
        for affected_day in result.affected_days:
            selected[affected_day] = f"{result.oracle} {result.status}"

    rng = random.Random(f"review-samples:{seed}:{model.id}:{len(days)}")
    remaining = [day.date for day in days if day.date not in selected]
    rng.shuffle(remaining)
    for day_date in remaining[:max_random_samples]:
        selected.setdefault(day_date, "seeded random review sample")

    gap_by_date = dict(zip((day.date for day in days), _days_since_last_checkin(days)))
    by_date = {day.date: (day, output) for day, output in zip(days, outputs)}
    samples = []
    for day_date, reason in sorted(selected.items()):
        day, output = by_date[day_date]
        samples.append(
            {
                "day": day.date,
                "profile": day.profile_id,
                "phase": day.phase_name,
                "inputs": dict(day.inputs),
                "missing_data": list(day.missing_inputs),
                "days_since_last_checkin": gap_by_date.get(day.date),
                "guidance_label": output.label,
                "drivers": list(output.top_drivers),
                "confidence": output.confidence,
                "action": output.primary_action,
                "oracle_notes": [
                    result.explanation
                    for result in oracle_results
                    if day.date in result.affected_days
                ],
                "why_selected": reason,
            }
        )
    return tuple(samples)


def write_simulation_report_zip(
    *,
    results: tuple[SimulationResult, ...] | None = None,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str | None = None,
) -> Path:
    results = results or simulate_required_models(seed=seed)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or date.today().strftime("%Y%m%d")
    zip_path = output_root / f"life_load_synthetic_user_evaluation_{stamp}.zip"
    work_dir = output_root / f"life_load_synthetic_user_evaluation_{stamp}"
    per_user_dir = work_dir / "per_user_results"
    review_dir = work_dir / "review_samples"
    per_user_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "synthetic_data_only": True,
        "clinical_or_real_world_efficacy_claim": False,
        "seed": seed,
        "model_count": len({result.user_model_id for result in results}),
        "simulation_count": len(results),
        "total_generated_days": sum(len(result.generated_days) for result in results),
        "top_anomalies": [asdict(result) for simulation in results for result in simulation.anomalies[:3]],
    }
    _write_json(work_dir / "simulation_summary.json", summary)
    _write_json(
        work_dir / "oracle_results.json",
        [asdict(oracle) | {"user_model_id": result.user_model_id} for result in results for oracle in result.oracle_results],
    )
    _write_json(
        work_dir / "anomalies.json",
        [asdict(anomaly) | {"user_model_id": result.user_model_id} for result in results for anomaly in result.anomalies],
    )
    thresholds = _thresholds()
    _write_json(work_dir / "thresholds.json", thresholds)
    for result in results:
        payload = _simulation_result_payload(result)
        _write_json(per_user_dir / f"{result.user_model_id}_{result.duration_days}d.json", payload)
        _write_json(review_dir / f"{result.user_model_id}_{result.duration_days}d_review_samples.json", result.review_samples)
    _write_review_markdown(work_dir / "review_samples.md", results)
    _write_report_markdown(work_dir / "simulation_report.md", results, summary)
    _write_readme(work_dir / "README.md", results, seed)
    _write_csv_summary(work_dir / "summary_metrics.csv", results)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def expectations_validate_schema(expectation: GuidanceExpectation) -> bool:
    return bool(expectation.scenario_id and expectation.phase_name and expectation.allowed_labels)


def phases_cover_full_duration(model: SyntheticUserModel, duration_days: int | None = None) -> bool:
    duration = duration_days or model.duration_days
    covered = set()
    for phase in model.event_schedule:
        covered.update(range(max(0, phase.start_day), min(duration, phase.end_day + 1)))
    return covered == set(range(duration))


def generated_values_valid(days: Iterable[SyntheticDay]) -> bool:
    for day in days:
        for signal_id, value in day.inputs.items():
            if signal_id in {"mental.stress", "energy.energy", "mood.mood", "relationship.family_stress"}:
                if not isinstance(value, int) or not 0 <= value <= 10:
                    return False
            if signal_id == "training.activity_duration_min":
                if not isinstance(value, int) or not 0 <= value <= 240:
                    return False
    return True


def _generate_day(
    model: SyntheticUserModel,
    day_index: int,
    rng: random.Random,
    start_date: date,
) -> SyntheticDay:
    phase = _phase_for_day(model, day_index)
    current_date = start_date + timedelta(days=day_index)
    weekday = current_date.weekday()
    base = dict(model.baseline_traits)
    tendencies = dict(phase.tendencies)
    missing_chance = float(tendencies.get("missing_chance", model.missingness_pattern.get("day_skip_rate", 0.1)))
    partial_chance = float(tendencies.get("partial_chance", model.missingness_pattern.get("partial_rate", 0.15)))
    if rng.random() < missing_chance:
        return SyntheticDay(
            date=current_date.isoformat(),
            profile_id=model.profile_id,
            inputs={},
            missing_inputs=_required_signal_ids(model.profile_id),
            tags=("no_checkin", phase.name),
            phase_name=phase.name,
            notes="No fake check-in generated for this day.",
        )

    inputs = _phase_inputs(model, phase, weekday, rng, base)
    minimal_signal_ids = tuple(tendencies.get("minimal_signal_ids", ()))
    if minimal_signal_ids:
        inputs = {signal_id: inputs[signal_id] for signal_id in minimal_signal_ids if signal_id in inputs}
    required = _required_signal_ids(model.profile_id)
    visible = _active_signal_ids_for_profile(model.profile_id, model.optional_packs)
    missing: list[str] = []
    if rng.random() < partial_chance:
        optional_candidates = [signal_id for signal_id in visible if signal_id not in required]
        rng.shuffle(optional_candidates)
        for signal_id in optional_candidates[: max(1, len(optional_candidates) // 2)]:
            inputs.pop(signal_id, None)
            missing.append(signal_id)
    for signal_id in required:
        if signal_id not in inputs:
            missing.append(signal_id)
    return SyntheticDay(
        date=current_date.isoformat(),
        profile_id=model.profile_id,
        inputs=inputs,
        missing_inputs=tuple(dict.fromkeys(missing)),
        tags=tuple(dict.fromkeys((phase.name,) + _tags_for_inputs(inputs, weekday))),
        phase_name=phase.name,
        notes=str(phase.expected_guidance),
    )


def _phase_inputs(
    model: SyntheticUserModel,
    phase: SyntheticPhase,
    weekday: int,
    rng: random.Random,
    base: Mapping[str, Any],
) -> dict[str, Any]:
    stress = _bounded_int(_jitter(base.get("stress", 4), phase.tendencies.get("stress_delta", 0), rng, 1), 0, 10)
    energy = _bounded_int(_jitter(base.get("energy", 6), phase.tendencies.get("energy_delta", 0), rng, 1), 0, 10)
    mood = _bounded_int(_jitter(base.get("mood", 6), phase.tendencies.get("mood_delta", 0), rng, 1), 0, 10)
    sleep_ok = rng.random() > float(phase.tendencies.get("bad_sleep_chance", base.get("bad_sleep_chance", 0.15)))
    nutrition_ok = rng.random() > float(phase.tendencies.get("nutrition_miss_chance", 0.12))
    shutdown_done = rng.random() > float(phase.tendencies.get("shutdown_miss_chance", 0.2))
    inputs: dict[str, Any] = {
        "core.sleep_ok": sleep_ok,
        "core.nutrition_ok": nutrition_ok,
        "mental.stress": stress,
        "energy.energy": energy,
        "mood.mood": mood,
        "recovery.shutdown_done": shutdown_done,
    }

    if model.profile_id in {"general_balance", "work_stress"}:
        inputs["recovery.decompression_done"] = rng.random() > float(phase.tendencies.get("decompression_miss_chance", 0.25))
    if model.profile_id == "work_stress" or "life_load_pack" in model.optional_packs:
        inputs["work.work_intensity"] = _work_intensity(stress, phase.name, weekday)
        inputs["work.home_office"] = weekday < 5 and rng.random() < 0.55
        if rng.random() < float(phase.tendencies.get("project_overrun_chance", 0.1)):
            inputs["work.project_overrun"] = True
        if "life_load_pack" in model.optional_packs:
            inputs["relationship.family_stress"] = _bounded_int(stress - 1 + rng.choice((-1, 0, 1)), 0, 10)
    if model.profile_id == "training_recovery":
        hard_training = weekday in {0, 2, 4} and rng.random() < float(phase.tendencies.get("training_chance", 0.8))
        duration = rng.randint(45, 80) if hard_training else rng.choice((0, 20, 30))
        inputs["training.activity_duration_min"] = duration
        inputs["training.primary_activity_type"] = "run" if hard_training and rng.random() < 0.35 else ("crossfit" if hard_training else "walk")
        inputs["training.rehab_done"] = rng.random() > 0.25
        if rng.random() < float(phase.tendencies.get("body_warning_chance", 0.15)):
            inputs["body.migraine_warning"] = True
    if model.profile_id == "body_signal_awareness":
        if rng.random() < float(phase.tendencies.get("body_warning_chance", 0.25)):
            inputs["body.migraine_warning"] = True
    if "pattern_awareness_pack" in model.optional_packs:
        pull_chance = float(phase.tendencies.get("private_pattern_chance", 0.1))
        if rng.random() < pull_chance:
            inputs["evening.phone_after_21"] = True
            inputs["evening.evening_chain_broken"] = True
            inputs["work.project_overrun"] = True
    if model.id == "long_term_inconsistent_user" and phase.name == "profile_switch":
        inputs["placeholder.body_signal_instance"] = min(10, max(0, stress + rng.choice((-1, 0, 1))))
    return _filter_active_inputs(inputs, model.profile_id, model.optional_packs)


def _guidance_for_day(
    day: SyntheticDay,
    optional_packs: tuple[str, ...],
    history: tuple[SyntheticDay, ...],
    *,
    guidance_variant: GuidanceVariant | None = None,
) -> GuidanceOutput:
    entries = [
        {"signal_id": signal_id, "value": value, "is_present": True}
        for signal_id, value in day.inputs.items()
        if not signal_id.startswith("placeholder.")
    ]
    snapshot = build_guidance_bridge_from_signal_entries(
        entries,
        profile_id=day.profile_id,
        optional_pack_ids=optional_packs,
    )
    bridge_keys = set(snapshot.inputs)
    recent = tuple(history[-3:])
    recent_severity = mean(_day_severity(item) for item in recent) if recent else _day_severity(day)
    current_severity = _day_severity(day)
    confidence = "limited" if snapshot.data_confidence < 0.67 or len(day.inputs) <= 2 else "normal"
    if not day.inputs:
        label: GuidanceLabel = "Maintain"
    elif confidence == "limited" and current_severity < 3:
        label = "Simplify"
    elif "private_pattern_active" in bridge_keys and ("energy_low" in bridge_keys or "recovery_low" in bridge_keys):
        label = "Protect Sleep"
    elif "physical_load_high" in bridge_keys and ("energy_low" in bridge_keys or "recovery_low" in bridge_keys):
        label = "Recover"
    elif "mental_load_high" in bridge_keys and "energy_low" in bridge_keys:
        label = "Simplify"
    elif current_severity >= 4:
        label = "Protect Sleep"
    elif current_severity >= 3:
        label = "Simplify"
    elif recent_severity <= 1 and "energy_good" in bridge_keys and "recovery_good" in bridge_keys:
        label = "Push"
    else:
        label = "Maintain"
    drivers = _drivers_for_snapshot(snapshot.inputs, day)
    if not drivers:
        drivers = ("Missing data",) if confidence == "limited" else ("Recovery steady",)
    if not day.inputs:
        action_family, primary_action = (
            "check_in_first",
            "Complete a short check-in for a better suggestion.",
        )
    else:
        action_family, primary_action = _action_for_label(label, day.profile_id, bridge_keys)
    confidence_note = (
        "Limited confidence: several expected signals are missing."
        if confidence == "limited"
        else "Normal confidence from the available check-in."
    )
    output = GuidanceOutput(
        date=day.date,
        profile_id=day.profile_id,
        label=label,
        top_drivers=drivers[:4],
        confidence=confidence,
        confidence_note=confidence_note,
        primary_action=primary_action,
        action_family=action_family,
        recent_change=_recent_change_text(history),
        warning_sensitive_text="Private pattern noticed; keep the next step stabilizing."
        if "private_pattern_active" in bridge_keys
        else "",
        missing_signal_ids=tuple(snapshot.missing_required_signal_ids),
        bridge_inputs={key: value.value for key, value in snapshot.inputs.items()},
    )
    if guidance_variant == BASELINE_092_PRE_AC_PROMOTION:
        return replace(
            output,
            bridge_inputs={**dict(output.bridge_inputs), "baseline_variant": BASELINE_092_PRE_AC_PROMOTION},
        )
    output = _apply_experiment_3_ac_production_rules(output, day, history, bridge_keys)
    if guidance_variant == SHADOW_GUIDANCE_V1:
        return _shadow_guidance_v1_output(output, day, optional_packs, bridge_keys)
    if guidance_variant in {
        SHADOW_FORMULA_BODY_SIGNAL_V1,
        SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
        SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1,
        SHADOW_FORMULA_COMBINED_V1,
    }:
        return _shadow_formula_output(output, day, history, bridge_keys, guidance_variant)
    return output


def _drivers_for_snapshot(inputs: Mapping[str, Any], day: SyntheticDay) -> tuple[str, ...]:
    drivers: list[str] = []
    if "mental_load_high" in inputs:
        drivers.append("Work pressure" if day.profile_id == "work_stress" else "Stress")
    if "energy_low" in inputs:
        drivers.append("Energy")
    if "recovery_low" in inputs:
        drivers.append("Sleep")
    if "private_pattern_active" in inputs:
        drivers.append(_private_pattern_driver(day))
    if "evening_boundary_broken" in inputs:
        drivers.append("Decompression")
    if "physical_load_high" in inputs:
        drivers.append("Training load")
    if "body_signal_high" in inputs:
        drivers.append("Body signal")
    if "protective_behavior_present" in inputs and not any(driver in drivers for driver in ("Sleep", "Decompression")):
        drivers.append("Protective behavior")
    if "energy_good" in inputs and len(drivers) < 2:
        drivers.append("Energy")
    if "recovery_good" in inputs and len(drivers) < 2:
        drivers.append("Recovery")
    return tuple(dict.fromkeys(drivers))


def _shadow_guidance_v1_output(
    output: GuidanceOutput,
    day: SyntheticDay,
    optional_packs: tuple[str, ...],
    bridge_keys: set[str],
) -> GuidanceOutput:
    """Shadow-only copy/confidence/action quality variant for synthetic tests."""

    label = output.label
    drivers = tuple(
        "Work spillover" if driver == "Private pattern" and day.profile_id == "work_stress" and "pattern_awareness_pack" not in optional_packs else driver
        for driver in output.top_drivers
    )
    confidence = output.confidence
    confidence_note = output.confidence_note
    action_family = output.action_family
    primary_action = output.primary_action

    if not day.inputs:
        return replace(
            output,
            label="Maintain",
            top_drivers=("Missing data",),
            confidence="limited",
            confidence_note="Not enough recent data yet. Complete a short check-in for a better suggestion.",
            primary_action="Complete a short check-in for a better suggestion.",
            action_family="check_in_first",
            bridge_inputs={**dict(output.bridge_inputs), "shadow_guidance_variant": SHADOW_GUIDANCE_V1},
        )

    if day.phase_name in {"biased_bad_logging", "biased_good_logging"}:
        confidence = "limited"
        confidence_note = "Recent check-ins are uneven, so guidance is cautious."

    if (
        label == "Maintain"
        and day.inputs.get("core.sleep_ok") is False
        and int(day.inputs.get("mental.stress") or 0) <= 3
        and int(day.inputs.get("energy.energy") or 0) >= 4
    ):
        action_family = "protect_sleep"
        primary_action = "Keep the day steady and protect an earlier sleep window."
    else:
        action_family, primary_action = _shadow_action_for_context(
            output,
            day,
            bridge_keys,
            drivers,
        )

    return replace(
        output,
        top_drivers=drivers,
        confidence=confidence,
        confidence_note=confidence_note,
        primary_action=primary_action,
        action_family=action_family,
        bridge_inputs={**dict(output.bridge_inputs), "shadow_guidance_variant": SHADOW_GUIDANCE_V1},
    )


def _shadow_formula_output(
    output: GuidanceOutput,
    day: SyntheticDay,
    history: tuple[SyntheticDay, ...],
    bridge_keys: set[str],
    guidance_variant: GuidanceVariant,
) -> GuidanceOutput:
    """Shadow-only formula threshold candidates for Experiment 3."""

    result = output
    if guidance_variant in {SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1, SHADOW_FORMULA_COMBINED_V1}:
        result = _apply_general_balance_stress_energy_candidate(result, day, history, bridge_keys)
    return replace(
        result,
        bridge_inputs={**dict(result.bridge_inputs), "shadow_formula_variant": guidance_variant},
    )


def _apply_experiment_3_ac_production_rules(
    output: GuidanceOutput,
    day: SyntheticDay,
    history: tuple[SyntheticDay, ...],
    bridge_keys: set[str],
) -> GuidanceOutput:
    result = _apply_body_signal_candidate(output, day, history, bridge_keys)
    result = _apply_training_recovery_candidate(result, day, history, bridge_keys)
    if result is output:
        return output
    return replace(
        result,
        bridge_inputs={**dict(result.bridge_inputs), "formula_threshold_version": "experiment_3_ac"},
    )


def _apply_body_signal_candidate(
    output: GuidanceOutput,
    day: SyntheticDay,
    history: tuple[SyntheticDay, ...],
    bridge_keys: set[str],
) -> GuidanceOutput:
    if day.profile_id != "body_signal_awareness" or "body_signal_high" not in bridge_keys:
        return output
    recent_body_signal_days = sum(
        1
        for item in history[-3:]
        if item.inputs.get("body.migraine_warning") is True
    )
    low_capacity = "energy_low" in bridge_keys or "recovery_low" in bridge_keys or "mental_load_high" in bridge_keys
    if output.label == "Push":
        return replace(
            output,
            label="Maintain",
            primary_action="Keep the current shape and leave recovery protected.",
            action_family="maintain_plan",
        )
    if low_capacity:
        return replace(
            output,
            label="Recover",
            primary_action="Keep load lighter and avoid adding strain today.",
            action_family="recover_body_signal",
        )
    if recent_body_signal_days >= 2 and output.label == "Maintain":
        return replace(
            output,
            label="Simplify",
            primary_action="Keep load lighter and avoid adding strain today.",
            action_family="recover_body_signal",
        )
    return output


def _apply_general_balance_stress_energy_candidate(
    output: GuidanceOutput,
    day: SyntheticDay,
    history: tuple[SyntheticDay, ...],
    bridge_keys: set[str],
) -> GuidanceOutput:
    if day.profile_id != "general_balance":
        return output
    stress = int(day.inputs.get("mental.stress") or 0)
    energy = int(day.inputs.get("energy.energy") or 0)
    if stress < 8 or energy > 4:
        return output
    strongly_protected = (
        day.inputs.get("core.sleep_ok") is True
        and day.inputs.get("recovery.shutdown_done") is True
        and "protective_behavior_present" in bridge_keys
        and energy == 4
    )
    if strongly_protected and output.label == "Maintain":
        return replace(
            output,
            primary_action="Keep the current shape and leave recovery protected.",
            action_family="maintain_plan",
        )
    if output.label == "Maintain":
        return replace(
            output,
            label="Simplify",
            primary_action="Save the basics first and remove one optional demand.",
            action_family="avoid_extra_commitment",
        )
    return output


def _apply_training_recovery_candidate(
    output: GuidanceOutput,
    day: SyntheticDay,
    history: tuple[SyntheticDay, ...],
    bridge_keys: set[str],
) -> GuidanceOutput:
    if day.profile_id != "training_recovery" or "physical_load_high" not in bridge_keys:
        return output
    load_conflict = (
        "recovery_low" in bridge_keys
        or "body_signal_high" in bridge_keys
        or day.inputs.get("core.sleep_ok") is False
        or int(day.inputs.get("training.activity_duration_min") or 0) >= 70
    )
    if output.label == "Push" and load_conflict:
        return replace(
            output,
            label="Maintain",
            primary_action="Keep training easy and stop before extra fatigue.",
            action_family="keep_training_easy",
        )
    if output.label == "Maintain" and ("recovery_low" in bridge_keys or "body_signal_high" in bridge_keys):
        return replace(
            output,
            label="Recover",
            primary_action="Keep training easy and stop before extra fatigue.",
            action_family="keep_training_easy",
        )
    return output


def _shadow_action_for_context(
    output: GuidanceOutput,
    day: SyntheticDay,
    bridge_keys: set[str],
    drivers: tuple[str, ...],
) -> tuple[str, str]:
    if output.label == "Simplify":
        if "Missing data" in drivers:
            return "check_in_first", "Complete a short check-in first, then choose the smallest useful next step."
        if day.profile_id == "work_stress" or "Work pressure" in drivers or "Work spillover" in drivers:
            variants = (
                ("reduce_optional_load", "Reduce one optional work demand before adding anything else."),
                ("simplify_evening", "Keep the evening simple and protect a decompression break."),
                ("avoid_extra_commitment", "Avoid one extra commitment until the work pressure settles."),
            )
            return _choose_shadow_variant(variants, day.date)
        if day.profile_id == "body_signal_awareness" or "Body signal" in drivers:
            variants = (
                ("recover_body_signal", "Avoid adding extra physical load today."),
                ("take_recovery_break", "Choose the lighter version and leave room for recovery."),
            )
            return _choose_shadow_variant(variants, day.date)
        if "Sleep" in drivers or "recovery_low" in bridge_keys:
            return "protect_sleep", "Keep the evening simple and protect recovery."
        variants = (
            ("avoid_extra_commitment", "Remove one optional demand and keep the basics covered."),
            ("small_start", "Do the minimum useful version first."),
            ("maintain_plan", "Hold the current shape without adding new load."),
        )
        return _choose_shadow_variant(variants, day.date)
    if output.label == "Protect Sleep" and "private_pattern_active" not in bridge_keys:
        variants = (
            ("protect_sleep", "Make the evening smaller and protect the sleep window."),
            ("simplify_evening", "Close one loop early and keep the rest of the evening quiet."),
        )
        return _choose_shadow_variant(variants, day.date)
    if output.label == "Maintain":
        if "Recovery" in drivers or "Sleep" in drivers:
            variants = (
                ("maintain_plan", "Keep the current shape and leave recovery protected."),
                ("no_action_needed", "Stay with the plan and avoid adding bonus load."),
            )
            return _choose_shadow_variant(variants, day.date)
        variants = (
            ("maintain_plan", "Keep the current shape and avoid adding extra load."),
            ("small_start", "Start with the planned basics and stop before extra load."),
            ("no_action_needed", "Hold steady; no extra correction is needed today."),
        )
        return _choose_shadow_variant(variants, day.date)
    if output.label == "Push":
        variants = (
            ("use_good_capacity", "Use the available capacity, but keep one clear stop point."),
            ("maintain_plan", "Use the good capacity for the planned priority, not bonus load."),
        )
        return _choose_shadow_variant(variants, day.date)
    return output.action_family, output.primary_action


def _choose_shadow_variant(variants: tuple[tuple[str, str], ...], date_value: str) -> tuple[str, str]:
    index = sum(ord(char) for char in date_value) % len(variants)
    return variants[index]


def _action_for_label(label: str, profile_id: str, bridge_keys: set[str]) -> tuple[str, str]:
    if label == "Protect Sleep":
        if "private_pattern_active" in bridge_keys:
            return "protect_private_pattern", "Make the evening simple and choose one stabilizing routine."
        return "protect_sleep", "Make the evening smaller and protect the sleep window."
    if label == "Recover":
        if "body_signal_high" in bridge_keys:
            return "recover_body_signal", "Keep load lighter and avoid adding strain today."
        if "physical_load_high" in bridge_keys:
            return "keep_training_easy", "Keep training easy and stop before extra fatigue."
        return "take_recovery_break", "Choose a recovery-first day and keep load capped."
    if label == "Simplify":
        if profile_id == "work_stress":
            return "reduce_optional_load", "Remove one optional work demand and protect a decompression break."
        if "evening_boundary_broken" in bridge_keys:
            return "simplify_evening", "Make the evening smaller and close one loop early."
        if profile_id == "body_signal_awareness":
            return "recover_body_signal", "Keep load lighter and avoid adding strain today."
        return "avoid_extra_commitment", "Save the basics first and remove one optional demand."
    if label == "Push":
        return "use_good_capacity", "Use the good capacity for the planned priority, not bonus load."
    if "recovery_good" in bridge_keys or "protective_behavior_present" in bridge_keys:
        return "maintain_plan", "Keep the current shape and leave recovery protected."
    return "maintain_plan", "Stay with the plan and avoid adding bonus load."


def _private_pattern_driver(day: SyntheticDay) -> str:
    if day.profile_id == "work_stress" and not any(signal_id.startswith("nutrition.") for signal_id in day.inputs):
        return "Work spillover"
    return "Private pattern"


def _recent_change_text(history: tuple[SyntheticDay, ...]) -> str:
    if len(history) < 3:
        return "Learning baseline from early check-ins."
    older = history[-3]
    current = history[-1]
    delta = _day_severity(current) - _day_severity(older)
    if delta <= -1:
        return "Recent context is improving."
    if delta >= 1:
        return "Recent context is getting heavier."
    return "Recent context is steady."


def _general_balance_stable() -> SyntheticUserModel:
    return _model(
        "general_balance_stable",
        "General Balance stable user",
        "general_balance",
        (),
        90,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.12},
        {"day_skip_rate": 0.18, "partial_rate": 0.12},
        _phases(
            (0, 29, "baseline", {"stress_delta": 0, "energy_delta": 0}, "mostly Maintain"),
            (30, 44, "stable_good", {"stress_delta": -1, "energy_delta": 1, "bad_sleep_chance": 0.05}, "some Push"),
            (45, 59, "acute_overload", {"stress_delta": 2, "energy_delta": -2, "bad_sleep_chance": 0.35}, "some Simplify"),
            (60, 89, "recovery", {"stress_delta": -1, "energy_delta": 1, "bad_sleep_chance": 0.08}, "Maintain or Push"),
        ),
        "Mostly stable with occasional bad sleep and weekday check-in gaps.",
    )


def _general_balance_overload_drift() -> SyntheticUserModel:
    return _model(
        "general_balance_overload_drift",
        "General Balance overload drift",
        "general_balance",
        (),
        90,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.15},
        {"day_skip_rate": 0.16, "partial_rate": 0.25},
        _phases(
            (0, 13, "baseline", {}, "Maintain"),
            (14, 27, "overload_building", {"stress_delta": 2, "energy_delta": -1, "bad_sleep_chance": 0.25}, "Simplify rising"),
            (28, 41, "acute_overload", {"stress_delta": 4, "energy_delta": -3, "bad_sleep_chance": 0.55, "shutdown_miss_chance": 0.65}, "Protect Sleep or Simplify"),
            (42, 59, "recovery", {"stress_delta": -1, "energy_delta": 1, "bad_sleep_chance": 0.08}, "softens"),
            (60, 89, "baseline", {}, "Maintain"),
        ),
        "Stress rises for two weeks, then recovery improves.",
    )


def _work_stress_project_crunch() -> SyntheticUserModel:
    return _model(
        "work_stress_project_crunch",
        "Work Stress project crunch",
        "work_stress",
        ("pattern_awareness_pack",),
        90,
        {"stress": 5, "energy": 6, "mood": 6, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.12, "partial_rate": 0.18},
        _phases(
            (0, 13, "baseline", {"project_overrun_chance": 0.1}, "Maintain"),
            (14, 34, "acute_overload", {"stress_delta": 3, "energy_delta": -2, "project_overrun_chance": 0.65, "decompression_miss_chance": 0.75}, "Simplify"),
            (35, 48, "weekend_recovery", {"stress_delta": -1, "energy_delta": 1, "project_overrun_chance": 0.05}, "Maintain"),
            (49, 69, "second_crunch", {"stress_delta": 3, "energy_delta": -2, "project_overrun_chance": 0.55, "bad_sleep_chance": 0.45}, "Protect Sleep"),
            (70, 89, "recovery", {"stress_delta": -1, "energy_delta": 1}, "Maintain"),
        ),
        "Weekday work pressure with missed decompression and weekend recovery.",
    )


def _training_recovery_recreational_athlete() -> SyntheticUserModel:
    return _model(
        "training_recovery_recreational_athlete",
        "Training Recovery recreational athlete",
        "training_recovery",
        ("life_load_pack",),
        90,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.12, "partial_rate": 0.14},
        _phases(
            (0, 20, "baseline", {"training_chance": 0.65}, "Maintain"),
            (21, 38, "acute_overload", {"training_chance": 0.9, "energy_delta": -2, "bad_sleep_chance": 0.35, "body_warning_chance": 0.25}, "Recover"),
            (39, 55, "recovery", {"training_chance": 0.35, "energy_delta": 1, "bad_sleep_chance": 0.08}, "Maintain or Push"),
            (56, 89, "stable_good", {"training_chance": 0.55, "energy_delta": 1}, "Maintain"),
        ),
        "Training sessions vary with soreness/body load and sleep.",
    )


def _body_signal_awareness_recurring_signal() -> SyntheticUserModel:
    return _model(
        "body_signal_awareness_recurring_signal",
        "Body Signal recurring signal",
        "body_signal_awareness",
        (),
        90,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.16},
        {"day_skip_rate": 0.14, "partial_rate": 0.16},
        _phases(
            (0, 20, "baseline", {"body_warning_chance": 0.12}, "Maintain"),
            (21, 38, "overload_building", {"stress_delta": 2, "energy_delta": -1, "body_warning_chance": 0.45}, "Simplify"),
            (39, 55, "acute_overload", {"stress_delta": 3, "energy_delta": -2, "body_warning_chance": 0.7}, "Recover"),
            (56, 89, "recovery", {"stress_delta": -1, "energy_delta": 1, "body_warning_chance": 0.1}, "Maintain"),
        ),
        "Generic body signal rises under stress and improves with recovery.",
    )


def _pattern_awareness_private_pull() -> SyntheticUserModel:
    return _model(
        "pattern_awareness_private_pull",
        "Pattern Awareness private pull",
        "general_balance",
        ("pattern_awareness_pack",),
        90,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.12, "partial_rate": 0.18},
        _phases(
            (0, 20, "baseline", {"private_pattern_chance": 0.05}, "Maintain"),
            (21, 44, "acute_overload", {"stress_delta": 3, "energy_delta": -2, "private_pattern_chance": 0.7, "bad_sleep_chance": 0.45}, "Simplify or Protect Sleep"),
            (45, 59, "recovery", {"stress_delta": -1, "energy_delta": 1, "private_pattern_chance": 0.12}, "softens"),
            (60, 89, "baseline", {"private_pattern_chance": 0.08}, "Maintain"),
        ),
        "Private pattern signals are explicitly enabled and vary with stress/sleep.",
    )


def _sparse_low_compliance_user() -> SyntheticUserModel:
    return _model(
        "sparse_low_compliance_user",
        "Sparse low-compliance user",
        "general_balance",
        (),
        90,
        {"stress": 5, "energy": 5, "mood": 5, "bad_sleep_chance": 0.22},
        {"day_skip_rate": 0.55, "partial_rate": 0.75},
        _phases(
            (0, 89, "sparse_tracking", {"missing_chance": 0.55, "partial_chance": 0.75}, "limited confidence"),
        ),
        "Checks in a few times weekly and often records only core signals.",
    )


def _long_term_inconsistent_user() -> SyntheticUserModel:
    return _model(
        "long_term_inconsistent_user",
        "Long-term inconsistent user",
        "body_signal_awareness",
        ("life_load_pack",),
        730,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.35, "partial_rate": 0.35},
        _phases(
            (0, 89, "baseline", {}, "Maintain"),
            (90, 180, "long_gap", {"missing_chance": 0.9}, "limited confidence"),
            (181, 220, "profile_switch", {"stress_delta": 1, "body_warning_chance": 0.35}, "profile switch represented as tags"),
            (221, 365, "baseline", {"missing_chance": 0.25}, "Maintain"),
            (366, 430, "acute_overload", {"stress_delta": 3, "energy_delta": -2, "bad_sleep_chance": 0.45, "body_warning_chance": 0.5}, "Simplify"),
            (431, 520, "recovery", {"stress_delta": -1, "energy_delta": 1, "body_warning_chance": 0.1}, "softens"),
            (521, 729, "sparse_tracking", {"missing_chance": 0.55, "partial_chance": 0.55}, "limited confidence"),
        ),
        "Two-year fake history with bursts, long gaps, and profile-switch tags.",
    )


def _general_balance_high_baseline_stress_stable() -> SyntheticUserModel:
    return _model(
        "general_balance_high_baseline_stress_stable",
        "General Balance high baseline stress stable",
        "general_balance",
        (),
        90,
        {"stress": 6, "energy": 6, "mood": 6, "bad_sleep_chance": 0.12},
        {"day_skip_rate": 0.12, "partial_rate": 0.12},
        _phases(
            (0, 44, "baseline", {"stress_delta": 0, "energy_delta": 0}, "stable Maintain"),
            (45, 59, "overload_building", {"stress_delta": 2, "energy_delta": -2}, "Simplify"),
            (60, 89, "recovery", {"stress_delta": -1, "energy_delta": 1}, "softens"),
        ),
        "Stable high-ish stress baseline should not be punished forever.",
    )


def _general_balance_low_baseline_sudden_spike() -> SyntheticUserModel:
    return _model(
        "general_balance_low_baseline_sudden_spike",
        "General Balance low baseline sudden spike",
        "general_balance",
        (),
        90,
        {"stress": 2, "energy": 7, "mood": 7, "bad_sleep_chance": 0.08},
        {"day_skip_rate": 0.1, "partial_rate": 0.1},
        _phases(
            (0, 29, "stable_good", {"stress_delta": 0, "energy_delta": 1}, "Push or Maintain"),
            (30, 39, "acute_overload", {"stress_delta": 6, "energy_delta": -4, "bad_sleep_chance": 0.4}, "Simplify"),
            (40, 89, "recovery", {"stress_delta": 0, "energy_delta": 0}, "Maintain"),
        ),
        "Low baseline should make sudden stress/load spikes visible.",
    )


def _general_balance_good_sleep_high_life_load() -> SyntheticUserModel:
    return _model(
        "general_balance_good_sleep_high_life_load",
        "General Balance good sleep high life load",
        "general_balance",
        ("life_load_pack",),
        90,
        {"stress": 6, "energy": 5, "mood": 5, "bad_sleep_chance": 0.02},
        {"day_skip_rate": 0.1, "partial_rate": 0.12},
        _phases(
            (0, 44, "overload_building", {"project_overrun_chance": 0.55, "stress_delta": 1}, "Simplify despite sleep"),
            (45, 89, "recovery", {"project_overrun_chance": 0.1, "stress_delta": -1, "energy_delta": 1}, "Maintain"),
        ),
        "Good sleep should not hide high life load.",
    )


def _general_balance_poor_sleep_low_demand() -> SyntheticUserModel:
    return _model(
        "general_balance_poor_sleep_low_demand",
        "General Balance poor sleep low demand",
        "general_balance",
        (),
        90,
        {"stress": 2, "energy": 5, "mood": 6, "bad_sleep_chance": 0.45},
        {"day_skip_rate": 0.1, "partial_rate": 0.12},
        _phases(
            (0, 89, "baseline", {"stress_delta": 0, "energy_delta": 0, "bad_sleep_chance": 0.45}, "Protect sleep without alarm"),
        ),
        "Poor sleep with low demand should protect sleep without panic.",
    )


def _work_stress_weekend_recovery() -> SyntheticUserModel:
    return _model(
        "work_stress_weekend_recovery",
        "Work Stress weekend recovery",
        "work_stress",
        (),
        90,
        {"stress": 5, "energy": 6, "mood": 6, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.1, "partial_rate": 0.15},
        _phases(
            (0, 20, "acute_overload", {"stress_delta": 3, "energy_delta": -2, "project_overrun_chance": 0.55}, "Simplify"),
            (21, 34, "weekend_recovery", {"stress_delta": -2, "energy_delta": 1, "project_overrun_chance": 0.05}, "Maintain"),
            (35, 89, "baseline", {"stress_delta": 0}, "Maintain"),
        ),
        "Weekend/after-recovery work guidance should acknowledge improvement.",
    )


def _training_recovery_overenthusiastic_athlete() -> SyntheticUserModel:
    return _model(
        "training_recovery_overenthusiastic_athlete",
        "Training Recovery overenthusiastic athlete",
        "training_recovery",
        (),
        90,
        {"stress": 3, "energy": 8, "mood": 7, "bad_sleep_chance": 0.16},
        {"day_skip_rate": 0.1, "partial_rate": 0.12},
        _phases(
            (0, 29, "stable_good", {"training_chance": 0.75, "energy_delta": 1}, "Maintain or Push"),
            (30, 59, "acute_overload", {"training_chance": 0.95, "energy_delta": 0, "body_warning_chance": 0.45}, "not always Push"),
            (60, 89, "recovery", {"training_chance": 0.4, "energy_delta": 0}, "Maintain"),
        ),
        "High energy plus high training load should not always become Push.",
    )


def _custom_avoidance_risk_small_start() -> SyntheticUserModel:
    return _model(
        "custom_avoidance_risk_small_start",
        "Custom small-start pattern",
        "custom_stub",
        (),
        90,
        {"stress": 6, "energy": 4, "mood": 5, "bad_sleep_chance": 0.22},
        {"day_skip_rate": 0.18, "partial_rate": 0.25},
        _phases(
            (0, 29, "baseline", {"stress_delta": 0}, "Maintain"),
            (30, 59, "overload_building", {"stress_delta": 2, "energy_delta": -1}, "small start"),
            (60, 89, "recovery", {"stress_delta": -1, "energy_delta": 1}, "softens"),
        ),
        "Custom profile should prefer a small-start action under avoidant load.",
    )


def _family_load_carrier() -> SyntheticUserModel:
    return _model(
        "family_load_carrier",
        "Family/admin load carrier",
        "general_balance",
        ("life_load_pack",),
        90,
        {"stress": 5, "energy": 5, "mood": 5, "bad_sleep_chance": 0.1},
        {"day_skip_rate": 0.12, "partial_rate": 0.16},
        _phases(
            (0, 44, "overload_building", {"stress_delta": 1, "project_overrun_chance": 0.5}, "Simplify even if sleep okay"),
            (45, 89, "recovery", {"stress_delta": -1, "project_overrun_chance": 0.08}, "Maintain"),
        ),
        "Obligation/family/admin load can justify Simplify even when sleep is okay.",
    )


def _high_to_recovery_transition() -> SyntheticUserModel:
    return _model(
        "high_to_recovery_transition",
        "High load to recovery transition",
        "general_balance",
        (),
        90,
        {"stress": 5, "energy": 5, "mood": 5, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.08, "partial_rate": 0.1},
        _phases(
            (0, 13, "acute_overload", {"stress_delta": 3, "energy_delta": -2, "bad_sleep_chance": 0.55, "shutdown_miss_chance": 0.65}, "Simplify or Protect Sleep"),
            (14, 23, "recovery", {"stress_delta": -2, "energy_delta": 2, "bad_sleep_chance": 0.04, "shutdown_miss_chance": 0.05}, "softens"),
            (24, 89, "baseline", {"stress_delta": 0, "energy_delta": 0}, "Maintain"),
        ),
        "High load should soften when recent sleep, stress, and energy recover.",
    )


def _stable_to_sudden_spike() -> SyntheticUserModel:
    return _model(
        "stable_to_sudden_spike",
        "Stable period to sudden spike",
        "work_stress",
        (),
        90,
        {"stress": 3, "energy": 7, "mood": 7, "bad_sleep_chance": 0.08},
        {"day_skip_rate": 0.08, "partial_rate": 0.1},
        _phases(
            (0, 29, "baseline", {"stress_delta": 0, "energy_delta": 0, "project_overrun_chance": 0.02}, "Maintain"),
            (30, 34, "acute_overload", {"stress_delta": 5, "energy_delta": -4, "project_overrun_chance": 0.85, "decompression_miss_chance": 0.8}, "escalates"),
            (35, 89, "recovery", {"stress_delta": -1, "energy_delta": 1, "project_overrun_chance": 0.05}, "softens"),
        ),
        "Old calm history should not hide a sudden work/life spike.",
    )


def _repeated_load_waves() -> SyntheticUserModel:
    return _model(
        "repeated_load_waves",
        "Repeated load waves",
        "general_balance",
        (),
        180,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.15},
        {"day_skip_rate": 0.1, "partial_rate": 0.12},
        _phases(
            (0, 13, "baseline", {}, "Maintain"),
            (14, 20, "acute_overload", {"stress_delta": 4, "energy_delta": -3, "bad_sleep_chance": 0.5}, "Simplify"),
            (21, 34, "recovery", {"stress_delta": -1, "energy_delta": 1}, "softens"),
            (35, 41, "acute_overload", {"stress_delta": 4, "energy_delta": -3, "bad_sleep_chance": 0.5}, "Simplify"),
            (42, 69, "recovery", {"stress_delta": -1, "energy_delta": 1}, "softens"),
            (70, 83, "baseline", {}, "Maintain"),
            (84, 90, "acute_overload", {"stress_delta": 4, "energy_delta": -3, "bad_sleep_chance": 0.5}, "Simplify"),
            (91, 124, "recovery", {"stress_delta": -1, "energy_delta": 1}, "softens"),
            (125, 131, "acute_overload", {"stress_delta": 4, "energy_delta": -3, "bad_sleep_chance": 0.5}, "Simplify"),
            (132, 179, "recovery", {"stress_delta": -1, "energy_delta": 1}, "softens"),
        ),
        "Guidance should follow repeated load/recovery waves without getting stuck.",
    )


def _bad_phase_then_long_gap() -> SyntheticUserModel:
    return _model(
        "bad_phase_then_long_gap",
        "Bad phase then long gap",
        "general_balance",
        (),
        120,
        {"stress": 5, "energy": 5, "mood": 5, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.1, "partial_rate": 0.12},
        _phases(
            (0, 6, "acute_overload", {"stress_delta": 4, "energy_delta": -3, "bad_sleep_chance": 0.65}, "Simplify"),
            (7, 66, "long_gap", {"missing_chance": 1.0}, "no check-ins"),
            (67, 75, "return_after_gap", {"minimal_signal_ids": ("energy.energy", "mental.stress"), "stress_delta": 0, "energy_delta": 0}, "limited confidence"),
            (76, 119, "baseline", {}, "Maintain"),
        ),
        "Old bad week should not dominate after a long silence and sparse return.",
    )


def _good_phase_then_long_gap() -> SyntheticUserModel:
    return _model(
        "good_phase_then_long_gap",
        "Good phase then long gap",
        "general_balance",
        (),
        140,
        {"stress": 2, "energy": 8, "mood": 7, "bad_sleep_chance": 0.04},
        {"day_skip_rate": 0.08, "partial_rate": 0.1},
        _phases(
            (0, 29, "stable_good", {"stress_delta": 0, "energy_delta": 1, "bad_sleep_chance": 0.02}, "Push or Maintain"),
            (30, 119, "long_gap", {"missing_chance": 1.0}, "no check-ins"),
            (120, 129, "return_after_gap", {"minimal_signal_ids": ("energy.energy", "mental.stress"), "stress_delta": 1, "energy_delta": -1}, "limited confidence"),
            (130, 139, "baseline", {"stress_delta": 0, "energy_delta": 0}, "Maintain"),
        ),
        "Old good history should not justify Push after a long silence.",
    )


def _bad_day_only_logger() -> SyntheticUserModel:
    return _model(
        "bad_day_only_logger",
        "Bad-day-only logger",
        "work_stress",
        (),
        120,
        {"stress": 5, "energy": 5, "mood": 5, "bad_sleep_chance": 0.18},
        {"day_skip_rate": 0.45, "partial_rate": 0.25},
        _phases(
            (0, 119, "biased_bad_logging", {"missing_chance": 0.55, "stress_delta": 3, "energy_delta": -2, "project_overrun_chance": 0.6}, "biased overload samples"),
        ),
        "Mostly logs high-stress days; confidence should not imply always overloaded.",
    )


def _good_day_only_logger() -> SyntheticUserModel:
    return _model(
        "good_day_only_logger",
        "Good-day-only logger",
        "general_balance",
        (),
        120,
        {"stress": 3, "energy": 7, "mood": 7, "bad_sleep_chance": 0.08},
        {"day_skip_rate": 0.45, "partial_rate": 0.2},
        _phases(
            (0, 119, "biased_good_logging", {"missing_chance": 0.5, "stress_delta": -1, "energy_delta": 1, "bad_sleep_chance": 0.03}, "biased good samples"),
        ),
        "Mostly logs good days; confidence should not become overconfidently positive.",
    )


def _partial_after_gap_user() -> SyntheticUserModel:
    return _model(
        "partial_after_gap_user",
        "Partial check-ins after gap",
        "body_signal_awareness",
        (),
        120,
        {"stress": 4, "energy": 6, "mood": 6, "bad_sleep_chance": 0.16},
        {"day_skip_rate": 0.12, "partial_rate": 0.2},
        _phases(
            (0, 20, "baseline", {"body_warning_chance": 0.12}, "Maintain"),
            (21, 70, "long_gap", {"missing_chance": 1.0}, "no check-ins"),
            (71, 80, "return_after_gap", {"minimal_signal_ids": ("energy.energy",), "stress_delta": 0, "energy_delta": -1}, "limited confidence"),
            (81, 119, "baseline", {"body_warning_chance": 0.12}, "Maintain"),
        ),
        "Return after gap with very partial data should stay uncertainty-aware.",
    )


def _model(
    model_id: str,
    name: str,
    profile_id: str,
    optional_packs: tuple[str, ...],
    duration_days: int,
    baseline_traits: Mapping[str, Any],
    missingness_pattern: Mapping[str, Any],
    phases: tuple[SyntheticPhase, ...],
    notes: str,
) -> SyntheticUserModel:
    return SyntheticUserModel(
        id=model_id,
        name=name,
        profile_id=profile_id,
        optional_packs=optional_packs,
        duration_days=duration_days,
        baseline_traits=dict(baseline_traits),
        missingness_pattern=dict(missingness_pattern),
        event_schedule=phases,
        expectations=tuple(_expectation(model_id, profile_id, phase) for phase in phases),
        expected_behavior_notes=notes,
    )


def _phases(*items: tuple[int, int, str, Mapping[str, Any], str]) -> tuple[SyntheticPhase, ...]:
    return tuple(SyntheticPhase(name=name, start_day=start, end_day=end, tendencies=dict(tendencies), expected_guidance=expected) for start, end, name, tendencies, expected in items)


def _expectation(model_id: str, profile_id: str, phase: SyntheticPhase) -> GuidanceExpectation:
    phase_name = phase.name
    allowed = ("Maintain", "Push") if phase_name in {"baseline", "stable_good", "weekend_recovery", "recovery"} else ("Simplify", "Recover", "Protect Sleep", "Maintain")
    if phase_name in {"sparse_tracking", "long_gap"}:
        allowed = ("Simplify", "Maintain")
    required_drivers = {
        "work_stress": ("work pressure", "decompression", "stress", "energy"),
        "training_recovery": ("training", "energy", "sleep", "recovery"),
        "body_signal_awareness": ("body signal", "stress", "energy"),
    }.get(profile_id, ("stress", "energy", "sleep", "recovery", "private pattern"))
    return GuidanceExpectation(
        scenario_id=f"{model_id}:{phase_name}",
        phase_name=phase_name,
        allowed_labels=allowed,
        discouraged_labels=("Push",) if phase_name in {"acute_overload", "overload_building"} else (),
        required_driver_any_of=required_drivers,
        forbidden_driver_any_of=PROFILE_FORBIDDEN_DRIVER_TERMS.get(profile_id, ()),
        expected_action_families=("maintain", "push", "simplify", "recover", "protect_sleep"),
        expected_confidence_behavior="limited" if phase_name in {"sparse_tracking", "long_gap"} else "normal",
        required_copy_traits=("concrete_action",),
        recency_expectation="soften after recovery" if phase_name == "recovery" else "",
    )


def _phase_for_day(model: SyntheticUserModel, day_index: int) -> SyntheticPhase:
    for phase in model.event_schedule:
        if phase.contains(day_index):
            return phase
    raise ValueError(f"No phase covers day {day_index} for {model.id}")


def _filter_active_inputs(inputs: Mapping[str, Any], profile_id: str, optional_packs: tuple[str, ...]) -> dict[str, Any]:
    active = set(_active_signal_ids_for_profile(profile_id, optional_packs))
    return {signal_id: value for signal_id, value in inputs.items() if signal_id in active or signal_id.startswith("placeholder.")}


def _active_signal_ids_for_profile(profile_id: str, optional_packs: tuple[str, ...]) -> tuple[str, ...]:
    profile = PROFILE_TEMPLATE_METADATA[profile_id]
    hidden = set(profile.hidden_signal_ids) | set(profile.disabled_signal_ids)
    signal_ids = list(profile.visible_signal_ids + profile.optional_signal_ids)
    if "life_load_pack" in optional_packs:
        signal_ids.extend(("work.work_intensity", "work.project_overrun", "work.home_office", "relationship.family_stress"))
    if "pattern_awareness_pack" in optional_packs:
        signal_ids.extend(("nutrition.alcohol", "nutrition.binge", "evening.phone_after_21", "evening.evening_chain_broken", "work.project_overrun"))
    return tuple(dict.fromkeys(signal_id for signal_id in signal_ids if signal_id in SIGNALS_BY_ID and signal_id not in hidden))


def _required_signal_ids(profile_id: str) -> tuple[str, ...]:
    profile = PROFILE_TEMPLATE_METADATA[profile_id]
    inactive = set(profile.hidden_signal_ids) | set(profile.disabled_signal_ids)
    return tuple(signal_id for signal_id in profile.required_for_confidence_signal_ids if signal_id not in inactive)


def _jitter(base: Any, delta: Any, rng: random.Random, spread: int) -> int:
    return int(base) + int(delta) + rng.randint(-spread, spread)


def _bounded_int(value: int, low: int, high: int) -> int:
    return min(high, max(low, int(value)))


def _work_intensity(stress: int, phase_name: str, weekday: int) -> str:
    if weekday >= 5:
        return "low"
    if phase_name in {"acute_overload", "second_crunch"} or stress >= 7:
        return "high"
    if stress >= 5:
        return "medium"
    return "low"


def _tags_for_inputs(inputs: Mapping[str, Any], weekday: int) -> tuple[str, ...]:
    tags = ["weekend" if weekday >= 5 else "weekday"]
    if inputs.get("work.project_overrun") is True:
        tags.append("project_overrun")
    if inputs.get("evening.evening_chain_broken") is True:
        tags.append("private_pattern")
    if int(inputs.get("training.activity_duration_min") or 0) >= 45:
        tags.append("training")
    if inputs.get("body.migraine_warning") is True:
        tags.append("body_signal")
    return tuple(tags)


def _day_severity(day: SyntheticDay) -> int:
    if not day.inputs:
        return 1
    severity = 0
    stress = int(day.inputs.get("mental.stress") or 0)
    energy = int(day.inputs.get("energy.energy") or 5)
    if day.inputs.get("core.sleep_ok") is False:
        severity += 1
    if stress >= 7:
        severity += 1
    if energy <= 3:
        severity += 1
    if day.inputs.get("recovery.shutdown_done") is False or day.inputs.get("recovery.decompression_done") is False:
        severity += 1
    if int(day.inputs.get("training.activity_duration_min") or 0) >= 60:
        severity += 1
    if day.inputs.get("body.migraine_warning") is True:
        severity += 1
    if day.inputs.get("evening.evening_chain_broken") is True:
        severity += 1
    return min(5, severity)


def _expected_driver_terms(day: SyntheticDay) -> tuple[str, ...]:
    terms: list[str] = []
    if int(day.inputs.get("mental.stress") or 0) >= 7:
        terms.append("stress")
        if day.profile_id == "work_stress":
            terms.append("work pressure")
    if int(day.inputs.get("energy.energy") or 10) <= 3:
        terms.append("energy")
    if day.inputs.get("core.sleep_ok") is False:
        terms.append("sleep")
    if int(day.inputs.get("training.activity_duration_min") or 0) >= 45:
        terms.append("training")
    if day.inputs.get("body.migraine_warning") is True:
        terms.append("body signal")
    if day.inputs.get("evening.evening_chain_broken") is True:
        terms.append("private pattern")
    return tuple(terms)


def _severity(output: GuidanceOutput) -> int:
    return LABEL_SEVERITY[output.label]


def _replace_input(day: SyntheticDay, signal_id: str, value: Any) -> SyntheticDay:
    return _replace_many(day, {signal_id: value})


def _replace_many(day: SyntheticDay, values: Mapping[str, Any]) -> SyntheticDay:
    inputs = dict(day.inputs)
    inputs.update(values)
    return SyntheticDay(
        date=day.date,
        profile_id=day.profile_id,
        inputs=inputs,
        missing_inputs=tuple(signal_id for signal_id in day.missing_inputs if signal_id not in values),
        tags=day.tags,
        phase_name=day.phase_name,
        notes=day.notes,
    )


def _profile_leakage_count(outputs: Iterable[GuidanceOutput]) -> int:
    total = 0
    for output in outputs:
        forbidden = PROFILE_FORBIDDEN_DRIVER_TERMS.get(output.profile_id, ())
        text = " ".join(output.top_drivers).lower()
        if any(term in text for term in forbidden):
            total += 1
    return total


def _contains_forbidden(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in FORBIDDEN_SENSITIVE_TERMS)


def _guidance_text(output: GuidanceOutput) -> str:
    return " ".join(
        (
            output.label,
            " ".join(output.top_drivers),
            output.confidence_note,
            output.primary_action,
            output.warning_sensitive_text,
            output.recent_change,
        )
    )


def _stuck_state_count(outputs: Iterable[GuidanceOutput]) -> int:
    return len(tuple(_stuck_state_days(tuple(outputs), max_run=10)))


def _stuck_state_days(outputs: tuple[GuidanceOutput, ...], max_run: int) -> tuple[str, ...]:
    affected: list[str] = []
    current_label = None
    current_run: list[GuidanceOutput] = []
    for output in outputs:
        if output.label != current_label:
            current_label = output.label
            current_run = [output]
            continue
        current_run.append(output)
        if len(current_run) > max_run and output.label in {"Protect Sleep", "Simplify", "Maintain"}:
            affected.append(output.date)
    return tuple(affected)


def _classified_stuck_state_days(
    days: tuple[SyntheticDay, ...],
    outputs: tuple[GuidanceOutput, ...],
    max_run: int,
) -> tuple[tuple[str, ...], str]:
    affected: list[str] = []
    classifications: list[str] = []
    current_label = None
    current_run: list[tuple[SyntheticDay, GuidanceOutput]] = []
    for day, output in zip(days, outputs):
        if output.label != current_label:
            current_label = output.label
            current_run = [(day, output)]
            continue
        current_run.append((day, output))
        if len(current_run) <= max_run:
            continue
        run_days = tuple(item[0] for item in current_run[-max_run:])
        severities = tuple(_day_severity(item) for item in run_days if item.inputs)
        empty_count = sum(1 for item in run_days if not item.inputs)
        first_severity = _day_severity(run_days[0])
        last_severity = _day_severity(run_days[-1])
        if output.label == "Maintain":
            if severities and max(severities) <= 1:
                classifications.append("stable_maintain_ok")
                continue
            if last_severity >= 2 or last_severity > first_severity:
                affected.append(output.date)
                classifications.append("neutral_despite_worsening")
        elif output.label in {"Protect Sleep", "Simplify", "Recover"}:
            if empty_count >= max_run // 2:
                affected.append(output.date)
                classifications.append("missing_data_loop")
            elif last_severity <= 1 and (last_severity < first_severity or output.label == "Protect Sleep"):
                affected.append(output.date)
                classifications.append("severe_stuck")
            elif output.label == "Simplify" and severities and max(severities) <= 1:
                affected.append(output.date)
                classifications.append("needs_review")
    if affected:
        ordered = ("severe_stuck", "neutral_despite_worsening", "missing_data_loop", "needs_review")
        classification = next((item for item in ordered if item in classifications), "needs_review")
        return tuple(dict.fromkeys(affected)), classification
    if classifications and set(classifications) == {"stable_maintain_ok"}:
        return (), "stable_maintain_ok"
    return (), ""


def _recency_mismatch_count(days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> int:
    return sum(
        1
        for day, output in zip(days, outputs)
        if day.phase_name == "recovery" and _day_severity(day) <= 1 and output.label == "Protect Sleep"
    )


def _recent_recovery_responsiveness(days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> str:
    recovery_pairs = [(day, output) for day, output in zip(days, outputs) if day.phase_name == "recovery" and day.inputs]
    if not recovery_pairs:
        return "not_applicable"
    severe = sum(1 for _, output in recovery_pairs if output.label in {"Protect Sleep", "Simplify"})
    return "responsive" if severe / len(recovery_pairs) < 0.5 else "review"


def _old_drift_overweighting(days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> str:
    return "review" if _recency_mismatch_count(days, outputs) else "not_detected"


def _gap_lengths(days: tuple[SyntheticDay, ...]) -> tuple[int, ...]:
    lengths: list[int] = []
    current = 0
    for day in days:
        if day.inputs:
            if current:
                lengths.append(current)
            current = 0
        else:
            current += 1
    if current:
        lengths.append(current)
    return tuple(lengths)


def _days_since_last_checkin(days: tuple[SyntheticDay, ...]) -> list[int | None]:
    result: list[int | None] = []
    since: int | None = None
    for day in days:
        if day.inputs:
            result.append(since)
            since = 0
        else:
            since = 1 if since is None else since + 1
            result.append(since)
    return result


def _post_gap_dates(days: tuple[SyntheticDay, ...], *, min_gap: int, window: int) -> tuple[str, ...]:
    dates: list[str] = []
    gap = 0
    capture_remaining = 0
    for day in days:
        if not day.inputs:
            gap += 1
            continue
        if gap >= min_gap:
            capture_remaining = window
        gap = 0
        if capture_remaining > 0:
            dates.append(day.date)
            capture_remaining -= 1
    return tuple(dates)


def _output_by_date(outputs: tuple[GuidanceOutput, ...], date_value: str) -> GuidanceOutput | None:
    return next((output for output in outputs if output.date == date_value), None)


def _day_by_date(days: tuple[SyntheticDay, ...], date_value: str) -> SyntheticDay | None:
    return next((day for day in days if day.date == date_value), None)


def _stale_history_influence_count(days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> int:
    affected = 0
    for date_value in _post_gap_dates(days, min_gap=30, window=3):
        day = _day_by_date(days, date_value)
        output = _output_by_date(outputs, date_value)
        if day is None or output is None:
            continue
        if output.label == "Push" or (
            output.label in {"Protect Sleep", "Simplify"}
            and output.confidence == "normal"
            and _day_severity(day) <= 1
            and len(day.inputs) <= 2
            and "Missing data" not in output.top_drivers
        ):
            affected += 1
    return affected


def _phase_transition_response_days(days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> list[str]:
    responded: list[str] = []
    for index in range(1, len(days)):
        if days[index].phase_name == days[index - 1].phase_name:
            continue
        previous = outputs[index - 1]
        current = outputs[index]
        severity_delta = _day_severity(days[index]) - _day_severity(days[index - 1])
        label_delta = LABEL_SEVERITY[current.label] - LABEL_SEVERITY[previous.label]
        if severity_delta == 0 or severity_delta * label_delta >= 0:
            responded.append(current.date)
    return responded


def _sampling_bias_score(days: tuple[SyntheticDay, ...], phase_name: str) -> float:
    phase_days = [day for day in days if day.phase_name == phase_name]
    if not phase_days:
        return 0.0
    logged = [day for day in phase_days if day.inputs]
    return round(1.0 - (len(logged) / len(phase_days)), 3)


def _limited_confidence_rate(outputs: tuple[GuidanceOutput, ...]) -> float:
    if not outputs:
        return 0.0
    return round(sum(1 for output in outputs if output.confidence == "limited") / len(outputs), 3)


def _oracle_result(
    name: str,
    affected: tuple[str, ...],
    pass_text: str,
    fail_text: str,
    *,
    warning_limit: int = 0,
    classification: str = "",
) -> OracleResult:
    status: OracleStatus = "pass"
    if len(affected) > warning_limit:
        status = "fail"
    elif affected:
        status = "warning"
    return OracleResult(
        oracle=name,
        status=status,
        affected_days=affected,
        explanation=pass_text if status == "pass" else fail_text,
        suggested_review_sample=affected[:5],
        classification=classification,
    )


def _thresholds() -> Mapping[str, Any]:
    return {
        "general_balance_stable": {
            "protect_sleep_rate_max": 0.25,
            "maintain_rate_min": 0.25,
        },
        "sparse_low_compliance_user": {
            "limited_confidence_expected": True,
        },
        "all_models": {
            "sensitive_word_violation_count": 0,
            "profile_leakage_count": 0,
        },
    }


def _simulation_result_payload(result: SimulationResult) -> Mapping[str, Any]:
    return {
        "user_model_id": result.user_model_id,
        "duration_days": result.duration_days,
        "generated_days": [asdict(day) for day in result.generated_days],
        "guidance_outputs": [asdict(output) for output in result.guidance_outputs],
        "summary_metrics": dict(result.summary_metrics),
        "anomalies": [asdict(anomaly) for anomaly in result.anomalies],
        "oracle_results": [asdict(oracle) for oracle in result.oracle_results],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_review_markdown(path: Path, results: tuple[SimulationResult, ...]) -> None:
    lines = ["# Life Load Synthetic User Review Samples", "", "Synthetic fake data only.", ""]
    for result in results:
        lines.extend((f"## {result.user_model_id} ({result.duration_days} days)", ""))
        for sample in result.review_samples[:20]:
            lines.extend(
                (
                    f"- {sample['day']} [{sample['phase']}] {sample['guidance_label']}: "
                    f"{', '.join(sample['drivers']) or 'no drivers'}; reason: {sample['why_selected']}",
                )
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_report_markdown(path: Path, results: tuple[SimulationResult, ...], summary: Mapping[str, Any]) -> None:
    lines = [
        "# Life Load Synthetic User Simulation Report",
        "",
        "This report uses synthetic fake data only. It is designed to catch formula, copy, profile, and missingness regressions. It does not prove clinical or real-world efficacy.",
        "",
        f"- Simulations: {summary['simulation_count']}",
        f"- Total generated days: {summary['total_generated_days']}",
        "",
        "## Results",
        "",
    ]
    for result in results:
        metrics = result.summary_metrics
        lines.extend(
            (
                f"### {result.user_model_id} ({result.duration_days} days)",
                f"- labels: {metrics['guidance_label_distribution']}",
                f"- confidence: {metrics['confidence_distribution']}",
                f"- missing data rate: {metrics['missing_data_rate']}",
                f"- anomalies: {len(result.anomalies)}",
                "",
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_readme(path: Path, results: tuple[SimulationResult, ...], seed: int) -> None:
    lines = [
        "# Life Load Synthetic User Evaluation",
        "",
        "Synthetic data only. No real diary, health, family, work, or private user data is included.",
        "",
        "This package is intended to catch formula, copy, profile, missingness, and temporal-response regressions. It does not prove clinical or real-world efficacy.",
        "",
        f"- Seed: {seed}",
        f"- Models: {', '.join(sorted({result.user_model_id for result in results}))}",
        f"- Durations: {', '.join(str(result.duration_days) for result in results)}",
        "",
        "## Top Anomalies",
        "",
    ]
    anomalies = [(result.user_model_id, anomaly) for result in results for anomaly in result.anomalies]
    if not anomalies:
        lines.append("- No oracle failures or warnings in this run.")
    else:
        for user_model_id, anomaly in anomalies[:20]:
            lines.append(f"- {user_model_id}: {anomaly.oracle} {anomaly.status} on {len(anomaly.affected_days)} day(s)")
    lines.extend(
        (
            "",
            "## Recommended Next Action",
            "",
            "Review oracle warnings and sampled days before changing production scoring. Treat findings as hypothesis-generating, not proof of real-world behavior.",
        )
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv_summary(path: Path, results: tuple[SimulationResult, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "user_model_id",
                "duration_days",
                "missing_data_rate",
                "push_rate",
                "maintain_rate",
                "recover_rate",
                "simplify_rate",
                "protect_sleep_rate",
                "profile_leakage_count",
                "sensitive_word_violation_count",
                "stuck_state_count",
            ),
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "user_model_id": result.user_model_id,
                    "duration_days": result.duration_days,
                    **{key: result.summary_metrics[key] for key in writer.fieldnames[2:]},
                }
            )
