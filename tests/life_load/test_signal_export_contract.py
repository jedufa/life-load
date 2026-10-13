from __future__ import annotations

import json
from pathlib import Path

from life_load.signal_export_contract import (
    DELETE_RESET_FUTURE_CLEAR_REQUIREMENTS,
    FUTURE_EXPORT_SCHEMA_VERSION,
    build_future_export_bundle_fixture,
    extract_signal_sections,
    preserve_unknown_signal_definitions,
    preserve_unknown_signal_entries,
    validate_future_export_bundle_shape,
)


ROOT = Path(__file__).resolve().parents[2]


def test_future_export_bundle_contains_legacy_entries():
    bundle = build_future_export_bundle_fixture()

    assert bundle["version"] == FUTURE_EXPORT_SCHEMA_VERSION
    assert isinstance(bundle["entries"], list)
    assert bundle["entries"]
    assert bundle["contract_notes"]["fixed_entries_are_compatibility_truth"] is True
    assert "sleep_ok" in bundle["entries"][0]


def test_future_export_bundle_contains_profile_sections():
    bundle = build_future_export_bundle_fixture()

    assert bundle["profile_template"]["id"] == "personal_legacy"
    assert bundle["selected_profile_config"]["active_profile_id"] == "personal_legacy"
    assert bundle["selected_profile_config"]["enabled_signal_ids"]


def test_future_export_bundle_contains_signal_sections():
    bundle = build_future_export_bundle_fixture()

    assert bundle["signal_definitions"]
    assert bundle["signal_entries"]
    assert bundle["optional_packs"]
    assert bundle["influence_policies"]
    assert validate_future_export_bundle_shape(bundle).ok is True


def test_future_export_bundle_preserves_unknown_signal_definitions_inertly():
    unknown_definition = {
        "id": "custom.future_signal",
        "label": "Private custom signal label",
        "scale_type": "ordinal_0_10",
        "version": 99,
    }
    bundle = build_future_export_bundle_fixture(signal_definitions=(unknown_definition,))

    validation = validate_future_export_bundle_shape(bundle)
    preserved = preserve_unknown_signal_definitions(bundle)
    sections = extract_signal_sections(bundle)

    assert validation.ok is True
    assert sections["signal_definitions"] == [unknown_definition]
    assert preserved == (
        {
            "import_status": "inert_unknown_signal_definition",
            "applied_to_runtime": False,
            "definition": unknown_definition,
        },
    )


def test_future_export_bundle_preserves_unknown_signal_entries_inertly():
    unknown_entry = {
        "date": "2026-05-17",
        "signal_id": "custom.future_signal",
        "value": 4,
        "is_present": True,
        "source": "future_client",
    }
    bundle = build_future_export_bundle_fixture(signal_entries=(unknown_entry,))

    validation = validate_future_export_bundle_shape(bundle)
    preserved = preserve_unknown_signal_entries(bundle)
    sections = extract_signal_sections(bundle)

    assert validation.ok is True
    assert sections["signal_entries"] == [unknown_entry]
    assert preserved == (
        {
            "import_status": "inert_unknown_signal_entry",
            "applied_to_scoring": False,
            "entry": unknown_entry,
        },
    )


def test_future_export_bundle_distinguishes_absent_false_zero():
    bundle = json.loads(json.dumps(build_future_export_bundle_fixture()))
    signal_values = {entry["signal_id"]: entry["value"] for entry in bundle["signal_entries"]}

    assert signal_values["evening.phone_after_21"] is False
    assert signal_values["body.foot_pain"] == 0
    assert type(signal_values["body.foot_pain"]) is int
    assert "body.shoulder_pain" not in signal_values


def test_selected_profile_config_round_trips_in_fixture():
    bundle = build_future_export_bundle_fixture(profile_id="general_balance")
    reloaded = json.loads(json.dumps(bundle))

    assert reloaded["selected_profile_config"] == bundle["selected_profile_config"]
    assert reloaded["selected_profile_config"]["active_profile_id"] == "general_balance"
    assert reloaded["selected_profile_config"]["optional_pack_ids"] == []


def test_sensitive_labels_not_logged_by_contract_helpers():
    sensitive_label = "Private custom signal label that must stay inside the artifact"
    bundle = build_future_export_bundle_fixture(
        signal_definitions=(
            {
                "id": "custom.private_signal",
                "label": sensitive_label,
                "scale_type": "text",
            },
        )
    )
    malformed = dict(bundle)
    malformed["signal_entries"] = {"bad": "section"}

    validation = validate_future_export_bundle_shape(malformed)

    assert validation.ok is False
    assert sensitive_label not in "\n".join(validation.errors)


def test_current_export_import_behavior_not_changed():
    current_export_import_sources = (
        ROOT / "app" / "backend" / "life_load" / "sqlite_core.py",
        ROOT / "app" / "backend" / "life_load" / "mobile_web.py",
        ROOT / "app" / "backend" / "life_load" / "core_engine.py",
        ROOT / "app" / "backend" / "life_load" / "backend_test_app.py",
    )

    for path in current_export_import_sources:
        source = path.read_text(encoding="utf-8")
        assert "signal_export_contract" not in source
        assert "FUTURE_EXPORT_SCHEMA_VERSION" not in source


