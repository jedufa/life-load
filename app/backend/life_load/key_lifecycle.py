"""E2EE key lifecycle policy contracts for P-INFRA/MVP4 continuity rehearsal.

The functions here do not perform cryptography. They make the key-lifecycle
decisions testable so backend fixtures, test apps, reports, and future Android
integration keep the same boundaries: client-held Vault Key, opaque server
packages, account password separate from private-history recovery, and no
production backup claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


KEY_LIFECYCLE_SCHEMA_VERSION = "life_load_e2ee_key_lifecycle_v1"

PlatformName = Literal["android", "ios", "web", "unknown"]
TrustedState = Literal["untrusted", "trusted", "revoked", "pending"]
BackupOptInMode = Literal["blocked", "recommended_safer", "advanced_risky"]

ALLOWED_PLATFORMS: tuple[PlatformName, ...] = ("android", "ios", "web", "unknown")
ALLOWED_TRUSTED_STATES: tuple[TrustedState, ...] = ("untrusted", "trusted", "revoked", "pending")
ALLOWED_WRAPPING_METHODS = {
    "android_keystore_user_auth_v1",
    "android_keystore_simulator_v1",
    "recovery_key_phrase_v1",
    "trusted_device_transfer_v1",
    "recovery_key_prototype",
    "device_key_wrapped",
    "unknown",
}

PASSWORD_RESET_BOUNDARY_COPY = "Password reset restores account access, not private encrypted history."
LOST_ALL_MATERIAL_COPY = (
    "If you lose all trusted devices and your recovery key, your private history cannot be recovered."
)
SUPPORT_BOUNDARY_COPY = "Support can help with account access and device state. Support cannot decrypt or recover private history."
LOCAL_ALPHA_WARNING = (
    "This is an experimental continuity test. Do not rely on it as your only backup. "
    "The server is not production-hosted. Private payloads are end-to-end encrypted, "
    "but service availability, durability, and recovery guarantees are not production-grade."
)


@dataclass(frozen=True)
class BackupOptInPolicy:
    allowed: bool
    mode: BackupOptInMode
    required_action: str
    recovery_package_expected: bool
    backend_receives_plaintext_vault_key: bool = False
    backend_receives_recovery_key_or_phrase: bool = False
    production_claim_allowed: bool = False
    redacted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
            "allowed": self.allowed,
            "mode": self.mode,
            "required_action": self.required_action,
            "recovery_package_expected": self.recovery_package_expected,
            "backend_receives_plaintext_vault_key": self.backend_receives_plaintext_vault_key,
            "backend_receives_recovery_key_or_phrase": self.backend_receives_recovery_key_or_phrase,
            "production_claim_allowed": self.production_claim_allowed,
            "copy": {
                "password_reset_boundary": PASSWORD_RESET_BOUNDARY_COPY,
                "lost_all_material": LOST_ALL_MATERIAL_COPY,
            },
            "redacted": self.redacted,
        }


@dataclass(frozen=True)
class LocalAlphaHostingConfig:
    environment: str = "alpha_local"
    non_local_access: bool = False
    tls_enabled: bool = False
    secure_tunnel_enabled: bool = False
    public_http_enabled: bool = False
    router_port_forwarding_enabled: bool = False
    explicit_tester_consent: bool = False
    backup_before_destructive_tests: bool = False
    server_backup_policy_documented: bool = False
    db_backup_policy_documented: bool = False
    object_store_backup_policy_documented: bool = False
    migration_export_path_documented: bool = False
    wipe_delete_limitations_documented: bool = False
    tester_deletion_request_path_documented: bool = False
    admin_access_limited_to_developer: bool = False
    logs_redacted_by_default: bool = False
    privacy_canary_scan_planned: bool = False
    production_claims_disabled: bool = False


def evaluate_backup_opt_in(
    *,
    recovery_key_or_phrase_configured: bool,
    unrecoverable_if_lost_acknowledged: bool,
) -> BackupOptInPolicy:
    """Return the allowed backup opt-in mode without silent continuity enablement."""

    if recovery_key_or_phrase_configured:
        return BackupOptInPolicy(
            allowed=True,
            mode="recommended_safer",
            required_action="confirm_recovery_key_or_phrase_saved",
            recovery_package_expected=True,
        )
    if unrecoverable_if_lost_acknowledged:
        return BackupOptInPolicy(
            allowed=True,
            mode="advanced_risky",
            required_action="continue_without_recovery_after_explicit_acknowledgement",
            recovery_package_expected=False,
        )
    return BackupOptInPolicy(
        allowed=False,
        mode="blocked",
        required_action="set_up_recovery_key_or_phrase_or_acknowledge_unrecoverable_if_lost",
        recovery_package_expected=False,
    )


def key_lifecycle_contract() -> dict[str, Any]:
    """Return the durable E2EE boundary expected by backend and test apps."""

    return {
        "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
        "maturity": "P-INFRA / internal alpha rehearsal; not externally reviewed production E2EE",
        "backend_treated_as_untrusted_storage": True,
        "vault_key_generated_client_side": True,
        "backend_receives_plaintext_private_payloads": False,
        "backend_receives_plaintext_vault_key": False,
        "backend_receives_recovery_key_or_phrase": False,
        "server_stores_opaque_key_packages_only": True,
        "password_reset_restores_account_access": True,
        "password_reset_recovers_private_history": False,
        "trusted_device_recovery_preferred": True,
        "recovery_key_or_phrase_supported": True,
        "recovery_key_mandatory_for_mvp4_alpha": False,
        "silent_continuity_enablement_allowed": False,
        "support_can_decrypt_private_history": False,
        "initial_platform": "android",
        "future_platforms_reserved": list(ALLOWED_PLATFORMS),
        "external_review_required_before_public_production_claims": True,
        "redacted": True,
    }


def validate_device_key_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Validate platform-neutral device key metadata for backend storage."""

    platform = str(metadata.get("platform") or "unknown").strip().lower()
    trusted_state = str(metadata.get("trusted_state") or "untrusted").strip().lower()
    wrapping_method = str(metadata.get("wrapping_method") or "unknown").strip().lower()
    missing: list[str] = []
    fatal: list[str] = []

    for field in (
        "platform",
        "app_version",
        "device_label",
        "device_public_id",
        "trusted_state",
        "key_package_version",
        "wrapping_method",
    ):
        if metadata.get(field) in (None, ""):
            missing.append(field)
    if platform not in ALLOWED_PLATFORMS:
        fatal.append("unsupported_platform")
    if trusted_state not in ALLOWED_TRUSTED_STATES:
        fatal.append("unsupported_trusted_state")
    if wrapping_method not in ALLOWED_WRAPPING_METHODS:
        fatal.append("unsupported_wrapping_method")
    if str(metadata.get("key_package_version") or "").strip() in {"", "0"}:
        missing.append("versioned_key_package_metadata")

    return {
        "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
        "ok": not missing and not fatal,
        "platform": platform if platform in ALLOWED_PLATFORMS else "unknown",
        "trusted_state": trusted_state if trusted_state in ALLOWED_TRUSTED_STATES else "untrusted",
        "wrapping_method": wrapping_method if wrapping_method in ALLOWED_WRAPPING_METHODS else "unknown",
        "missing": sorted(set(missing)),
        "fatal": sorted(set(fatal)),
        "backend_receives_plaintext_vault_key": False,
        "redacted": True,
    }


