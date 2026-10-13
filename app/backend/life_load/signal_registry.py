"""Read-only metadata for current fixed Life Load entry fields.

This registry is intentionally passive. It classifies existing backend contract
fields for future configurable-signal work without changing storage, scoring,
extraction, serialization, or UI behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


SIGNAL_REGISTRY_CONTRACT_SCHEMA_VERSION = "life_load_signal_registry_contract_v1"
SIGNAL_REGISTRY_CONTRACT_SOURCE = "backend.life_load.signal_registry"


class SignalClassification(str, Enum):
    CONFIGURABLE_SIGNAL = "configurable_signal"
    DERIVED_FIELD = "derived_field"
    METADATA = "metadata"
    LEGACY_ONLY_COMPATIBILITY = "legacy_only_compatibility"


class SignalCategory(str, Enum):
    CORE_RECOVERY = "core_recovery"
    ENERGY_MOOD = "energy_mood"
    MENTAL_LOAD = "mental_load"
    BODY_SIGNAL = "body_signal"
    TRAINING_LOAD = "training_load"
    EVENING_BOUNDARY = "evening_boundary"
    WORK_LOAD = "work_load"
    RELATIONSHIP_CONTEXT = "relationship_context"
    CAREGIVING_CONTEXT = "caregiving_context"
    NUTRITION_RISK = "nutrition_risk"
    PASSIVE_HEALTH = "passive_health"
    METADATA = "metadata"
    DERIVED = "derived"


class SignalScaleType(str, Enum):
    BOOLEAN = "boolean"
    TERNARY = "ternary"
    ORDINAL_0_10 = "ordinal_0_10"
    BOUNDED_INT = "bounded_int"
    ENUM = "enum"
    DURATION_MINUTES = "duration_minutes"
    TEXT = "text"
    DERIVED = "derived"


class SignalVisibility(str, Enum):
    VISIBLE = "visible"
    OPTIONAL = "optional"
    HIDDEN = "hidden"
    LEGACY_ONLY = "legacy_only"


class SignalPrivacyClass(str, Enum):
    LOCAL_ONLY = "local_only"
    EXPORTABLE = "exportable"
    SENSITIVE_LABEL = "sensitive_label"


@dataclass(frozen=True)
class SignalDefinition:
    id: str
    legacy_field_key: str | None
    label: str
    category: SignalCategory
    scale_type: SignalScaleType
    classification: SignalClassification
    default_visibility: SignalVisibility
    guidance_bridge_key: str | None
    required_for_confidence: bool
    privacy_class: SignalPrivacyClass
    version: int = 1


@dataclass(frozen=True)
class ProfileTemplate:
    id: str
    label: str
    signal_ids: tuple[str, ...]
    version: int = 1


def _signal(
    id: str,
    legacy_field_key: str | None,
    label: str,
    category: SignalCategory,
    scale_type: SignalScaleType,
    classification: SignalClassification,
    default_visibility: SignalVisibility,
    guidance_bridge_key: str | None = None,
    required_for_confidence: bool = False,
    privacy_class: SignalPrivacyClass = SignalPrivacyClass.EXPORTABLE,
) -> SignalDefinition:
    return SignalDefinition(
        id=id,
        legacy_field_key=legacy_field_key,
        label=label,
        category=category,
        scale_type=scale_type,
        classification=classification,
        default_visibility=default_visibility,
        guidance_bridge_key=guidance_bridge_key,
        required_for_confidence=required_for_confidence,
        privacy_class=privacy_class,
    )


SIGNAL_DEFINITIONS: tuple[SignalDefinition, ...] = (
    _signal(
        "metadata.date",
        "date",
        "Entry date",
        SignalCategory.METADATA,
        SignalScaleType.TEXT,
        SignalClassification.METADATA,
        SignalVisibility.HIDDEN,
        privacy_class=SignalPrivacyClass.LOCAL_ONLY,
    ),
    _signal(
        "metadata.diary_text",
        "diary_text",
        "Diary text",
        SignalCategory.METADATA,
        SignalScaleType.TEXT,
        SignalClassification.METADATA,
        SignalVisibility.OPTIONAL,
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "metadata.diary_summary",
        "diary_summary",
        "Diary summary",
        SignalCategory.METADATA,
        SignalScaleType.TEXT,
        SignalClassification.METADATA,
        SignalVisibility.HIDDEN,
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "metadata.tags",
        "tags",
        "Tags",
        SignalCategory.METADATA,
        SignalScaleType.TEXT,
        SignalClassification.METADATA,
        SignalVisibility.OPTIONAL,
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "core.sleep_ok",
        "sleep_ok",
        "Sleep on time",
        SignalCategory.CORE_RECOVERY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="sleep_recovery",
        required_for_confidence=True,
    ),
    _signal(
        "core.nutrition_ok",
        "nutrition_ok",
        "Nutrition clean",
        SignalCategory.CORE_RECOVERY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="nutrition_recovery",
        required_for_confidence=True,
    ),
    _signal(
        "nutrition.alcohol",
        "alcohol",
        "Alcohol",
        SignalCategory.NUTRITION_RISK,
        SignalScaleType.ENUM,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="alcohol_exposure",
        required_for_confidence=True,
    ),
    _signal(
        "nutrition.binge",
        "binge",
        "Eating episode",
        SignalCategory.NUTRITION_RISK,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="food_risk",
        required_for_confidence=True,
    ),
    _signal(
        "mood.mood",
        "mood",
        "Mood",
        SignalCategory.ENERGY_MOOD,
        SignalScaleType.ORDINAL_0_10,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="mood_recovery",
    ),
    _signal(
        "mental.stress",
        "stress",
        "Stress",
        SignalCategory.MENTAL_LOAD,
        SignalScaleType.ORDINAL_0_10,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="stress_load",
        required_for_confidence=True,
    ),
    _signal(
        "energy.energy",
        "energy",
        "Energy",
        SignalCategory.ENERGY_MOOD,
        SignalScaleType.ORDINAL_0_10,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="energy_recovery",
        required_for_confidence=True,
    ),
    _signal(
        "stimulant.coffee_cups",
        "coffee_cups",
        "Coffee cups",
        SignalCategory.NUTRITION_RISK,
        SignalScaleType.BOUNDED_INT,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.OPTIONAL,
        guidance_bridge_key="stimulant_context",
    ),
    _signal(
        "body.foot_pain",
        "foot_pain",
        "Foot pain",
        SignalCategory.BODY_SIGNAL,
        SignalScaleType.ORDINAL_0_10,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="body_pain",
        required_for_confidence=True,
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "body.shoulder_pain",
        "shoulder_pain",
        "Shoulder pain",
        SignalCategory.BODY_SIGNAL,
        SignalScaleType.ORDINAL_0_10,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="body_pain",
        required_for_confidence=True,
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "body.migraine_warning",
        "migraine_warning",
        "Migraine warning",
        SignalCategory.BODY_SIGNAL,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="body_warning",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "recovery.decompression_done",
        "decompression_done",
        "Decompression done",
        SignalCategory.CORE_RECOVERY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="decompression_recovery",
    ),
    _signal(
        "recovery.after_work_decompression_done",
        "after_work_decompression_done",
        "After-work decompression",
        SignalCategory.CORE_RECOVERY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="after_work_decompression",
    ),
    _signal(
        "evening.evening_chain_broken",
        "evening_chain_broken",
        "Evening chain broken",
        SignalCategory.EVENING_BOUNDARY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="evening_sequence",
    ),
    _signal(
        "recovery.shutdown_done",
        "shutdown_done",
        "Shutdown done",
        SignalCategory.CORE_RECOVERY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="shutdown_recovery",
    ),
    _signal(
        "evening.phone_after_21",
        "phone_after_21",
        "Phone after 21:00",
        SignalCategory.EVENING_BOUNDARY,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="late_phone",
    ),
    _signal(
        "work.project_overrun",
        "project_overrun",
        "Project overrun",
        SignalCategory.WORK_LOAD,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="project_spillover",
    ),
    _signal(
        "training.primary_activity_type",
        "primary_activity_type",
        "Primary activity type",
        SignalCategory.TRAINING_LOAD,
        SignalScaleType.ENUM,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="training_activity",
        required_for_confidence=True,
    ),
    _signal(
        "training.activity_types",
        "activity_types",
        "Activity types",
        SignalCategory.TRAINING_LOAD,
        SignalScaleType.ENUM,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.OPTIONAL,
        guidance_bridge_key="training_activity",
    ),
    _signal(
        "training.activity_duration_min",
        "activity_duration_min",
        "Activity duration minutes",
        SignalCategory.TRAINING_LOAD,
        SignalScaleType.DURATION_MINUTES,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="training_duration",
    ),
    _signal(
        "training.rehab_done",
        "rehab_done",
        "Rehab done",
        SignalCategory.TRAINING_LOAD,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.OPTIONAL,
        guidance_bridge_key="training_rehab",
    ),
    _signal(
        "body.other_symptoms",
        "other_symptoms",
        "Other symptoms",
        SignalCategory.BODY_SIGNAL,
        SignalScaleType.TEXT,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.HIDDEN,
        guidance_bridge_key="body_context",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "work.work_intensity",
        "work_intensity",
        "Work intensity",
        SignalCategory.WORK_LOAD,
        SignalScaleType.ENUM,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="work_intensity",
    ),
    _signal(
        "relationship.family_stress",
        "family_stress",
        "Family stress",
        SignalCategory.RELATIONSHIP_CONTEXT,
        SignalScaleType.ORDINAL_0_10,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="relationship_context",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "relationship.wife_conflict_count",
        "wife_conflict_count",
        "Relationship conflict count",
        SignalCategory.RELATIONSHIP_CONTEXT,
        SignalScaleType.BOUNDED_INT,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="relationship_conflict",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "relationship.wife_conflict_school",
        "wife_conflict_school",
        "School conflict",
        SignalCategory.RELATIONSHIP_CONTEXT,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="relationship_conflict_detail",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "relationship.wife_conflict_chores",
        "wife_conflict_chores",
        "Chores conflict",
        SignalCategory.RELATIONSHIP_CONTEXT,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="relationship_conflict_detail",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "relationship.wife_conflict_other",
        "wife_conflict_other",
        "Other relationship conflict",
        SignalCategory.RELATIONSHIP_CONTEXT,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="relationship_conflict_detail",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "work.home_office",
        "home_office",
        "Home office",
        SignalCategory.WORK_LOAD,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.OPTIONAL,
        guidance_bridge_key="home_office_context",
    ),
    _signal(
        "caregiving.alone_home",
        "alone_home",
        "Alone home",
        SignalCategory.CAREGIVING_CONTEXT,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="alone_home_context",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "caregiving.homework_done",
        "homework_done",
        "Homework done",
        SignalCategory.CAREGIVING_CONTEXT,
        SignalScaleType.BOOLEAN,
        SignalClassification.CONFIGURABLE_SIGNAL,
        SignalVisibility.VISIBLE,
        guidance_bridge_key="homework_context",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
    _signal(
        "caregiving.homework_status",
        "homework_status",
        "Homework status",
        SignalCategory.CAREGIVING_CONTEXT,
        SignalScaleType.ENUM,
        SignalClassification.LEGACY_ONLY_COMPATIBILITY,
        SignalVisibility.LEGACY_ONLY,
        guidance_bridge_key="homework_context",
        privacy_class=SignalPrivacyClass.SENSITIVE_LABEL,
    ),
)


SIGNALS_BY_ID: Mapping[str, SignalDefinition] = MappingProxyType(
    {definition.id: definition for definition in SIGNAL_DEFINITIONS}
)

SIGNALS_BY_LEGACY_FIELD: Mapping[str, SignalDefinition] = MappingProxyType(
    {
        definition.legacy_field_key: definition
        for definition in SIGNAL_DEFINITIONS
        if definition.legacy_field_key is not None
    }
)

PERSONAL_LEGACY_PROFILE = ProfileTemplate(
    id="personal_legacy",
    label="Personal legacy",
    signal_ids=tuple(
        definition.id
        for definition in SIGNAL_DEFINITIONS
        if definition.classification
        in (
            SignalClassification.CONFIGURABLE_SIGNAL,
            SignalClassification.LEGACY_ONLY_COMPATIBILITY,
        )
    ),
)

PROFILE_TEMPLATES: Mapping[str, ProfileTemplate] = MappingProxyType(
    {PERSONAL_LEGACY_PROFILE.id: PERSONAL_LEGACY_PROFILE}
)


def signal_for_legacy_field(legacy_field_key: str) -> SignalDefinition | None:
    return SIGNALS_BY_LEGACY_FIELD.get(legacy_field_key)


def _signal_contract_record(definition: SignalDefinition) -> dict[str, Any]:
    return {
        "id": definition.id,
        "legacy_field_key": definition.legacy_field_key,
        "label": definition.label,
        "category": definition.category.value,
        "scale_type": definition.scale_type.value,
        "classification": definition.classification.value,
        "default_visibility": definition.default_visibility.value,
        "guidance_bridge_key": definition.guidance_bridge_key,
        "required_for_confidence": definition.required_for_confidence,
        "privacy_class": definition.privacy_class.value,
        "version": definition.version,
    }


def _profile_contract_record(profile: Any) -> dict[str, Any]:
    profile_name = profile.name if hasattr(profile, "name") else profile.label
    return {
        "id": profile.id,
        "name": profile_name,
        "description": getattr(profile, "description", ""),
        "visible_signal_ids": sorted(getattr(profile, "visible_signal_ids", profile.signal_ids)),
        "optional_signal_ids": sorted(getattr(profile, "optional_signal_ids", ())),
        "hidden_signal_ids": sorted(getattr(profile, "hidden_signal_ids", ())),
        "disabled_signal_ids": sorted(getattr(profile, "disabled_signal_ids", ())),
        "required_for_confidence_signal_ids": sorted(getattr(profile, "required_for_confidence_signal_ids", ())),
        "guidance_bridge_policy_id": getattr(profile, "guidance_bridge_policy_id", None),
        "default_formula_modifier_id": getattr(profile, "default_formula_modifier_id", None),
        "allowed_optional_pack_ids": sorted(getattr(profile, "allowed_optional_pack_ids", ())),
        "max_active_signals": getattr(profile, "max_active_signals", len(profile.signal_ids)),
        "placeholder_signal_ids": sorted(getattr(profile, "placeholder_signal_ids", ())),
        "signal_ids": sorted(profile.signal_ids),
        "version": profile.version,
    }


def _optional_pack_contract_record(pack: Any) -> dict[str, Any]:
    return {
        "id": pack.id,
        "name": pack.name,
        "description": pack.description,
        "signal_ids": sorted(pack.signal_ids),
        "placeholder_signal_ids": sorted(pack.placeholder_signal_ids),
        "default_enabled": pack.default_enabled,
        "sensitive": pack.sensitive,
        "requires_explicit_opt_in": pack.requires_explicit_opt_in,
        "max_active_signals_added": pack.max_active_signals_added,
        "version": pack.version,
    }


def _influence_policy_contract_record(policy: Any) -> dict[str, Any]:
    return {
        "signal_id": policy.signal_id,
        "guidance_effect": policy.guidance_effect.value,
        "polarity": policy.polarity.value,
        "user_editable": policy.user_editable,
        "sensitivity_class": policy.sensitivity_class.value,
        "clinical_boundary": policy.clinical_boundary.value,
        "minimum_data_required": policy.minimum_data_required,
        "applies_to_profile_ids": sorted(policy.applies_to_profile_ids),
        "version": policy.version,
    }


def _profile_contract_templates() -> tuple[Any, ...]:
    from life_load.profile_templates import PROFILE_TEMPLATE_METADATA

    return tuple(PROFILE_TEMPLATE_METADATA.values())


def _optional_pack_contract_templates() -> tuple[Any, ...]:
    from life_load.optional_packs import OPTIONAL_PACK_TEMPLATES

    return tuple(OPTIONAL_PACK_TEMPLATES.values())


def _influence_policy_contract_templates() -> tuple[Any, ...]:
    from life_load.optional_packs import SIGNAL_INFLUENCE_POLICIES

    return tuple(SIGNAL_INFLUENCE_POLICIES.values())


def signal_registry_contract_payload() -> dict[str, Any]:
    """Return a deterministic JSON-safe snapshot of the read-only registry."""

    return {
        "schema_version": SIGNAL_REGISTRY_CONTRACT_SCHEMA_VERSION,
        "generated_from": SIGNAL_REGISTRY_CONTRACT_SOURCE,
        "signals": [
            _signal_contract_record(definition)
            for definition in sorted(SIGNAL_DEFINITIONS, key=lambda item: item.id)
        ],
        "profiles": [
            _profile_contract_record(profile)
            for profile in sorted(_profile_contract_templates(), key=lambda item: item.id)
        ],
        "optional_packs": [
            _optional_pack_contract_record(pack)
            for pack in sorted(_optional_pack_contract_templates(), key=lambda item: item.id)
        ],
        "influence_policies": [
            _influence_policy_contract_record(policy)
            for policy in sorted(_influence_policy_contract_templates(), key=lambda item: item.signal_id)
        ],
    }


def signal_registry_contract_json() -> str:
    """Return the deterministic registry contract JSON text."""

    return json.dumps(signal_registry_contract_payload(), indent=2, sort_keys=True) + "\n"
