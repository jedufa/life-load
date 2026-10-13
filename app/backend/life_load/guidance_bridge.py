"""Production guidance bridge for configurable Life Load signals.

The fixed personal_legacy scorer remains unchanged. This bridge projects
selected profile configs and generic signal entries into the same small set of
guidance inputs used by profile-driven beta guidance, while preserving
personal_legacy parity and absent/false/zero distinctions.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from life_load import scoring
from life_load.optional_packs import OPTIONAL_PACK_TEMPLATES
from life_load.profile_templates import PROFILE_TEMPLATE_METADATA, ProfileTemplateMetadata
from life_load.selected_profile_config import SelectedProfileConfig
from life_load.signal_registry import SIGNALS_BY_ID


BRIDGE_INPUT_KEYS = (
    "recovery_low",
    "recovery_good",
    "energy_low",
    "energy_good",
    "mental_load_high",
    "body_signal_high",
    "physical_load_high",
    "life_load_high",
    "evening_boundary_broken",
    "private_pattern_active",
    "protective_behavior_present",
    "data_confidence",
    "missing_required_signal_ids",
    "active_profile_id",
)

BETA_GUIDANCE_LABELS = ("Push", "Maintain", "Recover", "Simplify", "Protect Sleep")
LEGACY_GUIDANCE_LABELS = ("Continue", "Protect", "Hold", "Stabilize")
LOW_RISK_SIGNAL_GROUP_MIGRATION_STATUS = "deferred"


@dataclass(frozen=True)
class GuidanceBridgeInput:
    key: str
    value: Any
    source_signal_ids: tuple[str, ...]
    legacy_field_keys: tuple[str, ...]


@dataclass(frozen=True)
class GuidanceBridgeSnapshot:
    active_profile_id: str
    inputs: Mapping[str, GuidanceBridgeInput]
    present_signal_values: Mapping[str, Any]
    data_confidence: float
    missing_required_signal_ids: tuple[str, ...]
    inert_unknown_signal_ids: tuple[str, ...]
    optional_pack_ids: tuple[str, ...]


@dataclass(frozen=True)
class BetaGuidanceMapping:
    label: str
    confidence: str
    legacy_zone: str
    legacy_next_action: str


def build_guidance_bridge_from_fixed_entry(
    entry: Mapping[str, Any],
    *,
    profile_id: str = "personal_legacy",
    optional_pack_ids: tuple[str, ...] = (),
) -> GuidanceBridgeSnapshot:
    """Build a shadow bridge snapshot from current fixed-entry data."""

    profile = _profile(profile_id)
    _validate_optional_packs(profile, optional_pack_ids)
    active_signal_ids = _active_signal_ids(profile, optional_pack_ids)
    present_signal_values: dict[str, Any] = {}
    for signal_id in active_signal_ids:
        definition = SIGNALS_BY_ID[signal_id]
        legacy_field_key = definition.legacy_field_key
        if legacy_field_key is None or legacy_field_key not in entry:
            continue
        value = entry[legacy_field_key]
        if _is_present(value):
            present_signal_values[signal_id] = value
    return _snapshot_from_present_values(
        profile=profile,
        optional_pack_ids=optional_pack_ids,
        present_signal_values=present_signal_values,
        inert_unknown_signal_ids=(),
    )


def build_guidance_bridge_from_signal_entries(
    signal_entries: Iterable[Mapping[str, Any] | Any],
    *,
    profile_id: str = "personal_legacy",
    optional_pack_ids: tuple[str, ...] = (),
) -> GuidanceBridgeSnapshot:
    """Build a shadow bridge snapshot from generic signal-entry-like records."""

    profile = _profile(profile_id)
    _validate_optional_packs(profile, optional_pack_ids)
    active_signal_ids = set(_active_signal_ids(profile, optional_pack_ids))
    present_signal_values: dict[str, Any] = {}
    inert_unknown_signal_ids: list[str] = []
    for signal_entry in signal_entries:
        signal_id = _entry_attr(signal_entry, "signal_id")
        if not signal_id:
            continue
        if signal_id not in SIGNALS_BY_ID:
            inert_unknown_signal_ids.append(str(signal_id))
            continue
        if signal_id not in active_signal_ids:
            continue
        is_present = _entry_attr(signal_entry, "is_present", True)
        value = _entry_attr(signal_entry, "value")
        if is_present and _is_present(value):
            present_signal_values[str(signal_id)] = value
    return _snapshot_from_present_values(
        profile=profile,
        optional_pack_ids=optional_pack_ids,
        present_signal_values=present_signal_values,
        inert_unknown_signal_ids=tuple(dict.fromkeys(inert_unknown_signal_ids)),
    )


def build_guidance_bridge_from_selected_profile_config(
    selected_profile_config: SelectedProfileConfig | Mapping[str, Any],
    signal_entries: Iterable[Mapping[str, Any] | Any],
) -> GuidanceBridgeSnapshot:
    """Build a production bridge snapshot from selected config + generic entries."""

    config = _selected_config_mapping(selected_profile_config)
    profile_id = str(config.get("active_profile_id") or config.get("activeProfileId") or "personal_legacy")
    profile = _profile(profile_id)
    optional_pack_ids = tuple(str(pack_id) for pack_id in _config_sequence(config, "optional_pack_ids", "optionalPackIds"))
    _validate_optional_packs(profile, optional_pack_ids)

    hidden_or_disabled = set(_config_sequence(config, "hidden_signal_ids", "hiddenSignalIds")) | set(
        _config_sequence(config, "disabled_signal_ids", "disabledSignalIds")
    )
    enabled_signal_ids = tuple(
        dict.fromkeys(
            str(signal_id)
            for signal_id in _config_sequence(config, "enabled_signal_ids", "enabledSignalIds")
            if signal_id in SIGNALS_BY_ID and signal_id not in hidden_or_disabled
        )
    )
    required_for_confidence_signal_ids = tuple(
        dict.fromkeys(
            str(signal_id)
            for signal_id in _config_sequence(
                config,
                "required_for_confidence_signal_ids",
                "requiredForConfidenceSignalIds",
            )
            if signal_id in SIGNALS_BY_ID and signal_id not in hidden_or_disabled
        )
    )

    present_signal_values: dict[str, Any] = {}
    inert_unknown_signal_ids: list[str] = []
    active_signal_ids = set(enabled_signal_ids)
    for signal_entry in signal_entries:
        signal_id = _entry_attr(signal_entry, "signal_id")
        if not signal_id:
            continue
        signal_id = str(signal_id)
        if signal_id not in SIGNALS_BY_ID:
            inert_unknown_signal_ids.append(signal_id)
            continue
        if signal_id not in active_signal_ids:
            continue
        is_present = _entry_attr(signal_entry, "is_present", True)
        value = _entry_attr(signal_entry, "value")
        if is_present and _is_present(value):
            present_signal_values[signal_id] = value

    return _snapshot_from_present_values(
        profile=profile,
        optional_pack_ids=optional_pack_ids,
        present_signal_values=present_signal_values,
        inert_unknown_signal_ids=tuple(dict.fromkeys(inert_unknown_signal_ids)),
        required_for_confidence_signal_ids=required_for_confidence_signal_ids,
    )


def score_personal_legacy_via_bridge(
    entry: Mapping[str, Any],
    *,
    activity_rows: Iterable[Mapping[str, Any]] | None = None,
    garmin_passive: Mapping[str, Any] | None = None,
    prior_training_loads: Iterable[float] | None = None,
    formula_settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Shadow scoring adapter for personal_legacy parity tests.

    The bridge is built first to prove the fixed entry can be represented by
    generic inputs, but current scoring is deliberately delegated to the
    existing fixed-field engine.
    """

    build_guidance_bridge_from_fixed_entry(entry, profile_id="personal_legacy")
    return scoring.score_entry(
        entry,
        activity_rows=tuple(activity_rows or ()),
        garmin_passive=garmin_passive,
        prior_training_loads=tuple(prior_training_loads or ()),
        formula_settings=formula_settings,
    )


