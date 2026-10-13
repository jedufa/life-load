import zipfile

from life_load import scoring
from life_load.guidance_bridge import (
    build_guidance_bridge_from_fixed_entry,
    build_guidance_bridge_from_selected_profile_config,
    score_personal_legacy_via_bridge,
)
from life_load.selected_profile_config import build_selected_profile_config
from life_load.synthetic_guidance_quality import write_experiment_2_generic_profile_bridge_zip
from life_load.synthetic_users import SyntheticDay, guidance_for_synthetic_day


FIXTURE_ENTRIES = {
    "low_load_day": {
        "date": "2026-05-04",
        "sleep_ok": True,
        "nutrition_ok": True,
        "stress": 2,
        "energy": 7,
        "shutdown_done": True,
        "decompression_done": True,
    },
    "body_signal_day": {
        "date": "2026-05-05",
        "sleep_ok": True,
        "nutrition_ok": True,
        "stress": 5,
        "energy": 4,
        "foot_pain": 6,
        "shoulder_pain": 0,
        "migraine_warning": False,
    },
    "evening_risk_day": {
        "date": "2026-05-06",
        "sleep_ok": False,
        "nutrition_ok": True,
        "phone_after_21": True,
        "project_overrun": True,
        "evening_chain_broken": True,
        "shutdown_done": False,
        "decompression_done": False,
        "after_work_decompression_done": False,
        "stress": 7,
        "energy": 3,
    },
    "relationship_homework_day": {
        "date": "2026-05-07",
        "wife_conflict_count": 2,
        "wife_conflict_school": True,
        "wife_conflict_chores": False,
        "family_stress": 6,
        "homework_done": False,
        "stress": 6,
        "energy": 4,
    },
    "training_day": {
        "date": "2026-05-08",
        "primary_activity_type": "crossfit",
        "activity_duration_min": 45,
        "rehab_done": False,
        "foot_pain": 2,
        "shoulder_pain": 1,
        "stress": 4,
        "energy": 6,
        "nutrition_ok": True,
    },
    "nutrition_risk_day": {
        "date": "2026-05-09",
        "alcohol": "home",
        "binge": True,
        "nutrition_ok": False,
        "sleep_ok": False,
        "stress": 6,
        "energy": 2,
    },
    "sparse_unknown_day": {"date": "2026-05-10"},
    "explicit_false_zero_day": {
        "date": "2026-05-11",
        "phone_after_21": False,
        "project_overrun": False,
        "foot_pain": 0,
        "shoulder_pain": 0,
        "wife_conflict_count": 0,
        "coffee_cups": 0,
        "binge": False,
    },
}


def _entries(**values):
    return tuple({"signal_id": signal_id, "value": value, "is_present": True} for signal_id, value in values.items())


def _day(profile_id: str, inputs: dict):
    return SyntheticDay(
        date="2026-05-18",
        profile_id=profile_id,
        inputs=inputs,
        missing_inputs=(),
        tags=(),
        phase_name="baseline",
    )


def test_bridge_contract_preserves_absent_false_zero():
    config = build_selected_profile_config("personal_legacy")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "evening.phone_after_21": False,
                "work.project_overrun": False,
                "body.foot_pain": 0,
                "body.shoulder_pain": 0,
            }
        ),
    )

    assert "core.sleep_ok" not in snapshot.present_signal_values
    assert snapshot.present_signal_values["evening.phone_after_21"] is False
    assert snapshot.present_signal_values["work.project_overrun"] is False
    assert snapshot.present_signal_values["body.foot_pain"] == 0
    assert "evening_boundary_broken" not in snapshot.inputs
    assert "body_signal_high" not in snapshot.inputs


def test_hidden_disabled_signals_do_not_create_bridge_inputs():
    config = build_selected_profile_config("body_signal_awareness")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "core.sleep_ok": True,
                "mental.stress": 4,
                "energy.energy": 6,
                "body.foot_pain": 10,
                "body.shoulder_pain": 10,
                "relationship.wife_conflict_count": 2,
                "caregiving.homework_done": False,
            }
        ),
    )

    assert "body.foot_pain" not in snapshot.present_signal_values
    assert "body.shoulder_pain" not in snapshot.present_signal_values
    assert "relationship.wife_conflict_count" not in snapshot.present_signal_values
    assert "caregiving.homework_done" not in snapshot.present_signal_values
    assert "body_signal_high" not in snapshot.inputs
    assert "mental_load_high" not in snapshot.inputs


def test_unknown_future_signals_are_inert():
    config = build_selected_profile_config("general_balance")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        (
            {"signal_id": "custom.future_signal", "value": 9, "is_present": True},
            {"signal_id": "energy.energy", "value": 2, "is_present": True},
        ),
    )

    assert snapshot.inert_unknown_signal_ids == ("custom.future_signal",)
    assert "custom.future_signal" not in snapshot.present_signal_values
    assert snapshot.inputs["energy_low"].value is True


