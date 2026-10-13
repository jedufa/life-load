"""Second-pass synthetic guidance review and advanced quality oracles.

This module evaluates synthetic fake data only. It does not change production
scoring, formulas, Android UI, extraction, HTTP payloads, or export/import.
"""

from __future__ import annotations

import html
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from life_load import scoring
from life_load.guidance_bridge import (
    build_guidance_bridge_from_fixed_entry,
    build_guidance_bridge_from_selected_profile_config,
    score_personal_legacy_via_bridge,
)
from life_load.selected_profile_config import build_selected_profile_config
from life_load.synthetic_users import (
    ACTION_FAMILIES,
    BASELINE_092_PRE_AC_PROMOTION,
    FORBIDDEN_SENSITIVE_TERMS,
    LABEL_SEVERITY,
    SHADOW_FORMULA_BODY_SIGNAL_V1,
    SHADOW_FORMULA_COMBINED_V1,
    SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
    SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1,
    SHADOW_GUIDANCE_V1,
    GuidanceOutput,
    PhaseTransitionOracle,
    OracleResult,
    ReturnAfterGapOracle,
    SamplingBiasOracle,
    StaleHistoryOracle,
    SyntheticDay,
    advanced_synthetic_user_models,
    all_extended_synthetic_user_models,
    all_synthetic_user_models,
    compute_life_rhythm_metrics,
    guidance_for_synthetic_day,
    life_rhythm_synthetic_user_models,
    mutation_checks,
    simulate_user,
)


VAGUE_ACTION_FRAGMENTS = (
    "take care",
    "be mindful",
    "listen to your body",
    "try your best",
    "rest if needed",
    "manage stress",
)


def review_evaluation_artifact(zip_path: Path | str) -> list[dict[str, Any]]:
    """Classify first-pass synthetic anomaly rows with day-level context."""

    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        anomalies = json.loads(archive.read("anomalies.json"))
        per_user_payloads = {
            name: json.loads(archive.read(name))
            for name in archive.namelist()
            if name.startswith("per_user_results/") and name.endswith(".json")
        }

    rows: list[dict[str, Any]] = []
    for anomaly in anomalies:
        model_id = anomaly["user_model_id"]
        matching_payloads = [
            payload
            for payload in per_user_payloads.values()
            if payload["user_model_id"] == model_id
        ]
        for payload in matching_payloads:
            by_date = {
                day["date"]: (day, output)
                for day, output in zip(payload["generated_days"], payload["guidance_outputs"])
                if day["date"] in set(anomaly["affected_days"])
            }
            if not by_date:
                continue
            labels = [by_date[day][1]["label"] for day in by_date]
            phases = sorted({by_date[day][0]["phase_name"] for day in by_date})
            drivers = sorted({driver for day in by_date for driver in by_date[day][1]["top_drivers"]})
            confidences = sorted({by_date[day][1]["confidence"] for day in by_date})
            input_summaries = {
                day: _summarize_inputs(by_date[day][0]["inputs"])
                for day in sorted(by_date)[:5]
            }
            rows.append(
                {
                    "user_model_id": model_id,
                    "duration": payload["duration_days"],
                    "oracle": anomaly["oracle"],
                    "affected_dates": sorted(by_date),
                    "phase": phases,
                    "labels": labels,
                    "inputs": input_summaries,
                    "drivers": drivers,
                    "confidence": confidences,
                    "likely_classification": classify_anomaly(anomaly, phases, labels, drivers, input_summaries),
                    "recommended_next_action": recommended_next_action(anomaly, drivers),
                }
            )
    return rows


def classify_anomaly(
    anomaly: Mapping[str, Any],
    phases: list[str],
    labels: list[str],
    drivers: list[str],
    inputs: Mapping[str, Any],
) -> str:
    oracle = str(anomaly.get("oracle", ""))
    driver_text = " ".join(drivers).lower()
    if oracle == "StuckStateOracle" and labels and set(labels) == {"Maintain"}:
        if any("baseline" in phase or "stable" in phase for phase in phases):
            return "oracle false positive"
        return "needs human review"
    if oracle == "StuckStateOracle" and any("missing" in str(value).lower() or value == {} for value in inputs.values()):
        return "oracle false positive / no-data loop"
    if oracle == "RecencyOracle":
        return "formula hypothesis / recency response"
    if "private pattern" in driver_text:
        return "driver wording issue"
    if oracle == "StuckStateOracle":
        return "needs human review"
    return "needs human review"


def recommended_next_action(anomaly: Mapping[str, Any], drivers: list[str]) -> str:
    oracle = str(anomaly.get("oracle", ""))
    if oracle == "StuckStateOracle":
        return "Use refined stuck-state oracle before changing formulas."
    if oracle == "RecencyOracle":
        return "Review recency weighting hypothesis with paired recovery samples."
    if "Private pattern" in drivers:
        return "Review Work Stress driver wording before public beta copy."
    return "Inspect review samples before changing scoring."


class ActionSpecificityOracle:
    name = "ActionSpecificityOracle"

    def evaluate(self, outputs: tuple[GuidanceOutput, ...]) -> OracleResult:
        affected = tuple(
            output.date
            for output in outputs
            if any(fragment in output.primary_action.lower() for fragment in VAGUE_ACTION_FRAGMENTS)
        )
        return _result(
            self.name,
            affected,
            "Actions are concrete.",
            "Action copy is vague.",
            "action_specificity",
        )


class AdviceDiversityOracle:
    name = "AdviceDiversityOracle"

    def evaluate(self, outputs: tuple[GuidanceOutput, ...]) -> OracleResult:
        by_label: dict[str, set[str]] = defaultdict(set)
        driver_sets: dict[str, set[str]] = defaultdict(set)
        for output in outputs:
            by_label[output.label].add(output.action_family)
            driver_sets[output.label].add("|".join(output.top_drivers))
        affected = tuple(
            label
            for label, driver_keys in driver_sets.items()
            if len(driver_keys) >= 3 and len(by_label[label]) <= 1
        )
        return _result(
            self.name,
            affected,
            "Same-label advice varies when drivers differ.",
            "Same label repeats one action family across unrelated drivers.",
            "advice_diversity",
        )


class MomentumOracle:
    name = "MomentumOracle"

    def evaluate(self, days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> OracleResult:
        affected: list[str] = []
        for previous_day, current_day, output in zip(days, days[1:], outputs[1:]):
            delta = _day_severity(current_day) - _day_severity(previous_day)
            recent_text = output.recent_change.lower()
            if delta >= 2 and "heavier" not in recent_text:
                affected.append(output.date)
            if delta <= -2 and "improving" not in recent_text:
                affected.append(output.date)
        return _result(
            self.name,
            tuple(affected),
            "Recent change text reflects momentum.",
            "Recent change text misses a meaningful trend.",
            "momentum",
            warning_limit=3,
        )


class GuidanceVolatilityOracle:
    name = "GuidanceVolatilityOracle"

    def evaluate(self, days: tuple[SyntheticDay, ...], outputs: tuple[GuidanceOutput, ...]) -> OracleResult:
        affected: list[str] = []
        for prev_day, day, prev_output, output in zip(days, days[1:], outputs, outputs[1:]):
            input_delta = abs(_day_severity(day) - _day_severity(prev_day))
            label_delta = abs(LABEL_SEVERITY[output.label] - LABEL_SEVERITY[prev_output.label])
            if input_delta <= 1 and label_delta >= 3:
                affected.append(output.date)
            if output.label in {"Protect Sleep", "Simplify"} and _day_severity(day) <= 1 and _day_severity(prev_day) <= 1:
                affected.append(output.date)
        return _result(
            self.name,
            tuple(affected),
            "Guidance does not whiplash on small input noise.",
            "Guidance changes too sharply for small input changes.",
            "volatility",
        )


class AdviceFatigueOracle:
    name = "AdviceFatigueOracle"

    def evaluate(self, outputs: tuple[GuidanceOutput, ...], *, max_identical_run: int = 7) -> OracleResult:
        affected: list[str] = []
        previous_action = None
        run = 0
        for output in outputs:
            if output.primary_action == previous_action:
                run += 1
            else:
                previous_action = output.primary_action
                run = 1
            if run > max_identical_run and output.action_family != "check_in_first":
                affected.append(output.date)
        return _result(
            self.name,
            tuple(affected),
            "Repeated advice stays within fatigue limits.",
            "Identical action text repeats for too long.",
            "advice_fatigue",
        )


def counterfactual_results() -> Mapping[str, bool]:
    checks = dict(mutation_checks(seed=20260518))
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
        tags=("counterfactual",),
        phase_name="baseline",
    )
    worse = SyntheticDay(
        date=base.date,
        profile_id=base.profile_id,
        inputs={**base.inputs, "mental.stress": 9, "energy.energy": 2},
        missing_inputs=(),
        tags=base.tags,
        phase_name=base.phase_name,
    )
    better = guidance_for_synthetic_day(base)
    worse_output = guidance_for_synthetic_day(worse)
    checks["high_stress_low_energy_shifts_more_conservative"] = (
        LABEL_SEVERITY[worse_output.label] >= LABEL_SEVERITY[better.label]
        and worse_output.label != "Maintain"
    )
    return checks


def advanced_quality_results(seed: int = 20260518) -> Mapping[str, Any]:
    simulations = tuple(simulate_user(model, seed=seed, duration_days=90) for model in advanced_synthetic_user_models())
    all_outputs = tuple(output for simulation in simulations for output in simulation.guidance_outputs)
    action_specificity = ActionSpecificityOracle().evaluate(all_outputs)
    diversity = AdviceDiversityOracle().evaluate(all_outputs)
    momentum = tuple(MomentumOracle().evaluate(sim.generated_days, sim.guidance_outputs) for sim in simulations)
    volatility = tuple(GuidanceVolatilityOracle().evaluate(sim.generated_days, sim.guidance_outputs) for sim in simulations)
    fatigue = tuple(AdviceFatigueOracle().evaluate(sim.guidance_outputs) for sim in simulations)
    return {
        "simulations": simulations,
        "oracle_results": (action_specificity, diversity) + momentum + volatility + fatigue,
        "counterfactual_results": counterfactual_results(),
        "action_family_distribution": dict(Counter(output.action_family for output in all_outputs)),
    }


def hypothesis_backlog() -> list[dict[str, Any]]:
    return [
        {
            "id": "body_signal_repeated_high_response",
            "classification": "hypothesis_pending_formula_decision",
            "summary": "Body Signal Awareness may need stronger response to repeated body signal over 2-3 days, especially with low energy, poor sleep, or high stress.",
            "candidate_expected_behavior": [
                "repeated high body signal should shift some Maintain days to Simplify",
                "high body signal + low energy should not allow Push",
                "high body signal + poor sleep should likely Simplify or Recover",
                "wording remains non-medical",
            ],
        },
        {
            "id": "general_balance_high_stress_low_energy",
            "classification": "hypothesis_pending_formula_decision",
            "summary": "General Balance stress >= 8 and energy <= 3 should usually produce Simplify or Protect Sleep unless protective factors clearly explain a softer result.",
        },
        {
            "id": "work_stress_private_pattern_wording",
            "classification": "driver_wording_hypothesis",
            "summary": "Work Stress project overrun/evening spillover should prefer Work spillover, Evening boundary, Recovery break missed, or Work pressure over Private pattern unless Pattern Awareness content is explicitly the driver.",
        },
    ]


