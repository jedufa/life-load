import zipfile

from life_load.synthetic_guidance_quality import (
    shadow_guidance_experiment_1_results,
    write_experiment_1_low_risk_guidance_promotion_zip,
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


def _promotion_classes():
    return {
        item["improvement"]: item["promotion_class"]
        for item in shadow_guidance_experiment_1_results(seed=20260518)["promotion_candidate_summary"]
    }


def test_production_empty_day_maintain_limited_confidence_checkin_first():
    day = _day(inputs={}, missing_inputs=("core.sleep_ok", "mental.stress", "energy.energy"))

    output = guidance_for_synthetic_day(day)

    assert output.label == "Maintain"
    assert output.confidence == "limited"
    assert output.top_drivers == ("Missing data",)
    assert output.action_family == "check_in_first"
    assert output.primary_action == "Complete a short check-in for a better suggestion."


def test_production_empty_day_does_not_simplify_due_to_missing_data():
    output = guidance_for_synthetic_day(_day(inputs={}))

    assert output.label != "Simplify"
    assert output.label not in {"Push", "Recover", "Protect Sleep"}


def test_production_empty_day_missing_data_driver_only():
    output = guidance_for_synthetic_day(_day(inputs={}))

    assert output.top_drivers == ("Missing data",)


def test_production_repeated_empty_days_do_not_claim_known_overload():
    outputs = tuple(
        guidance_for_synthetic_day(_day(date=f"2026-05-{day:02d}", inputs={}))
        for day in range(1, 6)
    )

    assert {output.label for output in outputs} == {"Maintain"}
    assert {output.confidence for output in outputs} == {"limited"}
    assert all(output.top_drivers == ("Missing data",) for output in outputs)
    assert all("overload" not in output.confidence_note.lower() for output in outputs)


def test_production_empty_day_does_not_create_false_zero_values():
    output = guidance_for_synthetic_day(_day(inputs={}))

    assert not {
        "mental_load_high",
        "energy_low",
        "body_signal_high",
        "private_pattern_active",
        "physical_load_high",
        "recovery_low",
    } & set(output.bridge_inputs)


def test_production_push_action_uses_planned_priority_not_bonus_load():
    day = _day(inputs={"core.sleep_ok": True, "mental.stress": 1, "energy.energy": 9, "recovery.shutdown_done": True})

    output = guidance_for_synthetic_day(day, history=(day, day, day))

    assert output.label == "Push"
    assert output.primary_action == "Use the good capacity for the planned priority, not bonus load."


def test_push_action_does_not_encourage_extra_load():
    day = _day(inputs={"core.sleep_ok": True, "mental.stress": 1, "energy.energy": 9, "recovery.shutdown_done": True})

    output = guidance_for_synthetic_day(day, history=(day, day, day))

    assert "bonus load" in output.primary_action
    assert "extra load" not in output.primary_action.lower()
    assert "do everything" not in output.primary_action.lower()


def test_push_action_remains_concrete():
    day = _day(inputs={"core.sleep_ok": True, "mental.stress": 1, "energy.energy": 9, "recovery.shutdown_done": True})

    output = guidance_for_synthetic_day(day, history=(day, day, day))

    assert "planned priority" in output.primary_action
    assert output.action_family == "use_good_capacity"


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


def test_production_maintain_missing_data_uses_checkin_first_action():
    output = guidance_for_synthetic_day(_day(inputs={}))

    assert output.label == "Maintain"
    assert output.action_family == "check_in_first"
    assert output.primary_action == "Complete a short check-in for a better suggestion."


def test_production_maintain_action_variation_is_driver_relevant_not_random():
    recovery_day = _day(date="2026-05-18", inputs={"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "recovery.shutdown_done": True})
    same_recovery_next_day = _day(date="2026-05-19", inputs=recovery_day.inputs)
    stable_day = _day(inputs={"core.sleep_ok": False, "mental.stress": 2, "energy.energy": 4, "recovery.shutdown_done": False})

    first = guidance_for_synthetic_day(recovery_day)
    second = guidance_for_synthetic_day(same_recovery_next_day)
    stable = guidance_for_synthetic_day(stable_day)

    assert first.primary_action == second.primary_action
    assert first.primary_action != stable.primary_action


def test_production_broad_advice_fatigue_system_not_promoted():
    first = guidance_for_synthetic_day(
        _day(date="2026-05-18", profile_id="work_stress", inputs={"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 2})
    )
    second = guidance_for_synthetic_day(
        _day(date="2026-05-19", profile_id="work_stress", inputs={"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 2})
    )

    assert first.label == second.label == "Simplify"
    assert first.primary_action == second.primary_action
    assert first.action_family == second.action_family == "reduce_optional_load"


def test_biased_logger_confidence_candidate_remains_shadow_only():
    model = _model("bad_day_only_logger")
    baseline = simulate_user(model, seed=701, duration_days=model.duration_days)
    shadow = simulate_user(model, seed=701, duration_days=model.duration_days, guidance_variant=SHADOW_GUIDANCE_V1)

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
    assert _promotion_classes()["Work Stress driver wording without Pattern Awareness"] == "keep_shadow_needs_review"


def test_poor_sleep_low_demand_candidate_remains_shadow_only():
    day = _day(inputs={"core.sleep_ok": False, "mental.stress": 1, "energy.energy": 7})

    default = guidance_for_synthetic_day(day)
    shadow = guidance_for_synthetic_day(day, guidance_variant=SHADOW_GUIDANCE_V1)

    assert default.action_family != "protect_sleep"
    assert shadow.action_family == "protect_sleep"


def test_formula_threshold_hypotheses_remain_gated():
    classes = _promotion_classes()

    assert classes["Body Signal Awareness repeated-signal response"] == "formula_threshold_experiment_later"
    assert classes["General Balance high stress plus low energy gate"] == "formula_threshold_experiment_later"
    assert classes["Training Recovery enthusiastic-athlete Push reduction"] == "formula_threshold_experiment_later"


def test_profile_leakage_still_zero():
    check = shadow_guidance_experiment_1_results(seed=702)["profile_leakage_check"]

    assert check["status"] == "pass"
    assert check["affected_day_count"] == 0


def test_sensitive_copy_still_safe():
    check = shadow_guidance_experiment_1_results(seed=703)["sensitive_copy_check"]

    assert check["status"] == "pass"
    assert check["affected_day_count"] == 0


def test_scoring_thresholds_unchanged():
    severe_day = _day(inputs={"core.sleep_ok": True, "mental.stress": 9, "energy.energy": 2})
    body_day = _day(
        profile_id="body_signal_awareness",
        inputs={"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True},
    )

    assert guidance_for_synthetic_day(severe_day).label == "Simplify"
    assert guidance_for_synthetic_day(body_day).label == "Maintain"


def test_experiment_1_report_contains_expected_files(tmp_path):
    cross_profile_doc = tmp_path / "cross_profile.html"
    decision_doc = tmp_path / "decision.html"

    zip_path = write_experiment_1_low_risk_guidance_promotion_zip(
        seed=704,
        output_dir=tmp_path,
        timestamp="experiment-one",
        cross_profile_review_doc=cross_profile_doc,
        decision_doc=decision_doc,
    )

    assert cross_profile_doc.exists()
    assert decision_doc.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "promoted_changes.json",
        "kept_shadow_only.json",
        "formula_hypotheses_still_gated.json",
        "before_after_promotion_summary.json",
        "oracle_regression_summary.json",
        "review_samples_after_promotion.html",
        "synthetic_metrics_delta.json",
    }.issubset(names)