def test_pattern_awareness_disabled_has_no_private_pattern_bridge_input():
    config = build_selected_profile_config("general_balance")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(**{"evening.phone_after_21": True, "work.project_overrun": True}),
    )

    assert "private_pattern_active" not in snapshot.inputs
    assert "evening.phone_after_21" not in snapshot.present_signal_values
    assert "work.project_overrun" not in snapshot.present_signal_values


def test_pattern_awareness_enabled_entries_can_bridge_private_pattern():
    config = build_selected_profile_config("general_balance", optional_pack_ids=("pattern_awareness_pack",))
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(**{"evening.phone_after_21": True, "work.project_overrun": True}),
    )

    assert snapshot.inputs["private_pattern_active"].value is True
    assert "evening.phone_after_21" in snapshot.present_signal_values
    assert "work.project_overrun" in snapshot.present_signal_values


def test_personal_legacy_production_bridge_matches_fixed_scorer_for_golden_fixtures():
    for fixture_name, entry in FIXTURE_ENTRIES.items():
        assert score_personal_legacy_via_bridge(entry) == scoring.score_entry(entry), fixture_name


def test_personal_legacy_projection_false_zero_absent_parity():
    fixed = build_guidance_bridge_from_fixed_entry(FIXTURE_ENTRIES["explicit_false_zero_day"])
    config = build_selected_profile_config("personal_legacy")
    generic = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "evening.phone_after_21": False,
                "work.project_overrun": False,
                "body.foot_pain": 0,
                "body.shoulder_pain": 0,
                "relationship.wife_conflict_count": 0,
                "nutrition.binge": False,
            }
        ),
    )

    assert generic.present_signal_values["evening.phone_after_21"] == fixed.present_signal_values["evening.phone_after_21"]
    assert generic.present_signal_values["body.foot_pain"] == fixed.present_signal_values["body.foot_pain"]
    assert "evening_boundary_broken" not in generic.inputs
    assert "body_signal_high" not in generic.inputs


def test_personal_legacy_driver_parity():
    fixed = build_guidance_bridge_from_fixed_entry(FIXTURE_ENTRIES["evening_risk_day"])
    config = build_selected_profile_config("personal_legacy")
    generic = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "core.sleep_ok": False,
                "core.nutrition_ok": True,
                "evening.phone_after_21": True,
                "work.project_overrun": True,
                "evening.evening_chain_broken": True,
                "recovery.shutdown_done": False,
                "recovery.decompression_done": False,
                "recovery.after_work_decompression_done": False,
                "mental.stress": 7,
                "energy.energy": 3,
            }
        ),
    )

    assert set(generic.inputs) == set(fixed.inputs)
    assert generic.inputs["life_load_high"].source_signal_ids == fixed.inputs["life_load_high"].source_signal_ids


def test_personal_legacy_experiment1_copy_differences_are_expected_only():
    empty = guidance_for_synthetic_day(_day("personal_legacy", {}))

    assert empty.label == "Maintain"
    assert empty.top_drivers == ("Missing data",)
    assert empty.primary_action == "Complete a short check-in for a better suggestion."


def test_general_balance_bridge_excludes_personal_legacy_fields():
    config = build_selected_profile_config("general_balance")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "core.sleep_ok": True,
                "core.nutrition_ok": True,
                "mental.stress": 2,
                "energy.energy": 6,
                "nutrition.alcohol": True,
                "nutrition.binge": True,
                "body.foot_pain": 10,
                "body.shoulder_pain": 10,
                "relationship.wife_conflict_count": 3,
                "caregiving.homework_done": False,
                "training.primary_activity_type": "crossfit",
            }
        ),
    )

    forbidden = {
        "nutrition.alcohol",
        "nutrition.binge",
        "body.foot_pain",
        "body.shoulder_pain",
        "relationship.wife_conflict_count",
        "caregiving.homework_done",
        "training.primary_activity_type",
    }
    assert forbidden.isdisjoint(snapshot.present_signal_values)
    assert "private_pattern_active" not in snapshot.inputs
    assert "body_signal_high" not in snapshot.inputs
    assert "physical_load_high" not in snapshot.inputs


def test_work_stress_bridge_excludes_relationship_homework_bodypart_fields():
    config = build_selected_profile_config("work_stress")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "core.sleep_ok": True,
                "mental.stress": 4,
                "energy.energy": 6,
                "body.foot_pain": 10,
                "body.shoulder_pain": 10,
                "relationship.wife_conflict_count": 3,
                "caregiving.homework_done": False,
            }
        ),
    )

    assert "body_signal_high" not in snapshot.inputs
    assert "relationship.wife_conflict_count" not in snapshot.present_signal_values
    assert "caregiving.homework_done" not in snapshot.present_signal_values


