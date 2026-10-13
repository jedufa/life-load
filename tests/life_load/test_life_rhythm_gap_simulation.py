import ast
import zipfile
from pathlib import Path

from life_load.synthetic_guidance_quality import write_life_rhythm_gap_report_zip
from life_load.synthetic_users import (
    GuidanceOutput,
    PhaseTransitionOracle,
    ReturnAfterGapOracle,
    SamplingBiasOracle,
    StaleHistoryOracle,
    SyntheticDay,
    compute_life_rhythm_metrics,
    generated_values_valid,
    life_rhythm_synthetic_user_models,
    phases_cover_full_duration,
    simulate_user,
)


def _models():
    return {model.id: model for model in life_rhythm_synthetic_user_models()}


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


def test_all_life_rhythm_models_generate():
    models = life_rhythm_synthetic_user_models()

    assert {model.id for model in models} == {
        "high_to_recovery_transition",
        "stable_to_sudden_spike",
        "repeated_load_waves",
        "bad_phase_then_long_gap",
        "good_phase_then_long_gap",
        "bad_day_only_logger",
        "good_day_only_logger",
        "partial_after_gap_user",
    }
    for model in models:
        result = simulate_user(model, seed=401, duration_days=min(90, model.duration_days))
        assert len(result.generated_days) == min(90, model.duration_days)
        assert generated_values_valid(result.generated_days)


def test_life_rhythm_models_have_phases_and_expectations():
    for model in life_rhythm_synthetic_user_models():
        assert phases_cover_full_duration(model)
        assert model.event_schedule
        assert model.expectations


def test_long_gap_models_include_expected_gap_lengths():
    for model_id in ("bad_phase_then_long_gap", "good_phase_then_long_gap", "partial_after_gap_user"):
        model = _models()[model_id]
        result = simulate_user(model, seed=402, duration_days=model.duration_days)
        metrics = compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs)

        assert metrics["max_gap_days"] >= 30


def test_stale_bad_history_does_not_dominate_after_gap():
    model = _models()["bad_phase_then_long_gap"]
    result = simulate_user(model, seed=403, duration_days=model.duration_days)
    metrics = compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs)
    oracle = StaleHistoryOracle().evaluate(result.generated_days, result.guidance_outputs, model, metrics)

    assert oracle.status == "pass"
    assert metrics["stale_bad_simplify_or_protect_count"] == 0


def test_stale_good_history_does_not_create_push_after_gap():
    model = _models()["good_phase_then_long_gap"]
    result = simulate_user(model, seed=404, duration_days=model.duration_days)
    metrics = compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs)
    labels = metrics["gap_return_guidance_labels"]

    assert labels
    assert "Push" not in labels[:3]
    assert metrics["stale_good_push_count"] == 0


def test_return_after_gap_has_limited_confidence():
    for model_id in ("bad_phase_then_long_gap", "good_phase_then_long_gap", "partial_after_gap_user"):
        model = _models()[model_id]
        result = simulate_user(model, seed=405, duration_days=model.duration_days)
        metrics = compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs)

        assert metrics["return_after_gap_limited_confidence_rate"] >= 0.9


def test_high_to_recovery_transition_softens():
    result = simulate_user(_models()["high_to_recovery_transition"], seed=406, duration_days=30)
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
    assert max(_severity(output) for output in recovery) <= max(_severity(output) for output in overload)


def test_stable_to_spike_transition_escalates():
    result = simulate_user(_models()["stable_to_sudden_spike"], seed=407, duration_days=40)
    baseline = [
        output
        for day, output in zip(result.generated_days, result.guidance_outputs)
        if day.phase_name == "baseline" and day.inputs
    ]
    spike = [
        output
        for day, output in zip(result.generated_days, result.guidance_outputs)
        if day.phase_name == "acute_overload" and day.inputs
    ]

    assert baseline and spike
    assert max(_severity(output) for output in spike) > min(_severity(output) for output in baseline)


