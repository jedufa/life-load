"""Selected profile configuration helpers.

The selected config model is persisted by Android profile setup and consumed by
the generic guidance bridge. It remains additive: fixed personal_legacy scoring,
HTTP payloads, and export/import semantics are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from life_load.optional_packs import OPTIONAL_PACK_TEMPLATES
from life_load.profile_templates import PROFILE_TEMPLATE_METADATA
from life_load.signal_registry import SIGNALS_BY_ID


@dataclass(frozen=True)
class SelectedProfileConfig:
    active_profile_id: str
    template_version: int
    enabled_signal_ids: tuple[str, ...]
    optional_signal_ids: tuple[str, ...]
    hidden_signal_ids: tuple[str, ...]
    disabled_signal_ids: tuple[str, ...]
    required_for_confidence_signal_ids: tuple[str, ...]
    optional_pack_ids: tuple[str, ...]
    user_added_signal_ids: tuple[str, ...]
    user_overridden_signal_ids: tuple[str, ...]
    guidance_bridge_policy_id: str | None
    default_formula_modifier_id: str | None
    max_active_signals: int


def build_selected_profile_config(
    profile_id: str,
    optional_pack_ids: tuple[str, ...] = (),
    user_added_signal_ids: tuple[str, ...] = (),
) -> SelectedProfileConfig:
    template = PROFILE_TEMPLATE_METADATA.get(profile_id)
    if template is None:
        available = ", ".join(sorted(PROFILE_TEMPLATE_METADATA))
        raise ValueError(f"Unknown Life Load profile template {profile_id!r}; available profiles: {available}")

    unknown_registered_pack_ids = tuple(pack_id for pack_id in optional_pack_ids if pack_id not in OPTIONAL_PACK_TEMPLATES)
    if unknown_registered_pack_ids:
        known = ", ".join(sorted(OPTIONAL_PACK_TEMPLATES)) or "none"
        raise ValueError(
            f"Unknown optional pack id(s): {', '.join(unknown_registered_pack_ids)}; known packs: {known}"
        )

    unknown_pack_ids = tuple(pack_id for pack_id in optional_pack_ids if pack_id not in template.allowed_optional_pack_ids)
    if unknown_pack_ids:
        allowed = ", ".join(template.allowed_optional_pack_ids) or "none"
        raise ValueError(
            f"Optional pack id(s) not allowed for profile {profile_id!r}: {', '.join(unknown_pack_ids)}; "
            f"allowed packs: {allowed}"
        )

    template_placeholder_ids = set(template.placeholder_signal_ids)
    unknown_user_signal_ids = tuple(
        signal_id
        for signal_id in user_added_signal_ids
        if signal_id not in SIGNALS_BY_ID and signal_id not in template_placeholder_ids
    )
    if unknown_user_signal_ids:
        raise ValueError(
            f"Unknown user-added signal id(s) for profile {profile_id!r}: {', '.join(unknown_user_signal_ids)}"
        )

    hidden_or_disabled = set(template.hidden_signal_ids) | set(template.disabled_signal_ids)
    required_for_confidence = tuple(
        signal_id
        for signal_id in template.required_for_confidence_signal_ids
        if signal_id not in hidden_or_disabled
    )
    pack_signal_ids = tuple(
        signal_id
        for pack_id in optional_pack_ids
        for signal_id in OPTIONAL_PACK_TEMPLATES[pack_id].signal_ids
    )
    enabled_signal_ids = _unique_tuple(
        tuple(
            signal_id
            for signal_id in template.visible_signal_ids + pack_signal_ids + user_added_signal_ids
            if signal_id not in hidden_or_disabled
        )
    )

    return SelectedProfileConfig(
        active_profile_id=template.id,
        template_version=template.version,
        enabled_signal_ids=enabled_signal_ids,
        optional_signal_ids=template.optional_signal_ids,
        hidden_signal_ids=template.hidden_signal_ids,
        disabled_signal_ids=template.disabled_signal_ids,
        required_for_confidence_signal_ids=required_for_confidence,
        optional_pack_ids=tuple(optional_pack_ids),
        user_added_signal_ids=tuple(user_added_signal_ids),
        user_overridden_signal_ids=(),
        guidance_bridge_policy_id=template.guidance_bridge_policy_id,
        default_formula_modifier_id=template.default_formula_modifier_id,
        max_active_signals=template.max_active_signals,
    )


def _unique_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
