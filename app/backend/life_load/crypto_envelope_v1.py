"""P-INFRA2 production-algorithm crypto envelope V1 contract.

This module exposes the AES-256-GCM local/dev crypto-envelope prototype through
an explicit P-INFRA2 surface. It is still not Android-connected, not production
E2EE, and not a product backup feature.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from life_load.backup_crypto import (
    P_INFRA_CRYPTO_V1_SUITE,
    P_INFRA_CRYPTO_V1_VERSION,
    decrypt_payload_v1,
    encrypt_payload_v1,
    generate_backup_key,
    generate_recovery_key,
    unwrap_key_with_recovery_key_v1,
    validate_crypto_envelope_v1,
    wrap_key_with_recovery_key_v1,
)


REDACTED_CRYPTO_FIELDS = {"ciphertext", "tag", "nonce", "wrapped_key", "salt"}


def validate_production_algorithm_envelope_v1(
    envelope: Mapping[str, Any],
    *,
    production_like: bool = False,
    seen_nonces: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Validate the P-INFRA2 envelope contract without decrypting payloads."""

    return validate_crypto_envelope_v1(envelope, production_like=production_like, seen_nonces=seen_nonces)


def redacted_envelope_report(envelope: Mapping[str, Any], *, view_mode: str = "redacted_default") -> dict[str, Any]:
    """Return a report-safe envelope summary.

    `operator_debug` may include hashes and byte counts for operational
    inspection, but it still never includes raw ciphertext, nonce, tag, wrapped
    keys, or salts.
    """

    mode = str(view_mode or "redacted_default").strip().lower()
    if mode not in {"redacted_default", "operator_debug"}:
        raise ValueError("unsupported crypto envelope report view mode")
    aad = envelope.get("aad") if isinstance(envelope.get("aad"), Mapping) else {}
    ciphertext = str(envelope.get("ciphertext") or "")
    tag = str(envelope.get("tag") or "")
    nonce = str(envelope.get("nonce") or "")
    report: dict[str, Any] = {
        "schema_version": "life_load_crypto_envelope_v1_report",
        "view_mode": mode,
        "crypto_version": str(envelope.get("crypto_version") or ""),
        "crypto_suite": str(envelope.get("crypto_suite") or ""),
        "key_wrapping_mode": str(envelope.get("key_wrapping_mode") or ""),
        "schema_version_bound": str(envelope.get("schema_version") or aad.get("schema_version") or ""),
        "object_type": str(aad.get("object_type") or ""),
        "object_version": int(envelope.get("object_version") or aad.get("object_version") or 0),
        "prototype_only": bool(envelope.get("prototype_only")),
        "ciphertext_present": bool(ciphertext),
        "tag_present": bool(tag),
        "nonce_present": bool(nonce),
        "aad_fields": sorted(str(key) for key in aad.keys()),
        "redacted": True,
    }
    if mode == "operator_debug":
        report.update(
            {
                "key_id_hash": _short_hash(str(envelope.get("key_id") or "")),
                "object_id_hash": _short_hash(str(aad.get("object_id") or "")),
                "user_id_hash_present": bool(aad.get("user_id_hash")),
                "ciphertext_length": len(ciphertext),
                "ciphertext_sha256_present": bool(envelope.get("ciphertext_sha256")),
            }
        )
    return report


def redacted_wrapped_key_report(wrapped: Mapping[str, Any], *, view_mode: str = "redacted_default") -> dict[str, Any]:
    mode = str(view_mode or "redacted_default").strip().lower()
    if mode not in {"redacted_default", "operator_debug"}:
        raise ValueError("unsupported crypto envelope report view mode")
    report: dict[str, Any] = {
        "schema_version": "life_load_wrapped_key_v1_report",
        "view_mode": mode,
        "wrap_version": str(wrapped.get("wrap_version") or ""),
        "crypto_suite": str(wrapped.get("crypto_suite") or ""),
        "key_wrapping_mode": str(wrapped.get("key_wrapping_mode") or ""),
        "prototype_only": bool(wrapped.get("prototype_only")),
        "wrapped_key_present": bool(wrapped.get("wrapped_key")),
        "salt_present": bool(wrapped.get("salt")),
        "nonce_present": bool(wrapped.get("nonce")),
        "redacted": True,
    }
    if mode == "operator_debug":
        report["aad_hash"] = _short_hash(str(wrapped.get("aad") or ""))
    return report


def _short_hash(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "P_INFRA_CRYPTO_V1_SUITE",
    "P_INFRA_CRYPTO_V1_VERSION",
    "decrypt_payload_v1",
    "encrypt_payload_v1",
    "generate_backup_key",
    "generate_recovery_key",
    "redacted_envelope_report",
    "redacted_wrapped_key_report",
    "unwrap_key_with_recovery_key_v1",
    "validate_production_algorithm_envelope_v1",
    "wrap_key_with_recovery_key_v1",
]