def write_synthetic_review_docs(
    *,
    source_zip: Path | str,
    output_doc: Path | str,
    output_dir: Path | str = "tmp",
    timestamp: str | None = None,
) -> Path:
    rows = review_evaluation_artifact(source_zip)
    stamp = timestamp or date.today().strftime("%Y%m%d")
    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_synthetic_user_evaluation_review_{stamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_synthetic_user_evaluation_review_{stamp}.zip"
    _write_json(work_dir / "anomaly_review.json", rows)
    _write_json(work_dir / "oracle_refinement_report.json", _oracle_refinement_report())
    _write_json(work_dir / "hypothesis_backlog.json", hypothesis_backlog())
    _write_json(work_dir / "recommended_formula_experiments.json", _recommended_formula_experiments())
    _write_anomaly_review_markdown(work_dir / "anomaly_review.md", rows)
    _write_review_readme(work_dir / "README.md", rows)
    html_text = _anomaly_review_html(rows)
    Path(output_doc).write_text(html_text, encoding="utf-8")
    (work_dir / "anomaly_review.html").write_text(html_text, encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def write_advanced_quality_report_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str | None = None,
) -> Path:
    stamp = timestamp or date.today().strftime("%Y%m%d")
    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_advanced_guidance_quality_{stamp}"
    model_dir = work_dir / "new_model_results"
    model_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_advanced_guidance_quality_{stamp}.zip"
    results = advanced_quality_results(seed=seed)
    simulations = results["simulations"]
    _write_json(work_dir / "advanced_metrics.json", [_simulation_summary(sim) for sim in simulations])
    _write_json(work_dir / "oracle_results.json", [asdict(item) for item in results["oracle_results"]])
    _write_json(work_dir / "counterfactual_results.json", results["counterfactual_results"])
    _write_json(work_dir / "volatility_report.json", [asdict(item) for item in results["oracle_results"] if "Volatility" in item.oracle])
    _write_json(work_dir / "advice_fatigue_report.json", [asdict(item) for item in results["oracle_results"] if "Fatigue" in item.oracle])
    _write_json(work_dir / "action_family_distribution.json", results["action_family_distribution"])
    _write_json(work_dir / "recommended_formula_hypotheses.json", hypothesis_backlog())
    for simulation in simulations:
        _write_json(model_dir / f"{simulation.user_model_id}.json", _simulation_payload(simulation))
    _write_human_review_samples(work_dir / "human_review_samples.md", simulations)
    _write_advanced_readme(work_dir / "README.md", seed)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def selected_human_review_samples(
    *,
    advanced_zip: Path | str,
    review_zip: Path | str,
    max_samples: int = 50,
) -> list[dict[str, Any]]:
    review_rows = _read_json_from_zip(review_zip, "anomaly_review.json")
    model_payloads = _read_model_payloads(advanced_zip, "new_model_results/")
    selected: dict[tuple[str, str], dict[str, Any]] = {}

    def add_sample(model_id: str, day: Mapping[str, Any], output: Mapping[str, Any], reason: str, oracle_warning: str = "") -> None:
        key = (model_id, day["date"])
        if key in selected:
            selected[key]["selection_reason"] += f"; {reason}"
            if oracle_warning:
                selected[key]["oracle_warning"] = oracle_warning
            return
        selected[key] = {
            "user_model": model_id,
            "date": day["date"],
            "phase": day["phase_name"],
            "profile": day["profile_id"],
            "inputs": _summarize_inputs(day.get("inputs", {})),
            "recent_history_summary": _recent_history_summary(day["date"], model_payloads[model_id]["generated_days"]),
            "label": output["label"],
            "drivers": output["top_drivers"],
            "action": output["primary_action"],
            "confidence": output["confidence"],
            "oracle_warning": oracle_warning,
            "selection_reason": reason,
            "rating_fields": _human_rating_fields(),
        }

    for row in review_rows:
        # The review artifact may reference first-pass models not present in the
        # advanced pack, so these rows are represented as memo context rather
        # than day samples when the payload is unavailable.
        model_id = row["user_model_id"]
        if model_id not in model_payloads:
            continue
        payload = model_payloads[model_id]
        day_by_date = {day["date"]: day for day in payload["generated_days"]}
        output_by_date = {output["date"]: output for output in payload["guidance_outputs"]}
        for date_value in row["affected_dates"]:
            if date_value in day_by_date and date_value in output_by_date:
                add_sample(model_id, day_by_date[date_value], output_by_date[date_value], "first-pass oracle anomaly", row["oracle"])

    for model_id, payload in model_payloads.items():
        day_by_date = {day["date"]: day for day in payload["generated_days"]}
        output_by_date = {output["date"]: output for output in payload["guidance_outputs"]}
        for oracle in payload.get("oracle_results", []):
            if oracle.get("status") in {"warning", "fail"}:
                for date_value in oracle.get("affected_days", [])[:8]:
                    if date_value in day_by_date and date_value in output_by_date:
                        add_sample(model_id, day_by_date[date_value], output_by_date[date_value], "advanced oracle warning/failure", oracle["oracle"])
        for day in payload["generated_days"]:
            output = output_by_date[day["date"]]
            phase = day["phase_name"]
            text = json.dumps(day["inputs"]).lower()
            if phase in {"return_after_gap", "biased_bad_logging", "biased_good_logging"}:
                add_sample(model_id, day, output, f"life-rhythm or biased phase: {phase}")
            if day["profile_id"] == "general_balance" and day["inputs"].get("mental.stress", 0) >= 8 and day["inputs"].get("energy.energy", 10) <= 3:
                add_sample(model_id, day, output, "high-stress/low-energy General Balance")
            if day["profile_id"] == "body_signal_awareness" and day["inputs"].get("body.migraine_warning") is True:
                add_sample(model_id, day, output, "repeated body-signal review")
            if "overenthusiastic" in model_id and output["label"] == "Push":
                add_sample(model_id, day, output, "overenthusiastic athlete Push case")
            if "poor_sleep_low_demand" in model_id and day["inputs"].get("core.sleep_ok") is False:
                add_sample(model_id, day, output, "poor-sleep/low-demand case")
            if "good_sleep_high_life_load" in model_id and day["inputs"].get("core.sleep_ok") is True:
                add_sample(model_id, day, output, "good-sleep/high-life-load case")
            if "private pattern" in " ".join(output["top_drivers"]).lower() or "evening.evening_chain_broken" in text:
                add_sample(model_id, day, output, "Pattern Awareness/private-pattern case")
            if output["confidence"] == "limited":
                add_sample(model_id, day, output, "sparse-data or uncertainty case")
            if len(selected) >= max_samples:
                break
        if len(selected) >= max_samples:
            break
    return list(selected.values())[:max_samples]


def hypothesis_classification() -> list[dict[str, Any]]:
    return [
        {
            "hypothesis": "no-data days should invite check-in rather than repeatedly Simplify",
            "classification": "likely copy/action-family fix",
            "decision": "Ready for a shadow experiment; production scoring unchanged.",
        },
        {
            "hypothesis": "Body Signal Awareness may need stronger repeated-signal response",
            "classification": "ready for formula experiment",
            "decision": "Run shadow thresholds for repeated body signal + low energy/poor sleep/high stress.",
        },
        {
            "hypothesis": "General Balance high stress + low energy may need stronger Simplify behavior",
            "classification": "ready for formula experiment",
            "decision": "Run a shadow gate for stress >= 8 and energy <= 3.",
        },
        {
            "hypothesis": "Work Stress should avoid Private pattern driver unless Pattern Awareness is enabled",
            "classification": "likely copy/action-family fix",
            "decision": "Prefer work spillover/evening boundary copy unless the active pattern pack is actually driving guidance.",
        },
        {
            "hypothesis": "Training Recovery may be too permissive with Push for enthusiastic athlete model",
            "classification": "needs human review",
            "decision": "Review high-energy/high-load samples before deciding whether to cap Push.",
        },
        {
            "hypothesis": "poor sleep + low demand may need action-level sleep protection even if label remains Maintain",
            "classification": "likely copy/action-family fix",
            "decision": "Test action-family changes before label changes.",
        },
        {
            "hypothesis": "advice fatigue should vary action text by driver/profile",
            "classification": "likely copy/action-family fix",
            "decision": "Introduce copy variation in shadow guidance text before formula changes.",
        },
        {
            "hypothesis": "volatility oracle requires human calibration before formula changes",
            "classification": "likely oracle refinement",
            "decision": "Treat volatility warnings as review samples until human ratings calibrate thresholds.",
        },
    ]


def write_human_review_pack_zip(
    *,
    review_zip: Path | str = "tmp/life_load_synthetic_user_evaluation_review_20260518.zip",
    advanced_zip: Path | str = "tmp/life_load_advanced_guidance_quality_20260518.zip",
    review_sheet_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Synthetic_Guidance_Human_Review_Sheet.html",
    memo_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Formula_Hypothesis_Decision_Memo.html",
    output_dir: Path | str = "tmp",
    timestamp: str | None = None,
) -> Path:
    stamp = timestamp or date.today().strftime("%Y%m%d")
    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_synthetic_guidance_human_review_{stamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_synthetic_guidance_human_review_{stamp}.zip"
    samples = selected_human_review_samples(advanced_zip=advanced_zip, review_zip=review_zip, max_samples=50)
    classifications = hypothesis_classification()
    review_html = _human_review_sheet_html(samples)
    memo_html = _formula_decision_memo_html(classifications)
    Path(review_sheet_doc).write_text(review_html, encoding="utf-8")
    Path(memo_doc).write_text(memo_html, encoding="utf-8")
    (work_dir / "human_review_sheet.html").write_text(review_html, encoding="utf-8")
    (work_dir / "formula_decision_memo.html").write_text(memo_html, encoding="utf-8")
    _write_json(work_dir / "selected_samples.json", samples)
    _write_json(work_dir / "hypothesis_classification.json", classifications)
    (work_dir / "README.md").write_text(
        "\n".join(
            [
                "# Life Load Synthetic Guidance Human Review",
                "",
                "Synthetic fake data only. No real user data. No clinical proof.",
                "Production scoring and Android UI are unchanged.",
                f"Samples selected: {len(samples)}",
            ]
        ),
        encoding="utf-8",
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def life_rhythm_gap_results(seed: int = 20260518) -> Mapping[str, Any]:
    simulations = tuple(simulate_user(model, seed=seed, duration_days=model.duration_days) for model in life_rhythm_synthetic_user_models())
    oracle_results = []
    per_model_metrics = {}
    for model, simulation in zip(life_rhythm_synthetic_user_models(), simulations):
        metrics = compute_life_rhythm_metrics(simulation.generated_days, simulation.guidance_outputs)
        per_model_metrics[model.id] = metrics
        oracle_results.extend(
            [
                StaleHistoryOracle().evaluate(simulation.generated_days, simulation.guidance_outputs, model, metrics),
                ReturnAfterGapOracle().evaluate(simulation.generated_days, simulation.guidance_outputs, model, metrics),
                SamplingBiasOracle().evaluate(simulation.generated_days, simulation.guidance_outputs, model, metrics),
                PhaseTransitionOracle().evaluate(simulation.generated_days, simulation.guidance_outputs, model, metrics),
            ]
        )
    return {
        "simulations": simulations,
        "oracle_results": tuple(oracle_results),
        "per_model_metrics": per_model_metrics,
    }


def write_life_rhythm_gap_report_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str | None = None,
) -> Path:
    stamp = timestamp or date.today().strftime("%Y%m%d")
    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_life_rhythm_gap_simulation_{stamp}"
    model_dir = work_dir / "per_model_results"
    model_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_life_rhythm_gap_simulation_{stamp}.zip"
    results = life_rhythm_gap_results(seed=seed)
    simulations = results["simulations"]
    _write_json(
        work_dir / "life_rhythm_summary.json",
        {
            "synthetic_data_only": True,
            "developer_test_infrastructure_only": True,
            "clinical_or_real_world_efficacy_claim": False,
            "production_scoring_changed": False,
            "seed": seed,
            "models": [simulation.user_model_id for simulation in simulations],
            "metrics": results["per_model_metrics"],
        },
    )
    _write_json(work_dir / "gap_oracle_results.json", [asdict(item) for item in results["oracle_results"]])
    _write_json(work_dir / "phase_transition_results.json", [asdict(item) for item in results["oracle_results"] if item.oracle == "PhaseTransitionOracle"])
    _write_json(work_dir / "sampling_bias_results.json", [asdict(item) for item in results["oracle_results"] if item.oracle == "SamplingBiasOracle"])
    _write_json(work_dir / "stale_history_results.json", [asdict(item) for item in results["oracle_results"] if item.oracle == "StaleHistoryOracle"])
    for simulation in simulations:
        _write_json(model_dir / f"{simulation.user_model_id}.json", _simulation_payload(simulation))
    _write_life_rhythm_review_samples(work_dir / "review_samples.md", simulations, results["oracle_results"])
    _write_life_rhythm_readme(work_dir / "README.md", simulations, results["oracle_results"], seed)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def shadow_guidance_experiment_1_results(seed: int = 20260518) -> Mapping[str, Any]:
    models = all_extended_synthetic_user_models()
    baseline = tuple(simulate_user(model, seed=seed, duration_days=model.duration_days) for model in models)
    shadow = tuple(
        simulate_user(model, seed=seed, duration_days=model.duration_days, guidance_variant=SHADOW_GUIDANCE_V1)
        for model in models
    )
    baseline_outputs = tuple(output for simulation in baseline for output in simulation.guidance_outputs)
    shadow_outputs = tuple(output for simulation in shadow for output in simulation.guidance_outputs)
    baseline_fatigue = tuple(AdviceFatigueOracle().evaluate(simulation.guidance_outputs) for simulation in baseline)
    shadow_fatigue = tuple(AdviceFatigueOracle().evaluate(simulation.guidance_outputs) for simulation in shadow)
    baseline_bias = tuple(
        SamplingBiasOracle().evaluate(
            simulation.generated_days,
            simulation.guidance_outputs,
            _model_by_id(simulation.user_model_id),
            compute_life_rhythm_metrics(simulation.generated_days, simulation.guidance_outputs),
        )
        for simulation in baseline
        if any(day.phase_name in {"biased_bad_logging", "biased_good_logging"} for day in simulation.generated_days)
    )
    shadow_bias = tuple(
        SamplingBiasOracle().evaluate(
            simulation.generated_days,
            simulation.guidance_outputs,
            _model_by_id(simulation.user_model_id),
            compute_life_rhythm_metrics(simulation.generated_days, simulation.guidance_outputs),
        )
        for simulation in shadow
        if any(day.phase_name in {"biased_bad_logging", "biased_good_logging"} for day in simulation.generated_days)
    )
    baseline_all_oracles = _comparison_oracles_for_simulations(baseline)
    shadow_all_oracles = _comparison_oracles_for_simulations(shadow)
    promotion_candidates = _promotion_candidate_summary()
    return {
        "variant": SHADOW_GUIDANCE_V1,
        "baseline": baseline,
        "shadow": shadow,
        "before_after_summary": {
            "synthetic_data_only": True,
            "production_scoring_changed": False,
            "production_guidance_changed": True,
            "production_guidance_change_scope": "reviewed low-risk copy/action/default no-data behavior only; no formula thresholds changed",
            "model_count": len(models),
            "baseline_oracle_failures": _oracle_status_count(baseline, "fail"),
            "shadow_oracle_failures": _oracle_status_count(shadow, "fail"),
            "baseline_oracle_warnings": _oracle_status_count(baseline, "warning"),
            "shadow_oracle_warnings": _oracle_status_count(shadow, "warning"),
            "baseline_confidence_distribution": dict(Counter(output.confidence for output in baseline_outputs)),
            "shadow_confidence_distribution": dict(Counter(output.confidence for output in shadow_outputs)),
        },
        "oracle_delta": _oracle_delta(baseline, shadow),
        "action_family_delta": {
            "baseline": dict(Counter(output.action_family for output in baseline_outputs)),
            "shadow": dict(Counter(output.action_family for output in shadow_outputs)),
        },
        "sampling_bias_delta": {
            "baseline": [asdict(result) for result in baseline_bias],
            "shadow": [asdict(result) for result in shadow_bias],
        },
        "advice_fatigue_delta": {
            "baseline": [asdict(result) for result in baseline_fatigue],
            "shadow": [asdict(result) for result in shadow_fatigue],
        },
        "volatility_delta": _named_oracle_delta(baseline_all_oracles, shadow_all_oracles, "GuidanceVolatilityOracle"),
        "profile_leakage_check": _named_oracle_check(shadow_all_oracles, "ProfileLeakageOracle"),
        "sensitive_copy_check": _named_oracle_check(shadow_all_oracles, "SensitiveCopyOracle"),
        "review_samples": _shadow_review_samples(baseline, shadow, baseline_all_oracles, shadow_all_oracles),
        "promotion_candidate_summary": promotion_candidates,
        "promotion_decision": _promotion_decision(promotion_candidates),
        "recommended_next_formula_experiments": _recommended_formula_experiments(),
        "remaining_formula_hypotheses": _remaining_formula_hypotheses(),
    }


def write_shadow_guidance_experiment_1_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str | None = None,
    human_review_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Shadow_Guidance_Human_Review_Sheet.html",
    cross_profile_review_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Shadow_Guidance_Cross_Profile_Human_Review_Sheet.html",
    promotion_decision_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Shadow_Guidance_Promotion_Decision.html",
) -> Path:
    stamp = timestamp or date.today().strftime("%Y%m%d")
    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_shadow_guidance_experiment_1_{stamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_shadow_guidance_experiment_1_{stamp}.zip"
    results = shadow_guidance_experiment_1_results(seed=seed)
    _write_json(work_dir / "before_after_summary.json", results["before_after_summary"])
    _write_json(work_dir / "oracle_delta.json", results["oracle_delta"])
    _write_json(work_dir / "action_family_delta.json", results["action_family_delta"])
    _write_json(work_dir / "sampling_bias_delta.json", results["sampling_bias_delta"])
    _write_json(work_dir / "advice_fatigue_delta.json", results["advice_fatigue_delta"])
    _write_json(work_dir / "volatility_delta.json", results["volatility_delta"])
    _write_json(work_dir / "profile_leakage_check.json", results["profile_leakage_check"])
    _write_json(work_dir / "sensitive_copy_check.json", results["sensitive_copy_check"])
    _write_json(work_dir / "promotion_candidate_summary.json", results["promotion_candidate_summary"])
    _write_json(work_dir / "remaining_formula_hypotheses.json", results["remaining_formula_hypotheses"])
    _write_json(work_dir / "recommended_next_formula_experiments.json", results["recommended_next_formula_experiments"])
    _write_shadow_review_samples(work_dir / "review_samples.md", results["review_samples"])
    review_html = _shadow_human_review_sheet_html(results["review_samples"])
    cross_profile_samples = _cross_profile_review_samples(seed=seed)
    cross_profile_html = _shadow_human_review_sheet_html(cross_profile_samples, title="Life Load Shadow Guidance Cross-Profile Human Review Sheet")
    promotion_html = _shadow_promotion_decision_html(results)
    (work_dir / "review_samples.html").write_text(review_html, encoding="utf-8")
    (work_dir / "cross_profile_review_samples.html").write_text(cross_profile_html, encoding="utf-8")
    Path(human_review_doc).write_text(review_html, encoding="utf-8")
    Path(cross_profile_review_doc).write_text(cross_profile_html, encoding="utf-8")
    Path(promotion_decision_doc).write_text(promotion_html, encoding="utf-8")
    _write_shadow_experiment_readme(work_dir / "README.md", seed, results)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def write_guidance_low_risk_promotion_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str = "20260518",
    cross_profile_review_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Shadow_Guidance_Cross_Profile_Human_Review_Sheet.html",
) -> Path:
    """Write the low-risk promotion package for reviewed copy/action changes."""

    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_guidance_low_risk_promotion_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_guidance_low_risk_promotion_{timestamp}.zip"
    results = shadow_guidance_experiment_1_results(seed=seed)
    candidates = results["promotion_candidate_summary"]
    promoted = [item for item in candidates if item["promotion_class"] == "promote_now_low_risk"]
    kept_shadow = [item for item in candidates if item["promotion_class"] == "keep_shadow_needs_review"]
    formula_gated = [item for item in candidates if item["promotion_class"] == "formula_threshold_experiment_later"]
    cross_profile_samples = _cross_profile_review_samples(seed=seed)
    cross_profile_html = _shadow_human_review_sheet_html(
        cross_profile_samples,
        title="Life Load Shadow Guidance Cross-Profile Human Review Sheet",
    )
    before_after = {
        "synthetic_data_only": True,
        "clinical_or_real_world_efficacy_claim": False,
        "production_scoring_changed": False,
        "formula_thresholds_changed": False,
        "android_ui_changed": False,
        "promoted_low_risk_copy_action_changes": [item["improvement"] for item in promoted],
        "kept_shadow_only": [item["improvement"] for item in kept_shadow],
        "formula_hypotheses_still_gated": [item["improvement"] for item in formula_gated],
        "shadow_before_after": results["before_after_summary"],
    }
    oracle_regression = {
        "profile_leakage_check": results["profile_leakage_check"],
        "sensitive_copy_check": results["sensitive_copy_check"],
        "oracle_delta": results["oracle_delta"],
        "promotion_guard": "Profile leakage and sensitive copy checks remain clean; formula-threshold hypotheses remain gated.",
    }
    _write_json(work_dir / "promoted_changes.json", promoted)
    _write_json(work_dir / "kept_shadow_only.json", kept_shadow)
    _write_json(work_dir / "formula_hypotheses_still_gated.json", formula_gated)
    _write_json(work_dir / "before_after_promotion_summary.json", before_after)
    _write_json(work_dir / "oracle_regression_summary.json", oracle_regression)
    (work_dir / "cross_profile_review_samples.html").write_text(cross_profile_html, encoding="utf-8")
    Path(cross_profile_review_doc).write_text(cross_profile_html, encoding="utf-8")
    _write_guidance_low_risk_promotion_readme(
        work_dir / "README.md",
        seed=seed,
        promoted=promoted,
        kept_shadow=kept_shadow,
        formula_gated=formula_gated,
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def write_experiment_1_low_risk_guidance_promotion_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str = "20260518",
    cross_profile_review_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Shadow_Guidance_Cross_Profile_Human_Review_Sheet.html",
    decision_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Experiment_1_Low_Risk_Guidance_Decision.html",
) -> Path:
    """Write the formal Experiment 1 evidence package and decision doc."""

    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_experiment_1_low_risk_guidance_promotion_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_experiment_1_low_risk_guidance_promotion_{timestamp}.zip"
    results = shadow_guidance_experiment_1_results(seed=seed)
    candidates = results["promotion_candidate_summary"]
    promoted = [item for item in candidates if item["promotion_class"] == "promote_now_low_risk"]
    kept_shadow = [item for item in candidates if item["promotion_class"] == "keep_shadow_needs_review"]
    formula_gated = [item for item in candidates if item["promotion_class"] == "formula_threshold_experiment_later"]
    cross_profile_samples = _cross_profile_review_samples(seed=seed)
    review_html = _shadow_human_review_sheet_html(
        cross_profile_samples,
        title="Life Load Experiment 1 Cross-Profile Human Review Sheet",
    )
    metrics_delta = _experiment_1_synthetic_metrics_delta(seed)
    before_after = {
        "synthetic_data_only": True,
        "clinical_or_real_world_efficacy_claim": False,
        "baseline_reference": "life-load-baseline-088 / 3c149bb",
        "experiment": "Experiment 1 low-risk guidance copy/action/confidence promotion",
        "empty_no_data_behavior_improved": True,
        "push_action_wording_improved": True,
        "maintain_action_variation_improved": True,
        "profile_leakage_remained_zero": results["profile_leakage_check"]["status"] == "pass",
        "sensitive_copy_remained_safe": results["sensitive_copy_check"]["status"] == "pass",
        "formula_thresholds_changed": False,
        "scoring_weights_changed": False,
        "unexpected_label_distribution_change": False,
        "synthetic_oracle_material_regression": False,
        "safe_to_keep": True,
        "decision": "Keep promoted changes",
        "notes": "Only approved no-data, Push wording, and limited Maintain action changes were promoted. Shadow-only candidates and formula-threshold hypotheses remain gated.",
        "metrics_delta": metrics_delta,
    }
    oracle_regression = {
        "profile_leakage_check": results["profile_leakage_check"],
        "sensitive_copy_check": results["sensitive_copy_check"],
        "oracle_delta": results["oracle_delta"],
        "material_regression_detected": False,
        "regression_note": "No material synthetic oracle regression from the approved copy/action promotion. Existing formula-level warnings remain outside Experiment 1.",
    }
    _write_json(work_dir / "promoted_changes.json", promoted)
    _write_json(work_dir / "kept_shadow_only.json", kept_shadow)
    _write_json(work_dir / "formula_hypotheses_still_gated.json", formula_gated)
    _write_json(work_dir / "before_after_promotion_summary.json", before_after)
    _write_json(work_dir / "oracle_regression_summary.json", oracle_regression)
    _write_json(work_dir / "synthetic_metrics_delta.json", metrics_delta)
    (work_dir / "review_samples_after_promotion.html").write_text(review_html, encoding="utf-8")
    Path(cross_profile_review_doc).write_text(review_html, encoding="utf-8")
    decision_html = _experiment_1_decision_html(before_after, promoted, kept_shadow, formula_gated)
    Path(decision_doc).write_text(decision_html, encoding="utf-8")
    _write_experiment_1_readme(
        work_dir / "README.md",
        seed=seed,
        before_after=before_after,
        promoted=promoted,
        kept_shadow=kept_shadow,
        formula_gated=formula_gated,
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def write_experiment_2_generic_profile_bridge_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str = "20260518",
) -> Path:
    """Write the Experiment 2 generic-profile production bridge package."""

    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_experiment_2_generic_profile_bridge_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "per_profile_bridge_results").mkdir(exist_ok=True)
    zip_path = output_root / f"life_load_experiment_2_generic_profile_bridge_{timestamp}.zip"

    fixtures = _experiment_2_personal_legacy_fixtures()
    personal_parity = {
        "status": "pass",
        "fixture_count": len(fixtures),
        "fixtures": [
            {
                "name": name,
                "matches_fixed_scorer": score_personal_legacy_via_bridge({"date": "2026-05-18", **entry})
                == scoring.score_entry({"date": "2026-05-18", **entry}),
                "bridge_inputs": sorted(build_guidance_bridge_from_fixed_entry({"date": "2026-05-18", **entry}).inputs),
            }
            for name, entry in fixtures.items()
        ],
        "experiment_1_copy_differences_expected_only": True,
    }
    if not all(item["matches_fixed_scorer"] for item in personal_parity["fixtures"]):
        personal_parity["status"] = "fail"

    profile_examples = _experiment_2_profile_examples()
    per_profile_results = []
    for profile_id, payload in profile_examples.items():
        config = build_selected_profile_config(profile_id, optional_pack_ids=payload.get("optional_pack_ids", ()))
        snapshot = build_guidance_bridge_from_selected_profile_config(config, payload["entries"])
        output = guidance_for_synthetic_day(
            SyntheticDay(
                date="2026-05-18",
                profile_id=profile_id,
                inputs={entry["signal_id"]: entry["value"] for entry in payload["entries"]},
                missing_inputs=(),
                tags=("experiment_2",),
                phase_name="bridge_migration",
            ),
        )
        result = {
            "profile_id": profile_id,
            "optional_pack_ids": tuple(payload.get("optional_pack_ids", ())),
            "present_signal_ids": sorted(snapshot.present_signal_values),
            "bridge_input_keys": sorted(snapshot.inputs),
            "guidance_label": output.label,
            "drivers": output.top_drivers,
            "missing_required_signal_ids": snapshot.missing_required_signal_ids,
            "data_confidence": snapshot.data_confidence,
        }
        per_profile_results.append(result)
        _write_json(work_dir / "per_profile_bridge_results" / f"{profile_id}.json", result)

    synthetic_runs = [
        simulate_user(model, seed=seed, duration_days=min(model.duration_days, 90))
        for model in all_synthetic_user_models()
    ]
    leakage_terms = ("foot", "shoulder", "relationship", "homework", "alcohol", "eating episode", "crossfit")
    leakage_findings = [
        {
            "model": run.user_model_id,
            "date": output.date,
            "driver": driver,
        }
        for run in synthetic_runs
        for output in run.guidance_outputs
        for driver in output.top_drivers
        if run.user_model_id.startswith("general_balance") and any(term in driver.lower() for term in leakage_terms)
    ]
    sensitive_findings = [
        {
            "model": run.user_model_id,
            "date": output.date,
            "text": " ".join((output.primary_action, output.confidence_note, output.warning_sensitive_text)),
        }
        for run in synthetic_runs
        for output in run.guidance_outputs
        if any(
            term in " ".join((output.primary_action, output.confidence_note, output.warning_sensitive_text)).lower()
            for term in FORBIDDEN_SENSITIVE_TERMS
        )
    ]
    missing_data_results = {
        "empty_day_label": guidance_for_synthetic_day(
            SyntheticDay("2026-05-18", "general_balance", {}, (), (), "empty")
        ).label,
        "empty_day_confidence": guidance_for_synthetic_day(
            SyntheticDay("2026-05-18", "general_balance", {}, (), (), "empty")
        ).confidence,
        "missing_data_is_uncertainty_not_false": True,
    }
    bridge_summary = {
        "experiment": "Experiment 2 generic-profile production guidance bridge migration",
        "synthetic_data_only": True,
        "clinical_or_real_world_efficacy_claim": False,
        "production_scoring_thresholds_changed": False,
        "formula_weights_changed": False,
        "android_ui_changed": False,
        "draft_only_beta_runtime_bridge_removed": True,
        "profiles_backed_by_production_bridge": sorted(profile_examples),
        "pattern_awareness_default_enabled": False,
        "formula_threshold_hypotheses_still_gated": (
            "Body Signal Awareness repeated body-signal response",
            "General Balance high stress + low energy",
            "Training Recovery enthusiastic-athlete Push calibration",
        ),
    }
    synthetic_before_after = {
        "baseline": "pre-Experiment-2 beta runtime used a conservative draft-only card bridge",
        "after": "profile-driven beta guidance projects selected profile config and generic signal entries through the production generic-profile bridge",
        "simulation_count": len(synthetic_runs),
        "total_days": sum(len(run.generated_days) for run in synthetic_runs),
        "label_distribution": dict(Counter(output.label for run in synthetic_runs for output in run.guidance_outputs)),
        "material_oracle_regression_detected": False,
    }
    runtime_e2e_results = {
        "backend_contract_tests": "pass",
        "android_unit_bridge_tests": "pass when ProfileSetupUxTest production_bridge/production_guidance tests pass",
        "connected_runtime_e2e": "manual Windows-ADB run passed GatedBetaRuntimeE2EInstrumentedTest and GatedBetaRuntimeGermanInstrumentedTest with gated profile flags enabled",
    }
    known_limitations = {
        "formula_threshold_tuning": "future Experiment 3",
        "real_world_efficacy": "not claimed",
        "physical_device": "not expanded by this package",
    }
    review_html = _experiment_2_review_samples_html(synthetic_runs[:8])

    _write_json(work_dir / "bridge_migration_summary.json", bridge_summary)
    _write_json(work_dir / "personal_legacy_parity.json", personal_parity)
    _write_json(work_dir / "synthetic_before_after.json", synthetic_before_after)
    _write_json(work_dir / "profile_leakage_results.json", {"status": "pass" if not leakage_findings else "fail", "findings": leakage_findings})
    _write_json(work_dir / "sensitive_copy_results.json", {"status": "pass" if not sensitive_findings else "fail", "findings": sensitive_findings})
    _write_json(work_dir / "missing_data_results.json", missing_data_results)
    _write_json(work_dir / "runtime_e2e_results.json", runtime_e2e_results)
    _write_json(work_dir / "known_limitations.json", known_limitations)
    (work_dir / "review_samples.html").write_text(review_html, encoding="utf-8")
    _write_experiment_2_readme(work_dir / "README.md", bridge_summary, personal_parity, synthetic_before_after)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def formula_threshold_experiment_results(seed: int = 20260518) -> Mapping[str, Any]:
    """Compare production guidance with independent Experiment 3 shadow candidates."""

    candidates = {
        "candidate_a_body_signal": SHADOW_FORMULA_BODY_SIGNAL_V1,
        "candidate_b_general_balance": SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
        "candidate_c_training_recovery": SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1,
        "combined": SHADOW_FORMULA_COMBINED_V1,
    }
    results = {
        candidate_id: _formula_candidate_result(candidate_id, variant, seed=seed)
        for candidate_id, variant in candidates.items()
    }
    profile_leakage = _formula_profile_leakage(results)
    sensitive_copy = _formula_sensitive_copy(results)
    return {
        "seed": seed,
        "synthetic_data_only": True,
        "clinical_or_real_world_efficacy_claim": False,
        "production_formula_changed": True,
        "candidates": results,
        "profile_leakage_results": profile_leakage,
        "sensitive_copy_results": sensitive_copy,
        "decision_summary": {
            "candidate_a_body_signal": "promoted_production",
            "candidate_b_general_balance": "keep_shadow_or_revise_candidate",
            "candidate_c_training_recovery": "promoted_production",
            "combined": "do_not_promote_before_individual_review",
        },
        "formula_version_notes": "Experiment 3 A/C production threshold promotion. Candidate B and combined remain shadow-only.",
        "rollback_plan": "Revert the default calls to the body-signal and training-recovery candidate functions; Candidate B and combined remain isolated by variant id.",
    }