def test_training_recovery_bridge_excludes_relationship_homework_fields():
    config = build_selected_profile_config("training_recovery")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(
            **{
                "core.sleep_ok": True,
                "core.nutrition_ok": True,
                "mental.stress": 3,
                "energy.energy": 6,
                "training.primary_activity_type": "run",
                "relationship.wife_conflict_count": 3,
                "caregiving.homework_done": False,
            }
        ),
    )

    assert "physical_load_high" in snapshot.inputs
    assert "mental_load_high" not in snapshot.inputs
    assert "relationship.wife_conflict_count" not in snapshot.present_signal_values


def test_body_signal_awareness_bridge_does_not_require_foot_or_shoulder():
    config = build_selected_profile_config("body_signal_awareness")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(**{"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.foot_pain": 10}),
    )

    assert "body.foot_pain" not in snapshot.present_signal_values
    assert "body_signal_high" not in snapshot.inputs
    assert "body.foot_pain" not in snapshot.missing_required_signal_ids
    assert "body.shoulder_pain" not in snapshot.missing_required_signal_ids


def test_custom_signal_entry_bridges_only_when_active():
    config = build_selected_profile_config("custom_stub")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(**{"core.sleep_ok": True, "mental.stress": 8, "energy.energy": 2, "body.foot_pain": 10}),
    )

    assert "mental_load_high" in snapshot.inputs
    assert "energy_low" in snapshot.inputs
    assert "body.foot_pain" not in snapshot.present_signal_values


def test_beta_guidance_uses_production_bridge_when_profile_checkin_enabled():
    day = _day(
        "general_balance",
        {"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 8, "energy.energy": 2},
    )
    output = guidance_for_synthetic_day(day)

    assert output.label == "Simplify"
    assert {"mental_load_high", "energy_low", "active_profile_id"} <= set(output.bridge_inputs)
    assert output.bridge_inputs["active_profile_id"] == "general_balance"


def test_beta_guidance_no_longer_uses_draft_only_bridge_for_general_balance():
    config = build_selected_profile_config("general_balance")
    snapshot = build_guidance_bridge_from_selected_profile_config(
        config,
        _entries(**{"core.sleep_ok": True, "core.nutrition_ok": True, "mental.stress": 8, "energy.energy": 2}),
    )

    assert snapshot.inputs["active_profile_id"].value == "general_balance"
    assert snapshot.inputs["mental_load_high"].source_signal_ids == ("mental.stress",)
    assert snapshot.inputs["energy_low"].source_signal_ids == ("energy.energy",)


def test_see_why_uses_production_bridge_drivers():
    output = guidance_for_synthetic_day(
        _day("training_recovery", {"core.sleep_ok": False, "mental.stress": 3, "energy.energy": 2, "training.activity_duration_min": 60})
    )

    assert "Training load" in output.top_drivers
    assert "physical_load_high" in output.bridge_inputs


def test_flag_off_legacy_guidance_unchanged():
    entry = FIXTURE_ENTRIES["evening_risk_day"]

    assert score_personal_legacy_via_bridge(entry) == scoring.score_entry(entry)


def test_missing_selected_config_uses_documented_default():
    beta_default = build_selected_profile_config("general_balance")
    normal_default = build_selected_profile_config("personal_legacy")

    assert beta_default.active_profile_id == "general_balance"
    assert normal_default.active_profile_id == "personal_legacy"


def test_formula_threshold_hypotheses_remain_gated():
    severe_day = _day("general_balance", {"core.sleep_ok": True, "mental.stress": 9, "energy.energy": 2})
    body_day = _day("body_signal_awareness", {"core.sleep_ok": True, "mental.stress": 4, "energy.energy": 6, "body.migraine_warning": True})

    assert guidance_for_synthetic_day(severe_day).label == "Simplify"
    assert guidance_for_synthetic_day(body_day).label == "Maintain"


def test_experiment_2_report_zip_contains_expected_files(tmp_path):
    zip_path = write_experiment_2_generic_profile_bridge_zip(output_dir=tmp_path, timestamp="experiment-two")

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert {
        "README.md",
        "bridge_migration_summary.json",
        "personal_legacy_parity.json",
        "synthetic_before_after.json",
        "profile_leakage_results.json",
        "sensitive_copy_results.json",
        "missing_data_results.json",
        "runtime_e2e_results.json",
        "known_limitations.json",
        "review_samples.html",
        "per_profile_bridge_results/general_balance.json",
        "per_profile_bridge_results/work_stress.json",
        "per_profile_bridge_results/training_recovery.json",
        "per_profile_bridge_results/body_signal_awareness.json",
        "per_profile_bridge_results/personal_legacy.json",
    }.issubset(names)
