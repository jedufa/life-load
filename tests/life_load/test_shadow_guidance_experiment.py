import zipfile

from life_load.synthetic_guidance_quality import (
    AdviceFatigueOracle,
    shadow_guidance_experiment_1_results,
    write_guidance_low_risk_promotion_zip,
    write_shadow_guidance_experiment_1_zip,
)
from life_load.synthetic_users import (
    SHADOW_GUIDANCE_V1,
    SyntheticDay,
    advanced_synthetic_user_models,
    guidance_for_synthetic_day,
    life_rhythm_synthetic_user_models,
    simulate_user,
)


def _day(**kwargs):
    base = {
        "date": "2026-05-18",
        "profile_id": "general_balance",
        "inputs": {
            "core.sleep_ok": True,
            "mental.stress": 3,
            "energy.energy": 7,
        },
        "missing_inputs": (),
        "tags": (),
        "phase_name": "baseline",
        "notes": "",
    }
    base.update(kwargs)
    return SyntheticDay(**base)


def _model(model_id):
    return {
        model.id: model
        for model in advanced_synthetic_user_models() + life_rhythm_synthetic_user_models()
    }[model_id]


def test_production_empty_day_maintain_limited_confidence_checkin_first():
    day = _day(inputs={}, missing_inputs=("core.sleep_ok", "mental.stress", "energy.energy"))

    default = guidance_for_synthetic_day(day)
    explicit_baseline = guidance_for_synthetic_day(day, guidance_variant=None)

    assert default == explicit_baseline
    assert default.label == "Maintain"
    assert default.confidence == "limited"
    assert default.top_drivers == ("Missing data",)
    assert default.action_family == "check_in_first"
    assert default.primary_action == "Complete a short check-in for a better suggestion."


def test_production_empty_day_does_not_simplify_due_to_missing_data():
    day = _day(inputs={}, missing_inputs=("core.sleep_ok", "mental.stress", "energy.energy"))

    output = guidance_for_synthetic_day(day)

    assert output.label != "Simplify"
    assert "mental_load_high" not in output.bridge_inputs
    assert "energy_low" not in output.bridge_inputs


def test_production_push_action_uses_planned_priority_not_bonus_load():
    day = _day(inputs={"core.sleep_ok": True, "mental.stress": 1, "energy.energy": 9, "recovery.shutdown_done": True})

    output = guidance_for_synthetic_day(day, history=(day, day, day))

    assert output.label == "Push"
    assert output.primary_action == "Use the good capacity for the planned priority, not bonus load."


