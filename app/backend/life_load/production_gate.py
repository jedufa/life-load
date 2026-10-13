"""Production promotion gate for P-INFRA backend work.

The current backend is hidden P-INFRA infrastructure. This module makes that
boundary executable so a production/public mode cannot be enabled just because
local tests happen to pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class ProductionGateError(RuntimeError):
    """Raised when a production/public backend path is requested too early."""


@dataclass(frozen=True)
class ProductionGateBlocker:
    id: str
    title: str
    category: str


PRODUCTION_GATE_BLOCKERS: tuple[ProductionGateBlocker, ...] = (
    ProductionGateBlocker("production_auth_gate", "Managed auth or Argon2id plus pepper", "auth"),
    ProductionGateBlocker("e2ee_crypto_review_gate", "Production E2EE crypto review", "crypto"),
    ProductionGateBlocker("recovery_ux_gate", "Recovery phrase/key and trusted-device UX", "recovery"),
    ProductionGateBlocker("android_secure_key_storage_gate", "Android secure key storage design", "mobile"),
    ProductionGateBlocker("tls_domain_secrets_gate", "TLS, domain, and secrets manager", "deployment"),
    ProductionGateBlocker("object_storage_gate", "Production object store and deletion proof", "storage"),
    ProductionGateBlocker("rate_limiting_abuse_gate", "Rate limiting and abuse controls", "abuse"),
    ProductionGateBlocker("observability_gate", "Sensitive-safe observability", "operations"),
    ProductionGateBlocker("purge_deletion_gate", "Purge/deletion pipeline and receipts", "deletion"),
    ProductionGateBlocker("incident_response_gate", "Incident and data-loss response runbook", "operations"),
    ProductionGateBlocker("migration_rollback_gate", "Migration rollback drill", "data"),
    ProductionGateBlocker("backup_restore_drill_gate", "Backup/restore failure drills", "continuity"),
    ProductionGateBlocker("privacy_legal_disclosure_gate", "Privacy/legal/app-store disclosures", "privacy"),
    ProductionGateBlocker("independent_security_review_gate", "Focused independent security review", "security"),
)


def list_blocking_items() -> list[dict[str, str]]:
    """Return the complete production blocker list in a redacted-safe shape."""

    return [
        {"id": blocker.id, "title": blocker.title, "category": blocker.category}
        for blocker in PRODUCTION_GATE_BLOCKERS
    ]


def get_production_gate_status(*, closed_items: Iterable[str] | None = None) -> dict[str, Any]:
    """Return gate status without claiming production readiness."""

    closed = {str(item) for item in (closed_items or ())}
    blockers = [blocker for blocker in PRODUCTION_GATE_BLOCKERS if blocker.id not in closed]
    return {
        "schema_version": "life_load_production_gate_v1",
        "gate": "ACCEPT-P-INFRA2-production-promotion",
        "closed": not blockers,
        "production_ready": False,
        "product_backup_ready": False,
        "public_mode_allowed": not blockers,
        "blocking_count": len(blockers),
        "blocking_items": [
            {"id": blocker.id, "title": blocker.title, "category": blocker.category}
            for blocker in blockers
        ],
    }


def assert_not_production_enabled(config: Mapping[str, Any] | None = None) -> None:
    """Fail closed if a production/public P-INFRA backend is requested."""

    values = dict(config or {})
    app_env = _env_name(values)
    public_requested = _truthy(values.get("remote_backend_public")) or _truthy(values.get("public_endpoints_enabled"))
    if app_env == "production" or public_requested:
        raise ProductionGateError("P-INFRA production/public backend is blocked by production promotion gate")


def require_gate_closed_for_public_mode(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Allow public mode only when every production blocker is explicitly closed.

    Tests may pass ``allow_open_gate_for_tests`` to inspect downstream validation
    without turning that into a real product gate.
    """

    values = dict(config or {})
    status = get_production_gate_status(closed_items=values.get("closed_gate_items") or ())
    public_requested = _env_name(values) == "production" or _truthy(values.get("remote_backend_public"))
    if public_requested and not status["closed"] and not _truthy(values.get("allow_open_gate_for_tests")):
        raise ProductionGateError("production promotion gate has open blockers")
    return status


def _env_name(values: Mapping[str, Any]) -> str:
    raw = str(values.get("app_env") or values.get("mode") or "local").strip().lower()
    if raw == "prod":
        return "production"
    if raw not in {"local", "dev", "staging", "production"}:
        return "local"
    return raw


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
