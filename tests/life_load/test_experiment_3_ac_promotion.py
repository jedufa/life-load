import zipfile

from life_load import scoring
from life_load.guidance_bridge import score_personal_legacy_via_bridge
from life_load.synthetic_guidance_quality import (
    experiment_3_ac_promotion_results,
    write_experiment_3_ac_promotion_zip,
)
from life_load.synthetic_users import (
    FORBIDDEN_SENSITIVE_TERMS,
    SHADOW_FORMULA_COMBINED_V1,
    SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
    SyntheticDay,
    guidance_for_synthetic_day,
)


def _day(profile_id, inputs, phase="target"):
    return SyntheticDay(
        date="2026-05-18",
        profile_id=profile_id,
        inputs=inputs,
        missing_inputs=(),
        tags=(),
        phase_name=phase,
    )


def _guidance_text(output):
    return " ".join((output.primary_action, output.confidence_note, output.warning_sensitive_text, " ".join(output.top_drivers))).lower()


def test_production_body_signal_repeated_high_shifts_some_maintain_to_simplify_or_recover():
    first = _day(
        "body_signal_awareness",
        {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True},
    )
    second = SyntheticDay(**{**first.__dict__, "date": "2026-05-19"})

    output = guidance_for_synthetic_day(second, history=(first, second))

    assert output.label in {"Simplify", "Recover"}
    assert output.action_family == "recover_body_signal"
    assert output.bridge_inputs["formula_threshold_version"] == "experiment_3_ac"


def test_production_body_signal_high_low_energy_does_not_push():
    output = guidance_for_synthetic_day(
        _day(
            "body_signal_awareness",
            {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 2, "body.migraine_warning": True},
        )
    )

    assert output.label != "Push"
    assert output.label in {"Simplify", "Recover", "Maintain"}


def test_production_body_signal_high_poor_sleep_simplify_or_recover():
    output = guidance_for_synthetic_day(
        _day(
            "body_signal_awareness",
            {"core.sleep_ok": False, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True},
        )
    )

    assert output.label in {"Simplify", "Recover"}
    assert output.action_family == "recover_body_signal"


def test_production_body_signal_wording_non_medical():
    output = guidance_for_synthetic_day(
        _day(
            "body_signal_awareness",
            {"core.sleep_ok": False, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True},
        )
    )

    text = _guidance_text(output)
    assert "Body signal" in output.top_drivers
    assert not any(term in text for term in FORBIDDEN_SENSITIVE_TERMS)
    assert "diagnosis" not in text
    assert "treatment" not in text


def test_production_body_signal_does_not_require_foot_or_shoulder():
    output = guidance_for_synthetic_day(
        _day(
            "body_signal_awareness",
            {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True},
        )
    )

    assert "body.foot_pain" not in output.missing_signal_ids
    assert "body.shoulder_pain" not in output.missing_signal_ids
    assert "foot" not in _guidance_text(output)
    assert "shoulder" not in _guidance_text(output)


def test_production_body_signal_profile_leakage_zero():
    results = experiment_3_ac_promotion_results()

    assert results["profile_leakage_results"]["status"] == "pass"
    assert results["profile_leakage_results"]["count"] == 0


def test_production_training_high_load_low_recovery_does_not_push():
    good = _day(
        "training_recovery",
        {
            "core.sleep_ok": True,
            "core.nutrition_ok": True,
            "mental.stress": 1,
            "energy.energy": 9,
            "training.activity_duration_min": 30,
            "training.primary_activity_type": "walk",
        },
    )
    high_load = _day(
        "training_recovery",
        {
            "core.sleep_ok": False,
            "core.nutrition_ok": True,
            "mental.stress": 2,
            "energy.energy": 9,
            "training.activity_duration_min": 80,
            "training.primary_activity_type": "run",
        },
    )

    output = guidance_for_synthetic_day(high_load, history=(good, high_load))

    assert output.label != "Push"
    assert output.label in {"Maintain", "Recover"}


def test_production_training_high_soreness_high_energy_does_not_auto_push():
    good = _day(
        "training_recovery",
        {
            "core.sleep_ok": True,
            "core.nutrition_ok": True,
            "mental.stress": 1,
            "energy.energy": 9,
            "training.activity_duration_min": 30,
            "training.primary_activity_type": "walk",
        },
    )
    body_load = _day(
        "training_recovery",
        {
            "core.sleep_ok": True,
            "core.nutrition_ok": True,
            "mental.stress": 2,
            "energy.energy": 9,
            "training.activity_duration_min": 75,
            "training.primary_activity_type": "run",
            "body.migraine_warning": True,
        },
    )

    output = guidance_for_synthetic_day(body_load, history=(good, body_load))

    assert output.label != "Push"
    assert output.action_family == "keep_training_easy"


def test_production_training_good_recovery_can_still_push():
    good = _day(
        "training_recovery",
        {
            "core.sleep_ok": True,
            "core.nutrition_ok": True,
            "mental.stress": 1,
            "energy.energy": 9,
            "training.activity_duration_min": 30,
            "training.primary_activity_type": "walk",
        },
    )

    output = guidance_for_synthetic_day(good, history=(good, good, good))

    assert output.label == "Push"
    assert output.action_family == "use_good_capacity"


def test_production_training_push_rate_not_zero():
    results = experiment_3_ac_promotion_results()

    assert results["production_label_distribution"]["Push"] > 0


