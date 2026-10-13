"""Backend-only continuity readiness contracts for P-INFRA/MVP4.

This module ties together the backend-only work that can be rehearsed without
touching the real Android app: local alpha hosting posture, auth provider
decisioning, E2EE lifecycle boundaries, migration portability, restore/lost
phone simulator scope, delete/purge honesty, and support/monitoring drills.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from life_load.key_lifecycle import (
    KEY_LIFECYCLE_SCHEMA_VERSION,
    LocalAlphaHostingConfig,
    evaluate_local_alpha_hosting,
    key_lifecycle_contract,
    migration_portability_contract,
    password_reset_boundary_contract,
    trusted_device_approval_contract,
)
from life_load.observability import observability_summary
from life_load.purge_policy import DeletionContract


READINESS_SCHEMA_VERSION = "life_load_continuity_readiness_v1"

FORBIDDEN_REPORT_TERMS = (
    "session_token",
    "authorization",
    "bearer ",
    "plaintext vault key",
    "plaintext recovery",
    "recovery phrase value",
    "raw ciphertext",
    "diary text",
    "garmin raw",
    "ai prompt",
    "data/health.sqlite",
)


@dataclass(frozen=True)
class ContinuityReadinessConfig:
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
    auth_provider_strategy: str = "self_host_alpha_revisit_managed_oidc"

    def hosting_config(self) -> LocalAlphaHostingConfig:
        values = asdict(self)
        values.pop("auth_provider_strategy", None)
        return LocalAlphaHostingConfig(**values)


def safe_local_alpha_config(*, non_local_access: bool = True) -> ContinuityReadinessConfig:
    """Return the safest local-alpha fixture posture for drills/tests."""

    return ContinuityReadinessConfig(
        environment="alpha_local",
        non_local_access=non_local_access,
        secure_tunnel_enabled=non_local_access,
        explicit_tester_consent=True,
        backup_before_destructive_tests=True,
        server_backup_policy_documented=True,
        db_backup_policy_documented=True,
        object_store_backup_policy_documented=True,
        migration_export_path_documented=True,
        wipe_delete_limitations_documented=True,
        tester_deletion_request_path_documented=True,
        admin_access_limited_to_developer=True,
        logs_redacted_by_default=True,
        privacy_canary_scan_planned=True,
        production_claims_disabled=True,
    )


def auth_provider_decision_package(strategy: str = "self_host_alpha_revisit_managed_oidc") -> dict[str, Any]:
    """Return the current auth provider decision as a reviewable scorecard."""

    criteria = [
        "keeps_password_reset_separate_from_vault_recovery",
        "supports_rate_limits_and_lockouts",
        "supports_device_bound_sessions",
        "supports_rotating_refresh_tokens",
        "supports_redacted_audit_events",
        "can_run_fixture_only_during_alpha",
        "can_migrate_toward_oidc_or_managed_auth_later",
        "does_not_require_backend_vault_key_access",
    ]
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "strategy": strategy,
        "alpha_decision": "self_host_auth_for_alpha_only",
        "later_decision_gate": "revisit_managed_eu_oidc_or_hosted_auth_before_public_production",
        "recommended_now": "self_host_alpha_with_provider_abstraction",
        "production_provider_selected": False,
        "selection_requires_current_vendor_review": True,
        "criteria": criteria,
        "hard_requirements": {
            "argon2id_or_approved_password_hashing": True,
            "server_side_pepper_from_secret_manager": True,
            "login_rate_limiting": True,
            "short_lived_access_tokens": True,
            "rotating_refresh_tokens": True,
            "token_reuse_detection": True,
            "device_bound_sessions": True,
            "account_disable": True,
            "redacted_auth_events": True,
            "password_reset_recovers_private_history": False,
        },
        "blocked_claims": [
            "public_account_system_ready",
            "production_auth_provider_selected",
            "password_reset_recovers_private_history",
        ],
        "redacted": True,
    }


def restore_lost_phone_simulator_contract() -> dict[str, Any]:
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "surface": "Android Backend Test App only",
        "real_life_load_app_touched": False,
        "scenarios": [
            "lost_phone_with_trusted_device",
            "lost_phone_with_recovery_key",
            "lost_phone_with_no_recovery",
            "wrong_recovery_key_fails",
            "password_reset_account_only",
            "new_vault_required_after_lost_all_material",
        ],
        "required_terminal_states": [
            "key_present",
            "key_missing",
            "recovery_required",
            "trusted_device_required",
            "recovery_key_required",
            "unrecoverable_private_history",
            "new_vault_required",
            "new_vault_created",
        ],
        "support_or_admin_recovery": False,
        "production_restore_ux_claim_allowed": False,
        "redacted": True,
    }


def delete_purge_honesty_contract() -> dict[str, Any]:
    deletion = DeletionContract().as_dict()
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "delete_mode_now": deletion["current_mode"],
        "soft_delete_excludes_restore_manifest": deletion["restore_manifest_excluded"],
        "soft_delete_blocks_direct_download": deletion["direct_download_blocked"],
        "purge_implemented": deletion["purge_implemented"],
        "purge_receipt_truth_rule": "only claim hard purge when purge_complete is true",
        "allowed_wording": deletion["allowed_wording"],
        "prohibited_claims": deletion["prohibited_claims"],
        "production_permanent_delete_claim_allowed": False,
        "redacted": True,
    }


def support_monitoring_contract(events: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    summary = observability_summary(events or [])
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "support_can_decrypt_private_history": False,
        "support_can_bypass_recovery_material": False,
        "support_has_decrypt_action": False,
        "allowed_support_fields": [
            "account_status",
            "device_count",
            "revoked_devices",
            "last_sync_time",
            "backup_object_count",
            "recovery_package_exists",
            "recovery_state",
            "delete_purge_status",
            "request_ids",
            "error_summaries",
        ],
        "observability": summary,
        "production_monitoring_claim_allowed": False,
        "redacted": True,
    }


def build_continuity_readiness_report(
    *,
    repo_root: Path,
    config: ContinuityReadinessConfig | None = None,
    migration_report: Mapping[str, Any] | None = None,
    observability_events: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = config or ContinuityReadinessConfig()
    repo = Path(repo_root).resolve()
    alpha = evaluate_local_alpha_hosting(cfg.hosting_config())
    auth = auth_provider_decision_package(cfg.auth_provider_strategy)
    e2ee = key_lifecycle_contract()
    migration_contract = migration_portability_contract()
    reset = password_reset_boundary_contract()
    trust = trusted_device_approval_contract()
    restore = restore_lost_phone_simulator_contract()
    deletion = delete_purge_honesty_contract()
    support = support_monitoring_contract(observability_events)
    migration = dict(migration_report or {"ok": False, "skipped": True, "reason": "migration_drill_not_run"})
    report: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "repo_root_name": repo.name,
        "component_ready_target": True,
        "system_ready": False,
        "production_ready": False,
        "real_life_load_app_touched": False,
        "product_cloud_backup_claim_introduced": False,
        "config": {
            "environment": cfg.environment,
            "non_local_access": cfg.non_local_access,
            "tls_enabled": cfg.tls_enabled,
            "secure_tunnel_enabled": cfg.secure_tunnel_enabled,
            "public_http_enabled": cfg.public_http_enabled,
            "router_port_forwarding_enabled": cfg.router_port_forwarding_enabled,
            "auth_provider_strategy": cfg.auth_provider_strategy,
        },
        "auth_provider_decision": auth,
        "local_alpha_preflight": alpha,
        "e2ee_lifecycle": e2ee,
        "password_reset_boundary": reset,
        "trusted_device_recovery": trust,
        "restore_lost_phone_simulator": restore,
        "delete_purge_honesty": deletion,
        "support_monitoring": support,
        "migration_portability": migration_contract,
        "migration_rehearsal": migration,
        "acceptance": {
            "local_alpha_preflight_ok": alpha["ok"] is True,
            "migration_rehearsal_ok": migration.get("ok") is True,
            "auth_provider_decision_recorded": auth["production_provider_selected"] is False,
            "e2ee_backend_untrusted": e2ee["backend_treated_as_untrusted_storage"] is True,
            "password_reset_account_only": reset["recovers_private_history"] is False,
            "restore_simulator_backend_test_app_only": restore["real_life_load_app_touched"] is False,
            "delete_purge_no_false_claim": deletion["production_permanent_delete_claim_allowed"] is False,
            "support_monitoring_no_decrypt": support["support_can_decrypt_private_history"] is False,
            "migration_requires_no_decryption": migration_contract["requires_payload_decryption"] is False,
        },
        "known_gaps": [
            "external_crypto_review_not_done",
            "production_auth_provider_not_selected",
            "real_life_load_app_integration_deferred",
            "real_restore_ux_not_validated",
            "production_hosting_not_selected",
            "hard_purge_not_implemented",
            "production_monitoring_not_deployed",
            "real_support_process_not_operational",
        ],
        "recommendations": [
            "keep current work backend/test-app only until MVP4 integration gate",
            "choose auth provider after current EU hosting and vendor terms review",
            "run Android Backend Test App E2EE and continuity scenarios before any alpha window",
            "run migration/export/import rehearsal before moving from local alpha to hosted server",
        ],
        "redacted": True,
    }
    report["privacy_scan"] = privacy_scan_report(report)
    report["ok"] = all(report["acceptance"].values()) and report["privacy_scan"]["ok"]
    return report


def privacy_scan_report(report: Mapping[str, Any]) -> dict[str, Any]:
    text = json.dumps(report, sort_keys=True).lower()
    hits = sorted(term for term in FORBIDDEN_REPORT_TERMS if term in text)
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "ok": not hits,
        "forbidden_term_count": len(hits),
        "forbidden_terms": hits,
        "redacted": True,
    }


def render_continuity_readiness_markdown(report: Mapping[str, Any]) -> str:
    acceptance = dict(report["acceptance"])
    def fmt(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    lines = [
        "# Life Load Continuity Readiness Report",
        "",
        f"- ok: `{fmt(report['ok'])}`",
        f"- component_ready_target: `{fmt(report['component_ready_target'])}`",
        f"- system_ready: `{fmt(report['system_ready'])}`",
        f"- production_ready: `{fmt(report['production_ready'])}`",
        f"- real_life_load_app_touched: `{fmt(report['real_life_load_app_touched'])}`",
        f"- product_cloud_backup_claim_introduced: `{fmt(report['product_cloud_backup_claim_introduced'])}`",
        "",
        "## Acceptance",
        "",
    ]
    for key, value in sorted(acceptance.items()):
        lines.append(f"- `{key}`: `{fmt(value)}`")
    lines.extend(
        [
            "",
            "## Auth Provider",
            "",
            f"- alpha_decision: `{report['auth_provider_decision']['alpha_decision']}`",
            f"- later_gate: `{report['auth_provider_decision']['later_decision_gate']}`",
            f"- production_provider_selected: `{fmt(report['auth_provider_decision']['production_provider_selected'])}`",
            "",
            "## Alpha Preflight",
            "",
            f"- ok: `{fmt(report['local_alpha_preflight']['ok'])}`",
            f"- fatal: `{', '.join(report['local_alpha_preflight']['fatal'])}`",
            f"- missing: `{', '.join(report['local_alpha_preflight']['missing'])}`",
            "",
            "## Migration",
            "",
            f"- ok: `{fmt(report['migration_rehearsal'].get('ok'))}`",
            f"- active_manifest_count: `{report['migration_rehearsal'].get('active_manifest_count', 'n/a')}`",
            f"- purge_job_count: `{report['migration_rehearsal'].get('purge_job_count', 'n/a')}`",
            "",
            "## Delete And Purge",
            "",
            f"- delete_mode_now: `{report['delete_purge_honesty']['delete_mode_now']}`",
            f"- purge_implemented: `{fmt(report['delete_purge_honesty']['purge_implemented'])}`",
            f"- production_permanent_delete_claim_allowed: `{fmt(report['delete_purge_honesty']['production_permanent_delete_claim_allowed'])}`",
            "",
            "## Support And Monitoring",
            "",
            f"- support_can_decrypt_private_history: `{fmt(report['support_monitoring']['support_can_decrypt_private_history'])}`",
            f"- support_has_decrypt_action: `{fmt(report['support_monitoring']['support_has_decrypt_action'])}`",
            f"- observability_events: `{report['support_monitoring']['observability']['event_count']}`",
            "",
            "## Known Gaps",
            "",
        ]
    )
    for gap in report["known_gaps"]:
        lines.append(f"- `{gap}`")
    lines.extend(["", "## Privacy Scan", ""])
    lines.append(f"- ok: `{fmt(report['privacy_scan']['ok'])}`")
    lines.append(f"- forbidden_term_count: `{report['privacy_scan']['forbidden_term_count']}`")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ContinuityReadinessConfig",
    "auth_provider_decision_package",
    "build_continuity_readiness_report",
    "delete_purge_honesty_contract",
    "privacy_scan_report",
    "render_continuity_readiness_markdown",
    "restore_lost_phone_simulator_contract",
    "safe_local_alpha_config",
    "support_monitoring_contract",
]
