from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from life_load.profile_templates import PROFILE_TEMPLATE_METADATA
from life_load.selected_profile_config import SelectedProfileConfig, build_selected_profile_config
from life_load.signal_registry import SIGNALS_BY_ID


ROOT = Path(__file__).resolve().parents[2]
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

GENERAL_BALANCE_PERSONAL_FIELDS = {
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


def _enabled_or_required_legacy_keys(config: SelectedProfileConfig) -> set[str]:
    return _legacy_keys(config.enabled_signal_ids + config.required_for_confidence_signal_ids)


def test_build_selected_profile_config_for_each_profile():
    for profile_id, template in PROFILE_TEMPLATE_METADATA.items():
        config = build_selected_profile_config(profile_id)

        assert config.active_profile_id == profile_id
        assert config.template_version == template.version
        assert config.guidance_bridge_policy_id == template.guidance_bridge_policy_id
        assert config.default_formula_modifier_id == template.default_formula_modifier_id
        assert config.max_active_signals == template.max_active_signals


def test_unknown_profile_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown Life Load profile template 'not_a_profile'"):
        build_selected_profile_config("not_a_profile")


def test_selected_config_signal_ids_exist_or_are_documented_placeholders():
    for profile_id, template in PROFILE_TEMPLATE_METADATA.items():
        config = build_selected_profile_config(profile_id)
        placeholder_ids = set(template.placeholder_signal_ids)
        all_signal_ids = (
            config.enabled_signal_ids
            + config.optional_signal_ids
            + config.hidden_signal_ids
            + config.disabled_signal_ids
            + config.required_for_confidence_signal_ids
            + config.user_added_signal_ids
        )

        for signal_id in all_signal_ids:
            assert signal_id in SIGNALS_BY_ID or signal_id in placeholder_ids


def test_selected_config_is_immutable():
    config = build_selected_profile_config("general_balance")

    with pytest.raises(FrozenInstanceError):
        config.active_profile_id = "mutated"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        config.enabled_signal_ids.append("core.sleep_ok")  # type: ignore[attr-defined]


def test_personal_legacy_selected_config_preserves_behavior_fields():
    config = build_selected_profile_config("personal_legacy")

    assert PERSONAL_BEHAVIOR_FIELDS <= _legacy_keys(config.enabled_signal_ids + config.optional_signal_ids)


def test_general_balance_selected_config_does_not_enable_personal_fields():
    config = build_selected_profile_config("general_balance")

    assert GENERAL_BALANCE_PERSONAL_FIELDS.isdisjoint(_enabled_or_required_legacy_keys(config))


def test_work_stress_selected_config_excludes_relationship_homework_body_part_pain():
    config = build_selected_profile_config("work_stress")

    assert (RELATIONSHIP_HOMEWORK_FIELDS | {"foot_pain", "shoulder_pain"}).isdisjoint(
        _enabled_or_required_legacy_keys(config)
    )


def test_training_recovery_selected_config_excludes_relationship_homework():
    config = build_selected_profile_config("training_recovery")

    assert RELATIONSHIP_HOMEWORK_FIELDS.isdisjoint(_enabled_or_required_legacy_keys(config))


def test_body_signal_awareness_selected_config_does_not_require_specific_body_parts():
    config = build_selected_profile_config("body_signal_awareness")
    required_legacy_keys = _legacy_keys(config.required_for_confidence_signal_ids)
    enabled_legacy_keys = _legacy_keys(config.enabled_signal_ids)

    assert {"foot_pain", "shoulder_pain"}.isdisjoint(required_legacy_keys)
    assert {"foot_pain", "shoulder_pain"}.isdisjoint(enabled_legacy_keys)
    assert "body.foot_pain" in config.hidden_signal_ids
    assert "body.shoulder_pain" in config.hidden_signal_ids


def test_hidden_disabled_not_required_for_confidence():
    for profile_id in PROFILE_TEMPLATE_METADATA:
        config = build_selected_profile_config(profile_id)
        hidden_or_disabled = set(config.hidden_signal_ids) | set(config.disabled_signal_ids)

        assert hidden_or_disabled.isdisjoint(config.required_for_confidence_signal_ids), profile_id


def test_optional_pack_validation_rejects_unallowed_pack():
    with pytest.raises(ValueError, match="Optional pack id\\(s\\) not allowed for profile 'custom_stub'"):
        build_selected_profile_config("custom_stub", optional_pack_ids=("life_load_pack",))


def test_allowed_optional_pack_is_recorded_and_adds_pack_signals_to_bridge_config():
    baseline = build_selected_profile_config("general_balance")
    with_pack = build_selected_profile_config("general_balance", optional_pack_ids=("life_load_pack",))

    assert with_pack.optional_pack_ids == ("life_load_pack",)
    assert set(baseline.enabled_signal_ids).issubset(with_pack.enabled_signal_ids)
    assert {"work.work_intensity", "work.project_overrun", "work.home_office", "relationship.family_stress"} <= set(
        with_pack.enabled_signal_ids
    )
    assert with_pack.required_for_confidence_signal_ids == baseline.required_for_confidence_signal_ids
    assert with_pack.hidden_signal_ids == baseline.hidden_signal_ids
    assert with_pack.disabled_signal_ids == baseline.disabled_signal_ids


def test_user_added_placeholder_signal_is_recorded_without_runtime_effect():
    config = build_selected_profile_config(
        "body_signal_awareness",
        user_added_signal_ids=("placeholder.body_signal_instance",),
    )

    assert config.user_added_signal_ids == ("placeholder.body_signal_instance",)
    assert "placeholder.body_signal_instance" in config.enabled_signal_ids


def test_unknown_user_added_signal_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown user-added signal id\\(s\\) for profile 'body_signal_awareness'"):
        build_selected_profile_config("body_signal_awareness", user_added_signal_ids=("custom.body_left_knee",))


def test_selected_profile_config_not_consumed_by_scoring():
    for path in SCORING_SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "selected_profile_config" not in source
        assert "SelectedProfileConfig" not in source
