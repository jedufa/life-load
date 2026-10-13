import json
from pathlib import Path

from life_load.profile_templates import OPTIONAL_PACK_IDS, PROFILE_TEMPLATE_METADATA
from life_load.signal_registry import SIGNALS_BY_ID, signal_registry_contract_payload


ROOT = Path(__file__).resolve().parents[2]
SHARED_CONTRACT_PATH = ROOT / "app" / "shared" / "contracts" / "life_load_signal_registry.json"
SCORING_SOURCE_PATHS = (
    ROOT / "app" / "backend" / "life_load" / "core_engine.py",
    ROOT / "app" / "backend" / "life_load" / "scoring.py",
)


PERSONAL_BEHAVIOR_FIELDS = {
    "foot_pain",
    "shoulder_pain",
    "migraine_warning",
    "alcohol",
    "binge",
    "phone_after_21",
    "project_overrun",
    "primary_activity_type",
    "wife_conflict_count",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
    "alone_home",
    "homework_done",
    "homework_status",
}

GENERAL_BALANCE_EXCLUDED_VISIBLE_REQUIRED = {
    "foot_pain",
    "shoulder_pain",
    "wife_conflict_count",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
    "homework_done",
    "homework_status",
    "alcohol",
    "binge",
    "primary_activity_type",
}

RELATIONSHIP_HOMEWORK_FIELDS = {
    "wife_conflict_count",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
    "homework_done",
    "homework_status",
}


def _legacy_keys(signal_ids: tuple[str, ...]) -> set[str]:
    return {
        SIGNALS_BY_ID[signal_id].legacy_field_key
        for signal_id in signal_ids
        if signal_id in SIGNALS_BY_ID and SIGNALS_BY_ID[signal_id].legacy_field_key is not None
    }


def _visible_or_required_legacy_keys(profile_id: str) -> set[str]:
    profile = PROFILE_TEMPLATE_METADATA[profile_id]
    return _legacy_keys(profile.visible_signal_ids + profile.required_for_confidence_signal_ids)


def test_profile_template_ids_unique():
    profile_ids = [profile.id for profile in PROFILE_TEMPLATE_METADATA.values()]

    assert len(profile_ids) == len(set(profile_ids))


def test_profile_template_signal_ids_exist_or_are_documented_placeholders():
    for profile in PROFILE_TEMPLATE_METADATA.values():
        for signal_id in profile.signal_ids:
            assert signal_id in SIGNALS_BY_ID
        for placeholder in profile.placeholders:
            assert placeholder.id.startswith("placeholder.")
            assert placeholder.id not in SIGNALS_BY_ID
            assert placeholder.label
            assert placeholder.reason
        assert set(profile.allowed_optional_pack_ids) <= set(OPTIONAL_PACK_IDS)


def test_personal_legacy_includes_current_behavior_fields():
    profile = PROFILE_TEMPLATE_METADATA["personal_legacy"]

    assert PERSONAL_BEHAVIOR_FIELDS <= _legacy_keys(profile.signal_ids)


def test_general_balance_excludes_personal_fields():
    visible_or_required = _visible_or_required_legacy_keys("general_balance")

    assert GENERAL_BALANCE_EXCLUDED_VISIBLE_REQUIRED.isdisjoint(visible_or_required)


def test_work_stress_excludes_relationship_homework_and_body_part_pain_by_default():
    visible_or_required = _visible_or_required_legacy_keys("work_stress")

    assert (RELATIONSHIP_HOMEWORK_FIELDS | {"foot_pain", "shoulder_pain"}).isdisjoint(visible_or_required)


def test_training_recovery_excludes_relationship_homework_by_default():
    visible_or_required = _visible_or_required_legacy_keys("training_recovery")

    assert RELATIONSHIP_HOMEWORK_FIELDS.isdisjoint(visible_or_required)


def test_body_signal_awareness_does_not_require_specific_body_parts():
    profile = PROFILE_TEMPLATE_METADATA["body_signal_awareness"]
    required_legacy_keys = _legacy_keys(profile.required_for_confidence_signal_ids)

    assert {"foot_pain", "shoulder_pain"}.isdisjoint(required_legacy_keys)
    assert "body.foot_pain" not in profile.visible_signal_ids
    assert "body.shoulder_pain" not in profile.visible_signal_ids
    assert "body.foot_pain" in profile.hidden_signal_ids
    assert "body.shoulder_pain" in profile.hidden_signal_ids


def test_hidden_and_disabled_are_not_required_for_confidence():
    for profile in PROFILE_TEMPLATE_METADATA.values():
        hidden_or_disabled = set(profile.hidden_signal_ids) | set(profile.disabled_signal_ids)
        required = set(profile.required_for_confidence_signal_ids)

        assert hidden_or_disabled.isdisjoint(required), profile.id


def test_max_active_signals_reasonable_for_beta_profiles():
    for profile_id in ("general_balance", "work_stress", "training_recovery", "body_signal_awareness"):
        assert PROFILE_TEMPLATE_METADATA[profile_id].max_active_signals <= 8


def test_profile_metadata_not_consumed_by_scoring():
    for path in SCORING_SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "profile_templates" not in source
        assert "ProfileTemplateMetadata" not in source


def test_registry_contract_export_includes_profile_templates():
    payload = signal_registry_contract_payload()
    exported_profiles = {profile["id"]: profile for profile in payload["profiles"]}
    snapshot = json.loads(SHARED_CONTRACT_PATH.read_text(encoding="utf-8"))
    snapshot_profiles = {profile["id"]: profile for profile in snapshot["profiles"]}

    assert set(exported_profiles) == set(PROFILE_TEMPLATE_METADATA)
    assert set(snapshot_profiles) == set(PROFILE_TEMPLATE_METADATA)
    for profile_id, profile in PROFILE_TEMPLATE_METADATA.items():
        exported = exported_profiles[profile_id]
        assert exported["visible_signal_ids"] == sorted(profile.visible_signal_ids)
        assert exported["optional_signal_ids"] == sorted(profile.optional_signal_ids)
        assert exported["hidden_signal_ids"] == sorted(profile.hidden_signal_ids)
        assert exported["disabled_signal_ids"] == sorted(profile.disabled_signal_ids)
        assert exported["required_for_confidence_signal_ids"] == sorted(profile.required_for_confidence_signal_ids)
        assert exported["placeholder_signal_ids"] == sorted(profile.placeholder_signal_ids)
