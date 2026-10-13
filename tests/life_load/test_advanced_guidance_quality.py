import pytest
from life_load.synthetic_users import write_simulation_report_zip
import zipfile

from life_load.synthetic_guidance_quality import (
    ActionSpecificityOracle,
    AdviceDiversityOracle,
    AdviceFatigueOracle,
    GuidanceVolatilityOracle,
    MomentumOracle,
    action_family_schema_valid,
    counterfactual_results,
    hypothesis_backlog,
    hypothesis_classification,
    review_evaluation_artifact,
    selected_human_review_samples,
    write_advanced_quality_report_zip,
    write_human_review_pack_zip,
    write_synthetic_review_docs,
)
from life_load.synthetic_users import (
    ACTION_FAMILIES,
    NoDataGuidanceOracle,
    StuckStateOracle,
    GuidanceOutput,
    SyntheticDay,
    advanced_synthetic_user_models,
    guidance_for_synthetic_day,
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


def _output(**kwargs):
    base = {
        "date": "2026-05-18",
        "profile_id": "general_balance",
        "label": "Maintain",
        "top_drivers": ("Energy", "Recovery"),
        "confidence": "normal",
        "confidence_note": "Normal confidence from the available check-in.",
        "primary_action": "Keep the current shape and avoid adding extra load.",
        "action_family": "maintain_plan",
        "recent_change": "Recent context is steady.",
        "warning_sensitive_text": "",
        "missing_signal_ids": (),
        "bridge_inputs": {},
    }
    base.update(kwargs)
    return GuidanceOutput(**base)


def test_action_family_taxonomy_valid():
    assert action_family_schema_valid()
    assert "check_in_first" in ACTION_FAMILIES
    assert "recover_body_signal" in ACTION_FAMILIES


def test_each_guidance_output_has_action_family():
    result = simulate_user(advanced_synthetic_user_models()[0], seed=201, duration_days=14)

    assert all(output.action_family in ACTION_FAMILIES for output in result.guidance_outputs)


def test_vague_actions_flagged():
    output = _output(primary_action="Be mindful", action_family="maintain_plan")

    result = ActionSpecificityOracle().evaluate((output,))

    assert result.status == "fail"


def test_concrete_action_passes():
    output = _output(primary_action="Remove one optional demand.", action_family="reduce_optional_load")

    result = ActionSpecificityOracle().evaluate((output,))

    assert result.status == "pass"


def test_same_label_different_profiles_have_relevant_action_variation():
    outputs = (
        _output(label="Simplify", top_drivers=("Work pressure",), action_family="reduce_optional_load"),
        _output(label="Simplify", top_drivers=("Body signal",), action_family="recover_body_signal"),
        _output(label="Simplify", top_drivers=("Missing data",), action_family="check_in_first"),
    )

    result = AdviceDiversityOracle().evaluate(outputs)

    assert result.status == "pass"


def test_repeated_same_action_for_unrelated_drivers_warns():
    outputs = (
        _output(label="Simplify", top_drivers=("Work pressure",), action_family="avoid_extra_commitment"),
        _output(label="Simplify", top_drivers=("Body signal",), action_family="avoid_extra_commitment"),
        _output(label="Simplify", top_drivers=("Missing data",), action_family="avoid_extra_commitment"),
    )

    result = AdviceDiversityOracle().evaluate(outputs)

    assert result.status == "fail"


def test_counterfactual_worse_sleep_not_more_aggressive():
    assert counterfactual_results()["worsening_sleep_does_not_make_guidance_more_aggressive"]


def test_counterfactual_pattern_awareness_toggle_respected():
    assert counterfactual_results()["pattern_awareness_off_removes_private_pattern_driver"]


def test_high_stress_low_energy_shifts_more_conservative():
    assert counterfactual_results()["high_stress_low_energy_shifts_more_conservative"]


def test_recent_improvement_softens_or_is_acknowledged():
    days = (
        _day(date="2026-05-17", inputs={"core.sleep_ok": False, "mental.stress": 9, "energy.energy": 2}),
        _day(date="2026-05-18", inputs={"core.sleep_ok": True, "mental.stress": 2, "energy.energy": 8}),
    )
    outputs = (
        _output(date="2026-05-17", label="Protect Sleep", recent_change="Recent context is getting heavier."),
        _output(date="2026-05-18", label="Maintain", recent_change="Recent context is improving."),
    )

    result = MomentumOracle().evaluate(days, outputs)

    assert result.status == "pass"


def test_small_noise_no_whiplash():
    days = (
        _day(date="2026-05-17", inputs={"core.sleep_ok": True, "mental.stress": 3, "energy.energy": 7}),
        _day(date="2026-05-18", inputs={"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6}),
    )
    outputs = (
        _output(date="2026-05-17", label="Maintain"),
        _output(date="2026-05-18", label="Maintain"),
    )

    result = GuidanceVolatilityOracle().evaluate(days, outputs)

    assert result.status == "pass"


def test_advice_fatigue_detects_repetition():
    outputs = tuple(
        _output(date=f"2026-05-{day:02d}", primary_action="Remove one optional demand.")
        for day in range(1, 11)
    )

    result = AdviceFatigueOracle().evaluate(outputs, max_identical_run=5)

    assert result.status == "fail"


def test_stable_maintain_sequence_does_not_fail():
    days = tuple(
        _day(date=f"2026-05-{day:02d}", inputs={"core.sleep_ok": True, "mental.stress": 2, "energy.energy": 8})
        for day in range(1, 14)
    )
    outputs = tuple(_output(date=day.date, label="Maintain") for day in days)

    result = StuckStateOracle().evaluate(days, outputs, advanced_synthetic_user_models()[0], {})

    assert result.status == "pass"
    assert result.classification == "stable_maintain_ok"


def test_maintain_despite_stress9_energy2_fails_or_warns():
    days = tuple(
        _day(date=f"2026-05-{day:02d}", inputs={"core.sleep_ok": True, "mental.stress": 9, "energy.energy": 2})
        for day in range(1, 14)
    )
    outputs = tuple(_output(date=day.date, label="Maintain") for day in days)

    result = StuckStateOracle().evaluate(days, outputs, advanced_synthetic_user_models()[0], {})

    assert result.status in {"warning", "fail"}
    assert result.classification == "neutral_despite_worsening"


def test_simplify_due_only_to_missing_data_for_many_days_warns():
    days = tuple(_day(date=f"2026-05-{day:02d}", inputs={}, missing_inputs=("core.sleep_ok",)) for day in range(1, 14))
    outputs = tuple(
        _output(
            date=day.date,
            label="Simplify",
            confidence="limited",
            top_drivers=("Missing data",),
            action_family="avoid_extra_commitment",
            primary_action="Save the basics first.",
        )
        for day in days
    )

    result = StuckStateOracle().evaluate(days, outputs, advanced_synthetic_user_models()[0], {})

    assert result.status in {"warning", "fail"}
    assert result.classification == "missing_data_loop"


def test_protect_sleep_despite_recent_recovery_warns():
    days = tuple(
        _day(date=f"2026-05-{day:02d}", inputs={"core.sleep_ok": True, "mental.stress": 1, "energy.energy": 8})
        for day in range(1, 14)
    )
    outputs = tuple(_output(date=day.date, label="Protect Sleep") for day in days)

    result = StuckStateOracle().evaluate(days, outputs, advanced_synthetic_user_models()[0], {})

    assert result.status in {"warning", "fail"}
    assert result.classification in {"severe_stuck", "needs_review"}


def test_severe_inputs_remaining_severe_can_continue_without_false_fail():
    days = tuple(
        _day(date=f"2026-05-{day:02d}", inputs={"core.sleep_ok": False, "mental.stress": 9, "energy.energy": 2})
        for day in range(1, 14)
    )
    outputs = tuple(_output(date=day.date, label="Protect Sleep") for day in days)

    result = StuckStateOracle().evaluate(days, outputs, advanced_synthetic_user_models()[0], {})

    assert result.status == "pass"


def test_empty_day_has_limited_confidence():
    day = _day(inputs={}, missing_inputs=("core.sleep_ok", "mental.stress", "energy.energy"))
    output = guidance_for_synthetic_day(day)

    assert output.confidence == "limited"
    assert output.action_family == "check_in_first"


def test_repeated_empty_days_do_not_claim_known_overload():
    days = tuple(_day(date=f"2026-05-{day:02d}", inputs={}, missing_inputs=("core.sleep_ok",)) for day in range(1, 4))
    outputs = tuple(guidance_for_synthetic_day(day) for day in days)

    assert all("mental_load_high" not in output.bridge_inputs for output in outputs)
    assert all("energy_low" not in output.bridge_inputs for output in outputs)


def test_empty_day_action_invites_checkin():
    output = guidance_for_synthetic_day(_day(inputs={}, missing_inputs=("core.sleep_ok",)))

    assert "check-in" in output.primary_action.lower()


def test_empty_day_does_not_create_false_zero_values():
    output = guidance_for_synthetic_day(_day(inputs={}, missing_inputs=("core.sleep_ok",)))

    assert output.bridge_inputs["data_confidence"] == 0.0
    assert "private_pattern_active" not in output.bridge_inputs


def test_no_data_oracle_detects_bad_empty_day():
    day = _day(inputs={}, missing_inputs=("core.sleep_ok",))
    output = _output(confidence="normal", action_family="avoid_extra_commitment", primary_action="Remove one optional demand.")

    result = NoDataGuidanceOracle().evaluate((day,), (output,), advanced_synthetic_user_models()[0], {})

    assert result.status == "fail"


def test_body_signal_hypotheses_are_documented():
    backlog = {item["id"]: item for item in hypothesis_backlog()}

    assert "body_signal_repeated_high_response" in backlog
    assert backlog["body_signal_repeated_high_response"]["classification"] == "hypothesis_pending_formula_decision"


def test_general_balance_hypotheses_are_documented():
    backlog = {item["id"]: item for item in hypothesis_backlog()}

    assert "general_balance_high_stress_low_energy" in backlog
    assert backlog["general_balance_high_stress_low_energy"]["classification"] == "hypothesis_pending_formula_decision"


def test_work_stress_project_overrun_driver_not_private_pattern_without_pack():
    day = _day(
        profile_id="work_stress",
        inputs={
            "core.sleep_ok": True,
            "mental.stress": 8,
            "energy.energy": 4,
            "work.project_overrun": True,
        },
    )

    output = guidance_for_synthetic_day(day, optional_packs=())

    assert "Private pattern" not in output.top_drivers


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

    output = guidance_for_synthetic_day(day, optional_packs=("pattern_awareness_pack",))

    assert "Private pattern" in output.top_drivers


def test_all_new_models_generate():
    models = advanced_synthetic_user_models()

    assert len(models) == 8
    for model in models:
        result = simulate_user(model, seed=301, duration_days=14)
        assert len(result.generated_days) == 14


def test_new_models_have_expectations():
    assert all(model.expectations for model in advanced_synthetic_user_models())


def test_new_models_run_90_days():
    for model in advanced_synthetic_user_models():
        result = simulate_user(model, seed=302, duration_days=90)
        assert result.duration_days == 90


def test_key_profile_expectations_pass_or_report_warnings():
    for model in advanced_synthetic_user_models():
        result = simulate_user(model, seed=303, duration_days=90)
        assert result.oracle_results
        assert all(oracle.status in {"pass", "warning", "fail"} for oracle in result.oracle_results)


def test_review_artifact_classifies_anomalies(fresh_review_inputs):
    rows = review_evaluation_artifact(fresh_review_inputs["base"])

    assert rows
    assert all("likely_classification" in row for row in rows)


def test_anomaly_review_doc_and_zip_generated(tmp_path, fresh_review_inputs):
    doc = tmp_path / "review.html"

    zip_path = write_synthetic_review_docs(
        source_zip=fresh_review_inputs["base"],
        output_doc=doc,
        output_dir=tmp_path,
        timestamp="review",
    )

    assert doc.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "anomaly_review.json",
        "anomaly_review.md",
        "anomaly_review.html",
        "oracle_refinement_report.json",
        "hypothesis_backlog.json",
        "recommended_formula_experiments.json",
    }.issubset(names)


def test_human_review_samples_generated(tmp_path):
    zip_path = write_advanced_quality_report_zip(seed=304, output_dir=tmp_path, timestamp="human-review-test")
    with zipfile.ZipFile(zip_path) as archive:
        content = archive.read("human_review_samples.md").decode("utf-8")

    assert "would_a_tired_user_understand" in content


def test_advanced_report_contains_expected_files(tmp_path):
    zip_path = write_advanced_quality_report_zip(seed=305, output_dir=tmp_path, timestamp="advanced")

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "advanced_metrics.json",
        "oracle_results.json",
        "counterfactual_results.json",
        "volatility_report.json",
        "advice_fatigue_report.json",
        "action_family_distribution.json",
        "human_review_samples.md",
        "recommended_formula_hypotheses.json",
    }.issubset(names)
    assert any(name.startswith("new_model_results/") for name in names)


def test_hypothesis_classification_covers_required_decisions():
    hypotheses = {item["hypothesis"]: item for item in hypothesis_classification()}

    assert "no-data days should invite check-in rather than repeatedly Simplify" in hypotheses
    assert "Body Signal Awareness may need stronger repeated-signal response" in hypotheses
    assert "General Balance high stress + low energy may need stronger Simplify behavior" in hypotheses
    assert {item["classification"] for item in hypotheses.values()} <= {
        "ready for formula experiment",
        "needs human review",
        "likely copy/action-family fix",
        "likely oracle refinement",
        "defer",
    }


def test_selected_human_review_samples_include_rating_fields(fresh_review_inputs):
    samples = selected_human_review_samples(
        advanced_zip=fresh_review_inputs["advanced"],
        review_zip=fresh_review_inputs["review"],
        max_samples=12,
    )

    assert samples
    assert len(samples) <= 12
    assert {
        "label_fit_1_5",
        "driver_fit_1_5",
        "action_usefulness_1_5",
        "would_a_tired_user_understand_1_5",
    }.issubset(samples[0]["rating_fields"])


def test_human_review_pack_contains_expected_files(tmp_path, fresh_review_inputs):
    review_doc = tmp_path / "human_review.html"
    memo_doc = tmp_path / "memo.html"

    zip_path = write_human_review_pack_zip(
        review_zip=fresh_review_inputs["review"],
        advanced_zip=fresh_review_inputs["advanced"],
        review_sheet_doc=review_doc,
        memo_doc=memo_doc,
        output_dir=tmp_path,
        timestamp="human-pack",
    )

    assert review_doc.exists()
    assert memo_doc.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        selected = archive.read("selected_samples.json").decode("utf-8")
    assert {
        "README.md",
        "human_review_sheet.html",
        "formula_decision_memo.html",
        "selected_samples.json",
        "hypothesis_classification.json",
    }.issubset(names)
    assert "rating_fields" in selected


@pytest.fixture(scope="module")
def fresh_review_inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("fresh_synthetic_review")
    base = write_simulation_report_zip(output_dir=root, timestamp="fresh")
    review = write_synthetic_review_docs(source_zip=base, output_doc=root / "review.html", output_dir=root, timestamp="fresh")
    advanced = write_advanced_quality_report_zip(output_dir=root, timestamp="fresh")
    return {"base": base, "review": review, "advanced": advanced}
