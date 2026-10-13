"""Local crypto-envelope prototype for future E2EE backup.

This module is P-INFRA groundwork only. It is not connected to Android, not used
for real user data, and not a production crypto decision. The implementation uses cryptography for AEAD primitives. Tests exercise
envelope, AAD, tamper, and recovery-key semantics; this is not a production
security audit.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CRYPTO_PROTOTYPE_VERSION = "life_load_backup_crypto_prototype_v1"
P_INFRA_CRYPTO_V1_VERSION = "life_load_p_infra_crypto_v1"
P_INFRA_CRYPTO_V1_SUITE = "AES-256-GCM"
DEFAULT_KDF_ITERATIONS = 210_000
KEY_BYTES = 32
AES_GCM_NONCE_BYTES = 12
NONCE_BYTES = 24
SALT_BYTES = 16
TAG_BYTES = 32
RECOVERY_KEY_BYTES = 32
REQUIRED_AAD_FIELDS = {"user_id_hash", "object_type", "object_id", "object_version", "schema_version"}
LOCAL_DEV_WRAPPERS = {"raw_test_key", "recovery_key_prototype", "future_device_key_placeholder"}


def generate_backup_key() -> bytes:
    return secrets.token_bytes(KEY_BYTES)


def generate_recovery_key() -> str:
    return _b64encode(secrets.token_bytes(RECOVERY_KEY_BYTES))


def encrypt_payload_v1(
    payload: Mapping[str, Any],
    *,
    data_key: bytes,
    aad_fields: Mapping[str, Any],
    key_wrapping_mode: str = "raw_test_key",
    key_id: str = "local-dev-key",
) -> dict[str, Any]:
    """Encrypt with real AEAD primitives for local/dev contract testing only."""

    _require_key(data_key, field="data_key")
    aad = _canonical_aad(aad_fields)
    nonce = secrets.token_bytes(AES_GCM_NONCE_BYTES)
    encrypted = AESGCM(data_key).encrypt(nonce, _canonical_json(payload), aad)
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    return {
        "envelope_version": 1,
        "crypto_version": P_INFRA_CRYPTO_V1_VERSION,
        "crypto_suite": P_INFRA_CRYPTO_V1_SUITE,
        "key_wrapping_mode": _normalize_wrapping_mode(key_wrapping_mode),
        "schema_version": str(aad_fields["schema_version"]),
        "object_version": int(aad_fields["object_version"]),
        "created_at": str(aad_fields.get("created_at") or ""),
        "key_id": key_id,
        "prototype_only": True,
        "aad": dict(aad_fields),
        "nonce": _b64encode(nonce),
        "ciphertext": _b64encode(ciphertext),
        "tag": _b64encode(tag),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }


def decrypt_payload_v1(envelope: Mapping[str, Any], *, data_key: bytes, aad_fields: Mapping[str, Any]) -> dict[str, Any]:
    _require_key(data_key, field="data_key")
    validate_crypto_envelope_v1(envelope, production_like=False)
    expected_aad = _canonical_aad(aad_fields)
    if not hmac.compare_digest(_canonical_aad(envelope.get("aad") or {}), expected_aad):
        raise ValueError("aad mismatch")
    nonce = _b64decode(str(envelope.get("nonce") or ""), field="nonce")
    ciphertext = _b64decode(str(envelope.get("ciphertext") or ""), field="ciphertext")
    tag = _b64decode(str(envelope.get("tag") or ""), field="tag")
    expected_sha = hashlib.sha256(ciphertext).hexdigest()
    if not hmac.compare_digest(str(envelope.get("ciphertext_sha256") or ""), expected_sha):
        raise ValueError("ciphertext checksum mismatch")
    try:
        plaintext = AESGCM(data_key).decrypt(nonce, ciphertext + tag, expected_aad)
    except InvalidTag as exc:
        raise ValueError("authentication failed") from exc
    value = json.loads(plaintext.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("payload must be a JSON object")
    return value


def validate_crypto_envelope_v1(
    envelope: Mapping[str, Any],
    *,
    production_like: bool,
    seen_nonces: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if envelope.get("crypto_version") != P_INFRA_CRYPTO_V1_VERSION:
        raise ValueError("unsupported crypto_version")
    if envelope.get("crypto_suite") != P_INFRA_CRYPTO_V1_SUITE:
        raise ValueError("unsupported crypto_suite")
    wrapping_mode = _normalize_wrapping_mode(str(envelope.get("key_wrapping_mode") or ""))
    if production_like and (envelope.get("prototype_only") is True or wrapping_mode in LOCAL_DEV_WRAPPERS):
        raise ValueError("production-like mode cannot use local/dev crypto wrappers")
    aad = envelope.get("aad")
    if not isinstance(aad, dict) or REQUIRED_AAD_FIELDS.difference(aad):
        raise ValueError("missing AAD fields")
    nonce = _b64decode(str(envelope.get("nonce") or ""), field="nonce")
    if len(nonce) != AES_GCM_NONCE_BYTES:
        raise ValueError("invalid nonce length")
    _b64decode(str(envelope.get("ciphertext") or ""), field="ciphertext")
    _b64decode(str(envelope.get("tag") or ""), field="tag")
    if seen_nonces is not None:
        key_id = str(envelope.get("key_id") or "")
        nonce_key = (key_id, str(envelope.get("nonce") or ""))
        if nonce_key in seen_nonces:
            raise ValueError("nonce reuse detected")
        seen_nonces.add(nonce_key)
    for field in ("crypto_suite", "key_wrapping_mode", "nonce"):
        if str(envelope.get(field) or "").strip() in {"", "TBD", "test-nonce"}:
            raise ValueError("placeholder crypto metadata")
    return dict(envelope)


def wrap_key_with_recovery_key_v1(
    data_key: bytes,
    *,
    recovery_key: str,
    aad_fields: Mapping[str, Any],
    iterations: int = DEFAULT_KDF_ITERATIONS,
) -> dict[str, Any]:
    _require_key(data_key, field="data_key")
    recovery_key_bytes = _b64decode(recovery_key, field="recovery_key")
    salt = secrets.token_bytes(SALT_BYTES)
    wrapping_key = hashlib.pbkdf2_hmac("sha256", recovery_key_bytes, salt, iterations, dklen=KEY_BYTES)
    aad = _canonical_aad(aad_fields)
    nonce = secrets.token_bytes(AES_GCM_NONCE_BYTES)
    encrypted = AESGCM(wrapping_key).encrypt(nonce, data_key, aad)
    return {
        "wrap_version": P_INFRA_CRYPTO_V1_VERSION,
        "crypto_suite": P_INFRA_CRYPTO_V1_SUITE,
        "key_wrapping_mode": "recovery_key_prototype",
        "prototype_only": True,
        "iterations": iterations,
        "aad": dict(aad_fields),
        "salt": _b64encode(salt),
        "nonce": _b64encode(nonce),
        "wrapped_key": _b64encode(encrypted),
    }


def unwrap_key_with_recovery_key_v1(
    wrapped: Mapping[str, Any],
    *,
    recovery_key: str,
    aad_fields: Mapping[str, Any],
) -> bytes:
    if wrapped.get("wrap_version") != P_INFRA_CRYPTO_V1_VERSION:
        raise ValueError("unsupported wrap_version")
    if wrapped.get("prototype_only") is not True:
        raise ValueError("unexpected production wrapper label")
    if _normalize_wrapping_mode(str(wrapped.get("key_wrapping_mode") or "")) != "recovery_key_prototype":
        raise ValueError("unsupported key_wrapping_mode")
    aad = _canonical_aad(aad_fields)
    if not hmac.compare_digest(_canonical_aad(wrapped.get("aad") or {}), aad):
        raise ValueError("aad mismatch")
    recovery_key_bytes = _b64decode(recovery_key, field="recovery_key")
    salt = _b64decode(str(wrapped.get("salt") or ""), field="salt")
    nonce = _b64decode(str(wrapped.get("nonce") or ""), field="nonce")
    ciphertext = _b64decode(str(wrapped.get("wrapped_key") or ""), field="wrapped_key")
    wrapping_key = hashlib.pbkdf2_hmac(
        "sha256", recovery_key_bytes, salt, int(wrapped.get("iterations") or 0), dklen=KEY_BYTES
    )
    try:
        data_key = AESGCM(wrapping_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise ValueError("authentication failed") from exc
    _require_key(data_key, field="data_key")
    return data_key


def encrypt_payload_for_test(
    payload: Mapping[str, Any],
    *,
    backup_key: bytes,
    aad: str,
) -> dict[str, Any]:
    _require_key(backup_key, field="backup_key")
    plaintext = _canonical_json(payload)
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = _xor_stream(plaintext, backup_key=backup_key, nonce=nonce, aad=aad)
    tag = _auth_tag(backup_key=backup_key, nonce=nonce, aad=aad, ciphertext=ciphertext)
    return {
        "crypto_version": CRYPTO_PROTOTYPE_VERSION,
        "algorithm": "prototype_hmac_sha256_stream_xor",
        "production_ready": False,
        "aad": aad,
        "nonce": _b64encode(nonce),
        "ciphertext": _b64encode(ciphertext),
        "tag": _b64encode(tag),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }


def decrypt_payload_for_test(envelope: Mapping[str, Any], *, backup_key: bytes, aad: str) -> dict[str, Any]:
    _require_key(backup_key, field="backup_key")
    if envelope.get("crypto_version") != CRYPTO_PROTOTYPE_VERSION:
        raise ValueError("unsupported crypto_version")
    if envelope.get("production_ready") is not False:
        raise ValueError("prototype envelope must not be marked production ready")
    if str(envelope.get("aad") or "") != aad:
        raise ValueError("aad mismatch")
    nonce = _b64decode(str(envelope.get("nonce") or ""), field="nonce")
    ciphertext = _b64decode(str(envelope.get("ciphertext") or ""), field="ciphertext")
    tag = _b64decode(str(envelope.get("tag") or ""), field="tag")
    expected_tag = _auth_tag(backup_key=backup_key, nonce=nonce, aad=aad, ciphertext=ciphertext)
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("authentication tag mismatch")
    expected_sha = hashlib.sha256(ciphertext).hexdigest()
    if not hmac.compare_digest(str(envelope.get("ciphertext_sha256") or ""), expected_sha):
        raise ValueError("ciphertext checksum mismatch")
    plaintext = _xor_stream(ciphertext, backup_key=backup_key, nonce=nonce, aad=aad)
    value = json.loads(plaintext.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("payload must be a JSON object")
    return value


def wrap_backup_key_with_recovery_key(
    backup_key: bytes,
    *,
    recovery_key: str,
    aad: str,
    iterations: int = DEFAULT_KDF_ITERATIONS,
) -> dict[str, Any]:
    _require_key(backup_key, field="backup_key")
    recovery_key_bytes = _b64decode(recovery_key, field="recovery_key")
    if len(recovery_key_bytes) != RECOVERY_KEY_BYTES:
        raise ValueError("recovery_key length is invalid")
    salt = secrets.token_bytes(SALT_BYTES)
    wrapping_key = hashlib.pbkdf2_hmac("sha256", recovery_key_bytes, salt, iterations, dklen=KEY_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    wrapped_key = _xor_stream(backup_key, backup_key=wrapping_key, nonce=nonce, aad=aad)
    tag = _auth_tag(backup_key=wrapping_key, nonce=nonce, aad=aad, ciphertext=wrapped_key)
    return {
        "wrap_version": CRYPTO_PROTOTYPE_VERSION,
        "wrap_algorithm": "prototype_pbkdf2_hmac_sha256_stream_xor",
        "production_ready": False,
        "kdf": "pbkdf2_hmac_sha256",
        "iterations": iterations,
        "aad": aad,
        "salt": _b64encode(salt),
        "nonce": _b64encode(nonce),
        "wrapped_backup_key": _b64encode(wrapped_key),
        "tag": _b64encode(tag),
    }


def unwrap_backup_key_with_recovery_key(
    wrapped: Mapping[str, Any],
    *,
    recovery_key: str,
    aad: str,
) -> bytes:
    if wrapped.get("wrap_version") != CRYPTO_PROTOTYPE_VERSION:
        raise ValueError("unsupported wrap_version")
    if wrapped.get("production_ready") is not False:
        raise ValueError("prototype wrap must not be marked production ready")
    if str(wrapped.get("aad") or "") != aad:
        raise ValueError("aad mismatch")
    iterations = int(wrapped.get("iterations") or 0)
    if iterations < 100_000:
        raise ValueError("kdf iterations too low")
    recovery_key_bytes = _b64decode(recovery_key, field="recovery_key")
    salt = _b64decode(str(wrapped.get("salt") or ""), field="salt")
    nonce = _b64decode(str(wrapped.get("nonce") or ""), field="nonce")
    ciphertext = _b64decode(str(wrapped.get("wrapped_backup_key") or ""), field="wrapped_backup_key")
    tag = _b64decode(str(wrapped.get("tag") or ""), field="tag")
    wrapping_key = hashlib.pbkdf2_hmac("sha256", recovery_key_bytes, salt, iterations, dklen=KEY_BYTES)
    expected_tag = _auth_tag(backup_key=wrapping_key, nonce=nonce, aad=aad, ciphertext=ciphertext)
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("authentication tag mismatch")
    backup_key = _xor_stream(ciphertext, backup_key=wrapping_key, nonce=nonce, aad=aad)
    _require_key(backup_key, field="unwrapped_backup_key")
    return backup_key


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_aad(value: Mapping[str, Any]) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("aad must be an object")
    missing = REQUIRED_AAD_FIELDS.difference(value)
    if missing:
        raise ValueError("missing AAD fields")
    return _canonical_json({key: value[key] for key in sorted(REQUIRED_AAD_FIELDS)})


def _normalize_wrapping_mode(value: str) -> str:
    mode = str(value or "").strip()
    if mode in {"", "TBD"}:
        raise ValueError("unsupported key_wrapping_mode")
    allowed = LOCAL_DEV_WRAPPERS.union({"device_key_wrapped", "recovery_key_wrapped"})
    if mode not in allowed:
        raise ValueError("unsupported key_wrapping_mode")
    return mode


def _xor_stream(data: bytes, *, backup_key: bytes, nonce: bytes, aad: str) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(data):
        block = hmac.new(
            backup_key,
            nonce + counter.to_bytes(8, "big") + str(aad).encode("utf-8"),
            hashlib.sha256,
        ).digest()
        output.extend(block)
        counter += 1
    return bytes(left ^ right for left, right in zip(data, output))


def _auth_tag(*, backup_key: bytes, nonce: bytes, aad: str, ciphertext: bytes) -> bytes:
    return hmac.new(
        backup_key,
        b"life_load_backup_crypto_prototype|" + nonce + str(aad).encode("utf-8") + ciphertext,
        hashlib.sha256,
    ).digest()[:TAG_BYTES]


def _require_key(value: bytes, *, field: str) -> None:
    if not isinstance(value, bytes) or len(value) != KEY_BYTES:
        raise ValueError(f"{field} must be {KEY_BYTES} bytes")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str, *, field: str) -> bytes:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode((text + padding).encode("ascii"))
    except Exception as exc:
        raise ValueError(f"{field} is not valid base64url") from exc
