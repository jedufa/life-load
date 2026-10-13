"""P-INFRA key recovery state model.

This module models recovery outcomes for backend/test-app scenarios only. It
does not implement customer recovery UX and it never returns private key
material to the backend.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

RecoveryStateName = Literal[
    "key_present",
    "key_missing",
    "recovery_required",
    "trusted_device_required",
    "recovery_key_required",
    "unrecoverable_private_history",
    "new_vault_required",
    "new_vault_created",
]

RECOVERY_STATES: tuple[RecoveryStateName, ...] = (
    "key_present",
    "key_missing",
    "recovery_required",
    "trusted_device_required",
    "recovery_key_required",
    "unrecoverable_private_history",
    "new_vault_required",
    "new_vault_created",
)


@dataclass(frozen=True)
class RecoveryContext:
    has_local_key: bool = False
    trusted_device_available: bool = False
    recovery_key_available: bool = False
    account_password_reset: bool = False
    current_device_revoked: bool = False
    all_recovery_material_lost: bool = False
    new_vault_created: bool = False


@dataclass(frozen=True)
class RecoveryStateResult:
    state: RecoveryStateName
    required_action: str
    private_history_recoverable: bool
    backend_returns_private_key_material: bool = False
    password_reset_restores_private_history: bool = False
    redacted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_recovery_state_v1",
            "state": self.state,
            "required_action": self.required_action,
            "private_history_recoverable": self.private_history_recoverable,
            "backend_returns_private_key_material": self.backend_returns_private_key_material,
            "password_reset_restores_private_history": self.password_reset_restores_private_history,
            "redacted": self.redacted,
        }


def determine_recovery_state(context: RecoveryContext) -> RecoveryStateResult:
    """Return the recovery state without exposing any key material."""

    if context.new_vault_created:
        return RecoveryStateResult(
            state="new_vault_created",
            required_action="use_new_empty_vault",
            private_history_recoverable=False,
        )
    if context.account_password_reset:
        return RecoveryStateResult(
            state="recovery_required",
            required_action="prove_recovery_material_or_start_new_vault",
            private_history_recoverable=context.has_local_key
            or context.trusted_device_available
            or context.recovery_key_available,
        )
    if context.has_local_key and not context.current_device_revoked:
        return RecoveryStateResult(
            state="key_present",
            required_action="none",
            private_history_recoverable=True,
        )
    if context.all_recovery_material_lost:
        return RecoveryStateResult(
            state="unrecoverable_private_history",
            required_action="start_new_vault",
            private_history_recoverable=False,
        )
    if context.current_device_revoked and not (context.trusted_device_available or context.recovery_key_available):
        return RecoveryStateResult(
            state="new_vault_required",
            required_action="start_new_vault",
            private_history_recoverable=False,
        )
    if context.trusted_device_available:
        return RecoveryStateResult(
            state="trusted_device_required",
            required_action="approve_from_trusted_device",
            private_history_recoverable=True,
        )
    if context.recovery_key_available:
        return RecoveryStateResult(
            state="recovery_key_required",
            required_action="enter_recovery_key_or_phrase",
            private_history_recoverable=True,
        )
    return RecoveryStateResult(
        state="new_vault_required",
        required_action="start_new_vault",
        private_history_recoverable=False,
    )


def redacted_recovery_state_report(
    result: RecoveryStateResult,
    *,
    user_id: str | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    report = result.as_dict()
    report["user_id_hash"] = _hash_identifier(user_id)
    report["device_id_hash"] = _hash_identifier(device_id)
    report["contains_private_key_material"] = False
    report["contains_recovery_material"] = False
    return report


def _hash_identifier(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