def test_repeated_waves_not_stuck():
    model = _models()["repeated_load_waves"]
    result = simulate_user(model, seed=408, duration_days=120)
    metrics = compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs)

    assert metrics["long_gap_stuck_state_count"] < 10
    assert len(set(output.label for output in result.guidance_outputs)) >= 2


def test_bad_day_only_logger_gets_uncertainty():
    model = _models()["bad_day_only_logger"]
    result = simulate_user(model, seed=409, duration_days=model.duration_days)

    assert result.summary_metrics["confidence_distribution"].get("limited", 0) > 0
    assert SamplingBiasOracle().evaluate(
        result.generated_days,
        result.guidance_outputs,
        model,
        compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs),
    ).status in {"warning", "fail"}


def test_good_day_only_logger_gets_uncertainty():
    model = _models()["good_day_only_logger"]
    result = simulate_user(model, seed=410, duration_days=model.duration_days)

    assert result.summary_metrics["confidence_distribution"].get("limited", 0) > 0
    assert SamplingBiasOracle().evaluate(
        result.generated_days,
        result.guidance_outputs,
        model,
        compute_life_rhythm_metrics(result.generated_days, result.guidance_outputs),
    ).status in {"warning", "fail"}


def test_gap_oracles_detect_intentional_bad_cases():
    days = tuple(
        [_day(date=f"2026-01-{day:02d}", inputs={}, phase_name="long_gap") for day in range(1, 31)]
        + [_day(date="2026-02-01", inputs={"energy.energy": 8}, phase_name="return_after_gap")]
    )
    outputs = tuple(
        [_output(date=day.date, label="Maintain", confidence="limited", top_drivers=("Missing data",)) for day in days[:-1]]
        + [_output(date="2026-02-01", label="Push", confidence="normal", top_drivers=("Energy",))]
    )
    model = _models()["good_phase_then_long_gap"]
    metrics = compute_life_rhythm_metrics(days, outputs)

    assert StaleHistoryOracle().evaluate(days, outputs, model, metrics).status == "fail"
    assert ReturnAfterGapOracle().evaluate(days, outputs, model, metrics).status == "fail"

    transition_days = (
        _day(date="2026-03-01", inputs={"core.sleep_ok": True, "mental.stress": 2, "energy.energy": 8}, phase_name="baseline"),
        _day(date="2026-03-02", inputs={"core.sleep_ok": False, "mental.stress": 9, "energy.energy": 2}, phase_name="acute_overload"),
    )
    transition_outputs = (
        _output(date="2026-03-01", label="Maintain"),
        _output(date="2026-03-02", label="Push"),
    )
    assert PhaseTransitionOracle().evaluate(transition_days, transition_outputs, model, {}).status == "fail"


def test_life_rhythm_report_artifact_contains_expected_files(tmp_path):
    zip_path = write_life_rhythm_gap_report_zip(seed=411, output_dir=tmp_path, timestamp="life-rhythm")

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {
        "README.md",
        "life_rhythm_summary.json",
        "gap_oracle_results.json",
        "phase_transition_results.json",
        "sampling_bias_results.json",
        "stale_history_results.json",
        "review_samples.md",
    }.issubset(names)
    assert any(name.startswith("per_model_results/") and name.endswith(".json") for name in names)


def test_production_code_does_not_import_synthetic_harness():
    production_roots = (Path("app/backend/life_load"),)
    allowed_files = {
        Path("app/backend/life_load/synthetic_users.py"),
        Path("app/backend/life_load/synthetic_guidance_quality.py"),
    }
    offenders = []
    for root in production_roots:
        for path in root.rglob("*.py"):
            if path in allowed_files:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("life_load.synthetic"):
                    offenders.append(str(path))
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("life_load.synthetic"):
                            offenders.append(str(path))

    assert not offenders


def _severity(output):
    return {
        "Push": 0,
        "Maintain": 1,
        "Recover": 2,
        "Simplify": 3,
        "Protect Sleep": 4,
    }[output.label]
