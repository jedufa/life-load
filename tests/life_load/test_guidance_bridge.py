from pathlib import Path

from life_load import scoring
from life_load.guidance_bridge import (
    BETA_GUIDANCE_LABELS,
    LEGACY_GUIDANCE_LABELS,
    LOW_RISK_SIGNAL_GROUP_MIGRATION_STATUS,
    build_guidance_bridge_from_fixed_entry,
    build_guidance_bridge_from_signal_entries,
    map_score_to_beta_guidance,
    score_personal_legacy_via_bridge,
)


ROOT = Path(__file__).resolve().parents[2]
SCORING_SOURCE_PATHS = (
    ROOT / "app" / "backend" / "life_load" / "core_engine.py",
    ROOT / "app" / "backend" / "life_load" / "scoring.py",
)


FIXTURE_ENTRIES = {
    "normal_low_load_day": {
        "date": "2026-05-04",
        "sleep_ok": True,
        "nutrition_ok": True,
        "stress": 2,
        "energy": 7,
        "mood": 7,
        "shutdown_done": True,
        "decompression_done": True,
    },
    "pain_body_signal_day": {
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
        "wife_conflict_other": False,
        "family_stress": 6,
        "alone_home": True,
        "homework_done": False,
        "homework_status": "missed",
        "stress": 6,
        "energy": 4,
    },
    "training_day": {
        "date": "2026-05-08",
        "primary_activity_type": "crossfit",
        "activity_duration_min": 45,
        "activity_types": ["crossfit"],
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
    "sparse_unknown_day": {
        "date": "2026-05-10",
        "source": "fixture",
    },
    "explicit_false_zero_day": {
        "date": "2026-05-11",
        "phone_after_21": False,
        "project_overrun": False,
        "foot_pain": 0,
        "shoulder_pain": 0,
        "wife_conflict_count": 0,
        "coffee_cups": 0,
        "binge": False,
        "alone_home": False,
    },
}


GENERAL_EXCLUDED_FIELDS = {
    "body.foot_pain",
    "body.shoulder_pain",
    "relationship.wife_conflict_count",
    "relationship.wife_conflict_school",
    "relationship.wife_conflict_chores",
    "relationship.wife_conflict_other",
    "caregiving.homework_done",
    "caregiving.homework_status",
    "nutrition.alcohol",
    "nutrition.binge",
    "training.primary_activity_type",
}


def test_bridge_builds_from_personal_legacy_fixed_entry():
    snapshot = build_guidance_bridge_from_fixed_entry(FIXTURE_ENTRIES["evening_risk_day"])

    assert snapshot.active_profile_id == "personal_legacy"
    assert snapshot.inputs["recovery_low"].value is True
    assert snapshot.inputs["energy_low"].value is True
    assert snapshot.inputs["mental_load_high"].value is True
    assert snapshot.inputs["evening_boundary_broken"].value is True
    assert snapshot.inputs["life_load_high"].value is True


def test_bridge_preserves_absent_false_zero_distinctions():
    sparse = build_guidance_bridge_from_fixed_entry(FIXTURE_ENTRIES["sparse_unknown_day"])
    explicit = build_guidance_bridge_from_fixed_entry(FIXTURE_ENTRIES["explicit_false_zero_day"])

    assert "evening.phone_after_21" not in sparse.present_signal_values
    assert "body.foot_pain" not in sparse.present_signal_values
    assert explicit.present_signal_values["evening.phone_after_21"] is False
    assert explicit.present_signal_values["work.project_overrun"] is False
    assert explicit.present_signal_values["body.foot_pain"] == 0
    assert explicit.present_signal_values["body.shoulder_pain"] == 0
    assert "evening_boundary_broken" not in explicit.inputs
    assert "body_signal_high" not in explicit.inputs


def test_hidden_disabled_signals_do_not_create_false_bridge_inputs():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-12",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 4,
            "energy": 6,
            "foot_pain": 9,
            "shoulder_pain": 8,
            "wife_conflict_count": 2,
            "homework_done": False,
            "primary_activity_type": "crossfit",
        },
        profile_id="body_signal_awareness",
    )

    assert "body.foot_pain" not in snapshot.present_signal_values
    assert "body.shoulder_pain" not in snapshot.present_signal_values
    assert "relationship.wife_conflict_count" not in snapshot.present_signal_values
    assert "caregiving.homework_done" not in snapshot.present_signal_values
    assert "body_signal_high" not in snapshot.inputs
    assert "physical_load_high" not in snapshot.inputs