def trusted_device_approval_contract() -> dict[str, Any]:
    return {
        "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
        "new_device_requests_vault_access": True,
        "existing_trusted_device_approves": True,
        "local_biometric_or_device_unlock_required_when_available": True,
        "simulator_only_until_android_keystore_unlock_is_integrated": True,
        "backend_relay_opaque_packages_only": True,
        "backend_receives_plaintext_vault_key": False,
        "revoked_device_can_approve": False,
        "expired_request_can_approve": False,
        "cross_user_request_can_approve": False,
        "duplicate_request_policy": "idempotent_or_safely_rejected",
        "redacted": True,
    }


def password_reset_boundary_contract() -> dict[str, Any]:
    return {
        "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
        "copy": PASSWORD_RESET_BOUNDARY_COPY,
        "restores_account_access": True,
        "recovers_private_history": False,
        "derives_vault_key_from_account_password": False,
        "requires_recovery_material_for_private_history": True,
        "lost_all_material_result": "new_vault_required",
        "support_admin_recovery_available": False,
        "redacted": True,
    }


def evaluate_local_alpha_hosting(config: LocalAlphaHostingConfig | Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if isinstance(config, LocalAlphaHostingConfig) else LocalAlphaHostingConfig(**dict(config or {}))
    missing: list[str] = []
    fatal: list[str] = []
    warnings: list[str] = []

    if cfg.environment not in {"alpha_local", "staging_like"}:
        fatal.append("environment_must_be_alpha_local_or_staging_like")
    if cfg.non_local_access and not (cfg.tls_enabled or cfg.secure_tunnel_enabled):
        fatal.append("non_local_access_requires_tls_or_secure_tunnel")
    if cfg.public_http_enabled and cfg.non_local_access:
        fatal.append("plain_http_public_internet_blocked")
    if cfg.router_port_forwarding_enabled:
        fatal.append("router_port_forwarding_blocked")
    if cfg.non_local_access and cfg.secure_tunnel_enabled and not cfg.tls_enabled:
        warnings.append("secure_tunnel_used_for_non_local_alpha")

    required_flags = {
        "explicit_tester_consent": cfg.explicit_tester_consent,
        "backup_before_destructive_tests": cfg.backup_before_destructive_tests,
        "server_backup_policy_documented": cfg.server_backup_policy_documented,
        "db_backup_policy_documented": cfg.db_backup_policy_documented,
        "object_store_backup_policy_documented": cfg.object_store_backup_policy_documented,
        "migration_export_path_documented": cfg.migration_export_path_documented,
        "wipe_delete_limitations_documented": cfg.wipe_delete_limitations_documented,
        "tester_deletion_request_path_documented": cfg.tester_deletion_request_path_documented,
        "admin_access_limited_to_developer": cfg.admin_access_limited_to_developer,
        "logs_redacted_by_default": cfg.logs_redacted_by_default,
        "privacy_canary_scan_planned": cfg.privacy_canary_scan_planned,
        "production_claims_disabled": cfg.production_claims_disabled,
    }
    missing.extend(name for name, enabled in required_flags.items() if not enabled)

    return {
        "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
        "environment": cfg.environment,
        "ok": not missing and not fatal,
        "fatal": sorted(set(fatal)),
        "missing": sorted(set(missing)),
        "warnings": sorted(set(warnings)),
        "alpha_warning": LOCAL_ALPHA_WARNING,
        "public_production_claim_allowed": False,
        "contains_tokens": False,
        "contains_passwords": False,
        "contains_recovery_material": False,
        "redacted": True,
    }


def migration_portability_contract() -> dict[str, Any]:
    return {
        "schema_version": KEY_LIFECYCLE_SCHEMA_VERSION,
        "portable_across": ["local_developer_machine", "local_network_alpha", "staging_like", "european_hosted"],
        "preserve": [
            "encrypted_backup_objects",
            "namespaces",
            "users",
            "devices",
            "recovery_packages",
            "trusted_device_requests",
            "deletion_tombstones",
            "audit_security_history_where_appropriate",
        ],
        "requires_payload_decryption": False,
        "requires_plaintext_vault_keys": False,
        "requires_recovery_phrases": False,
        "provider_independent_object_ids_and_checksums": True,
        "environment_specific_config": True,
        "secrets_committed": False,
        "redacted": True,
    }


__all__ = [
    "KEY_LIFECYCLE_SCHEMA_VERSION",
    "LOCAL_ALPHA_WARNING",
    "LOST_ALL_MATERIAL_COPY",
    "PASSWORD_RESET_BOUNDARY_COPY",
    "SUPPORT_BOUNDARY_COPY",
    "LocalAlphaHostingConfig",
    "evaluate_backup_opt_in",
    "evaluate_local_alpha_hosting",
    "key_lifecycle_contract",
    "migration_portability_contract",
    "password_reset_boundary_contract",
    "trusted_device_approval_contract",
    "validate_device_key_metadata",
]
