"""Optional pack and guidance influence metadata for configurable profiles.

This metadata is consumed by selected profile config and the generic guidance
bridge. It remains additive: fixed scoring, HTTP payloads, and export/import
semantics are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class GuidanceEffect(str, Enum):
    TRACK_ONLY = "track_only"
    LIGHT = "light"
    NORMAL = "normal"
    STRONG = "strong"
    GUARDRAIL = "guardrail"


class SignalPolarity(str, Enum):
    CAPACITY_POSITIVE = "capacity_positive"
    CAPACITY_NEGATIVE = "capacity_negative"
    WARNING = "warning"
    PROTECTIVE = "protective"
    NEUTRAL = "neutral"


class SensitivityClass(str, Enum):
    NORMAL = "normal"
    PRIVATE = "private"
    PRIVATE_PLUS = "private_plus"


class ClinicalBoundary(str, Enum):
    WELLNESS_ONLY = "wellness_only"
    OUT_OF_SCOPE_IF_URGENT = "out_of_scope_if_urgent"
    NEVER_SUGGEST_TREATMENT = "never_suggest_treatment"


@dataclass(frozen=True)
class OptionalPackTemplate:
    id: str
    name: str
    description: str
    signal_ids: tuple[str, ...]
    placeholder_signal_ids: tuple[str, ...]
    default_enabled: bool
    sensitive: bool
    requires_explicit_opt_in: bool
    max_active_signals_added: int
    version: int = 1


@dataclass(frozen=True)
class SignalInfluencePolicy:
    signal_id: str
    guidance_effect: GuidanceEffect
    polarity: SignalPolarity
    user_editable: bool
    sensitivity_class: SensitivityClass
    clinical_boundary: ClinicalBoundary
    minimum_data_required: int
    applies_to_profile_ids: tuple[str, ...]
    version: int = 1


LIFE_LOAD_PACK = OptionalPackTemplate(
    id="life_load_pack",
    name="Life load pack",
    description="External pressure and invisible load signals.",
    signal_ids=(
        "work.work_intensity",
        "work.project_overrun",
        "work.home_office",
        "relationship.family_stress",
    ),
    placeholder_signal_ids=(
        "placeholder.care_demand",
        "placeholder.schedule_pressure",
        "placeholder.conflict_friction",
        "placeholder.admin_load",
        "placeholder.family_load",
    ),
    default_enabled=False,
    sensitive=False,
    requires_explicit_opt_in=False,
    max_active_signals_added=4,
)

PATTERN_AWARENESS_PACK = OptionalPackTemplate(
    id="pattern_awareness_pack",
    name="Pattern awareness pack",
    description="Private pattern awareness for risky pulls and protective routines.",
    signal_ids=(
        "nutrition.alcohol",
        "nutrition.binge",
        "evening.phone_after_21",
        "evening.evening_chain_broken",
        "work.project_overrun",
    ),
    placeholder_signal_ids=(
        "placeholder.risk_pull",
        "placeholder.more_than_intended",
        "placeholder.protective_routine_missed",
        "placeholder.protective_routine_done",
        "placeholder.evening_risk",
        "placeholder.eating_pattern",
        "placeholder.overtraining_urge",
        "placeholder.avoidance",
    ),
    default_enabled=False,
    sensitive=True,
    requires_explicit_opt_in=True,
    max_active_signals_added=5,
)

OPTIONAL_PACK_TEMPLATES: Mapping[str, OptionalPackTemplate] = MappingProxyType(
    {
        LIFE_LOAD_PACK.id: LIFE_LOAD_PACK,
        PATTERN_AWARENESS_PACK.id: PATTERN_AWARENESS_PACK,
    }
)


SIGNAL_INFLUENCE_POLICIES: Mapping[str, SignalInfluencePolicy] = MappingProxyType(
    {
        policy.signal_id: policy
        for policy in (
            SignalInfluencePolicy(
                signal_id="core.sleep_ok",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.CAPACITY_POSITIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "general_balance", "work_stress", "training_recovery"),
            ),
            SignalInfluencePolicy(
                signal_id="core.nutrition_ok",
                guidance_effect=GuidanceEffect.NORMAL,
                polarity=SignalPolarity.CAPACITY_POSITIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "general_balance", "training_recovery"),
            ),
            SignalInfluencePolicy(
                signal_id="mental.stress",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.CAPACITY_NEGATIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=(
                    "personal_legacy",
                    "general_balance",
                    "work_stress",
                    "training_recovery",
                    "body_signal_awareness",
                ),
            ),
            SignalInfluencePolicy(
                signal_id="energy.energy",
                guidance_effect=GuidanceEffect.NORMAL,
                polarity=SignalPolarity.CAPACITY_POSITIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=(
                    "personal_legacy",
                    "general_balance",
                    "work_stress",
                    "training_recovery",
                    "body_signal_awareness",
                ),
            ),
            SignalInfluencePolicy(
                signal_id="mood.mood",
                guidance_effect=GuidanceEffect.LIGHT,
                polarity=SignalPolarity.NEUTRAL,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=2,
                applies_to_profile_ids=("personal_legacy", "general_balance", "work_stress", "body_signal_awareness"),
            ),
            SignalInfluencePolicy(
                signal_id="body.foot_pain",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy",),
            ),
            SignalInfluencePolicy(
                signal_id="body.shoulder_pain",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy",),
            ),
            SignalInfluencePolicy(
                signal_id="body.migraine_warning",
                guidance_effect=GuidanceEffect.GUARDRAIL,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "training_recovery", "body_signal_awareness"),
            ),
            SignalInfluencePolicy(
                signal_id="recovery.shutdown_done",
                guidance_effect=GuidanceEffect.NORMAL,
                polarity=SignalPolarity.PROTECTIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "general_balance"),
            ),
            SignalInfluencePolicy(
                signal_id="recovery.decompression_done",
                guidance_effect=GuidanceEffect.LIGHT,
                polarity=SignalPolarity.PROTECTIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "general_balance", "training_recovery"),
            ),
            SignalInfluencePolicy(
                signal_id="nutrition.alcohol",
                guidance_effect=GuidanceEffect.GUARDRAIL,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE_PLUS,
                clinical_boundary=ClinicalBoundary.NEVER_SUGGEST_TREATMENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy",),
            ),
            SignalInfluencePolicy(
                signal_id="nutrition.binge",
                guidance_effect=GuidanceEffect.GUARDRAIL,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE_PLUS,
                clinical_boundary=ClinicalBoundary.NEVER_SUGGEST_TREATMENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy",),
            ),
            SignalInfluencePolicy(
                signal_id="evening.phone_after_21",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "work_stress"),
            ),
            SignalInfluencePolicy(
                signal_id="evening.evening_chain_broken",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy",),
            ),
            SignalInfluencePolicy(
                signal_id="work.project_overrun",
                guidance_effect=GuidanceEffect.STRONG,
                polarity=SignalPolarity.WARNING,
                user_editable=True,
                sensitivity_class=SensitivityClass.PRIVATE,
                clinical_boundary=ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "work_stress"),
            ),
            SignalInfluencePolicy(
                signal_id="work.work_intensity",
                guidance_effect=GuidanceEffect.NORMAL,
                polarity=SignalPolarity.CAPACITY_NEGATIVE,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=2,
                applies_to_profile_ids=("personal_legacy", "work_stress"),
            ),
            SignalInfluencePolicy(
                signal_id="training.primary_activity_type",
                guidance_effect=GuidanceEffect.NORMAL,
                polarity=SignalPolarity.NEUTRAL,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "training_recovery"),
            ),
            SignalInfluencePolicy(
                signal_id="training.activity_duration_min",
                guidance_effect=GuidanceEffect.NORMAL,
                polarity=SignalPolarity.NEUTRAL,
                user_editable=True,
                sensitivity_class=SensitivityClass.NORMAL,
                clinical_boundary=ClinicalBoundary.WELLNESS_ONLY,
                minimum_data_required=1,
                applies_to_profile_ids=("personal_legacy", "training_recovery"),
            ),
        )
    }
)