def map_score_to_beta_guidance(
    scoring_result: Mapping[str, Any],
    *,
    missing_required_signal_ids: tuple[str, ...] = (),
) -> BetaGuidanceMapping:
    """Map existing scoring output to future beta labels without UI changes."""

    zone = str(scoring_result.get("zone") or "")
    next_action = str(scoring_result.get("next_action") or "")
    warnings = {str(item).lower() for item in scoring_result.get("warnings") or ()}
    red_flags = {str(item).lower() for item in scoring_result.get("red_flags") or ()}
    confidence = "limited" if missing_required_signal_ids else "normal"
    lower_action = next_action.lower()
    if missing_required_signal_ids:
        label = "Simplify"
    elif "sleep" in lower_action or any("sleep" in item for item in warnings | red_flags):
        label = "Protect Sleep"
    elif zone in {"red", "orange"}:
        label = "Recover"
    elif zone == "yellow":
        label = "Simplify"
    elif zone == "green" and not warnings and not red_flags:
        label = "Maintain"
    else:
        label = "Push"
    return BetaGuidanceMapping(
        label=label,
        confidence=confidence,
        legacy_zone=zone,
        legacy_next_action=next_action,
    )


def _snapshot_from_present_values(
    *,
    profile: ProfileTemplateMetadata,
    optional_pack_ids: tuple[str, ...],
    present_signal_values: Mapping[str, Any],
    inert_unknown_signal_ids: tuple[str, ...],
    required_for_confidence_signal_ids: tuple[str, ...] | None = None,
) -> GuidanceBridgeSnapshot:
    inputs = _bridge_inputs(
        present_signal_values=present_signal_values,
        pattern_pack_enabled="pattern_awareness_pack" in optional_pack_ids,
        personal_legacy=profile.id == "personal_legacy",
    )
    required_signal_ids = required_for_confidence_signal_ids or profile.required_for_confidence_signal_ids
    missing_required = tuple(
        signal_id
        for signal_id in required_signal_ids
        if signal_id not in present_signal_values
        and signal_id not in profile.hidden_signal_ids
        and signal_id not in profile.disabled_signal_ids
    )
    required_count = len(
        tuple(
            signal_id
            for signal_id in required_signal_ids
            if signal_id not in profile.hidden_signal_ids and signal_id not in profile.disabled_signal_ids
        )
    )
    confidence = 1.0 if required_count == 0 else round((required_count - len(missing_required)) / required_count, 2)
    snapshot_inputs = dict(inputs)
    snapshot_inputs["data_confidence"] = GuidanceBridgeInput(
        key="data_confidence",
        value=confidence,
        source_signal_ids=required_signal_ids,
        legacy_field_keys=tuple(
            SIGNALS_BY_ID[signal_id].legacy_field_key or ""
            for signal_id in required_signal_ids
            if signal_id in SIGNALS_BY_ID
        ),
    )
    snapshot_inputs["missing_required_signal_ids"] = GuidanceBridgeInput(
        key="missing_required_signal_ids",
        value=missing_required,
        source_signal_ids=missing_required,
        legacy_field_keys=tuple(
            SIGNALS_BY_ID[signal_id].legacy_field_key or ""
            for signal_id in missing_required
            if signal_id in SIGNALS_BY_ID
        ),
    )
    snapshot_inputs["active_profile_id"] = GuidanceBridgeInput(
        key="active_profile_id",
        value=profile.id,
        source_signal_ids=(),
        legacy_field_keys=(),
    )
    return GuidanceBridgeSnapshot(
        active_profile_id=profile.id,
        inputs=MappingProxyType(snapshot_inputs),
        present_signal_values=MappingProxyType(dict(present_signal_values)),
        data_confidence=confidence,
        missing_required_signal_ids=missing_required,
        inert_unknown_signal_ids=inert_unknown_signal_ids,
        optional_pack_ids=optional_pack_ids,
    )