def test_production_maintain_recovery_action_leaves_recovery_protected():
    day = _day(inputs={"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "recovery.shutdown_done": True})

    output = guidance_for_synthetic_day(day)

    assert output.label == "Maintain"
    assert output.primary_action == "Keep the current shape and leave recovery protected."


def test_production_maintain_stable_action_avoids_bonus_load():
    day = _day(inputs={"core.sleep_ok": False, "mental.stress": 2, "energy.energy": 4, "recovery.shutdown_done": False})

    output = guidance_for_synthetic_day(day)

    assert output.label == "Maintain"
    assert output.primary_action == "Stay with the plan and avoid adding bonus load."


def test_shadow_guidance_variant_exists():
    assert SHADOW_GUIDANCE_V1 == "shadow_guidance_v1_confidence_action_quality"


def test_shadow_empty_day_invites_checkin():
    day = _day(inputs={}, missing_inputs=("core.sleep_ok", "mental.stress", "energy.energy"))

    output = guidance_for_synthetic_day(day, guidance_variant=SHADOW_GUIDANCE_V1)

    assert output.confidence == "limited"
    assert output.action_family == "check_in_first"
    assert "short check-in" in output.primary_action
    assert output.label == "Maintain"


def test_repeated_empty_days_do_not_claim_known_overload():
    days = tuple(
        _day(date=f"2026-05-{day:02d}", inputs={}, missing_inputs=("core.sleep_ok", "mental.stress", "energy.energy"))
        for day in range(1, 5)
    )
    outputs = tuple(guidance_for_synthetic_day(day, guidance_variant=SHADOW_GUIDANCE_V1) for day in days)

    assert all(output.confidence == "limited" for output in outputs)
    assert all("mental_load_high" not in output.bridge_inputs for output in outputs)
    assert all("energy_low" not in output.bridge_inputs for output in outputs)
    assert all(output.top_drivers == ("Missing data",) for output in outputs)


def test_shadow_sampling_bias_confidence_improves():
    bad_logger = _model("bad_day_only_logger")
    good_logger = _model("good_day_only_logger")
    bad_shadow = simulate_user(
        bad_logger,
        seed=501,
        duration_days=bad_logger.duration_days,
        guidance_variant=SHADOW_GUIDANCE_V1,
    )
    good_shadow = simulate_user(
        good_logger,
        seed=501,
        duration_days=good_logger.duration_days,
        guidance_variant=SHADOW_GUIDANCE_V1,
    )

    assert all(output.confidence == "limited" for output in bad_shadow.guidance_outputs if output.date and output.profile_id == "work_stress")
    assert all(output.confidence == "limited" for output in good_shadow.guidance_outputs if output.date and output.profile_id == "general_balance")
    assert any("uneven" in output.confidence_note for output in bad_shadow.guidance_outputs)
    assert any("uneven" in output.confidence_note for output in good_shadow.guidance_outputs)


def test_sampling_bias_oracle_improves_in_shadow_variant():
    results = shadow_guidance_experiment_1_results(seed=502)

    baseline_failures = sum(1 for item in results["sampling_bias_delta"]["baseline"] if item["status"] == "fail")
    shadow_failures = sum(1 for item in results["sampling_bias_delta"]["shadow"] if item["status"] == "fail")

    assert baseline_failures > shadow_failures
    assert shadow_failures == 0


def test_shadow_work_stress_driver_wording_improves():
    day = _day(
        profile_id="work_stress",
        inputs={
            "core.sleep_ok": True,
            "mental.stress": 8,
            "energy.energy": 4,
            "work.project_overrun": True,
            "evening.evening_chain_broken": True,
        },
    )

    output = guidance_for_synthetic_day(day, optional_packs=(), guidance_variant=SHADOW_GUIDANCE_V1)

    assert "Private pattern" not in output.top_drivers
    assert any(driver in output.top_drivers for driver in ("Work spillover", "Work pressure", "Evening boundary", "Decompression"))


def test_pattern_awareness_enabled_can_use_private_pattern_driver():
    day = _day(
        inputs={
            "core.sleep_ok": False,
            "mental.stress": 8,
            "energy.energy": 2,
            "evening.phone_after_21": True,
            "evening.evening_chain_broken": True,
        },
    )

    output = guidance_for_synthetic_day(
        day,
        optional_packs=("pattern_awareness_pack",),
        guidance_variant=SHADOW_GUIDANCE_V1,
    )

    assert "Private pattern" in output.top_drivers


def test_shadow_advice_fatigue_reduces_repetition():
    model = _model("general_balance_poor_sleep_low_demand")
    baseline = simulate_user(model, seed=503, duration_days=90)
    shadow = simulate_user(model, seed=503, duration_days=90, guidance_variant=SHADOW_GUIDANCE_V1)

    baseline_result = AdviceFatigueOracle().evaluate(baseline.guidance_outputs)
    shadow_result = AdviceFatigueOracle().evaluate(shadow.guidance_outputs)

    assert len(shadow_result.affected_days) < len(baseline_result.affected_days)
    assert shadow_result.status == "pass"


def test_same_label_different_drivers_get_different_action_families():
    work_day = _day(
        date="2026-05-18",
        profile_id="work_stress",
        inputs={"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 2, "work.project_overrun": True},
    )
    body_day = _day(
        date="2026-05-19",
        profile_id="body_signal_awareness",
        inputs={"core.sleep_ok": True, "mental.stress": 7, "energy.energy": 2, "body.migraine_warning": True},
    )
    missing_day = _day(date="2026-05-20", inputs={"energy.energy": 5}, missing_inputs=("core.sleep_ok", "mental.stress"))

    outputs = (
        guidance_for_synthetic_day(work_day, guidance_variant=SHADOW_GUIDANCE_V1),
        guidance_for_synthetic_day(body_day, guidance_variant=SHADOW_GUIDANCE_V1),
        guidance_for_synthetic_day(missing_day, guidance_variant=SHADOW_GUIDANCE_V1),
    )

    assert len({output.action_family for output in outputs}) >= 2
    assert outputs[0].action_family in {"reduce_optional_load", "simplify_evening", "avoid_extra_commitment"}
    assert outputs[1].action_family in {"recover_body_signal", "take_recovery_break", "maintain_plan"}


def test_shadow_poor_sleep_low_demand_uses_sleep_protective_action():
    day = _day(inputs={"core.sleep_ok": False, "mental.stress": 1, "energy.energy": 7})

    output = guidance_for_synthetic_day(day, guidance_variant=SHADOW_GUIDANCE_V1)

    assert output.label == "Maintain"
    assert output.action_family == "protect_sleep"
    assert "protect" in output.primary_action.lower()
    assert output.label != "Protect Sleep"


def test_biased_logger_confidence_candidate_remains_shadow_only():
    bad_logger = _model("bad_day_only_logger")
    baseline = simulate_user(bad_logger, seed=507, duration_days=bad_logger.duration_days)
    shadow = simulate_user(
        bad_logger,
        seed=507,
        duration_days=bad_logger.duration_days,
        guidance_variant=SHADOW_GUIDANCE_V1,
    )

    assert any(day.phase_name == "biased_bad_logging" for day in baseline.generated_days)
    assert any(
        output.confidence == "normal"
        for day, output in zip(baseline.generated_days, baseline.guidance_outputs)
        if day.phase_name == "biased_bad_logging"
    )
    assert all(
        output.confidence == "limited"
        for day, output in zip(shadow.generated_days, shadow.guidance_outputs)
        if day.phase_name == "biased_bad_logging"
    )


def test_work_stress_driver_wording_candidate_remains_shadow_only():
    results = shadow_guidance_experiment_1_results(seed=508)

    candidates = {
        item["improvement"]: item["promotion_class"]
        for item in results["promotion_candidate_summary"]
    }

    assert candidates["Work Stress driver wording without Pattern Awareness"] == "keep_shadow_needs_review"


def test_poor_sleep_low_demand_candidate_remains_shadow_only():
    day = _day(inputs={"core.sleep_ok": False, "mental.stress": 1, "energy.energy": 7})

    default = guidance_for_synthetic_day(day)
    shadow = guidance_for_synthetic_day(day, guidance_variant=SHADOW_GUIDANCE_V1)

    assert default.label == "Maintain"
    assert default.action_family != "protect_sleep"
    assert shadow.action_family == "protect_sleep"


def test_shadow_report_contains_before_after_outputs(tmp_path):
    human_doc = tmp_path / "human_review.html"
    cross_profile_doc = tmp_path / "cross_profile_review.html"
    promotion_doc = tmp_path / "promotion.html"

    zip_path = write_shadow_guidance_experiment_1_zip(
        seed=504,
        output_dir=tmp_path,
        timestamp="shadow-one",
        human_review_doc=human_doc,
        cross_profile_review_doc=cross_profile_doc,
        promotion_decision_doc=promotion_doc,
    )

    assert human_doc.exists()
    assert cross_profile_doc.exists()
    assert promotion_doc.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "before_after_summary.json",
        "oracle_delta.json",
        "action_family_delta.json",
        "sampling_bias_delta.json",
        "advice_fatigue_delta.json",
        "volatility_delta.json",
        "profile_leakage_check.json",
        "sensitive_copy_check.json",
        "review_samples.md",
        "review_samples.html",
        "cross_profile_review_samples.html",
        "promotion_candidate_summary.json",
        "remaining_formula_hypotheses.json",
        "recommended_next_formula_experiments.json",
    }.issubset(names)


def test_promotion_decision_is_recorded(tmp_path):
    human_doc = tmp_path / "human_review.html"
    cross_profile_doc = tmp_path / "cross_profile_review.html"
    promotion_doc = tmp_path / "promotion.html"

    write_shadow_guidance_experiment_1_zip(
        seed=505,
        output_dir=tmp_path,
        timestamp="promotion",
        human_review_doc=human_doc,
        cross_profile_review_doc=cross_profile_doc,
        promotion_decision_doc=promotion_doc,
    )

    text = promotion_doc.read_text(encoding="utf-8")
    assert "promote_reviewed_low_risk_copy_actions" in text
    assert "empty/no-data guidance now stays Maintain" in text
    assert "Kept shadow-only" in text


def test_formula_threshold_hypotheses_not_promoted():
    results = shadow_guidance_experiment_1_results(seed=506)

    formula_candidates = [
        item
        for item in results["promotion_candidate_summary"]
        if item["promotion_class"] == "formula_threshold_experiment_later"
    ]

    assert {item["improvement"] for item in formula_candidates} == {
        "Body Signal Awareness repeated-signal response",
        "General Balance high stress plus low energy gate",
        "Training Recovery enthusiastic-athlete Push reduction",
    }
    assert results["promotion_decision"]["promoted_count"] == 3


def test_low_risk_promotion_report_contains_expected_files(tmp_path):
    cross_profile_doc = tmp_path / "cross_profile_review.html"

    zip_path = write_guidance_low_risk_promotion_zip(
        seed=509,
        output_dir=tmp_path,
        timestamp="promotion",
        cross_profile_review_doc=cross_profile_doc,
    )

    assert cross_profile_doc.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "promoted_changes.json",
        "kept_shadow_only.json",
        "formula_hypotheses_still_gated.json",
        "before_after_promotion_summary.json",
        "cross_profile_review_samples.html",
        "oracle_regression_summary.json",
    }.issubset(names)


def test_cross_profile_review_sheet_has_required_coverage(tmp_path):
    cross_profile_doc = tmp_path / "cross_profile_review.html"

    write_guidance_low_risk_promotion_zip(
        seed=510,
        output_dir=tmp_path,
        timestamp="coverage",
        cross_profile_review_doc=cross_profile_doc,
    )

    text = cross_profile_doc.read_text(encoding="utf-8")
    lowered = text.lower()
    for model_id in (
        "bad_day_only_logger",
        "good_day_only_logger",
        "general_balance_poor_sleep_low_demand",
        "work_stress_project_crunch",
        "training_recovery_overenthusiastic_athlete",
        "body_signal_awareness_recurring_signal",
        "pattern_awareness_private_pull",
        "long_term_inconsistent_user",
    ):
        assert model_id in text
    assert lowered.count("coverage bucket:</strong> general_balance") >= 10
    assert lowered.count("coverage bucket:</strong> work_stress") >= 8
    assert lowered.count("coverage bucket:</strong> training_recovery") >= 8
    assert lowered.count("coverage bucket:</strong> body_signal_awareness") >= 8
    assert lowered.count("coverage bucket:</strong> pattern_awareness") >= 8
    assert lowered.count("coverage bucket:</strong> sparse_biased_gap") >= 8


def test_production_scoring_thresholds_unchanged_after_optional_promotion():
    severe_day = _day(inputs={"core.sleep_ok": True, "mental.stress": 9, "energy.energy": 2})
    body_day = _day(
        profile_id="body_signal_awareness",
        inputs={"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True},
    )

    assert guidance_for_synthetic_day(severe_day) == guidance_for_synthetic_day(severe_day, guidance_variant=None)
    assert guidance_for_synthetic_day(body_day) == guidance_for_synthetic_day(body_day, guidance_variant=None)
