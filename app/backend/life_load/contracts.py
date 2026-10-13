"""Portable Life Load contracts shared by backend, web, and Android clients."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from life_load.scoring import SCORING_CONTRACT, SCORING_CONTRACT_VERSION, SCORING_OUTPUT_KEYS
from life_load.trends import RULES_VERSION as TREND_RULES_VERSION

CONTRACT_SCHEMA_VERSION = "life_load_platform_contract_v1"
CONTRACT_JSON_PATH = Path(__file__).with_name("life_load_contract.json")


def _load_contract_definition() -> Dict[str, Any]:
    try:
        payload = json.loads(CONTRACT_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Life Load contract JSON is missing: {CONTRACT_JSON_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Life Load contract JSON is invalid: {CONTRACT_JSON_PATH}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Life Load contract JSON root must be an object")
    return payload


def _require_mapping(payload: Mapping[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"Life Load contract JSON field {key!r} must be an object")
    return dict(value)


def _require_string_list(payload: Mapping[str, Any], key: str) -> List[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise RuntimeError(f"Life Load contract JSON field {key!r} must be a non-empty string list")
    return list(value)


def _validate_contract_definition(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Life Load contract JSON schema_version must be {CONTRACT_SCHEMA_VERSION!r}, got {payload.get('schema_version')!r}"
        )
    _require_string_list(payload, "entry_fields")
    trend = _require_mapping(payload, "trend")
    feature_fields = _require_string_list(trend, "feature_fields")
    chart = _require_mapping(trend, "chart")
    for required in ("load_field", "load_fallback_field", "capacity_field"):
        if not isinstance(chart.get(required), str) or not chart[required]:
            raise RuntimeError(f"Life Load contract JSON trend.chart.{required} must be a string")
    for required in (chart["load_field"], chart["load_fallback_field"], chart["capacity_field"]):
        if required not in feature_fields:
            raise RuntimeError(f"Life Load contract JSON trend.chart field {required!r} is missing from feature_fields")
    formula = _require_mapping(payload, "formula")
    sections = formula.get("sections")
    if not isinstance(sections, list) or not sections:
        raise RuntimeError("Life Load contract JSON formula.sections must be a non-empty list")
    for index, section in enumerate(sections):
        if not isinstance(section, dict) or not section.get("title") or not isinstance(section.get("items"), list):
            raise RuntimeError(f"Life Load contract JSON formula.sections[{index}] is malformed")
    _require_mapping(payload, "garmin_import")


_CONTRACT_DEFINITION = _load_contract_definition()
_validate_contract_definition(_CONTRACT_DEFINITION)

ENTRY_FIELDS: List[str] = list(_CONTRACT_DEFINITION["entry_fields"])
TREND_FEATURE_FIELDS: List[str] = list(_CONTRACT_DEFINITION["trend"]["feature_fields"])
FORMULA_SECTIONS: List[Dict[str, Any]] = copy.deepcopy(_CONTRACT_DEFINITION["formula"]["sections"])


def contract_payload() -> Dict[str, Any]:
    """Return the portable contract consumed by thin UI clients."""

    payload = copy.deepcopy(_CONTRACT_DEFINITION)
    payload["score"] = {
        **SCORING_CONTRACT,
        "output_keys": list(SCORING_OUTPUT_KEYS),
    }
    payload["trend"]["rules_version"] = TREND_RULES_VERSION
    payload["formula"]["scoring_contract_version"] = SCORING_CONTRACT_VERSION
    return payload
