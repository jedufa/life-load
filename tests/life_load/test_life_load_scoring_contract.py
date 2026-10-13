from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from life_load import scoring
from life_load.contracts import CONTRACT_JSON_PATH, contract_payload
from life_load.settings import SETTINGS_SCHEMA


GOLDEN_PATH = Path(__file__).resolve().parents[2] / "app/backend/life_load/scoring_golden_cases.json"


def _load_golden_cases() -> Mapping[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_scoring_contract_metadata_is_stable_for_porting() -> None:
    payload = _load_golden_cases()

    assert payload["scoring_contract_version"] == scoring.SCORING_CONTRACT_VERSION
    assert tuple(scoring.SCORING_INPUT_KEYS) == ("entry", "activity_rows", "garmin_passive", "prior_training_loads")
    assert "life_load_score" in scoring.SCORING_OUTPUT_KEYS
    assert "training_load_ratio" in scoring.SCORING_OUTPUT_KEYS


def test_scoring_golden_cases_match_python_engine() -> None:
    payload = _load_golden_cases()
    output_keys = set(scoring.SCORING_OUTPUT_KEYS) - {"date"}

    for case in payload["cases"]:
        input_payload = case["input"]
        result = scoring.score_entry(
            input_payload["entry"],
            activity_rows=input_payload.get("activity_rows") or [],
            garmin_passive=input_payload.get("garmin_passive"),
            prior_training_loads=input_payload.get("prior_training_loads") or [],
        )
        comparable = {key: result[key] for key in output_keys}
        assert comparable == case["expected"], case["name"]


def test_scoring_golden_cases_are_portable_json() -> None:
    payload = _load_golden_cases()
    seen_names: set[str] = set()

    assert len(payload["cases"]) >= 10
    for case in payload["cases"]:
        assert case["name"] not in seen_names
        seen_names.add(case["name"])
        assert set(case["input"]) == set(scoring.SCORING_INPUT_KEYS)
        assert set(case["expected"]) == set(scoring.SCORING_OUTPUT_KEYS) - {"date"}
        json.dumps(case, sort_keys=True)


def test_scoring_golden_cases_cover_truth_boundaries() -> None:
    payload = _load_golden_cases()
    cases = {case["name"]: case for case in payload["cases"]}

    unknown = cases["unknown_structured_data_is_not_false"]["expected"]
    assert unknown["zone"] == "yellow"
    assert unknown["warnings"] == ["missing structured data"]
    assert set(unknown["unknown_fields"]) == {"sleep_ok", "nutrition_ok", "stress", "energy", "shutdown_done"}
    assert "sleep drift" not in unknown["warnings"]

    explicit_false = cases["explicit_false_evening_drift_is_real_signal"]["expected"]
    assert explicit_false["zone"] == "red"
    assert explicit_false["unknown_fields"] == []
    assert "sleep drift" in explicit_false["warnings"]
    assert "shutdown missed" in explicit_false["warnings"]

    no_alcohol = cases["no_alcohol_note_keeps_alcohol_false"]["expected"]
    assert no_alcohol["red_flags"] == []
    assert "alcohol" not in no_alcohol["warnings"]
    assert no_alcohol["zone"] == "green"


def test_scoring_golden_next_actions_stay_concrete() -> None:
    payload = _load_golden_cases()
    vague_phrases = {
        "be mindful",
        "do better",
        "listen to your body",
        "optimize",
        "try harder",
    }
    concrete_anchors = {
        "add them",
        "avoid",
        "decompress",
        "hold progression",
        "no ambitious decisions",
        "no extra training",
        "protect sleep",
        "protect tonight",
        "recovery-first",
        "stabilization",
    }

    for case in payload["cases"]:
        expected = case["expected"]
        action = expected["next_action"].strip()
        assert action
        assert len(action) <= 160
        assert not any(phrase in action.lower() for phrase in vague_phrases), case["name"]
        if expected["zone"] != "green":
            assert any(anchor in action.lower() for anchor in concrete_anchors), case["name"]


def test_scoring_reasons_and_warnings_stay_short_and_non_punitive() -> None:
    payload = _load_golden_cases()
    banned_fragments = {
        "compensat",
        "punish",
        "ruined",
        "try harder",
        "willpower",
    }
    signal_lists = ("warnings", "red_flags", "unknown_fields")

    for case in payload["cases"]:
        expected = case["expected"]
        for key in signal_lists:
            for item in expected[key]:
                text = str(item).strip()
                lowered = text.lower()
                assert text, f"{case['name']} {key}"
                assert len(text) <= 64, f"{case['name']} {key}: {text}"
                assert not any(fragment in lowered for fragment in banned_fragments), f"{case['name']} {key}: {text}"


def test_visible_formula_contract_matches_scoring_constants() -> None:
    payload = contract_payload()
    formula_text = json.dumps(payload["formula"]["sections"], sort_keys=True)

    assert "Run" in formula_text and "2.0 per 30 min, cap 8.0" in formula_text
    assert scoring.activity_training_points({"activity_type": "run", "duration_min": 30}) == 2.0
    assert scoring.activity_training_points({"activity_type": "run", "duration_min": 300}) == 8.0

    assert "Bike commute" in formula_text and "0.55 per 30 min, cap 4.0" in formula_text
    assert scoring.activity_training_points({"activity_type": "bike_commute", "duration_min": 30}) == 0.55
    assert scoring.activity_training_points({"activity_type": "bike_commute", "duration_min": 300}) == 4.0

    assert "Stress" in formula_text and "+0.7 per point" in formula_text
    no_stress = scoring.score_entry({"date": "2026-05-04", "stress": 0})
    high_stress = scoring.score_entry({"date": "2026-05-04", "stress": 10})
    assert round(high_stress["strain_score"] - no_stress["strain_score"], 2) == 7.0

    assert "Sleep on time" in formula_text and "+2" in formula_text
    sleep_unknown = scoring.score_entry({"date": "2026-05-04", "sleep_ok": None})
    sleep_ok = scoring.score_entry({"date": "2026-05-04", "sleep_ok": True})
    assert round(sleep_ok["recovery_score"] - sleep_unknown["recovery_score"], 2) == 2.0


def test_formula_contract_documents_every_runtime_formula_toggle() -> None:
    payload = contract_payload()
    formula_items = {
        str(item.get("input"))
        for section in payload["formula"]["sections"]
        for item in section.get("items", [])
    }
    formula_section = next(section for section in SETTINGS_SCHEMA["sections"] if section["key"] == "formula")
    toggle_keys = {
        field["key"]
        for field in formula_section["fields"]
        if field["type"] == "boolean"
    }

    assert toggle_keys <= formula_items


def test_platform_contract_covers_portable_ui_and_trend_boundaries() -> None:
    payload = contract_payload()

    assert payload["schema_version"] == "life_load_platform_contract_v1"
    assert payload["score"]["version"] == scoring.SCORING_CONTRACT_VERSION
    assert set(payload["score"]["output_keys"]) == set(scoring.SCORING_OUTPUT_KEYS)
    assert "after_work_decompression_done" in payload["entry_fields"]
    assert "wife_conflict_count" in payload["entry_fields"]
    assert "alone_home" in payload["entry_fields"]
    assert "activity_types" in payload["entry_fields"]
    assert "acute_load_7d" in payload["trend"]["feature_fields"]
    assert "chronic_capacity_42d" in payload["trend"]["feature_fields"]
    assert "project_overrun_weighted_7d" in payload["trend"]["feature_fields"]
    assert "phone_after_21_recent_count_3d" in payload["trend"]["feature_fields"]
    assert "phone_after_21_trend" in payload["trend"]["feature_fields"]
    assert payload["trend"]["chart"] == {
        "window_days": 14,
        "load_field": "acute_load_7d",
        "load_fallback_field": "life_load_rolling_avg_7d",
        "capacity_field": "chronic_capacity_42d",
        "shared_zero_based_y_axis": True,
        "minimum_y_max": 10,
    }
    assert any(section["title"] == "Strain Points" for section in payload["formula"]["sections"])
    assert payload["garmin_import"]["automatic_refresh"]["freshness_minutes"] == 180


def test_platform_contract_is_backed_by_json_definition() -> None:
    raw = json.loads(CONTRACT_JSON_PATH.read_text(encoding="utf-8"))
    payload = contract_payload()

    assert raw["schema_version"] == "life_load_platform_contract_v1"
    assert raw["entry_fields"] == payload["entry_fields"]
    assert raw["trend"]["feature_fields"] == payload["trend"]["feature_fields"]
    assert raw["trend"]["chart"] == payload["trend"]["chart"]
    assert raw["formula"]["sections"] == payload["formula"]["sections"]
