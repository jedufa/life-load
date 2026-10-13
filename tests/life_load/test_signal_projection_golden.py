import json
from pathlib import Path

import pytest

from life_load import scoring
from life_load.signal_projection import (
    SignalEntryProjection,
    fixed_entry_to_signal_entries_for_profile,
    signal_entries_to_fixed_entry_for_personal_legacy,
)
from life_load.signal_registry import PROFILE_TEMPLATES, SIGNALS_BY_ID


ROOT = Path(__file__).resolve().parents[2]
SHARED_CONTRACT_PATH = ROOT / "app" / "shared" / "contracts" / "life_load_signal_registry.json"
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


def _contract_signal_ids() -> set[str]:
    payload = json.loads(SHARED_CONTRACT_PATH.read_text(encoding="utf-8"))
    return {signal["id"] for signal in payload["signals"]}


def _expected_profile_values(entry: dict) -> dict:
    profile_signal_ids = set(PROFILE_TEMPLATES["personal_legacy"].signal_ids)
    expected = {}
    for signal_id in profile_signal_ids:
        definition = SIGNALS_BY_ID[signal_id]
        legacy_field_key = definition.legacy_field_key
        if legacy_field_key is None or legacy_field_key not in entry:
            continue
        value = entry[legacy_field_key]
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in {"", "unknown"}:
            continue
        if isinstance(value, (list, tuple, set, frozenset, dict)) and not value:
            continue
        expected[legacy_field_key] = value
    return expected


def _project_fixture(entry: dict) -> tuple[SignalEntryProjection, ...]:
    return fixed_entry_to_signal_entries_for_profile(entry, profile_id="personal_legacy")


@pytest.mark.parametrize("fixture_name,entry", FIXTURE_ENTRIES.items())
def test_golden_fixture_round_trip_preserves_explicit_personal_legacy_values(fixture_name: str, entry: dict):
    projections = _project_fixture(entry)
    reconstructed = signal_entries_to_fixed_entry_for_personal_legacy(projections)

    assert reconstructed == _expected_profile_values(entry), fixture_name


@pytest.mark.parametrize("fixture_name,entry", FIXTURE_ENTRIES.items())
def test_golden_fixture_projected_signals_map_to_registry(fixture_name: str, entry: dict):
    for projection in _project_fixture(entry):
        definition = SIGNALS_BY_ID[projection.signal_id]
        assert definition.legacy_field_key == projection.legacy_field_key, fixture_name
        assert definition.category == projection.category, fixture_name
        assert definition.classification == projection.classification, fixture_name
        assert definition.guidance_bridge_key == projection.guidance_bridge_key, fixture_name
        assert definition.required_for_confidence == projection.required_for_confidence, fixture_name


@pytest.mark.parametrize("fixture_name,entry", FIXTURE_ENTRIES.items())
def test_golden_fixture_projected_signals_map_to_shared_contract(fixture_name: str, entry: dict):
    contract_signal_ids = _contract_signal_ids()

    for projection in _project_fixture(entry):
        assert projection.signal_id in contract_signal_ids, fixture_name


@pytest.mark.parametrize("fixture_name,entry", FIXTURE_ENTRIES.items())
def test_golden_fixture_personal_legacy_projection_uses_profile_signal_ids(fixture_name: str, entry: dict):
    profile_signal_ids = set(PROFILE_TEMPLATES["personal_legacy"].signal_ids)

    for projection in _project_fixture(entry):
        assert projection.signal_id in profile_signal_ids, fixture_name


def test_absent_false_zero_distinction_across_golden_fixtures():
    sparse = signal_entries_to_fixed_entry_for_personal_legacy(_project_fixture(FIXTURE_ENTRIES["sparse_unknown_day"]))
    explicit = signal_entries_to_fixed_entry_for_personal_legacy(
        _project_fixture(FIXTURE_ENTRIES["explicit_false_zero_day"])
    )

    assert "phone_after_21" not in sparse
    assert "project_overrun" not in sparse
    assert "foot_pain" not in sparse
    assert "wife_conflict_count" not in sparse
    assert explicit["phone_after_21"] is False
    assert explicit["project_overrun"] is False
    assert explicit["foot_pain"] == 0
    assert explicit["shoulder_pain"] == 0
    assert explicit["wife_conflict_count"] == 0
    assert explicit["coffee_cups"] == 0


def test_unknown_profile_still_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown Life Load signal profile 'general_balance'"):
        fixed_entry_to_signal_entries_for_profile(FIXTURE_ENTRIES["normal_low_load_day"], "general_balance")


@pytest.mark.parametrize(
    "fixture_name",
    [
        "normal_low_load_day",
        "pain_body_signal_day",
        "evening_risk_day",
        "relationship_homework_day",
        "training_day",
        "nutrition_risk_day",
        "explicit_false_zero_day",
    ],
)
def test_scoring_parity_for_reverse_projected_explicit_personal_legacy_values(fixture_name: str):
    entry = FIXTURE_ENTRIES[fixture_name]
    projections = _project_fixture(entry)
    reconstructed = signal_entries_to_fixed_entry_for_personal_legacy(projections)
    reconstructed_for_scoring = {"date": entry["date"], **reconstructed}

    assert scoring.score_entry(entry) == scoring.score_entry(reconstructed_for_scoring)


def test_scoring_modules_do_not_import_signal_projection():
    for path in SCORING_SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "signal_projection" not in source
        assert "SignalEntryProjection" not in source