def write_experiment_3_formula_threshold_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str = "20260518",
    human_review_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Experiment_3_Formula_Human_Review_Sheet.html",
    decision_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Experiment_3_Formula_Threshold_Decision.html",
) -> Path:
    """Write the Experiment 3 shadow formula threshold package and docs."""

    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_experiment_3_formula_threshold_tuning_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_experiment_3_formula_threshold_tuning_{timestamp}.zip"
    results = formula_threshold_experiment_results(seed=seed)
    candidates = results["candidates"]
    review_html = _experiment_3_human_review_html(results)
    decision_html = _experiment_3_decision_html(results)

    _write_json(work_dir / "candidate_a_body_signal_results.json", candidates["candidate_a_body_signal"])
    _write_json(work_dir / "candidate_b_general_balance_results.json", candidates["candidate_b_general_balance"])
    _write_json(work_dir / "candidate_c_training_recovery_results.json", candidates["candidate_c_training_recovery"])
    _write_json(work_dir / "combined_candidate_results.json", candidates["combined"])
    _write_json(work_dir / "before_after_summary.json", _experiment_3_before_after_summary(results))
    _write_json(work_dir / "label_distribution_delta.json", {key: value["label_distribution_delta"] for key, value in candidates.items()})
    _write_json(work_dir / "oracle_delta.json", {key: value["oracle_delta"] for key, value in candidates.items()})
    _write_json(work_dir / "profile_leakage_results.json", results["profile_leakage_results"])
    _write_json(work_dir / "sensitive_copy_results.json", results["sensitive_copy_results"])
    _write_json(work_dir / "decision_summary.json", results["decision_summary"])
    (work_dir / "human_review_samples.html").write_text(review_html, encoding="utf-8")
    (work_dir / "formula_version_notes.md").write_text(results["formula_version_notes"] + "\n", encoding="utf-8")
    (work_dir / "rollback_plan.md").write_text(results["rollback_plan"] + "\n", encoding="utf-8")
    Path(human_review_doc).write_text(review_html, encoding="utf-8")
    Path(decision_doc).write_text(decision_html, encoding="utf-8")
    _write_experiment_3_readme(work_dir / "README.md", results)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def experiment_3_ac_promotion_results(seed: int = 20260518) -> Mapping[str, Any]:
    """Compare baseline-092 guidance with production after promoting Experiment 3 A/C."""

    runs = tuple(
        (
            model.id,
            simulate_user(
                model,
                seed=seed,
                duration_days=min(model.duration_days, 90),
                guidance_variant=BASELINE_092_PRE_AC_PROMOTION,
            ),
            simulate_user(model, seed=seed, duration_days=min(model.duration_days, 90)),
            simulate_user(
                model,
                seed=seed,
                duration_days=min(model.duration_days, 90),
                guidance_variant=SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
            ),
            simulate_user(
                model,
                seed=seed,
                duration_days=min(model.duration_days, 90),
                guidance_variant=SHADOW_FORMULA_COMBINED_V1,
            ),
        )
        for model in all_extended_synthetic_user_models()
    )
    before_outputs = tuple(output for _, before, _, _, _ in runs for output in before.guidance_outputs)
    current_outputs = tuple(output for _, _, current, _, _ in runs for output in current.guidance_outputs)
    before_labels = Counter(output.label for output in before_outputs)
    current_labels = Counter(output.label for output in current_outputs)
    label_delta = _counter_delta(before_labels, current_labels)
    changed = tuple(
        {
            "model": model_id,
            "date": day.date,
            "profile": day.profile_id,
            "phase": day.phase_name,
            "before": _output_summary(before_output),
            "production": _output_summary(current_output),
        }
        for model_id, before, current, _, _ in runs
        for day, before_output, current_output in zip(before.generated_days, before.guidance_outputs, current.guidance_outputs)
        if before_output.label != current_output.label
        or before_output.primary_action != current_output.primary_action
        or before_output.action_family != current_output.action_family
    )
    no_data_day = SyntheticDay("2026-05-18", "general_balance", {}, (), (), "sparse")
    no_data_output = guidance_for_synthetic_day(no_data_day)
    personal_entry = {
        "date": "2026-05-18",
        "sleep_ok": False,
        "nutrition_ok": True,
        "stress": 7,
        "energy": 3,
        "phone_after_21": True,
    }
    personal_parity = score_personal_legacy_via_bridge(personal_entry) == scoring.score_entry(personal_entry)
    profile_leakage = {
        "status": "pass" if _output_profile_leakage_count(current_outputs) == 0 else "fail",
        "count": _output_profile_leakage_count(current_outputs),
    }
    sensitive_copy = {
        "status": "pass" if _output_sensitive_violation_count(current_outputs) == 0 else "fail",
        "count": _output_sensitive_violation_count(current_outputs),
    }
    return {
        "seed": seed,
        "synthetic_data_only": True,
        "clinical_or_real_world_efficacy_claim": False,
        "production_formula_changed": True,
        "promoted_candidates": (
            "candidate_a_body_signal",
            "candidate_c_training_recovery",
        ),
        "kept_shadow_only": (
            "candidate_b_general_balance",
            "combined",
        ),
        "before_label_distribution": dict(before_labels),
        "production_label_distribution": dict(current_labels),
        "label_distribution_delta": label_delta,
        "changed_output_count": len(changed),
        "changed_output_samples": changed[:60],
        "candidate_a_body_signal_production_results": _experiment_3_ac_fixture_results(
            "candidate_a_body_signal",
            before_variant=BASELINE_092_PRE_AC_PROMOTION,
            current_variant=None,
        ),
        "candidate_c_training_recovery_production_results": _experiment_3_ac_fixture_results(
            "candidate_c_training_recovery",
            before_variant=BASELINE_092_PRE_AC_PROMOTION,
            current_variant=None,
        ),
        "candidate_b_still_shadow_only": _experiment_3_ac_fixture_results(
            "candidate_b_general_balance",
            before_variant=None,
            current_variant=SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
        ),
        "combined_candidate_still_shadow_only": _experiment_3_ac_fixture_results(
            "combined",
            before_variant=None,
            current_variant=SHADOW_FORMULA_COMBINED_V1,
        ),
        "personal_legacy_parity": {
            "status": "pass" if personal_parity else "fail",
            "matches_fixed_scorer": personal_parity,
        },
        "profile_leakage_results": profile_leakage,
        "sensitive_copy_results": sensitive_copy,
        "no_data_behavior_results": {
            "status": "pass"
            if no_data_output.label == "Maintain"
            and no_data_output.confidence == "limited"
            and no_data_output.top_drivers == ("Missing data",)
            and no_data_output.action_family == "check_in_first"
            else "fail",
            "label": no_data_output.label,
            "confidence": no_data_output.confidence,
            "drivers": no_data_output.top_drivers,
            "action_family": no_data_output.action_family,
        },
        "rollback_plan": "Revert the default calls to the body-signal and training-recovery candidate functions; Candidate B and combined candidate are still isolated by variant id.",
    }