def _bridge_inputs(
    *,
    present_signal_values: Mapping[str, Any],
    pattern_pack_enabled: bool,
    personal_legacy: bool,
) -> dict[str, GuidanceBridgeInput]:
    inputs: dict[str, GuidanceBridgeInput] = {}

    def add(key: str, value: Any, signal_ids: tuple[str, ...]) -> None:
        definitions = tuple(SIGNALS_BY_ID[signal_id] for signal_id in signal_ids if signal_id in SIGNALS_BY_ID)
        existing = inputs.get(key)
        merged_signal_ids = signal_ids
        merged_legacy_keys = tuple(
            definition.legacy_field_key for definition in definitions if definition.legacy_field_key is not None
        )
        if existing is not None:
            merged_signal_ids = tuple(dict.fromkeys(existing.source_signal_ids + signal_ids))
            merged_legacy_keys = tuple(dict.fromkeys(existing.legacy_field_keys + merged_legacy_keys))
        inputs[key] = GuidanceBridgeInput(
            key=key,
            value=value,
            source_signal_ids=merged_signal_ids,
            legacy_field_keys=merged_legacy_keys,
        )

    if present_signal_values.get("core.sleep_ok") is True:
        add("recovery_good", True, ("core.sleep_ok",))
    elif present_signal_values.get("core.sleep_ok") is False:
        add("recovery_low", True, ("core.sleep_ok",))
    if present_signal_values.get("recovery.shutdown_done") is True:
        add("protective_behavior_present", True, ("recovery.shutdown_done",))
        add("recovery_good", True, ("recovery.shutdown_done",))
    elif present_signal_values.get("recovery.shutdown_done") is False:
        add("recovery_low", True, ("recovery.shutdown_done",))
        add("evening_boundary_broken", True, ("recovery.shutdown_done",))
    for signal_id in ("recovery.decompression_done", "recovery.after_work_decompression_done"):
        if present_signal_values.get(signal_id) is True:
            add("protective_behavior_present", True, (signal_id,))
        elif present_signal_values.get(signal_id) is False:
            add("evening_boundary_broken", True, (signal_id,))

    energy = _as_int(present_signal_values.get("energy.energy"))
    if energy is not None and energy <= 3:
        add("energy_low", True, ("energy.energy",))
    elif energy is not None and energy >= 7:
        add("energy_good", True, ("energy.energy",))

    stress = _as_int(present_signal_values.get("mental.stress"))
    family_stress = _as_int(present_signal_values.get("relationship.family_stress"))
    conflict_count = _as_int(present_signal_values.get("relationship.wife_conflict_count"))
    if (
        (stress is not None and stress >= 7)
        or (family_stress is not None and family_stress >= 7)
        or (conflict_count is not None and conflict_count >= 1)
        or present_signal_values.get("relationship.wife_conflict_school") is True
        or present_signal_values.get("relationship.wife_conflict_chores") is True
        or present_signal_values.get("relationship.wife_conflict_other") is True
        or present_signal_values.get("caregiving.homework_done") is False
    ):
        add(
            "mental_load_high",
            True,
            tuple(
                signal_id
                for signal_id in (
                    "mental.stress",
                    "relationship.family_stress",
                    "relationship.wife_conflict_count",
                    "relationship.wife_conflict_school",
                    "relationship.wife_conflict_chores",
                    "relationship.wife_conflict_other",
                    "caregiving.homework_done",
                )
                if signal_id in present_signal_values
            ),
        )

    foot_pain = _as_int(present_signal_values.get("body.foot_pain"))
    shoulder_pain = _as_int(present_signal_values.get("body.shoulder_pain"))
    if (
        (foot_pain is not None and foot_pain >= 5)
        or (shoulder_pain is not None and shoulder_pain >= 5)
        or present_signal_values.get("body.migraine_warning") is True
    ):
        add(
            "body_signal_high",
            True,
            tuple(
                signal_id
                for signal_id in ("body.foot_pain", "body.shoulder_pain", "body.migraine_warning")
                if signal_id in present_signal_values
            ),
        )

    duration = _as_int(present_signal_values.get("training.activity_duration_min"))
    activity_type = str(present_signal_values.get("training.primary_activity_type") or "").strip().lower()
    if activity_type in {"crossfit", "run"} or (duration is not None and duration >= 45):
        add(
            "physical_load_high",
            True,
            tuple(
                signal_id
                for signal_id in ("training.primary_activity_type", "training.activity_duration_min")
                if signal_id in present_signal_values
            ),
        )

    evening_ids = tuple(
        signal_id
        for signal_id in (
            "evening.phone_after_21",
            "work.project_overrun",
            "evening.evening_chain_broken",
        )
        if present_signal_values.get(signal_id) is True
    )
    if evening_ids:
        add("evening_boundary_broken", True, evening_ids)

    pattern_allowed = personal_legacy or pattern_pack_enabled
    pattern_ids = tuple(
        signal_id
        for signal_id in (
            "nutrition.alcohol",
            "nutrition.binge",
            "evening.phone_after_21",
            "work.project_overrun",
            "evening.evening_chain_broken",
        )
        if signal_id in present_signal_values and _pattern_value_active(present_signal_values[signal_id])
    )
    if pattern_allowed and pattern_ids:
        add("private_pattern_active", True, pattern_ids)

    high_risk_keys = {
        "mental_load_high",
        "body_signal_high",
        "physical_load_high",
        "evening_boundary_broken",
        "private_pattern_active",
        "energy_low",
        "recovery_low",
    }
    if len(high_risk_keys.intersection(inputs)) >= 2:
        add(
            "life_load_high",
            True,
            tuple(
                dict.fromkeys(
                    signal_id
                    for key in high_risk_keys.intersection(inputs)
                    for signal_id in inputs[key].source_signal_ids
                )
            ),
        )

    return inputs


