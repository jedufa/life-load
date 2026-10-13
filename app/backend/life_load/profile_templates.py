"""Read-only profile template metadata for future Life Load beta profiles.

These templates are fixtures for generalization planning only. They are not
used by scoring, storage, Android runtime, UI, onboarding, or export/import.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from life_load.signal_registry import PERSONAL_LEGACY_PROFILE, SIGNALS_BY_ID


OPTIONAL_PACK_IDS = ("life_load_pack", "pattern_awareness_pack")


@dataclass(frozen=True)
class ProfileSignalPlaceholder:
    id: str
    label: str
    reason: str


@dataclass(frozen=True)
class ProfileTemplateMetadata:
    id: str
    name: str
    description: str
    visible_signal_ids: tuple[str, ...]
    optional_signal_ids: tuple[str, ...]
    hidden_signal_ids: tuple[str, ...]
    disabled_signal_ids: tuple[str, ...]
    required_for_confidence_signal_ids: tuple[str, ...]
    guidance_bridge_policy_id: str | None
    default_formula_modifier_id: str | None
    allowed_optional_pack_ids: tuple[str, ...]
    max_active_signals: int
    placeholders: tuple[ProfileSignalPlaceholder, ...] = ()
    version: int = 1

    @property
    def signal_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                self.visible_signal_ids
                + self.optional_signal_ids
                + self.hidden_signal_ids
                + self.disabled_signal_ids
            )
        )

    @property
    def placeholder_signal_ids(self) -> tuple[str, ...]:
        return tuple(placeholder.id for placeholder in self.placeholders)


def _required_from_registry(signal_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        signal_id
        for signal_id in signal_ids
        if SIGNALS_BY_ID[signal_id].required_for_confidence
    )


PERSONAL_LEGACY_TEMPLATE = ProfileTemplateMetadata(
    id="personal_legacy",
    name="Personal legacy",
    description="Compatibility wrapper for the current fixed Life Load behavior.",
    visible_signal_ids=PERSONAL_LEGACY_PROFILE.signal_ids,
    optional_signal_ids=(),
    hidden_signal_ids=(),
    disabled_signal_ids=(),
    required_for_confidence_signal_ids=_required_from_registry(PERSONAL_LEGACY_PROFILE.signal_ids),
    guidance_bridge_policy_id="fixed_field_legacy",
    default_formula_modifier_id=None,
    allowed_optional_pack_ids=OPTIONAL_PACK_IDS,
    max_active_signals=len(PERSONAL_LEGACY_PROFILE.signal_ids),
)

GENERAL_BALANCE_TEMPLATE = ProfileTemplateMetadata(
    id="general_balance",
    name="General balance",
    description="Future broad profile focused on core recovery, stress, energy, and mood.",
    visible_signal_ids=(
        "core.sleep_ok",
        "core.nutrition_ok",
        "mental.stress",
        "energy.energy",
        "mood.mood",
        "recovery.shutdown_done",
    ),
    optional_signal_ids=(
        "recovery.decompression_done",
        "recovery.after_work_decompression_done",
    ),
    hidden_signal_ids=(),
    disabled_signal_ids=(
        "body.foot_pain",
        "body.shoulder_pain",
        "relationship.wife_conflict_count",
        "relationship.wife_conflict_school",
        "relationship.wife_conflict_chores",
        "relationship.wife_conflict_other",
        "caregiving.homework_done",
        "caregiving.homework_status",
        "nutrition.alcohol",
        "nutrition.binge",
        "training.primary_activity_type",
    ),
    required_for_confidence_signal_ids=(
        "core.sleep_ok",
        "core.nutrition_ok",
        "mental.stress",
        "energy.energy",
    ),
    guidance_bridge_policy_id="general_balance_v0",
    default_formula_modifier_id="balanced",
    allowed_optional_pack_ids=("life_load_pack", "pattern_awareness_pack"),
    max_active_signals=8,
    placeholders=(
        ProfileSignalPlaceholder(
            id="placeholder.body_state",
            label="Generic body state",
            reason="Generic body signal instances are not implemented yet.",
        ),
        ProfileSignalPlaceholder(
            id="placeholder.life_load",
            label="Overall life load",
            reason="Overall load remains derived from fixed scoring for now.",
        ),
    ),
)

WORK_STRESS_TEMPLATE = ProfileTemplateMetadata(
    id="work_stress",
    name="Work stress",
    description="Future profile for work pressure and overload prevention.",
    visible_signal_ids=(
        "core.sleep_ok",
        "core.nutrition_ok",
        "mental.stress",
        "energy.energy",
        "mood.mood",
        "work.work_intensity",
        "work.home_office",
    ),
    optional_signal_ids=(
        "work.project_overrun",
        "evening.phone_after_21",
    ),
    hidden_signal_ids=(),
    disabled_signal_ids=(
        "body.foot_pain",
        "body.shoulder_pain",
        "relationship.wife_conflict_count",
        "relationship.wife_conflict_school",
        "relationship.wife_conflict_chores",
        "relationship.wife_conflict_other",
        "caregiving.homework_done",
        "caregiving.homework_status",
    ),
    required_for_confidence_signal_ids=(
        "core.sleep_ok",
        "mental.stress",
        "energy.energy",
    ),
    guidance_bridge_policy_id="work_stress_v0",
    default_formula_modifier_id="balanced",
    allowed_optional_pack_ids=("pattern_awareness_pack",),
    max_active_signals=8,
)

TRAINING_RECOVERY_TEMPLATE = ProfileTemplateMetadata(
    id="training_recovery",
    name="Training recovery",
    description="Future profile for recreational training recovery.",
    visible_signal_ids=(
        "core.sleep_ok",
        "core.nutrition_ok",
        "mental.stress",
        "energy.energy",
        "training.primary_activity_type",
        "training.activity_duration_min",
        "training.rehab_done",
    ),
    optional_signal_ids=(
        "recovery.decompression_done",
        "body.migraine_warning",
    ),
    hidden_signal_ids=(
        "body.foot_pain",
        "body.shoulder_pain",
    ),
    disabled_signal_ids=(
        "relationship.wife_conflict_count",
        "relationship.wife_conflict_school",
        "relationship.wife_conflict_chores",
        "relationship.wife_conflict_other",
        "caregiving.homework_done",
        "caregiving.homework_status",
        "nutrition.alcohol",
        "nutrition.binge",
    ),
    required_for_confidence_signal_ids=(
        "core.sleep_ok",
        "core.nutrition_ok",
        "mental.stress",
        "energy.energy",
        "training.primary_activity_type",
    ),
    guidance_bridge_policy_id="training_recovery_v0",
    default_formula_modifier_id="sports_light",
    allowed_optional_pack_ids=("life_load_pack",),
    max_active_signals=8,
)

BODY_SIGNAL_AWARENESS_TEMPLATE = ProfileTemplateMetadata(
    id="body_signal_awareness",
    name="Body signal awareness",
    description="Future profile for generic body-signal tracking.",
    visible_signal_ids=(
        "core.sleep_ok",
        "mental.stress",
        "energy.energy",
        "mood.mood",
    ),
    optional_signal_ids=(
        "body.migraine_warning",
    ),
    hidden_signal_ids=(
        "body.foot_pain",
        "body.shoulder_pain",
    ),
    disabled_signal_ids=(
        "relationship.wife_conflict_count",
        "relationship.wife_conflict_school",
        "relationship.wife_conflict_chores",
        "relationship.wife_conflict_other",
        "caregiving.homework_done",
        "caregiving.homework_status",
    ),
    required_for_confidence_signal_ids=(
        "core.sleep_ok",
        "mental.stress",
        "energy.energy",
    ),
    guidance_bridge_policy_id="body_signal_awareness_v0",
    default_formula_modifier_id=None,
    allowed_optional_pack_ids=("life_load_pack",),
    max_active_signals=8,
    placeholders=(
        ProfileSignalPlaceholder(
            id="placeholder.body_signal_instance",
            label="User-named body signal",
            reason="Configurable user-named body signal instances are future work.",
        ),
    ),
)

CUSTOM_STUB_TEMPLATE = ProfileTemplateMetadata(
    id="custom_stub",
    name="Custom stub",
    description="Metadata-only placeholder for future custom profile creation.",
    visible_signal_ids=(
        "core.sleep_ok",
        "mental.stress",
        "energy.energy",
    ),
    optional_signal_ids=(),
    hidden_signal_ids=(),
    disabled_signal_ids=(),
    required_for_confidence_signal_ids=(
        "core.sleep_ok",
        "mental.stress",
        "energy.energy",
    ),
    guidance_bridge_policy_id=None,
    default_formula_modifier_id=None,
    allowed_optional_pack_ids=(),
    max_active_signals=3,
    placeholders=(
        ProfileSignalPlaceholder(
            id="placeholder.custom_profile_editor",
            label="Custom profile editor",
            reason="Custom profile construction is not implemented yet.",
        ),
    ),
)

PROFILE_TEMPLATE_METADATA: Mapping[str, ProfileTemplateMetadata] = MappingProxyType(
    {
        template.id: template
        for template in (
            PERSONAL_LEGACY_TEMPLATE,
            GENERAL_BALANCE_TEMPLATE,
            WORK_STRESS_TEMPLATE,
            TRAINING_RECOVERY_TEMPLATE,
            BODY_SIGNAL_AWARENESS_TEMPLATE,
            CUSTOM_STUB_TEMPLATE,
        )
    }
)
