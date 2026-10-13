"""Secret-provider contract for P-INFRA2 backend preparation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol


SECRET_CLASSES: tuple[str, ...] = (
    "session_token_hmac_secret",
    "password_pepper",
    "api_signing_secret",
    "object_store_credentials",
    "database_credentials",
    "tls_private_key_ref",
    "encryption_service_key_ref",
    "monitoring_webhook_secret",
    "future_kms_key_ref",
)

PRODUCTION_REQUIRED_SECRETS: tuple[str, ...] = (
    "session_token_hmac_secret",
    "password_pepper",
    "object_store_credentials",
    "database_credentials",
    "tls_private_key_ref",
)

ENV_SECRET_NAMES: Mapping[str, str] = {
    "session_token_hmac_secret": "LIFE_LOAD_SESSION_TOKEN_HMAC_SECRET",
    "password_pepper": "LIFE_LOAD_PASSWORD_PEPPER",
    "api_signing_secret": "LIFE_LOAD_API_SIGNING_SECRET",
    "object_store_credentials": "LIFE_LOAD_OBJECT_STORE_CREDENTIALS",
    "database_credentials": "LIFE_LOAD_DATABASE_CREDENTIALS",
    "tls_private_key_ref": "LIFE_LOAD_TLS_PRIVATE_KEY_REF",
    "encryption_service_key_ref": "LIFE_LOAD_ENCRYPTION_SERVICE_KEY_REF",
    "monitoring_webhook_secret": "LIFE_LOAD_MONITORING_WEBHOOK_SECRET",
    "future_kms_key_ref": "LIFE_LOAD_FUTURE_KMS_KEY_REF",
}


class MissingSecretError(RuntimeError):
    """Raised when a required secret is unavailable."""


class SecretProvider(Protocol):
    name: str

    def get_secret(self, secret_class: str) -> str | None:
        """Return the secret value for internal use, or None if missing."""


@dataclass(frozen=True)
class RedactedSecretSummary:
    provider: str
    configured: tuple[str, ...]
    missing: tuple[str, ...]
    ephemeral: bool = False
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "life_load_secret_summary_v1",
            "provider": self.provider,
            "configured": list(self.configured),
            "missing": list(self.missing),
            "ephemeral": self.ephemeral,
            "warnings": list(self.warnings),
            "redacted": True,
        }


@dataclass(frozen=True)
class EnvSecretProvider:
    environ: Mapping[str, str] | None = None
    name: str = "env"

    def get_secret(self, secret_class: str) -> str | None:
        env = self.environ if self.environ is not None else os.environ
        variable = ENV_SECRET_NAMES.get(secret_class)
        if not variable:
            return None
        value = str(env.get(variable) or "").strip()
        return value or None


@dataclass(frozen=True)
class FileSecretProvider:
    path: Path
    app_env: str = "local"
    name: str = "file"

    def get_secret(self, secret_class: str) -> str | None:
        if self.app_env not in {"local", "dev"}:
            raise MissingSecretError("file secret provider is local/dev only")
        path = Path(self.path)
        if path.is_dir():
            target = path / secret_class
            return target.read_text(encoding="utf-8").strip() if target.exists() else None
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise MissingSecretError("file secret provider could not read local secrets") from exc
            if isinstance(payload, Mapping):
                value = str(payload.get(secret_class) or "").strip()
                return value or None
        return None


@dataclass(frozen=True)
class EphemeralLocalSecretProvider:
    """Local/dev-only placeholder used to make missing-secret warnings explicit."""

    name: str = "local_ephemeral"

    def get_secret(self, secret_class: str) -> str | None:
        if secret_class in SECRET_CLASSES:
            return f"ephemeral:{secret_class}"
        return None


def summarize_secret_provider(
    provider: SecretProvider,
    *,
    required: tuple[str, ...] = PRODUCTION_REQUIRED_SECRETS,
    app_env: str = "local",
) -> RedactedSecretSummary:
    configured: list[str] = []
    missing: list[str] = []
    for secret_class in SECRET_CLASSES:
        try:
            value = provider.get_secret(secret_class)
        except MissingSecretError:
            value = None
        if value:
            configured.append(secret_class)
        elif secret_class in required:
            missing.append(secret_class)

    warnings: list[str] = []
    ephemeral = isinstance(provider, EphemeralLocalSecretProvider)
    if ephemeral:
        warnings.append("local_ephemeral_secrets_not_for_staging_or_production")
    if app_env in {"staging", "production"} and provider.name in {"file", "local_ephemeral"}:
        warnings.append("staging_production_require_secret_provider")

    return RedactedSecretSummary(
        provider=provider.name,
        configured=tuple(sorted(configured)),
        missing=tuple(sorted(missing)),
        ephemeral=ephemeral,
        warnings=tuple(warnings),
    )


def require_secrets(summary: RedactedSecretSummary) -> None:
    if summary.missing:
        raise MissingSecretError("missing required secrets")
    if "staging_production_require_secret_provider" in summary.warnings:
        raise MissingSecretError("invalid secret provider for staging/production")
