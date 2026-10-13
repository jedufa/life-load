"""Future configurable-signal export contract fixtures.

This module defines a pure, additive future bundle shape for configurable Life
Load signals. It is not wired into current production export/import behavior,
storage, scoring, extraction, HTTP payloads, Android, or UI.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping

from life_load.optional_packs import OPTIONAL_PACK_TEMPLATES, SIGNAL_INFLUENCE_POLICIES
from life_load.profile_templates import PROFILE_TEMPLATE_METADATA
from life_load.selected_profile_config import SelectedProfileConfig, build_selected_profile_config
from life_load.signal_registry import SIGNALS_BY_ID


FUTURE_EXPORT_SCHEMA_VERSION = "life_load_export_v_next"

FUTURE_EXPORT_REQUIRED_TOP_LEVEL_KEYS = (
    "version",
    "entries",
    "profile_template",
    "selected_profile_config",
    "signal_definitions",
    "signal_entries",
    "optional_packs",
    "influence_policies",
    "contract_notes",
)

DELETE_RESET_FUTURE_CLEAR_REQUIREMENTS = (
    "selected_profile_config",
    "signal_definitions",
    "signal_entries",
    "optional_pack_selections",
    "influence_overrides",
)


@dataclass(frozen=True)
class FutureExportValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_future_export_bundle_fixture(
    *,
    entries: tuple[Mapping[str, Any], ...] | None = None,
    profile_id: str = "personal_legacy",
    selected_profile_config: SelectedProfileConfig | Mapping[str, Any] | None = None,
    signal_definitions: tuple[Mapping[str, Any], ...] | None = None,
    signal_entries: tuple[Mapping[str, Any], ...] | None = None,
    optional_packs: tuple[Mapping[str, Any], ...] | None = None,
    influence_policies: tuple[Mapping[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Build a deterministic fixture for the future additive export shape."""

    template = PROFILE_TEMPLATE_METADATA[profile_id]
    selected_config = selected_profile_config or build_selected_profile_config(profile_id)

    return {
        "version": FUTURE_EXPORT_SCHEMA_VERSION,
        "entries": [deepcopy(dict(entry)) for entry in (entries or _default_fixed_entries())],
        "profile_template": _profile_template_record(profile_id),
        "selected_profile_config": _selected_profile_config_record(selected_config),
        "signal_definitions": [
            deepcopy(dict(definition))
            for definition in (signal_definitions or _default_signal_definitions(template.signal_ids))
        ],
        "signal_entries": [
            deepcopy(dict(entry))
            for entry in (signal_entries or _default_signal_entries())
        ],
        "optional_packs": [
            deepcopy(dict(pack))
            for pack in (optional_packs or _default_optional_pack_records(template.allowed_optional_pack_ids))
        ],
        "influence_policies": [
            deepcopy(dict(policy))
            for policy in (influence_policies or _default_influence_policy_records(template.signal_ids))
        ],
        "contract_notes": {
            "fixed_entries_are_compatibility_truth": True,
            "signal_sections_are_additive_future_data": True,
            "unknown_signal_definitions_import_mode": "preserve_inert",
            "unknown_signal_entries_import_mode": "preserve_inert",
            "recognized_signal_entries_do_not_affect_scoring_until_bridge_enabled": True,
            "delete_reset_must_clear": list(DELETE_RESET_FUTURE_CLEAR_REQUIREMENTS),
            "sensitive_labels_must_not_be_logged": True,
        },
    }


def validate_future_export_bundle_shape(bundle: Mapping[str, Any]) -> FutureExportValidationResult:
    """Validate only the future bundle envelope shape.

    Validation deliberately reports section paths and types, not user-provided
    labels or values.
    """

    errors: list[str] = []
    if bundle.get("version") != FUTURE_EXPORT_SCHEMA_VERSION:
        errors.append("version: unsupported future export schema")

    for key in FUTURE_EXPORT_REQUIRED_TOP_LEVEL_KEYS:
        if key not in bundle:
            errors.append(f"{key}: missing required section")

    _require_list(bundle, "entries", errors)
    _require_mapping(bundle, "profile_template", errors)
    _require_mapping(bundle, "selected_profile_config", errors)
    _require_list(bundle, "signal_definitions", errors)
    _require_list(bundle, "signal_entries", errors)
    _require_list(bundle, "optional_packs", errors)
    _require_list(bundle, "influence_policies", errors)
    _require_mapping(bundle, "contract_notes", errors)

    return FutureExportValidationResult(ok=not errors, errors=tuple(errors))