def test_general_profile_excluded_fields_are_not_bridge_inputs():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-13",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 2,
            "energy": 6,
            "foot_pain": 10,
            "shoulder_pain": 10,
            "wife_conflict_count": 3,
            "wife_conflict_school": True,
            "homework_done": False,
            "alcohol": True,
            "binge": True,
            "primary_activity_type": "crossfit",
        },
        profile_id="general_balance",
    )

    assert GENERAL_EXCLUDED_FIELDS.isdisjoint(snapshot.present_signal_values)
    assert "body_signal_high" not in snapshot.inputs
    assert "private_pattern_active" not in snapshot.inputs
    assert "physical_load_high" not in snapshot.inputs
    assert "mental_load_high" not in snapshot.inputs


def test_unknown_signal_entries_are_inert():
    snapshot = build_guidance_bridge_from_signal_entries(
        (
            {"signal_id": "custom.future_signal", "value": 9, "is_present": True},
            {"signal_id": "energy.energy", "value": 2, "is_present": True},
        ),
        profile_id="general_balance",
    )

    assert snapshot.inert_unknown_signal_ids == ("custom.future_signal",)
    assert snapshot.inputs["energy_low"].value is True
    assert "custom.future_signal" not in snapshot.present_signal_values


def test_personal_legacy_bridge_scoring_matches_current_for_golden_fixtures():
    for fixture_name, entry in FIXTURE_ENTRIES.items():
        assert score_personal_legacy_via_bridge(entry) == scoring.score_entry(entry), fixture_name


def test_red_yellow_protective_flags_match_current_scoring():
    entry = FIXTURE_ENTRIES["evening_risk_day"]
    bridge_result = score_personal_legacy_via_bridge(entry)
    current_result = scoring.score_entry(entry)

    assert bridge_result["zone"] == current_result["zone"]
    assert bridge_result["red_flags"] == current_result["red_flags"]
    assert bridge_result["warnings"] == current_result["warnings"]
    assert bridge_result["next_action"] == current_result["next_action"]


def test_low_risk_signal_group_migration_deferred_for_block_6():
    assert LOW_RISK_SIGNAL_GROUP_MIGRATION_STATUS == "deferred"


def test_old_scoring_and_bridge_scoring_remain_identical_for_personal_legacy():
    entry = {
        **FIXTURE_ENTRIES["normal_low_load_day"],
        "coffee_cups": 3,
        "shutdown_done": False,
        "decompression_done": False,
    }

    assert score_personal_legacy_via_bridge(entry) == scoring.score_entry(entry)


def test_general_balance_does_not_score_excluded_personal_fields():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-14",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 1,
            "energy": 7,
            "foot_pain": 10,
            "shoulder_pain": 10,
            "wife_conflict_count": 4,
            "homework_done": False,
            "alcohol": True,
            "binge": True,
            "primary_activity_type": "crossfit",
        },
        profile_id="general_balance",
    )

    assert snapshot.data_confidence == 1.0
    assert "body_signal_high" not in snapshot.inputs
    assert "private_pattern_active" not in snapshot.inputs
    assert "physical_load_high" not in snapshot.inputs
    assert "mental_load_high" not in snapshot.inputs


def test_work_stress_does_not_score_relationship_homework_body_part_pain_by_default():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-15",
            "sleep_ok": True,
            "stress": 4,
            "energy": 6,
            "foot_pain": 10,
            "shoulder_pain": 10,
            "wife_conflict_count": 3,
            "homework_done": False,
        },
        profile_id="work_stress",
    )

    assert "body_signal_high" not in snapshot.inputs
    assert "mental_load_high" not in snapshot.inputs