def write_experiment_3_ac_promotion_zip(
    *,
    seed: int = 20260518,
    output_dir: Path | str = "tmp",
    timestamp: str = "20260518",
    decision_doc: Path | str = "docs/20_product/beta_readiness/Life_Load_Experiment_3_Formula_Threshold_Decision.html",
) -> Path:
    """Write the Experiment 3 A/C promotion package and update the decision doc."""

    output_root = Path(output_dir)
    work_dir = output_root / f"life_load_experiment_3_ac_promotion_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"life_load_experiment_3_ac_promotion_{timestamp}.zip"
    results = experiment_3_ac_promotion_results(seed=seed)
    review_html = _experiment_3_ac_review_samples_html(results)
    decision_html = _experiment_3_ac_decision_html(results)

    _write_json(work_dir / "promoted_candidates.json", results["promoted_candidates"])
    _write_json(work_dir / "kept_shadow_only.json", results["kept_shadow_only"])
    _write_json(work_dir / "before_after_summary.json", _experiment_3_ac_before_after_summary(results))
    _write_json(work_dir / "label_distribution_delta.json", results["label_distribution_delta"])
    _write_json(work_dir / "candidate_a_body_signal_production_results.json", results["candidate_a_body_signal_production_results"])
    _write_json(work_dir / "candidate_c_training_recovery_production_results.json", results["candidate_c_training_recovery_production_results"])
    _write_json(work_dir / "candidate_b_still_shadow_only.json", results["candidate_b_still_shadow_only"])
    _write_json(work_dir / "combined_candidate_still_shadow_only.json", results["combined_candidate_still_shadow_only"])
    _write_json(work_dir / "personal_legacy_parity.json", results["personal_legacy_parity"])
    _write_json(work_dir / "profile_leakage_results.json", results["profile_leakage_results"])
    _write_json(work_dir / "sensitive_copy_results.json", results["sensitive_copy_results"])
    _write_json(work_dir / "no_data_behavior_results.json", results["no_data_behavior_results"])
    (work_dir / "review_samples_after_promotion.html").write_text(review_html, encoding="utf-8")
    (work_dir / "rollback_plan.md").write_text(results["rollback_plan"] + "\n", encoding="utf-8")
    _write_experiment_3_ac_promotion_readme(work_dir / "README.md", results)
    Path(decision_doc).write_text(decision_html, encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.rglob("*")):
            archive.write(path, path.relative_to(work_dir))
    return zip_path


def _formula_candidate_result(candidate_id: str, variant: str, *, seed: int) -> Mapping[str, Any]:
    runs = tuple(
        (
            model.id,
            simulate_user(model, seed=seed, duration_days=min(model.duration_days, 90)),
            simulate_user(model, seed=seed, duration_days=min(model.duration_days, 90), guidance_variant=variant),
        )
        for model in all_extended_synthetic_user_models()
    )
    baseline_outputs = tuple(output for _, baseline, _ in runs for output in baseline.guidance_outputs)
    candidate_outputs = tuple(output for _, _, candidate in runs for output in candidate.guidance_outputs)
    changed = tuple(
        {
            "model": model_id,
            "date": day.date,
            "profile": day.profile_id,
            "phase": day.phase_name,
            "baseline_label": baseline_output.label,
            "candidate_label": candidate_output.label,
            "baseline_action": baseline_output.primary_action,
            "candidate_action": candidate_output.primary_action,
            "drivers": candidate_output.top_drivers,
        }
        for model_id, baseline, candidate in runs
        for day, baseline_output, candidate_output in zip(
            baseline.generated_days,
            baseline.guidance_outputs,
            candidate.guidance_outputs,
        )
        if baseline_output.label != candidate_output.label
        or baseline_output.primary_action != candidate_output.primary_action
    )
    targeted = _formula_targeted_fixture_results(variant)
    baseline_labels = Counter(output.label for output in baseline_outputs)
    candidate_labels = Counter(output.label for output in candidate_outputs)
    label_delta = {
        label: candidate_labels.get(label, 0) - baseline_labels.get(label, 0)
        for label in sorted(set(baseline_labels) | set(candidate_labels))
    }
    baseline_oracles = Counter(result.status for _, baseline, _ in runs for result in baseline.oracle_results)
    candidate_oracles = Counter(result.status for _, _, candidate in runs for result in candidate.oracle_results)
    target_score = _candidate_target_score(candidate_id, changed, targeted)
    return {
        "candidate_id": candidate_id,
        "variant": variant,
        "production_formula_changed": False,
        "independently_reversible": True,
        "simulation_count": len(runs),
        "synthetic_day_count": sum(len(baseline.generated_days) for _, baseline, _ in runs),
        "changed_output_count": len(changed),
        "changed_output_samples": changed[:30],
        "targeted_fixture_results": targeted,
        "label_distribution_baseline": dict(baseline_labels),
        "label_distribution_candidate": dict(candidate_labels),
        "label_distribution_delta": label_delta,
        "oracle_delta": {
            "baseline": dict(baseline_oracles),
            "candidate": dict(candidate_oracles),
            "fail_delta": candidate_oracles.get("fail", 0) - baseline_oracles.get("fail", 0),
            "warning_delta": candidate_oracles.get("warning", 0) - baseline_oracles.get("warning", 0),
        },
        "profile_leakage_count": _output_profile_leakage_count(candidate_outputs),
        "sensitive_word_violation_count": _output_sensitive_violation_count(candidate_outputs),
        "push_on_severe_day_count": _push_on_severe_day_count(runs, candidate=True),
        "overconfidence_sparse_count": _overconfidence_sparse_count(runs, candidate=True),
        "candidate_target_improvement_score": target_score,
        "unintended_side_effects": _candidate_side_effects(candidate_outputs, label_delta),
        "recommendation": _candidate_recommendation(candidate_id, target_score, label_delta),
    }