def test_production_training_recovery_profile_leakage_zero():
    output = guidance_for_synthetic_day(
        _day(
            "training_recovery",
            {
                "core.sleep_ok": True,
                "mental.stress": 2,
                "energy.energy": 9,
                "training.activity_duration_min": 75,
                "relationship.wife_conflict_count": 3,
                "caregiving.homework_done": False,
            },
        )
    )

    text = _guidance_text(output)
    assert "relationship" not in text
    assert "homework" not in text


def test_production_training_no_relationship_homework_drivers():
    output = guidance_for_synthetic_day(
        _day(
            "training_recovery",
            {
                "core.sleep_ok": True,
                "mental.stress": 2,
                "energy.energy": 9,
                "training.activity_duration_min": 75,
                "relationship.wife_conflict_count": 3,
                "caregiving.homework_done": False,
            },
        )
    )

    assert all("relationship" not in driver.lower() and "homework" not in driver.lower() for driver in output.top_drivers)


def test_candidate_b_general_balance_stress_energy_remains_shadow_only():
    near = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4})

    production = guidance_for_synthetic_day(near)
    candidate_b = guidance_for_synthetic_day(near, guidance_variant=SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1)

    assert production.label == "Maintain"
    assert candidate_b.label == "Simplify"


def test_production_general_balance_stress_energy_threshold_unchanged():
    near = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4})

    output = guidance_for_synthetic_day(near)

    assert output.label == "Maintain"
    assert output.action_family == "maintain_plan"


def test_production_general_balance_high_stress_low_energy_no_new_gate():
    near = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4})

    assert "formula_threshold_version" not in guidance_for_synthetic_day(near).bridge_inputs


def test_combined_candidate_not_promoted():
    near = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4})

    production = guidance_for_synthetic_day(near)
    combined = guidance_for_synthetic_day(near, guidance_variant=SHADOW_FORMULA_COMBINED_V1)

    assert production.label == "Maintain"
    assert combined.label == "Simplify"


def test_production_does_not_apply_stacked_candidate_rules():
    results = experiment_3_ac_promotion_results()

    assert "combined" in results["kept_shadow_only"]
    assert results["production_label_distribution"] != results["before_label_distribution"]


def test_production_label_distribution_not_combined_candidate_distribution():
    results = experiment_3_ac_promotion_results()

    combined = results["combined_candidate_still_shadow_only"]
    assert any(row["production_label"] != row["before_label"] for row in combined)
    assert "combined" in results["kept_shadow_only"]


def test_personal_legacy_parity_still_passes_after_experiment3_promotion():
    entry = {
        "date": "2026-05-18",
        "sleep_ok": False,
        "nutrition_ok": True,
        "stress": 7,
        "energy": 3,
        "phone_after_21": True,
    }

    assert score_personal_legacy_via_bridge(entry) == scoring.score_entry(entry)
    assert experiment_3_ac_promotion_results()["personal_legacy_parity"]["status"] == "pass"


def test_profile_leakage_zero_after_experiment3_promotion():
    assert experiment_3_ac_promotion_results()["profile_leakage_results"]["status"] == "pass"


def test_pattern_awareness_default_off_after_experiment3_promotion():
    output = guidance_for_synthetic_day(
        _day("general_balance", {"core.sleep_ok": False, "mental.stress": 7, "energy.energy": 3, "evening.phone_after_21": True})
    )

    assert "private_pattern_active" not in output.bridge_inputs


def test_absent_false_zero_preserved_after_experiment3_promotion():
    empty = guidance_for_synthetic_day(_day("general_balance", {}))
    explicit_false = guidance_for_synthetic_day(
        _day("general_balance", {"core.sleep_ok": False, "mental.stress": 0, "energy.energy": 0})
    )

    assert empty.bridge_inputs["data_confidence"] == 0.0
    assert explicit_false.bridge_inputs["data_confidence"] > empty.bridge_inputs["data_confidence"]
    assert explicit_false.bridge_inputs["recovery_low"] is True


def test_sparse_no_data_behavior_preserved_after_experiment3_promotion():
    results = experiment_3_ac_promotion_results()

    assert results["no_data_behavior_results"]["status"] == "pass"
    assert results["no_data_behavior_results"]["label"] == "Maintain"
    assert results["no_data_behavior_results"]["action_family"] == "check_in_first"


def test_sensitive_copy_safe_after_experiment3_promotion():
    assert experiment_3_ac_promotion_results()["sensitive_copy_results"]["status"] == "pass"


def test_report_artifact_contains_expected_files(tmp_path):
    zip_path = write_experiment_3_ac_promotion_zip(output_dir=tmp_path, decision_doc=tmp_path / "decision.html", timestamp="ac-promotion")

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert {
        "README.md",
        "promoted_candidates.json",
        "kept_shadow_only.json",
        "before_after_summary.json",
        "label_distribution_delta.json",
        "candidate_a_body_signal_production_results.json",
        "candidate_c_training_recovery_production_results.json",
        "candidate_b_still_shadow_only.json",
        "combined_candidate_still_shadow_only.json",
        "personal_legacy_parity.json",
        "profile_leakage_results.json",
        "sensitive_copy_results.json",
        "no_data_behavior_results.json",
        "review_samples_after_promotion.html",
        "rollback_plan.md",
    }.issubset(names)