def extract_signal_sections(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return deep-copied future signal sections without applying them."""

    return {
        "profile_template": deepcopy(bundle.get("profile_template", {})),
        "selected_profile_config": deepcopy(bundle.get("selected_profile_config", {})),
        "signal_definitions": deepcopy(list(bundle.get("signal_definitions", ()))),
        "signal_entries": deepcopy(list(bundle.get("signal_entries", ()))),
        "optional_packs": deepcopy(list(bundle.get("optional_packs", ()))),
        "influence_policies": deepcopy(list(bundle.get("influence_policies", ()))),
    }


def preserve_unknown_signal_definitions(bundle: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return unknown signal definitions as inert import records."""

    unknown_records: list[dict[str, Any]] = []
    for definition in bundle.get("signal_definitions", ()):
        if not isinstance(definition, Mapping):
            continue
        signal_id = definition.get("id")
        if isinstance(signal_id, str) and signal_id not in SIGNALS_BY_ID:
            unknown_records.append(
                {
                    "import_status": "inert_unknown_signal_definition",
                    "applied_to_runtime": False,
                    "definition": deepcopy(dict(definition)),
                }
            )
    return tuple(unknown_records)


def preserve_unknown_signal_entries(bundle: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return unknown signal entries as inert import records."""

    unknown_records: list[dict[str, Any]] = []
    for signal_entry in bundle.get("signal_entries", ()):
        if not isinstance(signal_entry, Mapping):
            continue
        signal_id = signal_entry.get("signal_id")
        if isinstance(signal_id, str) and signal_id not in SIGNALS_BY_ID:
            unknown_records.append(
                {
                    "import_status": "inert_unknown_signal_entry",
                    "applied_to_scoring": False,
                    "entry": deepcopy(dict(signal_entry)),
                }
            )
    return tuple(unknown_records)


def _default_fixed_entries() -> tuple[Mapping[str, Any], ...]:
    return (
        {
            "date": "2026-05-17",
            "source": "phase_5a_contract_fixture",
            "sleep_ok": True,
            "energy": 7,
            "stress": 3,
            "phone_after_21": False,
            "foot_pain": 0,
        },
    )


def _default_signal_definitions(signal_ids: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {
            "id": signal_id,
            "legacy_field_key": SIGNALS_BY_ID[signal_id].legacy_field_key,
            "label": SIGNALS_BY_ID[signal_id].label,
            "category": SIGNALS_BY_ID[signal_id].category.value,
            "scale_type": SIGNALS_BY_ID[signal_id].scale_type.value,
            "classification": SIGNALS_BY_ID[signal_id].classification.value,
            "version": SIGNALS_BY_ID[signal_id].version,
        }
        for signal_id in sorted(signal_ids)
        if signal_id in SIGNALS_BY_ID
    )


def _default_signal_entries() -> tuple[Mapping[str, Any], ...]:
    return (
        {
            "date": "2026-05-17",
            "signal_id": "core.sleep_ok",
            "value": True,
            "is_present": True,
            "source": "fixed_entry_projection",
        },
        {
            "date": "2026-05-17",
            "signal_id": "evening.phone_after_21",
            "value": False,
            "is_present": True,
            "source": "fixed_entry_projection",
        },
        {
            "date": "2026-05-17",
            "signal_id": "body.foot_pain",
            "value": 0,
            "is_present": True,
            "source": "fixed_entry_projection",
        },
    )


def _profile_template_record(profile_id: str) -> dict[str, Any]:
    template = PROFILE_TEMPLATE_METADATA[profile_id]
    return {
        "id": template.id,
        "name": template.name,
        "version": template.version,
        "signal_ids": list(template.signal_ids),
        "visible_signal_ids": list(template.visible_signal_ids),
        "optional_signal_ids": list(template.optional_signal_ids),
        "hidden_signal_ids": list(template.hidden_signal_ids),
        "disabled_signal_ids": list(template.disabled_signal_ids),
        "required_for_confidence_signal_ids": list(template.required_for_confidence_signal_ids),
        "allowed_optional_pack_ids": list(template.allowed_optional_pack_ids),
    }


def _selected_profile_config_record(config: SelectedProfileConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config, SelectedProfileConfig):
        record = asdict(config)
    else:
        record = dict(config)
    return json.loads(json.dumps(record))


def _default_optional_pack_records(pack_ids: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    records: list[Mapping[str, Any]] = []
    for pack_id in sorted(pack_ids):
        pack = OPTIONAL_PACK_TEMPLATES.get(pack_id)
        if pack is None:
            continue
        records.append(
            {
                "id": pack.id,
                "name": pack.name,
                "signal_ids": list(pack.signal_ids),
                "placeholder_signal_ids": list(pack.placeholder_signal_ids),
                "default_enabled": pack.default_enabled,
                "sensitive": pack.sensitive,
                "requires_explicit_opt_in": pack.requires_explicit_opt_in,
                "version": pack.version,
            }
        )
    return tuple(records)


def _default_influence_policy_records(signal_ids: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    signal_id_set = set(signal_ids)
    return tuple(
        {
            "signal_id": policy.signal_id,
            "guidance_effect": policy.guidance_effect.value,
            "polarity": policy.polarity.value,
            "sensitivity_class": policy.sensitivity_class.value,
            "clinical_boundary": policy.clinical_boundary.value,
            "applied_to_scoring": False,
            "version": policy.version,
        }
        for policy in sorted(SIGNAL_INFLUENCE_POLICIES.values(), key=lambda item: item.signal_id)
        if policy.signal_id in signal_id_set
    )


def _require_list(bundle: Mapping[str, Any], key: str, errors: list[str]) -> None:
    if key in bundle and not isinstance(bundle[key], list):
        errors.append(f"{key}: expected list section")


def _require_mapping(bundle: Mapping[str, Any], key: str, errors: list[str]) -> None:
    if key in bundle and not isinstance(bundle[key], Mapping):
        errors.append(f"{key}: expected object section")


__all__ = [
    "DELETE_RESET_FUTURE_CLEAR_REQUIREMENTS",
    "FUTURE_EXPORT_SCHEMA_VERSION",
    "FutureExportValidationResult",
    "build_future_export_bundle_fixture",
    "extract_signal_sections",
    "preserve_unknown_signal_definitions",
    "preserve_unknown_signal_entries",
    "validate_future_export_bundle_shape",
]
