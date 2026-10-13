from __future__ import annotations

import pytest

from life_load.backup_crypto import (
    CRYPTO_PROTOTYPE_VERSION,
    P_INFRA_CRYPTO_V1_SUITE,
    P_INFRA_CRYPTO_V1_VERSION,
    decrypt_payload_for_test,
    decrypt_payload_v1,
    encrypt_payload_for_test,
    encrypt_payload_v1,
    generate_backup_key,
    generate_recovery_key,
    unwrap_key_with_recovery_key_v1,
    unwrap_backup_key_with_recovery_key,
    validate_crypto_envelope_v1,
    wrap_key_with_recovery_key_v1,
    wrap_backup_key_with_recovery_key,
)


def test_crypto_prototype_encrypts_and_decrypts_payload_without_plaintext_in_envelope() -> None:
    backup_key = generate_backup_key()
    payload = {
        "diary_text": "private local diary text",
        "mood": "low",
        "entry_count": 1,
    }

    envelope = encrypt_payload_for_test(payload, backup_key=backup_key, aad="namespace:device:v1")

    assert envelope["crypto_version"] == CRYPTO_PROTOTYPE_VERSION
    assert envelope["production_ready"] is False
    assert "private local diary text" not in str(envelope)
    assert decrypt_payload_for_test(envelope, backup_key=backup_key, aad="namespace:device:v1") == payload


def test_crypto_prototype_rejects_wrong_key_wrong_aad_and_tamper() -> None:
    backup_key = generate_backup_key()
    envelope = encrypt_payload_for_test(
        {"diary_text": "private"},
        backup_key=backup_key,
        aad="namespace:device:v1",
    )

    with pytest.raises(ValueError, match="authentication tag"):
        decrypt_payload_for_test(envelope, backup_key=generate_backup_key(), aad="namespace:device:v1")

    with pytest.raises(ValueError, match="aad"):
        decrypt_payload_for_test(envelope, backup_key=backup_key, aad="other-aad")

    tampered = dict(envelope)
    tampered["ciphertext"] = tampered["ciphertext"][:-1] + ("A" if tampered["ciphertext"][-1] != "A" else "B")
    with pytest.raises(ValueError):
        decrypt_payload_for_test(tampered, backup_key=backup_key, aad="namespace:device:v1")


def test_crypto_prototype_wraps_backup_key_with_recovery_key() -> None:
    backup_key = generate_backup_key()
    recovery_key = generate_recovery_key()

    wrapped = wrap_backup_key_with_recovery_key(
        backup_key,
        recovery_key=recovery_key,
        aad="user:namespace:recovery:v1",
    )

    assert wrapped["production_ready"] is False
    assert "wrapped_backup_key" in wrapped
    assert backup_key.hex() not in str(wrapped)
    assert unwrap_backup_key_with_recovery_key(
        wrapped,
        recovery_key=recovery_key,
        aad="user:namespace:recovery:v1",
    ) == backup_key


def test_crypto_prototype_lost_recovery_key_means_backup_key_is_unrecoverable() -> None:
    backup_key = generate_backup_key()
    wrapped = wrap_backup_key_with_recovery_key(
        backup_key,
        recovery_key=generate_recovery_key(),
        aad="user:namespace:recovery:v1",
    )

    with pytest.raises(ValueError, match="authentication tag"):
        unwrap_backup_key_with_recovery_key(
            wrapped,
            recovery_key=generate_recovery_key(),
            aad="user:namespace:recovery:v1",
        )


def _aad_fields(object_id: str = "bko_fixture", object_version: int = 1) -> dict[str, object]:
    return {
        "user_id_hash": "usrhash_fixture",
        "object_type": "life_load_backup",
        "object_id": object_id,
        "object_version": object_version,
        "schema_version": "life_load_backup_payload_v1",
        "created_at": "2026-05-11T00:00:00Z",
    }


def test_p_infra_crypto_v1_uses_real_aead_and_keeps_payload_opaque() -> None:
    data_key = generate_backup_key()
    payload = {"diary_text": "private", "entry_count": 1}

    envelope = encrypt_payload_v1(payload, data_key=data_key, aad_fields=_aad_fields())

    assert envelope["crypto_version"] == P_INFRA_CRYPTO_V1_VERSION
    assert envelope["crypto_suite"] == P_INFRA_CRYPTO_V1_SUITE
    assert envelope["prototype_only"] is True
    assert "private" not in str(envelope)
    assert decrypt_payload_v1(envelope, data_key=data_key, aad_fields=_aad_fields()) == payload


def test_p_infra_crypto_v1_rejects_wrong_key_wrong_aad_and_tamper() -> None:
    data_key = generate_backup_key()
    envelope = encrypt_payload_v1({"diary_text": "private"}, data_key=data_key, aad_fields=_aad_fields())

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_payload_v1(envelope, data_key=generate_backup_key(), aad_fields=_aad_fields())

    with pytest.raises(ValueError, match="aad mismatch"):
        decrypt_payload_v1(envelope, data_key=data_key, aad_fields=_aad_fields(object_id="other"))

    tampered = dict(envelope)
    tampered["tag"] = "A" * len(str(tampered["tag"]))
    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_payload_v1(tampered, data_key=data_key, aad_fields=_aad_fields())


def test_p_infra_crypto_v1_strict_validation_blocks_prototype_and_nonce_reuse() -> None:
    envelope = encrypt_payload_v1({"entry_count": 1}, data_key=generate_backup_key(), aad_fields=_aad_fields())

    with pytest.raises(ValueError, match="production-like mode"):
        validate_crypto_envelope_v1(envelope, production_like=True)

    seen: set[tuple[str, str]] = set()
    validate_crypto_envelope_v1(envelope, production_like=False, seen_nonces=seen)
    with pytest.raises(ValueError, match="nonce reuse"):
        validate_crypto_envelope_v1(envelope, production_like=False, seen_nonces=seen)

    placeholder = dict(envelope, crypto_suite="TBD")
    with pytest.raises(ValueError):
        validate_crypto_envelope_v1(placeholder, production_like=False)


def test_p_infra_crypto_v1_recovery_key_wraps_data_key_without_revealing_it() -> None:
    data_key = generate_backup_key()
    recovery_key = generate_recovery_key()
    aad = _aad_fields(object_id="wrapped-key")

    wrapped = wrap_key_with_recovery_key_v1(data_key, recovery_key=recovery_key, aad_fields=aad)

    assert wrapped["key_wrapping_mode"] == "recovery_key_prototype"
    assert data_key.hex() not in str(wrapped)
    assert unwrap_key_with_recovery_key_v1(wrapped, recovery_key=recovery_key, aad_fields=aad) == data_key

    with pytest.raises(ValueError, match="authentication failed"):
        unwrap_key_with_recovery_key_v1(wrapped, recovery_key=generate_recovery_key(), aad_fields=aad)
