from copy import deepcopy

import pytest

from life_load.signal_projection import (
    SignalEntryProjection,
    fixed_entry_to_signal_entries,
    fixed_entry_to_signal_entries_for_profile,
    signal_entries_to_fixed_entry_for_personal_legacy,
)
from life_load.signal_registry import PROFILE_TEMPLATES, SIGNALS_BY_ID, SignalCategory, SignalClassification


def _by_legacy_field(projections: tuple[SignalEntryProjection, ...]) -> dict[str, SignalEntryProjection]:
    return {projection.legacy_field_key: projection for projection in projections}


def test_fixed_entry_to_signal_entries_projects_known_values():
    entry = {
        "sleep_ok": True,
        "energy": 7,
        "stress": 4,
        "foot_pain": 2,
        "alcohol": "none",
        "phone_after_21": True,
        "project_overrun": False,
    }

    projections = _by_legacy_field(fixed_entry_to_signal_entries(entry))

    assert projections["sleep_ok"].signal_id == "core.sleep_ok"
    assert projections["sleep_ok"].value is True
    assert projections["energy"].signal_id == "energy.energy"
    assert projections["energy"].value == 7
    assert projections["stress"].signal_id == "mental.stress"
    assert projections["stress"].value == 4
    assert projections["foot_pain"].signal_id == "body.foot_pain"
    assert projections["foot_pain"].value == 2
    assert projections["alcohol"].signal_id == "nutrition.alcohol"
    assert projections["alcohol"].value == "none"
    assert projections["phone_after_21"].signal_id == "evening.phone_after_21"
    assert projections["phone_after_21"].value is True
    assert projections["project_overrun"].signal_id == "work.project_overrun"
    assert projections["project_overrun"].value is False
    assert projections["foot_pain"].source == "fixed_entry"
    assert projections["foot_pain"].is_present is True
    assert projections["foot_pain"].classification == SignalClassification.CONFIGURABLE_SIGNAL
    assert projections["foot_pain"].category == SignalCategory.BODY_SIGNAL
    assert projections["foot_pain"].guidance_bridge_key == "body_pain"
    assert projections["foot_pain"].required_for_confidence is True


def test_projection_omits_absent_values_without_false_defaults():
    entry = {
        "sleep_ok": True,
        "foot_pain": None,
        "project_overrun": None,
        "primary_activity_type": "",
    }

    projections = _by_legacy_field(fixed_entry_to_signal_entries(entry))

    assert "sleep_ok" in projections
    assert "foot_pain" not in projections
    assert "shoulder_pain" not in projections
    assert "phone_after_21" not in projections
    assert "project_overrun" not in projections
    assert "primary_activity_type" not in projections


def test_false_boolean_is_preserved_when_explicit():
    entry = {"phone_after_21": False, "project_overrun": False}

    projections = _by_legacy_field(fixed_entry_to_signal_entries(entry))

    assert projections["phone_after_21"].value is False
    assert projections["project_overrun"].value is False


def test_zero_numeric_is_preserved_when_explicit():
    entry = {"foot_pain": 0, "shoulder_pain": 0}

    projections = _by_legacy_field(fixed_entry_to_signal_entries(entry))

    assert projections["foot_pain"].value == 0
    assert projections["shoulder_pain"].value == 0


def test_personal_legacy_profile_projection_only_uses_profile_signal_ids():
    entry = {
        "date": "2026-05-17",
        "diary_text": "kept the day boring",
        "sleep_ok": True,
        "foot_pain": 1,
    }
    profile_signal_ids = set(PROFILE_TEMPLATES["personal_legacy"].signal_ids)

    projections = fixed_entry_to_signal_entries_for_profile(entry)

    assert {projection.signal_id for projection in projections} <= profile_signal_ids
    assert {projection.legacy_field_key for projection in projections} == {"sleep_ok", "foot_pain"}


def test_unknown_profile_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown Life Load signal profile 'general_balance'"):
        fixed_entry_to_signal_entries_for_profile({}, profile_id="general_balance")


def test_reverse_projection_personal_legacy_round_trip():
    entry = {
        "sleep_ok": True,
        "nutrition_ok": False,
        "foot_pain": 0,
        "phone_after_21": False,
        "project_overrun": True,
        "homework_status": "na",
        "shoulder_pain": None,
    }

    projections = fixed_entry_to_signal_entries_for_profile(entry)
    fixed_entry = signal_entries_to_fixed_entry_for_personal_legacy(projections)

    assert fixed_entry == {
        "sleep_ok": True,
        "nutrition_ok": False,
        "foot_pain": 0,
        "phone_after_21": False,
        "project_overrun": True,
        "homework_status": "na",
    }
    assert "shoulder_pain" not in fixed_entry


def test_projection_does_not_mutate_input():
    entry = {
        "sleep_ok": True,
        "activity_types": ["walk", "rehab"],
        "foot_pain": None,
    }
    original = deepcopy(entry)

    fixed_entry_to_signal_entries(entry)

    assert entry == original


def test_projection_covers_required_personal_behavior_fields():
    required_values = {
        "foot_pain": 3,
        "shoulder_pain": 1,
        "migraine_warning": True,
        "alcohol": "none",
        "binge": False,
        "phone_after_21": False,
        "project_overrun": True,
        "primary_activity_type": "crossfit",
        "wife_conflict_count": 2,
        "wife_conflict_school": True,
        "wife_conflict_chores": False,
        "wife_conflict_other": True,
        "alone_home": False,
        "homework_done": True,
        "homework_status": "done",
    }

    projections = _by_legacy_field(fixed_entry_to_signal_entries_for_profile(required_values))

    assert set(required_values) <= set(projections)
    for legacy_field_key, expected_value in required_values.items():
        projection = projections[legacy_field_key]
        assert projection.value == expected_value
        assert projection.signal_id in SIGNALS_BY_ID
        assert SIGNALS_BY_ID[projection.signal_id].legacy_field_key == legacy_field_key
