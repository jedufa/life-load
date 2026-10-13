"""Pure shadow projections from fixed Life Load entries to signal entries.

These helpers prove that current fixed entry dictionaries can be represented as
generic signal-entry records. They are intentionally not used by scoring,
storage, extraction, HTTP payloads, Android, export/import, or UI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from life_load.signal_registry import (
    PROFILE_TEMPLATES,
    SIGNALS_BY_ID,
    SIGNAL_DEFINITIONS,
    SignalCategory,
    SignalClassification,
)


@dataclass(frozen=True)
class SignalEntryProjection:
    signal_id: str
    legacy_field_key: str
    value: Any
    source: str
    is_present: bool
    classification: SignalClassification
    category: SignalCategory
    guidance_bridge_key: str | None
    required_for_confidence: bool


def fixed_entry_to_signal_entries(entry: Mapping[str, Any]) -> tuple[SignalEntryProjection, ...]:
    """Project explicit fixed-entry values for all registry signals."""

    return _project_signal_ids(
        entry=entry,
        signal_ids=tuple(definition.id for definition in SIGNAL_DEFINITIONS),
    )


def fixed_entry_to_signal_entries_for_profile(
    entry: Mapping[str, Any],
    profile_id: str = "personal_legacy",
) -> tuple[SignalEntryProjection, ...]:
    """Project explicit fixed-entry values for the selected read-only profile."""

    profile = PROFILE_TEMPLATES.get(profile_id)
    if profile is None:
        available = ", ".join(sorted(PROFILE_TEMPLATES))
        raise ValueError(f"Unknown Life Load signal profile {profile_id!r}; available profiles: {available}")
    return _project_signal_ids(entry=entry, signal_ids=profile.signal_ids)


def signal_entries_to_fixed_entry_for_personal_legacy(
    signal_entries: Iterable[SignalEntryProjection],
) -> dict[str, Any]:
    """Reconstruct explicit fixed fields from personal_legacy projections only."""

    profile_signal_ids = set(PROFILE_TEMPLATES["personal_legacy"].signal_ids)
    fixed_entry: dict[str, Any] = {}
    for signal_entry in signal_entries:
        if not signal_entry.is_present or signal_entry.signal_id not in profile_signal_ids:
            continue
        definition = SIGNALS_BY_ID.get(signal_entry.signal_id)
        if definition is None or definition.legacy_field_key is None:
            continue
        fixed_entry[definition.legacy_field_key] = signal_entry.value
    return fixed_entry


def _project_signal_ids(
    entry: Mapping[str, Any],
    signal_ids: tuple[str, ...],
) -> tuple[SignalEntryProjection, ...]:
    projections: list[SignalEntryProjection] = []
    for signal_id in signal_ids:
        definition = SIGNALS_BY_ID[signal_id]
        legacy_field_key = definition.legacy_field_key
        if legacy_field_key is None or legacy_field_key not in entry:
            continue
        value = entry[legacy_field_key]
        if not _is_present(value):
            continue
        projections.append(
            SignalEntryProjection(
                signal_id=definition.id,
                legacy_field_key=legacy_field_key,
                value=value,
                source="fixed_entry",
                is_present=True,
                classification=definition.classification,
                category=definition.category,
                guidance_bridge_key=definition.guidance_bridge_key,
                required_for_confidence=definition.required_for_confidence,
            )
        )
    return tuple(projections)


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown"}
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return len(value) > 0
    return True
