import zipfile

from life_load.synthetic_users import (
    ActionQualityOracle,
    GuidanceExpectation,
    GuidanceOutput,
    MessageRelevanceOracle,
    MissingDataOracle,
    ProfileLeakageOracle,
    RecencyOracle,
    SensitiveCopyOracle,
    SeverityOracle,
    StuckStateOracle,
    SyntheticDay,
    compute_metrics,
    expectations_validate_schema,
    generate_review_samples,
    generated_values_valid,
    mutation_checks,
    phases_cover_full_duration,
    required_synthetic_user_models,
    run_all_oracles,
    simulate_user,
    write_simulation_report_zip,
)


def _model(model_id):
    return {model.id: model for model in required_synthetic_user_models()}[model_id]


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
        "action_family": "maintain",
        "recent_change": "Recent context is steady.",
        "warning_sensitive_text": "",
        "missing_signal_ids": (),
        "bridge_inputs": {},
    }
    base.update(kwargs)
    return GuidanceOutput(**base)


def test_same_seed_reproducible():
    model = _model("work_stress_project_crunch")

    first = simulate_user(model, seed=101, duration_days=30)
    second = simulate_user(model, seed=101, duration_days=30)

    assert first.generated_days == second.generated_days
    assert first.guidance_outputs == second.guidance_outputs


def test_different_seed_varies_but_preserves_shape():
    model = _model("training_recovery_recreational_athlete")

    first = simulate_user(model, seed=102, duration_days=30)
    second = simulate_user(model, seed=103, duration_days=30)

    assert first.generated_days != second.generated_days
    assert len(first.generated_days) == len(second.generated_days) == 30
    assert {day.profile_id for day in first.generated_days} == {"training_recovery"}
    assert generated_values_valid(first.generated_days)
    assert generated_values_valid(second.generated_days)


def test_all_required_models_have_phases_and_expectations():
    for model in required_synthetic_user_models():
        assert phases_cover_full_duration(model)
        assert model.event_schedule
        assert model.expectations
        assert all(expectations_validate_schema(expectation) for expectation in model.expectations)


def test_profile_leakage_oracle_detects_bad_driver():
    model = _model("general_balance_stable")
    output = _output(top_drivers=("Foot pain",), profile_id="general_balance")

    result = ProfileLeakageOracle().evaluate((_day(),), (output,), model, {})

    assert result.status == "fail"
    assert result.affected_days == ("2026-05-18",)


def test_missing_data_oracle_detects_overconfidence():
    model = _model("sparse_low_compliance_user")
    day = _day(inputs={"energy.energy": 5}, missing_inputs=("core.sleep_ok", "mental.stress"))
    output = _output(confidence="normal")

    result = MissingDataOracle().evaluate((day,), (output,), model, {})

    assert result.status == "fail"


def test_recency_oracle_detects_old_drift_overweighting():
    model = _model("general_balance_overload_drift")
    day = _day(phase_name="recovery", inputs={"core.sleep_ok": True, "mental.stress": 2, "energy.energy": 8})
    output = _output(label="Protect Sleep")

    result = RecencyOracle().evaluate((day,), (output,), model, {})

    assert result.status == "fail"


def test_severity_oracle_detects_push_on_severe_day():
    model = _model("training_recovery_recreational_athlete")
    day = _day(
        profile_id="training_recovery",
        inputs={
            "core.sleep_ok": False,
            "mental.stress": 8,
            "energy.energy": 2,
            "training.activity_duration_min": 70,
        },
    )
    output = _output(profile_id="training_recovery", label="Push")

    result = SeverityOracle().evaluate((day,), (output,), model, {})

    assert result.status == "fail"


def test_message_relevance_oracle_detects_driver_mismatch():
    model = _model("work_stress_project_crunch")
    days = tuple(
        _day(
            date=f"2026-05-{index:02d}",
            profile_id="work_stress",
            inputs={"mental.stress": 9, "energy.energy": 5, "core.sleep_ok": True},
        )
        for index in range(1, 5)
    )
    outputs = tuple(
        _output(date=day.date, profile_id="work_stress", top_drivers=("Recovery",))
        for day in days
    )

    result = MessageRelevanceOracle().evaluate(days, outputs, model, {})

    assert result.status == "fail"


