import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from life_load.signal_registry import (
    PERSONAL_LEGACY_PROFILE,
    PROFILE_TEMPLATES,
    SIGNAL_REGISTRY_CONTRACT_SCHEMA_VERSION,
    SIGNAL_DEFINITIONS,
    SIGNALS_BY_ID,
    SIGNALS_BY_LEGACY_FIELD,
    SignalClassification,
    SignalDefinition,
    SignalVisibility,
    signal_registry_contract_json,
    signal_registry_contract_payload,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "app" / "backend" / "life_load" / "life_load_contract.json"
REGISTRY_CONTRACT_PATH = ROOT / "app" / "shared" / "contracts" / "life_load_signal_registry.json"
EXPORTED_SIGNAL_REQUIRED_FIELDS = {
    "id",
    "legacy_field_key",
    "label",
    "category",
    "scale_type",
    "classification",
    "default_visibility",
    "guidance_bridge_key",
    "required_for_confidence",
    "privacy_class",
    "version",
}
EXPORTED_PROFILE_REQUIRED_FIELDS = {
    "id",
    "name",
    "description",
    "visible_signal_ids",
    "optional_signal_ids",
    "hidden_signal_ids",
    "disabled_signal_ids",
    "required_for_confidence_signal_ids",
    "guidance_bridge_policy_id",
    "default_formula_modifier_id",
    "allowed_optional_pack_ids",
    "max_active_signals",
    "placeholder_signal_ids",
    "signal_ids",
    "version",
}
EXPORTED_OPTIONAL_PACK_REQUIRED_FIELDS = {
    "id",
    "name",
    "description",
    "signal_ids",
    "placeholder_signal_ids",
    "default_enabled",
    "sensitive",
    "requires_explicit_opt_in",
    "max_active_signals_added",
    "version",
}
EXPORTED_INFLUENCE_POLICY_REQUIRED_FIELDS = {
    "signal_id",
    "guidance_effect",
    "polarity",
    "user_editable",
    "sensitivity_class",
    "clinical_boundary",
    "minimum_data_required",
    "applies_to_profile_ids",
    "version",
}


def test_registry_has_unique_signal_ids():
    signal_ids = [definition.id for definition in SIGNAL_DEFINITIONS]

    assert len(signal_ids) == len(set(signal_ids))


def test_registry_has_unique_legacy_field_keys():
    legacy_field_keys = [
        definition.legacy_field_key
        for definition in SIGNAL_DEFINITIONS
        if definition.legacy_field_key is not None
    ]

    assert len(legacy_field_keys) == len(set(legacy_field_keys))


def test_every_contract_entry_field_is_classified():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    entry_fields = set(contract["entry_fields"])
    classified_fields = set(SIGNALS_BY_LEGACY_FIELD)

    assert sorted(entry_fields - classified_fields) == []


def test_personal_legacy_profile_references_existing_signal_ids():
    profile = PROFILE_TEMPLATES["personal_legacy"]

    assert profile == PERSONAL_LEGACY_PROFILE
    assert set(profile.signal_ids) <= set(SIGNALS_BY_ID)


def test_personal_legacy_profile_covers_existing_behavior_fields():
    required_legacy_fields = {
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
    profile_legacy_fields = {
        SIGNALS_BY_ID[signal_id].legacy_field_key
        for signal_id in PERSONAL_LEGACY_PROFILE.signal_ids
    }

    assert required_legacy_fields <= profile_legacy_fields


def test_hidden_or_legacy_only_fields_are_not_treated_as_false():
    hidden_or_legacy_only = [
        definition
        for definition in SIGNAL_DEFINITIONS
        if definition.default_visibility
        in (SignalVisibility.HIDDEN, SignalVisibility.LEGACY_ONLY)
    ]

    assert hidden_or_legacy_only
    assert any(
        definition.default_visibility == SignalVisibility.LEGACY_ONLY
        for definition in hidden_or_legacy_only
    )
    assert all(not definition.required_for_confidence for definition in hidden_or_legacy_only)
    assert all(not hasattr(definition, "default_value") for definition in hidden_or_legacy_only)


def test_registry_is_read_only():
    first = SIGNAL_DEFINITIONS[0]

    assert isinstance(first, SignalDefinition)
    with pytest.raises(AttributeError):
        SIGNAL_DEFINITIONS.append(first)  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        SIGNALS_BY_ID["test.mutable"] = first  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        first.label = "Mutable"  # type: ignore[misc]


def test_registry_classifies_every_field_with_allowed_bucket():
    allowed = {
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalClassification.DERIVED_FIELD,
        SignalClassification.METADATA,
        SignalClassification.LEGACY_ONLY_COMPATIBILITY,
    }

    assert {definition.classification for definition in SIGNAL_DEFINITIONS} <= allowed


def test_registry_contract_export_is_deterministic():
    first_payload = signal_registry_contract_payload()
    second_payload = signal_registry_contract_payload()
    first_json = signal_registry_contract_json()
    second_json = signal_registry_contract_json()

    assert first_payload == second_payload
    assert first_json == second_json
    assert first_json.endswith("\n")
    assert [signal["id"] for signal in first_payload["signals"]] == sorted(
        signal["id"] for signal in first_payload["signals"]
    )
    assert [profile["id"] for profile in first_payload["profiles"]] == sorted(
        profile["id"] for profile in first_payload["profiles"]
    )
    assert [pack["id"] for pack in first_payload["optional_packs"]] == sorted(
        pack["id"] for pack in first_payload["optional_packs"]
    )
    assert [policy["signal_id"] for policy in first_payload["influence_policies"]] == sorted(
        policy["signal_id"] for policy in first_payload["influence_policies"]
    )
    assert first_payload["schema_version"] == SIGNAL_REGISTRY_CONTRACT_SCHEMA_VERSION
    assert first_payload["generated_from"] == "backend.life_load.signal_registry"


def test_registry_contract_snapshot_matches_backend_export():
    assert REGISTRY_CONTRACT_PATH.read_text(encoding="utf-8") == signal_registry_contract_json()


def test_exported_signal_ids_exist_in_backend_registry():
    payload = signal_registry_contract_payload()

    assert {signal["id"] for signal in payload["signals"]} == set(SIGNALS_BY_ID)


def test_exported_profile_signal_ids_exist():
    payload = signal_registry_contract_payload()
    exported_signal_ids = {signal["id"] for signal in payload["signals"]}

    for profile in payload["profiles"]:
        assert set(profile["signal_ids"]) <= exported_signal_ids


def test_exported_json_has_expected_required_fields():
    payload = json.loads(signal_registry_contract_json())

    assert set(payload) == {
        "schema_version",
        "generated_from",
        "signals",
        "profiles",
        "optional_packs",
        "influence_policies",
    }
    assert payload["schema_version"] == SIGNAL_REGISTRY_CONTRACT_SCHEMA_VERSION
    assert payload["signals"]
    assert payload["profiles"]
    assert payload["optional_packs"]
    assert payload["influence_policies"]
    assert all(set(signal) == EXPORTED_SIGNAL_REQUIRED_FIELDS for signal in payload["signals"])
    assert all(set(profile) == EXPORTED_PROFILE_REQUIRED_FIELDS for profile in payload["profiles"])
    assert all(set(pack) == EXPORTED_OPTIONAL_PACK_REQUIRED_FIELDS for pack in payload["optional_packs"])
    assert all(
        set(policy) == EXPORTED_INFLUENCE_POLICY_REQUIRED_FIELDS
        for policy in payload["influence_policies"]
    )