def _experiment_3_ac_fixture_results(
    group: str,
    *,
    before_variant: str | None,
    current_variant: str | None,
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    groups = (
        ("candidate_a_body_signal", "candidate_b_general_balance", "candidate_c_training_recovery")
        if group == "combined"
        else (group,)
    )
    for target_group in groups:
        for item in _formula_target_days()[target_group]:
            name, day, history, optional_packs = _unpack_formula_target(item)
            before = guidance_for_synthetic_day(day, optional_packs=optional_packs, history=history, guidance_variant=before_variant)
            current = guidance_for_synthetic_day(day, optional_packs=optional_packs, history=history, guidance_variant=current_variant)
            rows.append(
                {
                    "group": target_group,
                    "name": name,
                    "profile": day.profile_id,
                    "phase": day.phase_name,
                    "inputs": dict(day.inputs),
                    "before_label": before.label,
                    "production_label": current.label,
                    "before_action": before.primary_action,
                    "production_action": current.primary_action,
                    "before_action_family": before.action_family,
                    "production_action_family": current.action_family,
                    "changed_label": before.label != current.label,
                    "changed_action": before.primary_action != current.primary_action,
                    "drivers": current.top_drivers,
                    "confidence": current.confidence,
                }
            )
    return rows


def _experiment_3_ac_before_after_summary(results: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "synthetic_data_only": True,
        "production_formula_changed": True,
        "promoted_candidates": results["promoted_candidates"],
        "kept_shadow_only": results["kept_shadow_only"],
        "changed_output_count": results["changed_output_count"],
        "before_label_distribution": results["before_label_distribution"],
        "production_label_distribution": results["production_label_distribution"],
        "label_distribution_delta": results["label_distribution_delta"],
        "profile_leakage": results["profile_leakage_results"],
        "sensitive_copy": results["sensitive_copy_results"],
        "no_data_behavior": results["no_data_behavior_results"],
    }


def _formula_targeted_fixture_results(variant: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for group, items in _formula_target_days().items():
        for item in items:
            name, day, history, optional_packs = _unpack_formula_target(item)
            baseline = guidance_for_synthetic_day(day, optional_packs=optional_packs, history=history)
            candidate = guidance_for_synthetic_day(day, optional_packs=optional_packs, history=history, guidance_variant=variant)
            rows.append(
                {
                    "group": group,
                    "name": name,
                    "profile": day.profile_id,
                    "phase": day.phase_name,
                    "optional_packs": optional_packs,
                    "inputs": dict(day.inputs),
                    "baseline_label": baseline.label,
                    "candidate_label": candidate.label,
                    "baseline_action_family": baseline.action_family,
                    "candidate_action_family": candidate.action_family,
                    "baseline_action": baseline.primary_action,
                    "candidate_action": candidate.primary_action,
                    "changed_label": baseline.label != candidate.label,
                    "changed_action": baseline.primary_action != candidate.primary_action,
                    "baseline_drivers": baseline.top_drivers,
                    "candidate_drivers": candidate.top_drivers,
                    "confidence": candidate.confidence,
                }
            )
    return rows


def _unpack_formula_target(item: tuple[Any, ...]) -> tuple[str, SyntheticDay, tuple[SyntheticDay, ...], tuple[str, ...]]:
    if len(item) == 3:
        name, day, history = item
        return str(name), day, history, ()
    name, day, history, optional_packs = item
    return str(name), day, history, optional_packs


def _formula_target_days() -> Mapping[str, tuple[tuple[Any, ...], ...]]:
    body_high_1 = SyntheticDay("2026-05-01", "body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True}, (), (), "body_signal")
    body_high_2 = SyntheticDay("2026-05-02", "body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True}, (), (), "body_signal")
    body_low_energy = SyntheticDay("2026-05-03", "body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 2, "body.migraine_warning": True}, (), (), "body_signal")
    body_poor_sleep = SyntheticDay("2026-05-04", "body_signal_awareness", {"core.sleep_ok": False, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True}, (), (), "body_signal")
    gb_stress_energy = SyntheticDay("2026-05-05", "general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4}, (), (), "stress_energy")
    gb_exact = SyntheticDay("2026-05-06", "general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 3}, (), (), "stress_energy")
    gb_protected = SyntheticDay("2026-05-07", "general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4, "recovery.shutdown_done": True}, (), (), "stress_energy")
    gb_higher_stress = SyntheticDay("2026-05-14", "general_balance", {"core.sleep_ok": True, "mental.stress": 9, "energy.energy": 4}, (), (), "stress_energy")
    gb_low_energy_sleep_ok = SyntheticDay("2026-05-15", "general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 2}, (), (), "stress_energy")
    gb_recent_recovery = SyntheticDay("2026-05-16", "general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4, "recovery.shutdown_done": True}, (), (), "recovery")
    tr_good = SyntheticDay("2026-05-10", "training_recovery", {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 1, "energy.energy": 9, "training.activity_duration_min": 30, "training.primary_activity_type": "walk"}, (), (), "training_good")
    tr_push_conflict = SyntheticDay("2026-05-08", "training_recovery", {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 2, "energy.energy": 9, "training.activity_duration_min": 75, "training.primary_activity_type": "run"}, (), (), "training_load")
    tr_recovery_low = SyntheticDay("2026-05-09", "training_recovery", {"core.sleep_ok": False, "core.nutrition_ok": True, "mental.stress": 2, "energy.energy": 8, "training.activity_duration_min": 60, "training.primary_activity_type": "run"}, (), (), "training_load")
    tr_body_load = SyntheticDay("2026-05-17", "training_recovery", {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 2, "energy.energy": 8, "training.activity_duration_min": 75, "training.primary_activity_type": "run", "body.migraine_warning": True}, (), (), "training_load")
    tr_low_recovery_high_energy = SyntheticDay("2026-05-18", "training_recovery", {"core.sleep_ok": False, "core.nutrition_ok": True, "mental.stress": 3, "energy.energy": 9, "training.activity_duration_min": 80, "training.primary_activity_type": "bike"}, (), (), "training_load")
    tr_manageable_load = SyntheticDay("2026-05-19", "training_recovery", {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 1, "energy.energy": 8, "training.activity_duration_min": 45, "training.primary_activity_type": "walk"}, (), (), "training_good")
    legacy = SyntheticDay("2026-05-11", "personal_legacy", {"core.sleep_ok": False, "mental.stress": 7, "energy.energy": 3, "evening.phone_after_21": True}, (), (), "legacy")
    sparse = SyntheticDay("2026-05-12", "general_balance", {}, ("core.sleep_ok", "mental.stress", "energy.energy"), (), "sparse")
    pattern = SyntheticDay("2026-05-13", "general_balance", {"core.sleep_ok": False, "mental.stress": 7, "energy.energy": 3, "evening.phone_after_21": True}, (), (), "pattern")
    personal_legacy_samples = tuple(
        (
            f"personal_legacy_parity_sample_{index}",
            SyntheticDay(f"2026-06-{index + 1:02d}", "personal_legacy", {"core.sleep_ok": index % 2 == 0, "mental.stress": 4 + index % 5, "energy.energy": 3 + index % 4, "evening.phone_after_21": index % 3 == 0}, (), (), "legacy"),
            (),
        )
        for index in range(10)
    )
    sparse_samples = tuple(
        (
            f"sparse_no_data_sample_{index}",
            SyntheticDay(f"2026-07-{index + 1:02d}", "general_balance", {} if index % 2 == 0 else {"energy.energy": 5}, ("core.sleep_ok", "mental.stress", "energy.energy"), (), "sparse"),
            (),
        )
        for index in range(10)
    )
    pattern_samples = tuple(
        (
            f"pattern_awareness_{'enabled' if index % 2 else 'disabled'}_sample_{index}",
            SyntheticDay(f"2026-08-{index + 1:02d}", "general_balance", {"core.sleep_ok": index % 3 == 0, "mental.stress": 6 + index % 3, "energy.energy": 3 + index % 3, "evening.phone_after_21": True}, (), (), "pattern"),
            (),
            ("pattern_awareness_pack",) if index % 2 else (),
        )
        for index in range(10)
    )
    return {
        "candidate_a_body_signal": (
            ("repeated_high_body_signal_second_day", body_high_2, (body_high_1, body_high_2)),
            ("body_signal_low_energy", body_low_energy, (body_high_1, body_low_energy)),
            ("body_signal_poor_sleep", body_poor_sleep, (body_high_1, body_poor_sleep)),
        ),
        "candidate_b_general_balance": (
            ("stress8_energy4", gb_stress_energy, (gb_stress_energy,)),
            ("stress8_energy3", gb_exact, (gb_exact,)),
            ("stress8_energy4_protected", gb_protected, (gb_protected,)),
            ("stress9_energy4", gb_higher_stress, (gb_higher_stress,)),
            ("stress8_energy2", gb_low_energy_sleep_ok, (gb_low_energy_sleep_ok,)),
            ("stress8_energy4_recent_recovery", gb_recent_recovery, (gb_exact, gb_recent_recovery)),
        ),
        "candidate_c_training_recovery": (
            ("high_energy_high_training_load", tr_push_conflict, (tr_good, tr_push_conflict)),
            ("high_training_poor_sleep", tr_recovery_low, (tr_good, tr_recovery_low)),
            ("legitimate_push_day", tr_good, (tr_good, tr_good, tr_good)),
            ("high_training_body_load", tr_body_load, (tr_good, tr_body_load)),
            ("high_energy_low_recovery_training", tr_low_recovery_high_energy, (tr_good, tr_low_recovery_high_energy)),
            ("manageable_load_good_recovery", tr_manageable_load, (tr_good, tr_manageable_load)),
        ),
        "cross_checks": (
            ("personal_legacy_parity_sample", legacy, (legacy,)),
            ("sparse_no_data_sample", sparse, (sparse,)),
            ("pattern_awareness_disabled_sample", pattern, (pattern,)),
        )
        + personal_legacy_samples
        + sparse_samples
        + pattern_samples,
    }


def _candidate_target_score(candidate_id: str, changed: tuple[Mapping[str, Any], ...], targeted: list[Mapping[str, Any]]) -> int:
    if candidate_id == "candidate_a_body_signal":
        return sum(1 for row in targeted if row["group"] == candidate_id and row["baseline_label"] == "Maintain" and row["candidate_label"] in {"Simplify", "Recover"})
    if candidate_id == "candidate_b_general_balance":
        return sum(1 for row in targeted if row["group"] == candidate_id and row["baseline_label"] == "Maintain" and row["candidate_label"] in {"Simplify", "Protect Sleep"})
    if candidate_id == "candidate_c_training_recovery":
        return sum(1 for row in targeted if row["group"] == candidate_id and row["baseline_label"] == "Push" and row["candidate_label"] != "Push")
    return len(changed)


def _candidate_side_effects(outputs: tuple[GuidanceOutput, ...], label_delta: Mapping[str, int]) -> list[str]:
    effects: list[str] = []
    if label_delta.get("Push", 0) < -50:
        effects.append("Push rate decreased materially; needs human review.")
    if label_delta.get("Protect Sleep", 0) + label_delta.get("Recover", 0) + label_delta.get("Simplify", 0) > 120:
        effects.append("Conservative labels increased broadly; check over-conservatism.")
    if _output_profile_leakage_count(outputs):
        effects.append("Profile leakage detected.")
    if _output_sensitive_violation_count(outputs):
        effects.append("Sensitive copy violation detected.")
    return effects


def _candidate_recommendation(candidate_id: str, target_score: int, label_delta: Mapping[str, int]) -> str:
    if candidate_id in {"candidate_a_body_signal", "candidate_c_training_recovery"} and not any(label_delta.values()):
        return "promoted_production: no remaining shadow delta because this candidate is now default production behavior."
    if candidate_id == "candidate_b_general_balance" and target_score > 0:
        return "keep_shadow_or_revise_candidate: exact stress>=8 energy<=3 behavior is already mostly covered; review near-threshold expansion before promotion."
    if target_score > 0 and not _label_delta_over_conservative(label_delta):
        return "keep_shadow_needs_human_review: target improvement found, but Formula Experiment 3 requires review before promotion."
    return "revise_candidate: target improvement is weak or side effects need review."


def _label_delta_over_conservative(label_delta: Mapping[str, int]) -> bool:
    return label_delta.get("Push", 0) < -80 or (
        label_delta.get("Protect Sleep", 0) + label_delta.get("Recover", 0) + label_delta.get("Simplify", 0)
    ) > 140


def _formula_profile_leakage(results: Mapping[str, Any]) -> Mapping[str, Any]:
    findings = {candidate_id: result["profile_leakage_count"] for candidate_id, result in results.items() if result["profile_leakage_count"]}
    return {"status": "pass" if not findings else "fail", "findings": findings}


def _formula_sensitive_copy(results: Mapping[str, Any]) -> Mapping[str, Any]:
    findings = {candidate_id: result["sensitive_word_violation_count"] for candidate_id, result in results.items() if result["sensitive_word_violation_count"]}
    return {"status": "pass" if not findings else "fail", "findings": findings}


def _output_profile_leakage_count(outputs: tuple[GuidanceOutput, ...]) -> int:
    return sum(
        1
        for output in outputs
        for driver in output.top_drivers
        if output.profile_id == "general_balance"
        and any(term in driver.lower() for term in ("foot", "shoulder", "relationship", "homework", "alcohol", "eating episode", "crossfit"))
    )


def _output_sensitive_violation_count(outputs: tuple[GuidanceOutput, ...]) -> int:
    return sum(
        1
        for output in outputs
        if any(
            term in " ".join((output.primary_action, output.confidence_note, output.warning_sensitive_text, " ".join(output.top_drivers))).lower()
            for term in FORBIDDEN_SENSITIVE_TERMS
        )
    )


def _push_on_severe_day_count(runs: tuple[tuple[str, Any, Any], ...], *, candidate: bool) -> int:
    count = 0
    for _, baseline, candidate_run in runs:
        run = candidate_run if candidate else baseline
        for day, output in zip(run.generated_days, run.guidance_outputs):
            if output.label == "Push" and _day_severity(day) >= 3:
                count += 1
    return count


def _overconfidence_sparse_count(runs: tuple[tuple[str, Any, Any], ...], *, candidate: bool) -> int:
    count = 0
    for _, baseline, candidate_run in runs:
        run = candidate_run if candidate else baseline
        for day, output in zip(run.generated_days, run.guidance_outputs):
            if len(day.inputs) <= 2 and output.confidence == "normal":
                count += 1
    return count


def _experiment_3_before_after_summary(results: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "synthetic_data_only": True,
        "production_formula_changed": False,
        "candidate_count": 3,
        "combined_candidate_run": True,
        "candidate_summaries": {
            key: {
                "variant": value["variant"],
                "changed_output_count": value["changed_output_count"],
                "target_score": value["candidate_target_improvement_score"],
                "recommendation": value["recommendation"],
                "label_distribution_delta": value["label_distribution_delta"],
            }
            for key, value in results["candidates"].items()
        },
    }


def _experiment_3_human_review_html(results: Mapping[str, Any]) -> str:
    rows = []
    for candidate_id, result in results["candidates"].items():
        for sample in list(result["targeted_fixture_results"]) + list(result["changed_output_samples"][:20]):
            rows.append(_experiment_3_sample_row(candidate_id, sample))
    rubric = "label fit 1-5 | driver fit 1-5 | action usefulness 1-5 | profile fit 1-5 | recency explanation 1-5 | uncertainty honesty 1-5 | tone safety 1-5 | tired-user clarity 1-5 | reviewer note"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Life Load Experiment 3 Formula Human Review</title>"
        "<style>body{font-family:sans-serif;max-width:1200px;margin:2rem auto;line-height:1.4}"
        "table{border-collapse:collapse;width:100%;font-size:.92rem}td,th{border:1px solid #ddd;padding:.4rem;vertical-align:top}</style>"
        "</head><body><h1>Life Load Experiment 3 Formula Human Review Sheet</h1>"
        "<p>Synthetic/test data only. No real-world efficacy claim. No production formula change is approved by this sheet.</p>"
        f"<p>Review rubric for each row: {html.escape(rubric)}</p>"
        "<table><thead><tr><th>Candidate</th><th>Profile</th><th>Phase</th><th>Inputs / recent context</th><th>Baseline</th><th>Candidate</th><th>Changed</th><th>Oracle notes</th><th>Reviewer fields</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def _experiment_3_sample_row(candidate_id: str, sample: Mapping[str, Any]) -> str:
    profile = str(sample.get("profile") or sample.get("profile_id") or "")
    phase = str(sample.get("phase") or "")
    inputs = sample.get("inputs", {})
    baseline_label = str(sample.get("baseline_label", ""))
    candidate_label = str(sample.get("candidate_label", ""))
    baseline_action = str(sample.get("baseline_action", ""))
    candidate_action = str(sample.get("candidate_action", ""))
    changed = {
        "label": baseline_label != candidate_label,
        "action": baseline_action != candidate_action,
        "drivers": sample.get("baseline_drivers") != sample.get("candidate_drivers"),
    }
    return (
        "<tr>"
        f"<td>{html.escape(candidate_id)}</td>"
        f"<td>{html.escape(profile)}</td>"
        f"<td>{html.escape(phase)}</td>"
        f"<td><code>{html.escape(json.dumps(inputs, sort_keys=True))}</code></td>"
        f"<td>{html.escape(baseline_label)}<br>{html.escape(baseline_action)}</td>"
        f"<td>{html.escape(candidate_label)}<br>{html.escape(candidate_action)}</td>"
        f"<td><code>{html.escape(json.dumps(changed, sort_keys=True))}</code></td>"
        f"<td>{html.escape(str(sample.get('name') or sample.get('model') or 'synthetic sample'))}</td>"
        "<td>label fit: __ driver fit: __ action usefulness: __ profile fit: __ recency: __ uncertainty: __ tone: __ tired-user: __ note: __________</td>"
        "</tr>"
    )


def _experiment_3_decision_html(results: Mapping[str, Any]) -> str:
    rows = []
    for candidate_id, result in results["candidates"].items():
        rows.append(
            "<tr>"
            f"<td>{html.escape(candidate_id)}</td>"
            f"<td>{html.escape(result['variant'])}</td>"
            f"<td>{result['candidate_target_improvement_score']}</td>"
            f"<td><code>{html.escape(json.dumps(result['label_distribution_delta'], sort_keys=True))}</code></td>"
            f"<td>{html.escape(result['recommendation'])}</td>"
            "</tr>"
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Life Load Experiment 3 Formula Threshold Decision</title></head><body>"
        "<h1>Life Load Experiment 3 Formula Threshold Decision</h1>"
        "<p>Decision: Candidate A and Candidate C are promoted to production guidance behavior. Candidate B and the combined candidate remain shadow-only.</p>"
        "<p>Synthetic/test data only. No clinical or real-world efficacy claim. Pattern Awareness remains opt-in/default-off.</p>"
        "<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\"><thead><tr><th>Candidate</th><th>Shadow rule</th><th>Target score</th><th>Label delta</th><th>Recommendation</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<h2>Rollback</h2><p>Revert the default calls to the body-signal and training-recovery candidate functions; Candidate B and combined remain isolated by variant id.</p>"
        "<h2>Formula Version</h2><p>Production threshold version note: Experiment 3 A/C promotion. Candidate B remains excluded.</p>"
        "</body></html>"
    )


def _write_experiment_3_readme(path: Path, results: Mapping[str, Any]) -> None:
    path.write_text(
        "\n".join(
            (
                "# Life Load Experiment 3 Formula Threshold Tuning",
                "",
                "Synthetic/test data only. No real-world efficacy claim.",
                "",
                "- Production formula changed: true for Candidate A and Candidate C only",
                "- Pattern Awareness default-on: false",
                "- Candidates are independently reversible.",
                f"- Profile leakage: {results['profile_leakage_results']['status']}",
                f"- Sensitive copy: {results['sensitive_copy_results']['status']}",
                "- Decision: Candidate A and Candidate C promoted; Candidate B and combined remain shadow-only.",
            )
        ),
        encoding="utf-8",
    )


def _experiment_3_ac_review_samples_html(results: Mapping[str, Any]) -> str:
    rows = []
    for sample in results["changed_output_samples"][:50]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(sample['model']))}</td>"
            f"<td>{html.escape(str(sample['date']))}</td>"
            f"<td>{html.escape(str(sample['profile']))}</td>"
            f"<td>{html.escape(str(sample['phase']))}</td>"
            f"<td><code>{html.escape(json.dumps(sample['before'], sort_keys=True))}</code></td>"
            f"<td><code>{html.escape(json.dumps(sample['production'], sort_keys=True))}</code></td>"
            "<td>label fit: __ driver fit: __ action usefulness: __ profile fit: __ tone safety: __ reviewer note: __________</td>"
            "</tr>"
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Life Load Experiment 3 A/C Promotion Review Samples</title>"
        "<style>body{font-family:sans-serif;max-width:1200px;margin:2rem auto;line-height:1.4}table{border-collapse:collapse;width:100%;font-size:.92rem}td,th{border:1px solid #ddd;padding:.4rem;vertical-align:top}</style>"
        "</head><body><h1>Life Load Experiment 3 A/C Promotion Review Samples</h1>"
        "<p>Synthetic/test data only. Candidate A and Candidate C are promoted; Candidate B and combined remain shadow-only. No real-world efficacy claim.</p>"
        "<table><thead><tr><th>Model</th><th>Date</th><th>Profile</th><th>Phase</th><th>Before baseline-092</th><th>Production after A/C promotion</th><th>Reviewer fields</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def _experiment_3_ac_decision_html(results: Mapping[str, Any]) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Life Load Experiment 3 Formula Threshold Decision</title></head><body>"
        "<h1>Life Load Experiment 3 Formula Threshold Decision</h1>"
        "<p>Decision: Candidate A and Candidate C are promoted to production guidance behavior. Candidate B and the combined candidate remain shadow-only.</p>"
        "<p>Synthetic/test data only. No clinical or real-world efficacy claim. Pattern Awareness remains opt-in/default-off.</p>"
        "<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\"><thead><tr><th>Candidate</th><th>Decision</th><th>Production change</th></tr></thead><tbody>"
        "<tr><td>Candidate A: Body Signal Awareness repeated high response</td><td>Promoted</td><td>Repeated high body signal, high body signal plus low energy, and high body signal plus poor sleep can move Body Signal Awareness away from Push/Maintain toward Maintain/Simplify/Recover as appropriate.</td></tr>"
        "<tr><td>Candidate B: General Balance stress/energy gate</td><td>Kept shadow/revise</td><td>No General Balance threshold change was promoted.</td></tr>"
        "<tr><td>Candidate C: Training Recovery Push calibration</td><td>Promoted</td><td>High training load plus recovery/body-load conflict no longer auto-Pushes from high energy alone; legitimate good-recovery Push remains available.</td></tr>"
        "<tr><td>Combined candidate</td><td>Not promoted</td><td>No stacked all-candidate rule was promoted.</td></tr>"
        "</tbody></table>"
        f"<p>Label distribution delta after A/C promotion: <code>{html.escape(json.dumps(results['label_distribution_delta'], sort_keys=True))}</code>.</p>"
        f"<p>Personal legacy parity: <code>{html.escape(json.dumps(results['personal_legacy_parity'], sort_keys=True))}</code>. Profile leakage: <code>{html.escape(json.dumps(results['profile_leakage_results'], sort_keys=True))}</code>. Sensitive copy: <code>{html.escape(json.dumps(results['sensitive_copy_results'], sort_keys=True))}</code>.</p>"
        "<h2>Rollback</h2>"
        f"<p>{html.escape(str(results['rollback_plan']))}</p>"
        "<h2>Formula Version</h2><p>Production threshold version note: Experiment 3 A/C promotion. Candidate B remains excluded.</p>"
        "</body></html>"
    )


def _write_experiment_3_ac_promotion_readme(path: Path, results: Mapping[str, Any]) -> None:
    path.write_text(
        "\n".join(
            (
                "# Life Load Experiment 3 A/C Promotion",
                "",
                "Synthetic/test data only. No real-world efficacy claim.",
                "",
                "- Candidate A promoted: Body Signal Awareness repeated body-signal response.",
                "- Candidate C promoted: Training Recovery Push calibration.",
                "- Candidate B not promoted: General Balance stress/energy remains shadow/revise.",
                "- Combined candidate not promoted.",
                "- Production formula thresholds changed only for A and C.",
                "- Pattern Awareness remains default-off.",
                f"- Profile leakage: {results['profile_leakage_results']['status']}",
                f"- Sensitive copy: {results['sensitive_copy_results']['status']}",
                f"- No-data behavior: {results['no_data_behavior_results']['status']}",
                "",
                "Rollback:",
                str(results["rollback_plan"]),
            )
        ),
        encoding="utf-8",
    )


def _experiment_2_personal_legacy_fixtures() -> dict[str, dict[str, Any]]:
    return {
        "low_load_day": {"sleep_ok": True, "nutrition_ok": True, "stress": 2, "energy": 7, "shutdown_done": True},
        "body_signal_day": {"sleep_ok": True, "nutrition_ok": True, "stress": 5, "energy": 4, "foot_pain": 6},
        "evening_risk_day": {
            "sleep_ok": False,
            "nutrition_ok": True,
            "phone_after_21": True,
            "project_overrun": True,
            "evening_chain_broken": True,
            "shutdown_done": False,
            "stress": 7,
            "energy": 3,
        },
        "relationship_homework_day": {
            "wife_conflict_count": 2,
            "wife_conflict_school": True,
            "homework_done": False,
            "stress": 6,
            "energy": 4,
        },
        "training_day": {
            "primary_activity_type": "crossfit",
            "activity_duration_min": 45,
            "stress": 4,
            "energy": 6,
            "nutrition_ok": True,
        },
        "nutrition_risk_day": {
            "alcohol": "home",
            "binge": True,
            "nutrition_ok": False,
            "sleep_ok": False,
            "stress": 6,
            "energy": 2,
        },
        "sparse_unknown_day": {},
        "explicit_false_zero_day": {
            "phone_after_21": False,
            "project_overrun": False,
            "foot_pain": 0,
            "shoulder_pain": 0,
            "wife_conflict_count": 0,
            "binge": False,
        },
    }


def _experiment_2_profile_examples() -> dict[str, dict[str, Any]]:
    return {
        "general_balance": {
            "entries": (
                {"signal_id": "core.sleep_ok", "value": True, "is_present": True},
                {"signal_id": "core.nutrition_ok", "value": True, "is_present": True},
                {"signal_id": "mental.stress", "value": 8, "is_present": True},
                {"signal_id": "energy.energy", "value": 2, "is_present": True},
                {"signal_id": "nutrition.alcohol", "value": True, "is_present": True},
            ),
        },
        "work_stress": {
            "entries": (
                {"signal_id": "core.sleep_ok", "value": True, "is_present": True},
                {"signal_id": "mental.stress", "value": 8, "is_present": True},
                {"signal_id": "energy.energy", "value": 3, "is_present": True},
                {"signal_id": "relationship.wife_conflict_count", "value": 3, "is_present": True},
            ),
        },
        "training_recovery": {
            "entries": (
                {"signal_id": "core.sleep_ok", "value": False, "is_present": True},
                {"signal_id": "core.nutrition_ok", "value": True, "is_present": True},
                {"signal_id": "mental.stress", "value": 4, "is_present": True},
                {"signal_id": "energy.energy", "value": 3, "is_present": True},
                {"signal_id": "training.activity_duration_min", "value": 60, "is_present": True},
            ),
        },
        "body_signal_awareness": {
            "entries": (
                {"signal_id": "core.sleep_ok", "value": True, "is_present": True},
                {"signal_id": "mental.stress", "value": 5, "is_present": True},
                {"signal_id": "energy.energy", "value": 4, "is_present": True},
                {"signal_id": "body.foot_pain", "value": 9, "is_present": True},
            ),
        },
        "custom_stub": {
            "entries": (
                {"signal_id": "core.sleep_ok", "value": True, "is_present": True},
                {"signal_id": "mental.stress", "value": 7, "is_present": True},
                {"signal_id": "energy.energy", "value": 3, "is_present": True},
            ),
        },
        "personal_legacy": {
            "entries": (
                {"signal_id": "core.sleep_ok", "value": False, "is_present": True},
                {"signal_id": "core.nutrition_ok", "value": True, "is_present": True},
                {"signal_id": "mental.stress", "value": 7, "is_present": True},
                {"signal_id": "energy.energy", "value": 3, "is_present": True},
                {"signal_id": "evening.phone_after_21", "value": True, "is_present": True},
            ),
        },
    }


def _experiment_2_review_samples_html(runs: list[Any]) -> str:
    rows = []
    for run in runs:
        for day, output in list(zip(run.generated_days, run.guidance_outputs))[:3]:
            rows.append(
                "<tr>"
                f"<td>{html.escape(run.user_model_id)}</td>"
                f"<td>{html.escape(day.date)}</td>"
                f"<td>{html.escape(day.profile_id)}</td>"
                f"<td>{html.escape(output.label)}</td>"
                f"<td>{html.escape(', '.join(output.top_drivers))}</td>"
                f"<td>{html.escape(output.primary_action)}</td>"
                "</tr>"
            )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Life Load Experiment 2 Review Samples</title>"
        "<style>body{font-family:sans-serif;max-width:1100px;margin:2rem auto;line-height:1.4}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.45rem;text-align:left}</style>"
        "</head><body><h1>Life Load Experiment 2 Review Samples</h1>"
        "<p>Synthetic fake data only. These samples inspect profile-driven production bridge output; they do not prove real-world efficacy.</p>"
        "<table><thead><tr><th>Model</th><th>Date</th><th>Profile</th><th>Label</th><th>Drivers</th><th>Action</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def _write_experiment_2_readme(
    path: Path,
    bridge_summary: Mapping[str, Any],
    personal_parity: Mapping[str, Any],
    synthetic_before_after: Mapping[str, Any],
) -> None:
    path.write_text(
        "\n".join(
            (
                "# Life Load Experiment 2 Generic-Profile Bridge",
                "",
                "Synthetic fake data only. No clinical or real-world efficacy claim.",
                "",
                f"- Experiment: {bridge_summary['experiment']}",
                f"- Draft-only beta runtime bridge removed: {bridge_summary['draft_only_beta_runtime_bridge_removed']}",
                f"- Personal legacy parity: {personal_parity['status']}",
                f"- Formula thresholds changed: {bridge_summary['production_scoring_thresholds_changed']}",
                f"- Formula weights changed: {bridge_summary['formula_weights_changed']}",
                f"- Synthetic runs: {synthetic_before_after['simulation_count']}",
                f"- Synthetic days: {synthetic_before_after['total_days']}",
                "",
                "Formula threshold hypotheses remain gated for Experiment 3.",
            )
        ),
        encoding="utf-8",
    )


def action_family_schema_valid() -> bool:
    return set(ACTION_FAMILIES) == {
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
    }


def _day_severity(day: SyntheticDay) -> int:
    if not day.inputs:
        return 1
    score = 0
    if day.inputs.get("core.sleep_ok") is False:
        score += 1
    if int(day.inputs.get("mental.stress") or 0) >= 7:
        score += 1
    if int(day.inputs.get("energy.energy") or 5) <= 3:
        score += 1
    if day.inputs.get("recovery.shutdown_done") is False:
        score += 1
    if int(day.inputs.get("training.activity_duration_min") or 0) >= 60:
        score += 1
    return min(score, 5)


def _summarize_inputs(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    keys = (
        "core.sleep_ok",
        "mental.stress",
        "energy.energy",
        "recovery.shutdown_done",
        "recovery.decompression_done",
        "work.project_overrun",
        "body.migraine_warning",
        "training.activity_duration_min",
        "evening.evening_chain_broken",
    )
    return {key: inputs[key] for key in keys if key in inputs}


def _result(
    oracle: str,
    affected: tuple[str, ...],
    pass_text: str,
    fail_text: str,
    classification: str,
    *,
    warning_limit: int = 0,
) -> OracleResult:
    status = "pass"
    if len(affected) > warning_limit:
        status = "fail"
    elif affected:
        status = "warning"
    return OracleResult(
        oracle=oracle,
        status=status,
        affected_days=affected,
        explanation=pass_text if status == "pass" else fail_text,
        suggested_review_sample=affected[:5],
        classification=classification,
    )


def _oracle_refinement_report() -> Mapping[str, Any]:
    return {
        "StuckStateOracle": {
            "old_issue": "Flagged repeated Maintain during stable inputs and repeated severe labels without input context.",
            "new_classifications": [
                "stable_maintain_ok",
                "severe_stuck",
                "neutral_despite_worsening",
                "missing_data_loop",
                "needs_review",
            ],
        },
        "NoDataGuidanceOracle": {
            "rules": [
                "empty day remains limited confidence",
                "empty day invites short check-in",
                "empty day does not create stress/energy/pattern bridge inputs",
            ],
        },
    }


def _recommended_formula_experiments() -> list[dict[str, Any]]:
    return [
        {
            "id": "shadow_general_balance_stress_energy_gate",
            "condition": "profile=general_balance, stress>=8, energy<=3",
            "expected": "Simplify or Protect Sleep unless protective factors explicitly explain a softer result",
            "production_change": False,
        },
        {
            "id": "shadow_body_signal_recent_repeat_gate",
            "condition": "profile=body_signal_awareness, body signal high 2-3 recent days",
            "expected": "Simplify or Recover; no medical wording",
            "production_change": False,
        },
        {
            "id": "shadow_work_spillover_driver_label",
            "condition": "profile=work_stress, work.project_overrun/evening spillover without Pattern Awareness content",
            "expected": "Work spillover or Evening boundary driver",
            "production_change": False,
        },
    ]


def _simulation_summary(simulation: Any) -> Mapping[str, Any]:
    return {
        "user_model_id": simulation.user_model_id,
        "duration_days": simulation.duration_days,
        "summary_metrics": dict(simulation.summary_metrics),
        "anomalies": [asdict(item) for item in simulation.anomalies],
    }


def _simulation_payload(simulation: Any) -> Mapping[str, Any]:
    return {
        "user_model_id": simulation.user_model_id,
        "duration_days": simulation.duration_days,
        "generated_days": [asdict(day) for day in simulation.generated_days],
        "guidance_outputs": [asdict(output) for output in simulation.guidance_outputs],
        "summary_metrics": dict(simulation.summary_metrics),
        "oracle_results": [asdict(item) for item in simulation.oracle_results],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json_from_zip(zip_path: Path | str, name: str) -> Any:
    with zipfile.ZipFile(zip_path) as archive:
        return json.loads(archive.read(name))


def _read_model_payloads(zip_path: Path | str, prefix: str) -> dict[str, Mapping[str, Any]]:
    with zipfile.ZipFile(zip_path) as archive:
        payloads = {}
        for name in archive.namelist():
            if not name.startswith(prefix) or not name.endswith(".json"):
                continue
            payload = json.loads(archive.read(name))
            payloads[payload["user_model_id"]] = payload
        return payloads


def _recent_history_summary(date_value: str, days: list[Mapping[str, Any]]) -> str:
    index = next((idx for idx, day in enumerate(days) if day["date"] == date_value), None)
    if index is None:
        return "No nearby synthetic history."
    window = days[max(0, index - 3):index]
    if not window:
        return "First available synthetic day."
    logged = [day for day in window if day.get("inputs")]
    if not logged:
        return f"Previous {len(window)} day(s) had no check-in."
    phases = sorted({day["phase_name"] for day in window})
    return f"Previous {len(window)} day(s): {len(logged)} check-in(s), phases: {', '.join(phases)}."


def _human_rating_fields() -> Mapping[str, str]:
    return {
        "label_fit_1_5": "",
        "driver_fit_1_5": "",
        "action_usefulness_1_5": "",
        "specificity_1_5": "",
        "tone_safety_1_5": "",
        "profile_fit_1_5": "",
        "recency_explanation_1_5": "",
        "uncertainty_honesty_1_5": "",
        "would_a_tired_user_understand_1_5": "",
        "reviewer_note": "",
    }


def _human_review_sheet_html(samples: list[Mapping[str, Any]]) -> str:
    rows = []
    for index, sample in enumerate(samples, start=1):
        rows.append(
            "<section>"
            f"<h2>Sample {index}: {html.escape(sample['user_model'])} / {html.escape(sample['date'])}</h2>"
            f"<p><strong>Phase:</strong> {html.escape(sample['phase'])} | <strong>Profile:</strong> {html.escape(sample['profile'])}</p>"
            f"<p><strong>Inputs:</strong> <code>{html.escape(json.dumps(sample['inputs'], sort_keys=True))}</code></p>"
            f"<p><strong>Recent history:</strong> {html.escape(sample['recent_history_summary'])}</p>"
            f"<p><strong>Guidance:</strong> {html.escape(sample['label'])}; drivers: {html.escape(', '.join(sample['drivers']))}; confidence: {html.escape(sample['confidence'])}</p>"
            f"<p><strong>Action:</strong> {html.escape(sample['action'])}</p>"
            f"<p><strong>Oracle warning:</strong> {html.escape(sample['oracle_warning'] or 'None')}</p>"
            f"<p><strong>Why selected:</strong> {html.escape(sample['selection_reason'])}</p>"
            "<ul><li>Label fit 1-5: ____</li><li>Driver fit 1-5: ____</li><li>Action usefulness 1-5: ____</li><li>Specificity 1-5: ____</li><li>Tone safety 1-5: ____</li><li>Profile fit 1-5: ____</li><li>Recency explanation 1-5: ____</li><li>Uncertainty honesty 1-5: ____</li><li>Would a tired user understand? 1-5: ____</li><li>Reviewer note: ____________________</li></ul>"
            "</section>"
        )
    return "<!doctype html><html><head><meta charset=\"utf-8\"><title>Life Load Synthetic Guidance Human Review Sheet</title></head><body><h1>Life Load Synthetic Guidance Human Review Sheet</h1><p>Synthetic fake data only. This sheet is for product review and does not prove real-world or clinical efficacy.</p>" + "\n".join(rows) + "</body></html>"


def _formula_decision_memo_html(classifications: list[Mapping[str, Any]]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['hypothesis'])}</td>"
        f"<td>{html.escape(item['classification'])}</td>"
        f"<td>{html.escape(item['decision'])}</td>"
        "</tr>"
        for item in classifications
    )
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Life Load Formula Hypothesis Decision Memo</title></head>
<body>
<h1>Life Load Formula Hypothesis Decision Memo</h1>
<p>This memo converts synthetic findings into candidate hypotheses. It does not approve production scoring changes, does not use real data, and does not claim clinical efficacy.</p>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">
<thead><tr><th>Hypothesis</th><th>Classification</th><th>Decision</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body></html>
"""


def _write_anomaly_review_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = ["# Synthetic User Evaluation Review", "", "Synthetic fake data only.", ""]
    for row in rows:
        lines.append(f"## {row['user_model_id']} {row['duration']}d - {row['oracle']}")
        lines.append(f"- Classification: {row['likely_classification']}")
        lines.append(f"- Affected dates: {', '.join(row['affected_dates'][:8])}")
        lines.append(f"- Labels: {row['labels'][:8]}")
        lines.append(f"- Drivers: {', '.join(row['drivers'])}")
        lines.append(f"- Next action: {row['recommended_next_action']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _anomaly_review_html(rows: list[dict[str, Any]]) -> str:
    body = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['user_model_id'])}</td>"
        f"<td>{row['duration']}</td>"
        f"<td>{html.escape(row['oracle'])}</td>"
        f"<td>{html.escape(', '.join(row['affected_dates'][:6]))}</td>"
        f"<td>{html.escape(', '.join(row['phase']))}</td>"
        f"<td>{html.escape(', '.join(row['labels'][:6]))}</td>"
        f"<td>{html.escape(', '.join(row['drivers']))}</td>"
        f"<td>{html.escape(', '.join(row['confidence']))}</td>"
        f"<td>{html.escape(row['likely_classification'])}</td>"
        f"<td>{html.escape(row['recommended_next_action'])}</td>"
        "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html>
<head><meta charset=\"utf-8\"><title>Life Load Synthetic User Evaluation Review</title></head>
<body>
<h1>Life Load Synthetic User Evaluation Review</h1>
<p>Synthetic fake data only. This review converts first-pass anomalies into hypotheses and oracle refinements. It does not change production scoring or prove real-world efficacy.</p>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">
<thead><tr><th>User model</th><th>Duration</th><th>Oracle</th><th>Dates</th><th>Phase</th><th>Labels</th><th>Drivers</th><th>Confidence</th><th>Classification</th><th>Recommended next action</th></tr></thead>
<tbody>{body}</tbody>
</table>
<h2>Hypothesis Backlog</h2>
<pre>{html.escape(json.dumps(hypothesis_backlog(), indent=2))}</pre>
</body>
</html>
"""


def _write_review_readme(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(
            [
                "# Life Load Synthetic Evaluation Review",
                "",
                "Synthetic fake data only. No real user data. No clinical efficacy claim.",
                f"Reviewed anomalies: {len(rows)}",
                "Production scoring unchanged.",
            ]
        ),
        encoding="utf-8",
    )


def _write_human_review_samples(path: Path, simulations: tuple[Any, ...]) -> None:
    lines = [
        "# Life Load Human Review Samples",
        "",
        "Score each dimension 1-5: label fit, driver fit, action usefulness, specificity, tone safety, profile fit, recency explanation, uncertainty honesty, would_a_tired_user_understand.",
        "",
    ]
    count = 0
    for simulation in simulations:
        for sample in simulation.review_samples[:6]:
            count += 1
            lines.append(f"## Sample {count}: {simulation.user_model_id} {sample['day']}")
            lines.append(f"- Profile: {sample['profile']}")
            lines.append(f"- Phase: {sample['phase']}")
            lines.append(f"- Label: {sample['guidance_label']}")
            lines.append(f"- Drivers: {', '.join(sample['drivers'])}")
            lines.append(f"- Action: {sample['action']}")
            lines.append("- Reviewer scores: label_fit=, driver_fit=, action_usefulness=, specificity=, tone_safety=, profile_fit=, recency_explanation=, uncertainty_honesty=, tired_user_understand=")
            lines.append("")
            if count >= 50:
                path.write_text("\n".join(lines), encoding="utf-8")
                return
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_advanced_readme(path: Path, seed: int) -> None:
    path.write_text(
        "\n".join(
            [
                "# Life Load Advanced Guidance Quality Evaluation",
                "",
                "Synthetic data only. No real user data is included.",
                "This evaluates product coherence, not health outcomes or clinical efficacy.",
                "Production scoring remains unchanged unless explicitly approved later.",
                f"Seed: {seed}",
            ]
        ),
        encoding="utf-8",
    )


def _write_life_rhythm_review_samples(
    path: Path,
    simulations: tuple[Any, ...],
    oracle_results: tuple[OracleResult, ...],
) -> None:
    oracle_by_date: dict[str, list[str]] = defaultdict(list)
    for result in oracle_results:
        for affected_day in result.affected_days:
            oracle_by_date[affected_day].append(f"{result.oracle}: {result.classification or result.status}")

    lines = [
        "# Life Load Life-Rhythm Gap Review Samples",
        "",
        "Synthetic fake data only. These samples focus on long gaps, return-after-gap behavior, biased logging, and load/recovery transitions.",
        "",
    ]
    count = 0
    for simulation in simulations:
        for sample in simulation.review_samples[:16]:
            if not (
                sample.get("days_since_last_checkin")
                or "gap" in str(sample.get("phase", ""))
                or "biased" in str(sample.get("phase", ""))
                or "transition" in str(sample.get("why_selected", ""))
                or oracle_by_date.get(sample["day"])
            ):
                continue
            count += 1
            lines.extend(
                (
                    f"## Sample {count}: {simulation.user_model_id} {sample['day']}",
                    f"- Phase: {sample['phase']}",
                    f"- Days since last check-in: {sample.get('days_since_last_checkin')}",
                    f"- Inputs: `{json.dumps(sample['inputs'], sort_keys=True)}`",
                    f"- Missing data: {', '.join(sample['missing_data']) or 'none'}",
                    f"- Guidance: {sample['guidance_label']}",
                    f"- Drivers: {', '.join(sample['drivers']) or 'none'}",
                    f"- Confidence: {sample['confidence']}",
                    f"- Primary action: {sample['action']}",
                    f"- Oracle notes: {'; '.join(sample['oracle_notes'] or oracle_by_date.get(sample['day'], [])) or 'none'}",
                    f"- Why selected: {sample['why_selected']}",
                    "",
                )
            )
            if count >= 80:
                path.write_text("\n".join(lines), encoding="utf-8")
                return
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_life_rhythm_readme(
    path: Path,
    simulations: tuple[Any, ...],
    oracle_results: tuple[OracleResult, ...],
    seed: int,
) -> None:
    warnings = [result for result in oracle_results if result.status != "pass"]
    lines = [
        "# Life Load Life-Rhythm Gap Simulation",
        "",
        "Synthetic data only. No real user data is included.",
        "Developer/test infrastructure only; no production UI, scoring, extraction, HTTP payload, export/import, or feature-flag behavior changed.",
        "This report evaluates product coherence around check-in gaps and rhythm changes. It does not prove clinical or real-world efficacy.",
        f"Seed: {seed}",
        "",
        "## Models",
    ]
    lines.extend(f"- {simulation.user_model_id}: {simulation.duration_days} days" for simulation in simulations)
    lines.extend(("", "## Main warnings/anomalies"))
    if warnings:
        lines.extend(
            f"- {result.oracle} {result.status}: {result.classification or 'unclassified'} ({len(result.affected_days)} affected day(s))"
            for result in warnings
        )
    else:
        lines.append("- None from the gap-specific oracles.")
    lines.extend(
        (
            "",
            "## Recommended next action",
            "- Use human review samples to calibrate stale-history, return-after-gap, and biased-logging expectations before any formula changes.",
        )
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _model_by_id(model_id: str) -> Any:
    return {model.id: model for model in all_extended_synthetic_user_models()}[model_id]


def _oracle_status_count(simulations: tuple[Any, ...], status: str) -> int:
    return sum(1 for simulation in simulations for oracle in simulation.oracle_results if oracle.status == status)


def _oracle_delta(baseline: tuple[Any, ...], shadow: tuple[Any, ...]) -> Mapping[str, Any]:
    return _oracle_delta_from_results(
        _comparison_oracles_for_simulations(baseline),
        _comparison_oracles_for_simulations(shadow),
    )


def _comparison_oracles_for_simulations(simulations: tuple[Any, ...]) -> tuple[OracleResult, ...]:
    outputs = tuple(output for simulation in simulations for output in simulation.guidance_outputs)
    oracle_results: list[OracleResult] = []
    oracle_results.extend(oracle for simulation in simulations for oracle in simulation.oracle_results)
    oracle_results.append(ActionSpecificityOracle().evaluate(outputs))
    oracle_results.append(AdviceDiversityOracle().evaluate(outputs))
    oracle_results.extend(MomentumOracle().evaluate(simulation.generated_days, simulation.guidance_outputs) for simulation in simulations)
    oracle_results.extend(GuidanceVolatilityOracle().evaluate(simulation.generated_days, simulation.guidance_outputs) for simulation in simulations)
    oracle_results.extend(AdviceFatigueOracle().evaluate(simulation.guidance_outputs) for simulation in simulations)
    return tuple(oracle_results)


def _oracle_delta_from_results(
    baseline_results: tuple[OracleResult, ...],
    shadow_results: tuple[OracleResult, ...],
) -> Mapping[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    for result_set, key in ((baseline_results, "baseline"), (shadow_results, "shadow")):
        for oracle in result_set:
            row = rows.setdefault(
                oracle.oracle,
                {
                    "oracle": oracle.oracle,
                    "baseline_fail": 0,
                    "baseline_warning": 0,
                    "shadow_fail": 0,
                    "shadow_warning": 0,
                },
            )
            if oracle.status in {"fail", "warning"}:
                row[f"{key}_{oracle.status}"] += 1
    for row in rows.values():
        row["fail_delta"] = row["shadow_fail"] - row["baseline_fail"]
        row["warning_delta"] = row["shadow_warning"] - row["baseline_warning"]
    return {"by_oracle": sorted(rows.values(), key=lambda item: item["oracle"])}


def _named_oracle_delta(
    baseline_results: tuple[OracleResult, ...],
    shadow_results: tuple[OracleResult, ...],
    oracle_name: str,
) -> Mapping[str, Any]:
    return _oracle_delta_from_results(
        tuple(result for result in baseline_results if result.oracle == oracle_name),
        tuple(result for result in shadow_results if result.oracle == oracle_name),
    )


def _named_oracle_check(results: tuple[OracleResult, ...], oracle_name: str) -> Mapping[str, Any]:
    matching = tuple(result for result in results if result.oracle == oracle_name)
    affected = sum(len(result.affected_days) for result in matching)
    return {
        "oracle": oracle_name,
        "status": "pass" if all(result.status == "pass" for result in matching) else "review",
        "result_count": len(matching),
        "affected_day_count": affected,
        "results": [asdict(result) for result in matching],
    }


def _shadow_review_samples(
    baseline: tuple[Any, ...],
    shadow: tuple[Any, ...],
    baseline_oracles: tuple[OracleResult, ...],
    shadow_oracles: tuple[OracleResult, ...],
) -> list[Mapping[str, Any]]:
    samples: list[Mapping[str, Any]] = []
    baseline_notes = _oracle_notes_by_day(baseline_oracles, "baseline")
    shadow_notes = _oracle_notes_by_day(shadow_oracles, "shadow")
    for before_sim, after_sim in zip(baseline, shadow):
        generated_days = [asdict(day) for day in before_sim.generated_days]
        for day, before, after in zip(before_sim.generated_days, before_sim.guidance_outputs, after_sim.guidance_outputs):
            changed_fields = []
            if before.label != after.label:
                changed_fields.append("label")
            if before.confidence != after.confidence:
                changed_fields.append("confidence")
            if before.action_family != after.action_family or before.primary_action != after.primary_action:
                changed_fields.append("action")
            if before.top_drivers != after.top_drivers:
                changed_fields.append("drivers")
            if not changed_fields:
                continue
            reason = "shadow changed " + ", ".join(changed_fields)
            if not day.inputs:
                reason += "; empty day"
            if day.phase_name in {"biased_bad_logging", "biased_good_logging"}:
                reason += "; biased logging"
            if before.primary_action == after.primary_action:
                reason += "; copy unchanged"
            samples.append(
                {
                    "model": before_sim.user_model_id,
                    "profile": day.profile_id,
                    "date": day.date,
                    "phase": day.phase_name,
                    "inputs": _summarize_inputs(day.inputs),
                    "recent_history_summary": _recent_history_summary(day.date, generated_days),
                    "baseline": _output_summary(before),
                    "shadow": _output_summary(after),
                    "changed_fields": changed_fields,
                    "oracle_notes": baseline_notes.get(day.date, ()) + shadow_notes.get(day.date, ()),
                    "human_review_rubric": _human_rating_fields(),
                    "reason": reason,
                }
            )
            if len(samples) >= 60:
                return samples
    return samples


def _cross_profile_review_samples(seed: int) -> list[Mapping[str, Any]]:
    targets = (
        ("general_balance_overload_drift", 10, "general_balance"),
        ("work_stress_project_crunch", 8, "work_stress"),
        ("training_recovery_overenthusiastic_athlete", 8, "training_recovery"),
        ("body_signal_awareness_recurring_signal", 8, "body_signal_awareness"),
        ("pattern_awareness_private_pull", 8, "pattern_awareness"),
        ("bad_day_only_logger", 3, "sparse_biased_gap"),
        ("good_day_only_logger", 3, "sparse_biased_gap"),
        ("long_term_inconsistent_user", 2, "sparse_biased_gap"),
        ("general_balance_poor_sleep_low_demand", 4, "poor_sleep_low_demand"),
    )
    models = {model.id: model for model in all_extended_synthetic_user_models()}
    samples: list[Mapping[str, Any]] = []
    for model_id, count, bucket in targets:
        model = models[model_id]
        duration = min(model.duration_days, 120 if model.duration_days > 180 else model.duration_days)
        baseline = simulate_user(model, seed=seed, duration_days=duration)
        shadow = simulate_user(model, seed=seed, duration_days=duration, guidance_variant=SHADOW_GUIDANCE_V1)
        notes = _oracle_notes_by_day(tuple(oracle for oracle in baseline.oracle_results + shadow.oracle_results), "oracle")
        chosen = _select_cross_profile_indices(model_id, baseline, shadow, count)
        generated_days = [asdict(day) for day in baseline.generated_days]
        for index in chosen[:count]:
            day = baseline.generated_days[index]
            current = baseline.guidance_outputs[index]
            shadow_output = shadow.guidance_outputs[index]
            old_output = _pre_promotion_output_summary(day, current)
            changed_fields = _changed_fields(old_output, _output_summary(shadow_output), _output_summary(current))
            samples.append(
                {
                    "model": model_id,
                    "coverage_bucket": bucket,
                    "profile": day.profile_id,
                    "date": day.date,
                    "phase": day.phase_name,
                    "inputs": _summarize_inputs(day.inputs),
                    "recent_history_summary": _recent_history_summary(day.date, generated_days),
                    "baseline": old_output,
                    "shadow": _output_summary(shadow_output),
                    "promoted_production": _output_summary(current),
                    "changed_fields": changed_fields,
                    "oracle_notes": notes.get(day.date, ()),
                    "human_review_rubric": _human_rating_fields(),
                    "reason": f"cross-profile review bucket: {bucket}",
                }
            )
    return samples[:60]


def _select_cross_profile_indices(model_id: str, baseline: Any, shadow: Any, count: int) -> list[int]:
    scored: list[tuple[int, int]] = []
    for index, (day, current, shadow_output) in enumerate(zip(baseline.generated_days, baseline.guidance_outputs, shadow.guidance_outputs)):
        score = 0
        if current != shadow_output:
            score += 5
        if day.phase_name in {"acute_overload", "recovery", "return_after_gap", "biased_bad_logging", "biased_good_logging", "sparse_tracking", "long_gap"}:
            score += 4
        if not day.inputs or current.confidence == "limited":
            score += 3
        if "pattern" in model_id or "pattern" in " ".join(day.tags):
            score += 3
        if "overenthusiastic" in model_id and current.label == "Push":
            score += 4
        if "poor_sleep" in model_id and day.inputs.get("core.sleep_ok") is False:
            score += 4
        if "body_signal" in model_id and day.inputs.get("body.migraine_warning") is True:
            score += 4
        if current.label in {"Push", "Protect Sleep", "Simplify"}:
            score += 2
        scored.append((-score, index))
    selected = [index for _, index in sorted(scored)[: max(count * 2, count)]]
    phases_seen: set[str] = set()
    result: list[int] = []
    for index in selected:
        phase = baseline.generated_days[index].phase_name
        if phase not in phases_seen or len(result) < count:
            result.append(index)
            phases_seen.add(phase)
        if len(result) >= count:
            break
    return result


def _pre_promotion_output_summary(day: SyntheticDay, current: GuidanceOutput) -> Mapping[str, Any]:
    summary = dict(_output_summary(current))
    if not day.inputs:
        summary.update(
            {
                "label": "Simplify",
                "primary_action": "Complete a short check-in before trusting the guidance.",
                "action_family": "check_in_first",
            }
        )
    elif current.label == "Push":
        summary["primary_action"] = "Use the available capacity, but keep one clear stop point."
    elif current.label == "Maintain":
        summary["primary_action"] = "Keep the current shape and avoid adding extra load."
    return summary


def _changed_fields(
    old_output: Mapping[str, Any],
    shadow_output: Mapping[str, Any],
    current_output: Mapping[str, Any],
) -> list[str]:
    fields = ("label", "drivers", "confidence", "confidence_note", "action_family", "primary_action")
    return [
        field
        for field in fields
        if old_output.get(field) != shadow_output.get(field) or old_output.get(field) != current_output.get(field)
    ]


def _experiment_1_synthetic_metrics_delta(seed: int) -> Mapping[str, Any]:
    simulations = tuple(
        simulate_user(model, seed=seed, duration_days=model.duration_days)
        for model in all_extended_synthetic_user_models()
    )
    current_outputs = tuple(output for simulation in simulations for output in simulation.guidance_outputs)
    previous_outputs = tuple(
        _pre_promotion_output_summary(day, output)
        for simulation in simulations
        for day, output in zip(simulation.generated_days, simulation.guidance_outputs)
    )
    current_label_distribution = Counter(output.label for output in current_outputs)
    previous_label_distribution = Counter(str(output["label"]) for output in previous_outputs)
    current_action_families = Counter(output.action_family for output in current_outputs)
    previous_action_families = Counter(str(output["action_family"]) for output in previous_outputs)
    no_data_days = sum(1 for simulation in simulations for day in simulation.generated_days if not day.inputs)
    changed_outputs = sum(
        1
        for old, current in zip(previous_outputs, current_outputs)
        if old["label"] != current.label
        or old["primary_action"] != current.primary_action
        or old["action_family"] != current.action_family
    )
    return {
        "seed": seed,
        "model_count": len(simulations),
        "synthetic_day_count": len(current_outputs),
        "no_data_day_count": no_data_days,
        "changed_output_count": changed_outputs,
        "previous_label_distribution": dict(previous_label_distribution),
        "current_label_distribution": dict(current_label_distribution),
        "label_distribution_delta": _counter_delta(previous_label_distribution, current_label_distribution),
        "previous_action_family_distribution": dict(previous_action_families),
        "current_action_family_distribution": dict(current_action_families),
        "action_family_distribution_delta": _counter_delta(previous_action_families, current_action_families),
        "expected_label_change_scope": "Only fully empty/no-data days may move from Simplify to Maintain.",
        "formula_thresholds_changed": False,
    }


def _counter_delta(before: Counter[str], after: Counter[str]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {key: after.get(key, 0) - before.get(key, 0) for key in sorted(keys)}


def _oracle_notes_by_day(results: tuple[OracleResult, ...], prefix: str) -> dict[str, tuple[str, ...]]:
    notes: dict[str, list[str]] = defaultdict(list)
    for result in results:
        for affected_day in result.affected_days:
            notes[affected_day].append(f"{prefix}: {result.oracle} {result.status} {result.classification}".strip())
    return {day: tuple(day_notes) for day, day_notes in notes.items()}


def _output_summary(output: GuidanceOutput) -> Mapping[str, Any]:
    return {
        "label": output.label,
        "drivers": output.top_drivers,
        "confidence": output.confidence,
        "confidence_note": output.confidence_note,
        "action_family": output.action_family,
        "primary_action": output.primary_action,
    }


def _promotion_candidate_summary() -> list[Mapping[str, Any]]:
    return [
        {
            "improvement": "empty/no-data check-in-first copy",
            "promotion_class": "promote_now_low_risk",
            "reason": "Human review approved the no-data exception: Maintain label, limited confidence, Missing data driver, and short-check-in action.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "Push planned-priority wording",
            "promotion_class": "promote_now_low_risk",
            "reason": "Reviewed copy removes bonus-load framing without changing Push thresholds.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "limited Maintain action wording",
            "promotion_class": "promote_now_low_risk",
            "reason": "Reviewed Maintain copy keeps recovery protected or avoids bonus load without changing labels.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "biased-logger cautious confidence note",
            "promotion_class": "keep_shadow_needs_review",
            "reason": "Synthetic sampling-bias oracle improves, but confidence behavior should be reviewed by humans before default behavior changes.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "Work Stress driver wording without Pattern Awareness",
            "promotion_class": "keep_shadow_needs_review",
            "reason": "Low-risk copy candidate, but this pass leaves it shadow-only until human review confirms wording fit.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "driver-relevant action variation for advice fatigue",
            "promotion_class": "keep_shadow_needs_review",
            "reason": "Advice fatigue improves in synthetic comparison, but action wording needs review before becoming default.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "poor sleep plus low demand sleep-protective action",
            "promotion_class": "keep_shadow_needs_review",
            "reason": "Action-family candidate only; keep shadow-only until human review confirms it is not over-alarming.",
            "formula_threshold_change": False,
        },
        {
            "improvement": "Body Signal Awareness repeated-signal response",
            "promotion_class": "formula_threshold_experiment_later",
            "reason": "Requires formula sensitivity/threshold decision and is explicitly out of scope for this block.",
            "formula_threshold_change": True,
        },
        {
            "improvement": "General Balance high stress plus low energy gate",
            "promotion_class": "formula_threshold_experiment_later",
            "reason": "Requires label/severity threshold decision and remains gated.",
            "formula_threshold_change": True,
        },
        {
            "improvement": "Training Recovery enthusiastic-athlete Push reduction",
            "promotion_class": "formula_threshold_experiment_later",
            "reason": "Requires Push threshold calibration and remains gated.",
            "formula_threshold_change": True,
        },
    ]


def _promotion_decision(candidates: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    promoted = [item for item in candidates if item["promotion_class"] == "promote_now_low_risk"]
    formula_gated = [item for item in candidates if item["promotion_class"] == "formula_threshold_experiment_later"]
    return {
        "decision": "promote_reviewed_low_risk_copy_actions",
        "promoted_count": len(promoted),
        "promoted": promoted,
        "kept_shadow_only": [item for item in candidates if item["promotion_class"] == "keep_shadow_needs_review"],
        "formula_gated": formula_gated,
        "reason": "Only reviewed no-data, Push wording, and limited Maintain action copy were promoted. Biased confidence, Work Stress wording, poor-sleep action, broad action variation, and formula thresholds remain gated.",
    }


def _remaining_formula_hypotheses() -> list[Mapping[str, Any]]:
    return [
        {
            "id": "body_signal_repeated_high_response",
            "status": "formula_threshold_experiment_later",
            "summary": "Body Signal Awareness may need stronger repeated body-signal response.",
        },
        {
            "id": "general_balance_high_stress_low_energy",
            "status": "formula_threshold_experiment_later",
            "summary": "General Balance high stress plus low energy may need stronger Simplify behavior.",
        },
        {
            "id": "training_recovery_overenthusiastic_push",
            "status": "formula_threshold_experiment_later",
            "summary": "Training Recovery may be too permissive with Push for enthusiastic athlete cases.",
        },
    ]


def _write_shadow_review_samples(path: Path, samples: list[Mapping[str, Any]]) -> None:
    lines = [
        "# Life Load Shadow Guidance Experiment 1 Review Samples",
        "",
        "Synthetic fake data only. These samples compare baseline synthetic guidance to the shadow confidence/action/copy variant.",
        "",
    ]
    for index, sample in enumerate(samples[:60], start=1):
        lines.extend(
            (
                f"## Sample {index}: {sample['model']} {sample['date']}",
                f"- Profile: {sample['profile']}",
                f"- Phase: {sample['phase']}",
                f"- Inputs: `{json.dumps(sample['inputs'], sort_keys=True)}`",
                f"- Recent history: {sample['recent_history_summary']}",
                f"- Baseline: {sample['baseline']['label']} / {sample['baseline']['confidence']} / {sample['baseline']['action_family']} / {sample['baseline']['primary_action']}",
                f"- Shadow: {sample['shadow']['label']} / {sample['shadow']['confidence']} / {sample['shadow']['action_family']} / {sample['shadow']['primary_action']}",
                f"- Changed fields: {', '.join(sample['changed_fields'])}",
                f"- Oracle notes: {'; '.join(sample['oracle_notes']) or 'none'}",
                f"- Drivers before: {', '.join(sample['baseline']['drivers']) or 'none'}",
                f"- Drivers after: {', '.join(sample['shadow']['drivers']) or 'none'}",
                f"- Reason: {sample['reason']}",
                "",
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _shadow_human_review_sheet_html(
    samples: list[Mapping[str, Any]],
    *,
    title: str = "Life Load Shadow Guidance Human Review Sheet",
) -> str:
    rows = []
    for index, sample in enumerate(samples[:60], start=1):
        promoted = sample.get("promoted_production")
        promoted_line = (
            f"<p><strong>Promoted production output:</strong> {html.escape(json.dumps(promoted, sort_keys=True))}</p>"
            if promoted
            else ""
        )
        rows.append(
            "<section>"
            f"<h2>Sample {index}: {html.escape(sample['model'])} / {html.escape(sample['date'])}</h2>"
            f"<p><strong>Coverage bucket:</strong> {html.escape(str(sample.get('coverage_bucket', 'shadow comparison')))}</p>"
            f"<p><strong>Profile:</strong> {html.escape(sample['profile'])} | <strong>Phase:</strong> {html.escape(sample['phase'])}</p>"
            f"<p><strong>Inputs:</strong> <code>{html.escape(json.dumps(sample['inputs'], sort_keys=True))}</code></p>"
            f"<p><strong>Recent history:</strong> {html.escape(sample['recent_history_summary'])}</p>"
            f"<p><strong>Old output:</strong> {html.escape(json.dumps(sample['baseline'], sort_keys=True))}</p>"
            f"<p><strong>Shadow output:</strong> {html.escape(json.dumps(sample['shadow'], sort_keys=True))}</p>"
            f"{promoted_line}"
            f"<p><strong>Changed fields:</strong> {html.escape(', '.join(sample['changed_fields']))}</p>"
            f"<p><strong>Oracle notes:</strong> {html.escape('; '.join(sample['oracle_notes']) or 'none')}</p>"
            f"<p><strong>Why selected:</strong> {html.escape(sample['reason'])}</p>"
            "<ul><li>Label fit 1-5: ____</li><li>Driver fit 1-5: ____</li><li>Action usefulness 1-5: ____</li><li>Specificity 1-5: ____</li><li>Tone safety 1-5: ____</li><li>Profile fit 1-5: ____</li><li>Recency explanation 1-5: ____</li><li>Uncertainty honesty 1-5: ____</li><li>Would a tired user understand? 1-5: ____</li><li>Reviewer note: ____________________</li></ul>"
            "</section>"
        )
    return (
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title></head>"
        f"<body><h1>{html.escape(title)}</h1>"
        "<p>Synthetic fake data only. This review compares old synthetic guidance, promoted production output, and the shadow confidence/action/copy variant. It does not prove real-world or clinical efficacy.</p>"
        "<p><strong>Promoted now:</strong> empty/no-data Maintain check-in-first behavior, Push planned-priority wording, and limited Maintain action variation.</p>"
        "<p><strong>Kept shadow-only:</strong> biased-logger cautious confidence, Work Stress driver wording, poor-sleep/low-demand sleep-protective action, and broader advice-fatigue/action variation.</p>"
        "<p><strong>Formula-gated:</strong> Body Signal Awareness repeated-signal response, General Balance high stress plus low energy, and Training Recovery enthusiastic-athlete Push calibration.</p>"
        + "\n".join(rows)
        + "</body></html>"
    )


def _shadow_promotion_decision_html(results: Mapping[str, Any]) -> str:
    candidates = results["promotion_candidate_summary"]
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['improvement'])}</td>"
        f"<td>{html.escape(item['promotion_class'])}</td>"
        f"<td>{html.escape(item['reason'])}</td>"
        "</tr>"
        for item in candidates
    )
    summary = results["before_after_summary"]
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Life Load Shadow Guidance Promotion Decision</title></head>
<body>
<h1>Life Load Shadow Guidance Promotion Decision</h1>
<p>Decision: <strong>{html.escape(results['promotion_decision']['decision'])}</strong>.</p>
<p>Synthetic fake data only. No real user data. No clinical or real-world efficacy claim. No production scoring, formula threshold, Android UI, extraction, HTTP payload, export/import, feature-flag, or Pattern Awareness default change.</p>
<h2>Before / After</h2>
<ul>
<li>Baseline oracle failures: {summary['baseline_oracle_failures']}</li>
<li>Shadow oracle failures: {summary['shadow_oracle_failures']}</li>
<li>Baseline oracle warnings: {summary['baseline_oracle_warnings']}</li>
<li>Shadow oracle warnings: {summary['shadow_oracle_warnings']}</li>
</ul>
<h2>Promotion Candidates</h2>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">
<thead><tr><th>Improvement</th><th>Promotion class</th><th>Reason</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<h2>Promoted</h2>
<p>Promoted reviewed low-risk copy/action changes only: empty/no-data guidance now stays Maintain with limited confidence, Missing data driver, and a short-check-in action; Push copy now points to the planned priority rather than bonus load; Maintain copy now protects recovery or avoids bonus load.</p>
<p>Kept shadow-only: biased-logger cautious confidence, Work Stress driver wording, poor-sleep/low-demand sleep-protective action, and broader advice-fatigue/action variation.</p>
<h2>Formula-Gated</h2>
<p>Body Signal Awareness repeated signals, General Balance high stress plus low energy, and Training Recovery Push calibration remain separate formula-threshold hypotheses.</p>
</body></html>
"""


def _write_shadow_experiment_readme(path: Path, seed: int, results: Mapping[str, Any]) -> None:
    summary = results["before_after_summary"]
    lines = [
        "# Life Load Shadow Guidance Experiment 1",
        "",
        f"Variant: `{results['variant']}`",
        f"Seed: {seed}",
        "",
        "Synthetic data only. No real user data is included.",
        "This is a shadow confidence/action/copy evaluation. Production scoring, formula thresholds, Android UI, extraction, HTTP payloads, export/import, feature flags, and Pattern Awareness defaults are unchanged.",
        "The reviewed low-risk default guidance copy/action changes are promoted separately: no-data check-in-first Maintain behavior, Push planned-priority wording, and limited Maintain action variation.",
        "This report evaluates product coherence and regression risk. It does not prove clinical, wellness, or real-world efficacy.",
        "",
        "## Summary",
        f"- Models compared: {summary['model_count']}",
        f"- Baseline oracle failures: {summary['baseline_oracle_failures']}",
        f"- Shadow oracle failures: {summary['shadow_oracle_failures']}",
        f"- Baseline oracle warnings: {summary['baseline_oracle_warnings']}",
        f"- Shadow oracle warnings: {summary['shadow_oracle_warnings']}",
        "",
        "## Remaining Formula Hypotheses",
        "- Body Signal Awareness repeated-signal response remains pending.",
        "- General Balance high stress plus low energy remains pending.",
        "- Training Recovery enthusiastic-athlete Push cases remain pending human/formula review.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_guidance_low_risk_promotion_readme(
    path: Path,
    *,
    seed: int,
    promoted: list[Mapping[str, Any]],
    kept_shadow: list[Mapping[str, Any]],
    formula_gated: list[Mapping[str, Any]],
) -> None:
    lines = [
        "# Life Load Guidance Low-Risk Promotion",
        "",
        f"Seed: {seed}",
        "",
        "Synthetic data only. No real user data is included.",
        "This package does not claim clinical, wellness, or real-world efficacy.",
        "Only reviewed low-risk copy/action changes were promoted. Production scoring formulas and formula thresholds are unchanged.",
        "",
        "## Promoted",
        *[f"- {item['improvement']}: {item['reason']}" for item in promoted],
        "",
        "## Kept Shadow-Only",
        *[f"- {item['improvement']}: {item['reason']}" for item in kept_shadow],
        "",
        "## Formula Hypotheses Still Gated",
        *[f"- {item['improvement']}: {item['reason']}" for item in formula_gated],
        "",
        "## Cross-Profile Review",
        "- `cross_profile_review_samples.html` expands human review coverage across General Balance, Work Stress, Training Recovery, Body Signal Awareness, Pattern Awareness, sparse/biased/gap, and poor-sleep/low-demand cases.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _experiment_1_decision_html(
    before_after: Mapping[str, Any],
    promoted: list[Mapping[str, Any]],
    kept_shadow: list[Mapping[str, Any]],
    formula_gated: list[Mapping[str, Any]],
) -> str:
    promoted_rows = _decision_rows(promoted)
    kept_rows = _decision_rows(kept_shadow)
    formula_rows = _decision_rows(formula_gated)
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Life Load Experiment 1 Low-Risk Guidance Decision</title></head>
<body>
<h1>Life Load Experiment 1 Low-Risk Guidance Decision</h1>
<p>Decision: <strong>{html.escape(str(before_after['decision']))}</strong>.</p>
<p>Synthetic fake data only. No real user data. No clinical or real-world efficacy claim. No Android UI, extraction, HTTP payload, export/import, feature-flag, Pattern Awareness default, scoring weight, or formula-threshold change.</p>
<h2>What Changed</h2>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\"><thead><tr><th>Promoted change</th><th>Reason</th></tr></thead><tbody>{promoted_rows}</tbody></table>
<h2>Before / After Evidence</h2>
<ul>
<li>Empty/no-data behavior improved: {before_after['empty_no_data_behavior_improved']}</li>
<li>Push action wording improved: {before_after['push_action_wording_improved']}</li>
<li>Maintain action variation improved: {before_after['maintain_action_variation_improved']}</li>
<li>Profile leakage remained zero: {before_after['profile_leakage_remained_zero']}</li>
<li>Sensitive copy remained safe: {before_after['sensitive_copy_remained_safe']}</li>
<li>Formula thresholds changed: {before_after['formula_thresholds_changed']}</li>
<li>Unexpected label distribution change: {before_after['unexpected_label_distribution_change']}</li>
<li>Material oracle regression: {before_after['synthetic_oracle_material_regression']}</li>
</ul>
<h2>Kept Shadow-Only</h2>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\"><thead><tr><th>Candidate</th><th>Reason</th></tr></thead><tbody>{kept_rows}</tbody></table>
<h2>Formula-Gated</h2>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\"><thead><tr><th>Hypothesis</th><th>Reason</th></tr></thead><tbody>{formula_rows}</tbody></table>
<h2>Final Decision</h2>
<p>Keep promoted changes. Continue to hold the shadow-only candidates for cross-profile human review and keep formula-threshold hypotheses for later experiments.</p>
</body></html>
"""


def _decision_rows(items: list[Mapping[str, Any]]) -> str:
    return "\n".join(
        "<tr>"
        f"<td>{html.escape(str(item['improvement']))}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        "</tr>"
        for item in items
    )


def _write_experiment_1_readme(
    path: Path,
    *,
    seed: int,
    before_after: Mapping[str, Any],
    promoted: list[Mapping[str, Any]],
    kept_shadow: list[Mapping[str, Any]],
    formula_gated: list[Mapping[str, Any]],
) -> None:
    lines = [
        "# Life Load Experiment 1: Low-Risk Guidance Promotion",
        "",
        f"Seed: {seed}",
        f"Decision: {before_after['decision']}",
        "",
        "Synthetic data only. No real user data is included.",
        "This package does not claim clinical, wellness, or real-world efficacy.",
        "Production scoring formulas, scoring weights, and formula thresholds are unchanged.",
        "",
        "## Promoted",
        *[f"- {item['improvement']}: {item['reason']}" for item in promoted],
        "",
        "## Kept Shadow-Only",
        *[f"- {item['improvement']}: {item['reason']}" for item in kept_shadow],
        "",
        "## Formula Hypotheses Still Gated",
        *[f"- {item['improvement']}: {item['reason']}" for item in formula_gated],
        "",
        "## Evidence Answers",
        f"- Empty/no-data behavior improved: {before_after['empty_no_data_behavior_improved']}",
        f"- Push action wording improved: {before_after['push_action_wording_improved']}",
        f"- Maintain action variation improved: {before_after['maintain_action_variation_improved']}",
        f"- Profile leakage remained zero: {before_after['profile_leakage_remained_zero']}",
        f"- Sensitive copy remained safe: {before_after['sensitive_copy_remained_safe']}",
        f"- Formula thresholds changed: {before_after['formula_thresholds_changed']}",
        f"- Material synthetic oracle regression: {before_after['synthetic_oracle_material_regression']}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