def test_sensitive_copy_oracle_detects_forbidden_terms():
    model = _model("pattern_awareness_private_pull")
    output = _output(warning_sensitive_text="This is treatment wording.")

    result = SensitiveCopyOracle().evaluate((_day(),), (output,), model, {})

    assert result.status == "fail"


def test_stuck_state_oracle_detects_implausible_stuck_state():
    model = _model("general_balance_stable")
    outputs = tuple(
        _output(date=f"2026-05-{day:02d}", label="Protect Sleep")
        for day in range(1, 14)
    )
    days = tuple(_day(date=output.date) for output in outputs)

    result = StuckStateOracle().evaluate(days, outputs, model, {})

    assert result.status == "fail"


def test_each_oracle_passes_known_good_case():
    model = _model("general_balance_stable")
    result = simulate_user(model, seed=104, duration_days=14)
    oracle_results = run_all_oracles(
        result.generated_days,
        result.guidance_outputs,
        model,
        result.summary_metrics,
    )

    assert all(oracle.status in {"pass", "warning"} for oracle in oracle_results)


def test_metrics_are_computed_for_each_simulation():
    result = simulate_user(_model("general_balance_stable"), seed=105, duration_days=30)

    assert "guidance_label_distribution" in result.summary_metrics
    assert "confidence_distribution" in result.summary_metrics
    assert "missing_data_rate" in result.summary_metrics
    assert "push_rate" in result.summary_metrics


def test_stable_user_not_stuck_in_protect_sleep():
    result = simulate_user(_model("general_balance_stable"), seed=106, duration_days=90)

    assert result.summary_metrics["protect_sleep_rate"] < 0.25


def test_sparse_user_has_limited_confidence():
    result = simulate_user(_model("sparse_low_compliance_user"), seed=107, duration_days=90)

    assert result.summary_metrics["confidence_distribution"].get("limited", 0) > 0


def test_recent_recovery_reduces_severity():
    result = simulate_user(_model("general_balance_overload_drift"), seed=108, duration_days=70)
    overload = [
        output
        for day, output in zip(result.generated_days, result.guidance_outputs)
        if day.phase_name == "acute_overload" and day.inputs
    ]
    recovery = [
        output
        for day, output in zip(result.generated_days, result.guidance_outputs)
        if day.phase_name == "recovery" and day.inputs
    ]

    assert overload and recovery
    assert max({"Push": 0, "Maintain": 1, "Recover": 2, "Simplify": 3, "Protect Sleep": 4}[output.label] for output in recovery) <= 3


def test_mutation_tests_detect_directional_inversions():
    results = mutation_checks(seed=109)

    assert results
    assert all(results.values())


def test_review_sample_generator_outputs_samples():
    model = _model("pattern_awareness_private_pull")
    result = simulate_user(model, seed=110, duration_days=30)
    samples = generate_review_samples(
        result.generated_days,
        result.guidance_outputs,
        result.oracle_results,
        model,
        seed=110,
    )

    assert samples
    assert {"day", "profile", "phase", "guidance_label", "why_selected"}.issubset(samples[0])


def test_report_zip_contains_expected_files(tmp_path):
    results = (simulate_user(_model("general_balance_stable"), seed=111, duration_days=14),)

    zip_path = write_simulation_report_zip(results=results, seed=111, output_dir=tmp_path, timestamp="eval")

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "simulation_summary.json",
        "oracle_results.json",
        "anomalies.json",
        "review_samples.md",
        "thresholds.json",
        "summary_metrics.csv",
        "simulation_report.md",
    }.issubset(names)


def test_expectations_validate_schema_rejects_empty_exact_string_golden():
    assert not expectations_validate_schema(GuidanceExpectation(scenario_id="", phase_name="", allowed_labels=()))
