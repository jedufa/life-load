import zipfile

from life_load.synthetic_users import (
    FORBIDDEN_SENSITIVE_TERMS,
    GuidanceOutput,
    SyntheticDay,
    compute_metrics,
    generated_values_valid,
    required_synthetic_user_models,
    simulate_user,
    write_simulation_report_zip,
)


def _model(model_id):
    return {model.id: model for model in required_synthetic_user_models()}[model_id]


def test_all_required_synthetic_users_generate():
    models = required_synthetic_user_models()

    assert {model.id for model in models} == {
        "general_balance_stable",
        "general_balance_overload_drift",
        "work_stress_project_crunch",
        "training_recovery_recreational_athlete",
        "body_signal_awareness_recurring_signal",
        "pattern_awareness_private_pull",
        "sparse_low_compliance_user",
        "long_term_inconsistent_user",
    }
    for model in models:
        result = simulate_user(model, seed=17, duration_days=14)
        assert len(result.generated_days) == 14
        assert len(result.guidance_outputs) == 14


def test_14_day_simulations_complete():
    for model in required_synthetic_user_models():
        result = simulate_user(model, seed=18, duration_days=14)

        assert result.duration_days == 14
        assert result.summary_metrics["sensitive_word_violation_count"] == 0


def test_90_day_simulations_complete():
    for model in required_synthetic_user_models():
        if model.id == "long_term_inconsistent_user":
            continue

        result = simulate_user(model, seed=19, duration_days=90)

        assert result.duration_days == 90
        assert generated_values_valid(result.generated_days)


def test_2_year_long_term_user_completes():
    result = simulate_user(_model("long_term_inconsistent_user"), seed=20, duration_days=730)

    assert result.duration_days == 730
    assert len(result.generated_days) == 730
    assert result.summary_metrics["sensitive_word_violation_count"] == 0


def test_general_balance_no_personal_legacy_driver_leakage():
    result = simulate_user(_model("general_balance_overload_drift"), seed=21, duration_days=90)

    assert result.summary_metrics["profile_leakage_count"] == 0
    drivers = " ".join(driver for output in result.guidance_outputs for driver in output.top_drivers).lower()
    assert "alcohol" not in drivers
    assert "homework" not in drivers
    assert "foot" not in drivers
    assert "shoulder" not in drivers


def test_work_stress_no_homework_relationship_bodypart_leakage():
    result = simulate_user(_model("work_stress_project_crunch"), seed=22, duration_days=90)
    drivers = " ".join(driver for output in result.guidance_outputs for driver in output.top_drivers).lower()

    assert "homework" not in drivers
    assert "relationship" not in drivers
    assert "foot" not in drivers
    assert "shoulder" not in drivers


def test_training_recovery_no_relationship_homework_leakage():
    result = simulate_user(_model("training_recovery_recreational_athlete"), seed=23, duration_days=90)
    drivers = " ".join(driver for output in result.guidance_outputs for driver in output.top_drivers).lower()

    assert "homework" not in drivers
    assert "relationship" not in drivers


def test_pattern_awareness_disabled_has_no_pattern_effect():
    disabled_model = _model("general_balance_overload_drift")
    enabled_model = _model("pattern_awareness_private_pull")
    disabled = simulate_user(disabled_model, seed=24, duration_days=60)
    enabled = simulate_user(enabled_model, seed=24, duration_days=60)

    assert all("Private pattern" not in output.top_drivers for output in disabled.guidance_outputs)
    assert any("Private pattern" in output.top_drivers for output in enabled.guidance_outputs)


def test_pattern_awareness_enabled_uses_safe_private_pattern_wording():
    result = simulate_user(_model("pattern_awareness_private_pull"), seed=25, duration_days=90)
    text = " ".join(
        " ".join(output.top_drivers) + " " + output.warning_sensitive_text
        for output in result.guidance_outputs
    ).lower()

    assert "private pattern" in text
    assert not any(term in text for term in FORBIDDEN_SENSITIVE_TERMS)


def test_sparse_user_gets_limited_confidence():
    result = simulate_user(_model("sparse_low_compliance_user"), seed=26, duration_days=90)

    confidence = result.summary_metrics["confidence_distribution"]
    assert confidence.get("limited", 0) > confidence.get("normal", 0)


def test_recent_recovery_softens_old_overload():
    result = simulate_user(_model("general_balance_overload_drift"), seed=27, duration_days=70)
    recovery_labels = [
        output.label
        for day, output in zip(result.generated_days, result.guidance_outputs)
        if day.phase_name == "recovery" and day.inputs
    ]

    assert recovery_labels
    assert recovery_labels.count("Protect Sleep") < len(recovery_labels) / 2
    assert result.summary_metrics["old_drift_overweighting"] == "not_detected"


def test_forbidden_sensitive_terms_absent():
    for model in required_synthetic_user_models():
        result = simulate_user(model, seed=28, duration_days=90 if model.duration_days >= 90 else model.duration_days)
        text = " ".join(
            output.label
            + " "
            + " ".join(output.top_drivers)
            + " "
            + output.confidence_note
            + " "
            + output.primary_action
            + " "
            + output.warning_sensitive_text
            for output in result.guidance_outputs
        ).lower()
        assert not any(term in text for term in FORBIDDEN_SENSITIVE_TERMS), model.id


def test_report_generation_outputs_expected_files(tmp_path):
    results = tuple(simulate_user(model, seed=29, duration_days=14) for model in required_synthetic_user_models())

    zip_path = write_simulation_report_zip(results=results, seed=29, output_dir=tmp_path, timestamp="test")

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "README.md" in names
    assert "simulation_summary.json" in names
    assert "oracle_results.json" in names
    assert "anomalies.json" in names
    assert "thresholds.json" in names
    assert "review_samples.md" in names
    assert any(name.startswith("per_user_results/") and name.endswith(".json") for name in names)

