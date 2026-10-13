"""P-INFRA2 deployment environment validator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from life_load.production_gate import ProductionGateError, require_gate_closed_for_public_mode
from life_load.secrets_config import RedactedSecretSummary


VALID_APP_ENVS = {"local", "dev", "staging", "production"}
LOCAL_ENVS = {"local", "dev"}
LOCAL_OBJECT_STORES = {"sqlite", "sqlite_blob", "local_file", "memory"}
PRODUCTION_OBJECT_STORES = {"s3_compatible", "managed_object_store"}


class EnvironmentValidationError(RuntimeError):
    """Raised when an unsafe backend environment combination is requested."""


@dataclass(frozen=True)
class BackendEnvironmentConfig:
    app_env: str = "local"
    enable_dev_console: bool = False
    enable_backend_test_app: bool = False
    allow_lan_dev_server: bool = False
    allow_lan_backend_test_app: bool = False
    remote_backend_public: bool = False
    db_path: str = ""
    object_store_mode: str = "sqlite"
    secret_mode: str = "local_ephemeral"
    tls_required: bool = False
    strict_crypto_mode: bool = False
    staging_debug: bool = False
    staging_fixture_namespace_only: bool = False
    allow_local_tls_tunnel: bool = False
    allow_open_gate_for_tests: bool = False
    closed_gate_items: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None = None) -> "BackendEnvironmentConfig":
        raw = dict(values or {})
        app_env = _normalize_env(raw.get("APP_ENV") or raw.get("LIFE_LOAD_APP_ENV") or raw.get("app_env") or raw.get("mode"))
        return cls(
            app_env=app_env,
            enable_dev_console=_truthy(raw.get("LIFE_LOAD_ENABLE_DEV_CONSOLE") or raw.get("enable_dev_console")),
            enable_backend_test_app=_truthy(
                raw.get("LIFE_LOAD_ENABLE_BACKEND_TEST_APP") or raw.get("enable_backend_test_app")
            ),
            allow_lan_dev_server=_truthy(
                raw.get("LIFE_LOAD_ALLOW_LAN_DEV_SERVER") or raw.get("allow_lan_dev_server")
            ),
            allow_lan_backend_test_app=_truthy(
                raw.get("LIFE_LOAD_ALLOW_LAN_BACKEND_TEST_APP") or raw.get("allow_lan_backend_test_app")
            ),
            remote_backend_public=_truthy(
                raw.get("LIFE_LOAD_REMOTE_BACKEND_PUBLIC")
                or raw.get("remote_backend_public")
                or raw.get("public_endpoints_enabled")
            ),
            db_path=str(raw.get("LIFE_LOAD_DB_PATH") or raw.get("db_path") or ""),
            object_store_mode=str(raw.get("LIFE_LOAD_OBJECT_STORE_MODE") or raw.get("object_store_mode") or "sqlite")
            .strip()
            .lower(),
            secret_mode=str(raw.get("LIFE_LOAD_SECRET_MODE") or raw.get("secret_mode") or "local_ephemeral")
            .strip()
            .lower(),
            tls_required=_truthy(raw.get("LIFE_LOAD_TLS_REQUIRED") or raw.get("tls_required")),
            strict_crypto_mode=_truthy(raw.get("LIFE_LOAD_STRICT_CRYPTO_MODE") or raw.get("strict_crypto_mode")),
            staging_debug=_truthy(raw.get("LIFE_LOAD_STAGING_DEBUG") or raw.get("staging_debug")),
            staging_fixture_namespace_only=_truthy(
                raw.get("LIFE_LOAD_STAGING_FIXTURE_NAMESPACE_ONLY") or raw.get("staging_fixture_namespace_only")
            ),
            allow_local_tls_tunnel=_truthy(raw.get("LIFE_LOAD_ALLOW_LOCAL_TLS_TUNNEL") or raw.get("allow_local_tls_tunnel")),
            allow_open_gate_for_tests=_truthy(raw.get("allow_open_gate_for_tests")),
            closed_gate_items=tuple(str(item) for item in (raw.get("closed_gate_items") or ())),
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "BackendEnvironmentConfig":
        return cls.from_mapping(dict(environ or os.environ))


def validate_environment_config(
    config: BackendEnvironmentConfig | Mapping[str, Any] | None = None,
    *,
    secret_summary: RedactedSecretSummary | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config if isinstance(config, BackendEnvironmentConfig) else BackendEnvironmentConfig.from_mapping(config)
    missing: list[str] = []
    warnings: list[str] = []
    fatal: list[str] = []

    if cfg.app_env not in VALID_APP_ENVS:
        fatal.append("invalid_app_env")

    if cfg.app_env in LOCAL_ENVS:
        if cfg.remote_backend_public:
            fatal.append("local_dev_public_backend_blocked")
        if cfg.allow_lan_dev_server:
            warnings.append("lan_developer_server_explicitly_enabled")
        if cfg.enable_dev_console:
            warnings.append("developer_console_enabled_local_only")
        if cfg.enable_backend_test_app:
            warnings.append("backend_test_app_enabled_local_only")

    if cfg.app_env == "staging":
        if cfg.enable_dev_console and not cfg.staging_debug:
            fatal.append("staging_dev_console_blocked")
        if cfg.enable_backend_test_app and not cfg.staging_fixture_namespace_only:
            fatal.append("staging_backend_test_app_requires_fixture_namespace")
        if not cfg.strict_crypto_mode:
            missing.append("strict_crypto_mode")
        if not cfg.tls_required and not cfg.allow_local_tls_tunnel:
            missing.append("tls_required")
        if cfg.object_store_mode in LOCAL_OBJECT_STORES:
            missing.append("non_local_object_store")

    if cfg.app_env == "production":
        if cfg.enable_dev_console:
            fatal.append("production_dev_console_blocked")
        if cfg.enable_backend_test_app:
            fatal.append("production_backend_test_app_blocked")
        if cfg.allow_lan_dev_server or cfg.allow_lan_backend_test_app:
            fatal.append("production_debug_lan_flags_blocked")
        if not cfg.strict_crypto_mode:
            missing.append("strict_crypto_mode")
        if not cfg.tls_required:
            missing.append("tls_required")
        if cfg.secret_mode not in {"env", "secret_manager", "managed"}:
            missing.append("secret_manager")
        if cfg.object_store_mode not in PRODUCTION_OBJECT_STORES:
            missing.append("production_object_store")
        if _is_local_db_path(cfg.db_path):
            fatal.append("production_local_sqlite_db_blocked")
        try:
            require_gate_closed_for_public_mode(
                {
                    "app_env": cfg.app_env,
                    "remote_backend_public": cfg.remote_backend_public,
                    "closed_gate_items": cfg.closed_gate_items,
                    "allow_open_gate_for_tests": cfg.allow_open_gate_for_tests,
                }
            )
        except ProductionGateError:
            fatal.append("production_gate_open")

    if secret_summary is not None:
        summary = secret_summary.as_dict() if isinstance(secret_summary, RedactedSecretSummary) else dict(secret_summary)
        if cfg.app_env in {"staging", "production"}:
            if summary.get("missing"):
                missing.append("required_secrets")
            if summary.get("ephemeral"):
                fatal.append("ephemeral_secrets_blocked")
            if summary.get("provider") == "file":
                fatal.append("file_secret_provider_blocked")

    ok = not missing and not fatal
    return {
        "schema_version": "life_load_backend_environment_model_v1",
        "app_env": cfg.app_env,
        "ok": ok,
        "local_only": cfg.app_env in LOCAL_ENVS,
        "developer_console_allowed": cfg.enable_dev_console and cfg.app_env in LOCAL_ENVS,
        "backend_test_app_allowed": cfg.enable_backend_test_app
        and (cfg.app_env in LOCAL_ENVS or (cfg.app_env == "staging" and cfg.staging_fixture_namespace_only)),
        "remote_backend_public": cfg.remote_backend_public if cfg.app_env == "production" else False,
        "strict_crypto_mode": cfg.strict_crypto_mode,
        "tls_required": cfg.tls_required,
        "object_store_mode": cfg.object_store_mode,
        "secret_mode": cfg.secret_mode,
        "missing": sorted(set(missing)),
        "fatal": sorted(set(fatal)),
        "warnings": sorted(set(warnings)),
        "redacted": True,
    }


def assert_environment_allowed(
    config: BackendEnvironmentConfig | Mapping[str, Any] | None = None,
    *,
    secret_summary: RedactedSecretSummary | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status = validate_environment_config(config, secret_summary=secret_summary)
    if not status["ok"]:
        raise EnvironmentValidationError("unsafe backend environment configuration")
    return status


def _normalize_env(value: Any) -> str:
    raw = str(value or "local").strip().lower()
    if raw == "prod":
        return "production"
    return raw if raw in VALID_APP_ENVS else "local"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_local_db_path(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lower = text.lower()
    if lower.startswith(("postgres://", "postgresql://", "mysql://", "secret://", "vault://")):
        return False
    path = Path(text)
    return (
        lower.endswith((".sqlite", ".sqlite3", ".db"))
        or "runtime/" in lower
        or "runtime\\" in lower
        or "data/" in lower
        or "data\\" in lower
        or not path.is_absolute() and "://" not in lower
    )
