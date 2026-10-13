import zipfile

from life_load import scoring
from life_load.guidance_bridge import score_personal_legacy_via_bridge
from life_load.synthetic_guidance_quality import (
    formula_threshold_experiment_results,
    write_experiment_3_formula_threshold_zip,
)
from life_load.synthetic_users import (
    FORBIDDEN_SENSITIVE_TERMS,
    SHADOW_FORMULA_BODY_SIGNAL_V1,
    SHADOW_FORMULA_COMBINED_V1,
    SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
    SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1,
    SHADOW_FORMULA_VARIANTS,
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


def test_shadow_candidate_body_signal_available():
    assert SHADOW_FORMULA_BODY_SIGNAL_V1 in SHADOW_FORMULA_VARIANTS


def test_shadow_candidate_general_balance_stress_energy_available():
    assert SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1 in SHADOW_FORMULA_VARIANTS


def test_shadow_candidate_training_recovery_available():
    assert SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1 in SHADOW_FORMULA_VARIANTS


def test_candidates_can_run_independently():
    variants = {
        SHADOW_FORMULA_BODY_SIGNAL_V1,
        SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1,
        SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1,
    }

    outputs = {
        variant: guidance_for_synthetic_day(
            _day("body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True}),
            history=(
                _day("body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True}),
                _day("body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True}),
            ),
            guidance_variant=variant,
        )
        for variant in variants
    }

    assert set(outputs) == variants
    assert outputs[SHADOW_FORMULA_BODY_SIGNAL_V1].bridge_inputs["shadow_formula_variant"] == SHADOW_FORMULA_BODY_SIGNAL_V1


def test_candidate_b_does_not_change_production_default_outputs():
    day = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4})

    before = guidance_for_synthetic_day(day)
    guidance_for_synthetic_day(day, guidance_variant=SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1)
    after = guidance_for_synthetic_day(day)

    assert before == after


def test_body_signal_candidate_a_is_now_production_behavior():
    first = _day("body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True})
    second = SyntheticDay(**{**first.__dict__, "date": "2026-05-19"})

    baseline = guidance_for_synthetic_day(second, history=(first, second))
    candidate = guidance_for_synthetic_day(second, history=(first, second), guidance_variant=SHADOW_FORMULA_BODY_SIGNAL_V1)

    assert baseline.label == "Simplify"
    assert baseline.action_family == "recover_body_signal"
    assert candidate.label == baseline.label
    assert candidate.action_family == baseline.action_family


def test_general_balance_candidate_reduces_maintain_on_stress8_energy3_cases():
    exact = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 3})
    near = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 4})

    exact_candidate = guidance_for_synthetic_day(exact, guidance_variant=SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1)
    near_baseline = guidance_for_synthetic_day(near)
    near_candidate = guidance_for_synthetic_day(near, guidance_variant=SHADOW_FORMULA_GENERAL_BALANCE_STRESS_ENERGY_V1)

    assert exact_candidate.label == "Simplify"
    assert near_baseline.label == "Maintain"
    assert near_candidate.label == "Simplify"


def test_training_recovery_candidate_c_is_now_production_behavior():
    good = _day("training_recovery", {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 1, "energy.energy": 9, "training.activity_duration_min": 30})
    high_load = _day("training_recovery", {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 2, "energy.energy": 9, "training.activity_duration_min": 75, "training.primary_activity_type": "run"})

    baseline = guidance_for_synthetic_day(high_load, history=(good, high_load))
    candidate = guidance_for_synthetic_day(high_load, history=(good, high_load), guidance_variant=SHADOW_FORMULA_TRAINING_RECOVERY_PUSH_V1)

    assert baseline.label == "Maintain"
    assert baseline.action_family == "keep_training_easy"
    assert candidate.label == baseline.label
    assert candidate.action_family == baseline.action_family


def test_candidates_preserve_personal_legacy_parity():
    entry = {
        "date": "2026-05-18",
        "sleep_ok": False,
        "nutrition_ok": True,
        "stress": 7,
        "energy": 3,
        "phone_after_21": True,
    }

    assert score_personal_legacy_via_bridge(entry) == scoring.score_entry(entry)


def test_candidates_keep_profile_leakage_zero():
    results = formula_threshold_experiment_results()

    assert results["profile_leakage_results"]["status"] == "pass"
    assert all(candidate["profile_leakage_count"] == 0 for candidate in results["candidates"].values())


def test_candidates_keep_sensitive_copy_safe():
    results = formula_threshold_experiment_results()

    assert results["sensitive_copy_results"]["status"] == "pass"
    for candidate in results["candidates"].values():
        assert candidate["sensitive_word_violation_count"] == 0


def test_candidates_preserve_sparse_no_data_behavior():
    day = _day("general_balance", {})

    for variant in SHADOW_FORMULA_VARIANTS + (SHADOW_FORMULA_COMBINED_V1,):
        output = guidance_for_synthetic_day(day, guidance_variant=variant)
        assert output.label == "Maintain"
        assert output.confidence == "limited"
        assert output.top_drivers == ("Missing data",)
        assert output.action_family == "check_in_first"


def test_combined_candidate_does_not_over_conservatize():
    combined = formula_threshold_experiment_results()["candidates"]["combined"]

    assert combined["label_distribution_delta"]["Push"] > -80
    assert combined["label_distribution_candidate"]["Push"] > 0
    assert combined["profile_leakage_count"] == 0
    assert combined["sensitive_word_violation_count"] == 0


def test_report_artifact_contains_expected_files(tmp_path):
    review_doc = tmp_path / "review.html"
    decision_doc = tmp_path / "decision.html"
    zip_path = write_experiment_3_formula_threshold_zip(
        output_dir=tmp_path,
        timestamp="experiment-three",
        human_review_doc=review_doc,
        decision_doc=decision_doc,
    )

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert review_doc.exists()
    assert decision_doc.exists()
    assert {
        "README.md",
        "candidate_a_body_signal_results.json",
        "candidate_b_general_balance_results.json",
        "candidate_c_training_recovery_results.json",
        "combined_candidate_results.json",
        "before_after_summary.json",
        "label_distribution_delta.json",
        "oracle_delta.json",
        "profile_leakage_results.json",
        "sensitive_copy_results.json",
        "human_review_samples.html",
        "decision_summary.json",
        "formula_version_notes.md",
        "rollback_plan.md",
    }.issubset(names)


def test_decision_doc_exists(tmp_path):
    decision_doc = tmp_path / "decision.html"
    write_experiment_3_formula_threshold_zip(output_dir=tmp_path, decision_doc=decision_doc, human_review_doc=tmp_path / "human-review.html")

    assert decision_doc.exists()
    text = decision_doc.read_text(encoding="utf-8")
    assert "Candidate A and Candidate C are promoted" in text


def test_formula_threshold_experiment_keeps_only_b_and_combined_unpromoted():
    decisions = formula_threshold_experiment_results()["decision_summary"]

    assert decisions["candidate_b_general_balance"] == "keep_shadow_or_revise_candidate"
    assert decisions["combined"] == "do_not_promote_before_individual_review"