def _profile(profile_id: str) -> ProfileTemplateMetadata:
    profile = PROFILE_TEMPLATE_METADATA.get(profile_id)
    if profile is None:
        available = ", ".join(sorted(PROFILE_TEMPLATE_METADATA))
        raise ValueError(f"Unknown Life Load guidance profile {profile_id!r}; available profiles: {available}")
    return profile


def _active_signal_ids(profile: ProfileTemplateMetadata, optional_pack_ids: tuple[str, ...]) -> tuple[str, ...]:
    hidden_or_disabled = set(profile.hidden_signal_ids) | set(profile.disabled_signal_ids)
    signal_ids = list(profile.visible_signal_ids + profile.optional_signal_ids)
    for pack_id in optional_pack_ids:
        signal_ids.extend(OPTIONAL_PACK_TEMPLATES[pack_id].signal_ids)
    return tuple(
        dict.fromkeys(
            signal_id for signal_id in signal_ids if signal_id in SIGNALS_BY_ID and signal_id not in hidden_or_disabled
        )
    )


def _validate_optional_packs(profile: ProfileTemplateMetadata, optional_pack_ids: tuple[str, ...]) -> None:
    unknown = tuple(pack_id for pack_id in optional_pack_ids if pack_id not in OPTIONAL_PACK_TEMPLATES)
    if unknown:
        raise ValueError(f"Unknown optional pack id(s) for profile {profile.id!r}: {', '.join(unknown)}")
    unallowed = tuple(pack_id for pack_id in optional_pack_ids if pack_id not in profile.allowed_optional_pack_ids)
    if unallowed:
        raise ValueError(f"Optional pack id(s) not allowed for profile {profile.id!r}: {', '.join(unallowed)}")


def _entry_attr(signal_entry: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(signal_entry, Mapping):
        return signal_entry.get(key, default)
    return getattr(signal_entry, key, default)


def _selected_config_mapping(config: SelectedProfileConfig | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(config, Mapping):
        return config
    return {
        "active_profile_id": config.active_profile_id,
        "enabled_signal_ids": config.enabled_signal_ids,
        "hidden_signal_ids": config.hidden_signal_ids,
        "disabled_signal_ids": config.disabled_signal_ids,
        "required_for_confidence_signal_ids": config.required_for_confidence_signal_ids,
        "optional_pack_ids": config.optional_pack_ids,
    }


def _config_sequence(config: Mapping[str, Any], snake_key: str, camel_key: str) -> tuple[Any, ...]:
    value = config.get(snake_key)
    if value is None:
        value = config.get(camel_key)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown"}
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return len(value) > 0
    return True


def _as_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _pattern_value_active(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    text = str(value or "").strip().lower()
    return text not in {"", "0", "false", "no", "none", "unknown"}