def test_training_recovery_does_not_score_relationship_homework_by_default():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-16",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 3,
            "energy": 6,
            "primary_activity_type": "run",
            "wife_conflict_count": 3,
            "homework_done": False,
        },
        profile_id="training_recovery",
    )

    assert "physical_load_high" in snapshot.inputs
    assert "mental_load_high" not in snapshot.inputs
    assert "relationship.wife_conflict_count" not in snapshot.present_signal_values
    assert "caregiving.homework_done" not in snapshot.present_signal_values


def test_body_signal_awareness_does_not_require_foot_or_shoulder():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-17",
            "sleep_ok": True,
            "stress": 4,
            "energy": 6,
            "foot_pain": 10,
            "shoulder_pain": 10,
        },
        profile_id="body_signal_awareness",
    )

    assert "body.foot_pain" not in snapshot.present_signal_values
    assert "body.shoulder_pain" not in snapshot.present_signal_values
    assert "body_signal_high" not in snapshot.inputs
    assert "body.foot_pain" not in snapshot.missing_required_signal_ids
    assert "body.shoulder_pain" not in snapshot.missing_required_signal_ids


def test_pattern_awareness_pack_does_not_influence_bridge_unless_enabled():
    entry = {
        "date": "2026-05-18",
        "sleep_ok": True,
        "nutrition_ok": True,
        "stress": 3,
        "energy": 6,
        "phone_after_21": True,
    }
    without_pack = build_guidance_bridge_from_fixed_entry(entry, profile_id="general_balance")
    with_pack = build_guidance_bridge_from_fixed_entry(
        entry,
        profile_id="general_balance",
        optional_pack_ids=("pattern_awareness_pack",),
    )

    assert "private_pattern_active" not in without_pack.inputs
    assert "evening.phone_after_21" not in without_pack.present_signal_values
    assert with_pack.inputs["private_pattern_active"].value is True
    assert with_pack.present_signal_values["evening.phone_after_21"] is True


def test_hidden_disabled_fields_are_not_treated_as_false():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {
            "date": "2026-05-19",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 3,
            "energy": 7,
        },
        profile_id="general_balance",
    )

    assert snapshot.data_confidence == 1.0
    assert snapshot.missing_required_signal_ids == ()
    assert "recovery_low" not in snapshot.inputs
    assert "body_signal_high" not in snapshot.inputs


def test_missing_excluded_fields_do_not_reduce_confidence():
    snapshot = build_guidance_bridge_from_fixed_entry(
        {"date": "2026-05-20", "sleep_ok": True, "nutrition_ok": True, "stress": 2, "energy": 7},
        profile_id="general_balance",
    )

    assert snapshot.data_confidence == 1.0
    assert snapshot.missing_required_signal_ids == ()


def test_beta_guidance_labels_are_available():
    assert set(BETA_GUIDANCE_LABELS) == {"Push", "Maintain", "Recover", "Simplify", "Protect Sleep"}


def test_legacy_labels_remain_compatible():
    assert {"Continue", "Protect", "Hold", "Stabilize"} <= set(LEGACY_GUIDANCE_LABELS)


def test_guidance_mapping_does_not_change_current_ui_output():
    current_result = scoring.score_entry(FIXTURE_ENTRIES["evening_risk_day"])
    mapping = map_score_to_beta_guidance(current_result)

    assert mapping.label in BETA_GUIDANCE_LABELS
    assert mapping.legacy_next_action == current_result["next_action"]
    assert scoring.score_entry(FIXTURE_ENTRIES["evening_risk_day"])["next_action"] == current_result["next_action"]


def test_missing_data_can_map_to_limited_confidence():
    current_result = scoring.score_entry(FIXTURE_ENTRIES["sparse_unknown_day"])
    mapping = map_score_to_beta_guidance(
        current_result,
        missing_required_signal_ids=("core.sleep_ok", "mental.stress"),
    )

    assert mapping.label == "Simplify"
    assert mapping.confidence == "limited"


def test_scoring_modules_do_not_import_guidance_bridge():
    for path in SCORING_SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "guidance_bridge" not in source
        assert "GuidanceBridgeSnapshot" not in source
