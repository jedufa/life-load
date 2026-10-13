from __future__ import annotations

import hashlib

import pytest

from life_load.remote_backend import (
    FakeEntitlementProvider,
    MAX_BACKUP_ENVELOPE_BYTES,
    RemoteBackendStore,
    PostgresRemoteBackendStore,
    PostgresRemoteBackendUnavailable,
    cloud_ai_control_plane_placeholder,
    deployment_environment_status,
    make_backup_envelope,
    plan_capability_registry,
    remote_backend_metadata_store_capability,
    remote_backend_store_from_environment,
    validate_cloud_ai_payload_placeholder,
)


def _registered(store: RemoteBackendStore, email: str, *, label: str = "Pixel") -> dict[str, str]:
    return store.register_user(
        email=email,
        password="correct horse battery staple",
        device_label=label,
        platform="android",
    )


def test_remote_backend_namespace_isolation_and_delete_all(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user_a = _registered(store, "a@example.com", label="Pixel A")
    user_b = _registered(store, "b@example.com", label="Pixel B")

    envelope = make_backup_envelope(
        namespace_id=user_a["namespace_id"],
        device_id=user_a["device_id"],
        ciphertext="opaque encrypted diary payload",
    )
    created = store.create_backup_object(user_a["session_token"], envelope)

    assert store.list_backup_objects(user_a["session_token"])[0]["id"] == created["object_id"]
    assert store.list_backup_objects(user_b["session_token"]) == []

    with pytest.raises(PermissionError):
        store.get_backup_object(user_b["session_token"], created["object_id"])
    with pytest.raises(PermissionError):
        store.delete_backup_object(user_b["session_token"], created["object_id"])

    assert store.delete_all_backups(user_a["session_token"]) == {"deleted_count": 1}
    assert store.list_backup_objects(user_a["session_token"]) == []
    assert store.backup_status(user_a["session_token"])["object_count"] == 0


def test_remote_backend_auth_session_and_device_revocation(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "owner@example.com")
    second_device = store.register_device(
        user["session_token"],
        device_label="Trusted spare",
        platform="android",
    )
    login = store.login(
        email="owner@example.com",
        password="correct horse battery staple",
        device_id=second_device["device_id"],
    )

    store.revoke_device(user["session_token"], device_id=second_device["device_id"])

    envelope = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=second_device["device_id"],
        ciphertext="opaque backup from revoked device",
    )
    with pytest.raises(PermissionError):
        store.create_backup_object(login["session_token"], envelope)

    store.logout(user["session_token"])
    active_device_envelope = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext="opaque backup after logout",
    )
    with pytest.raises(PermissionError):
        store.create_backup_object(user["session_token"], active_device_envelope)


def test_remote_backend_rejects_malformed_oversized_and_checksum_mismatch(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "a@example.com")
    valid = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext="opaque encrypted content",
    )

    missing = dict(valid)
    missing.pop("ciphertext")
    with pytest.raises(ValueError, match="missing"):
        store.create_backup_object(user["session_token"], missing)

    mismatched = dict(valid)
    mismatched["ciphertext_sha256"] = hashlib.sha256(b"different").hexdigest()
    with pytest.raises(ValueError, match="checksum"):
        store.create_backup_object(user["session_token"], mismatched)

    oversized = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext="x" * (MAX_BACKUP_ENVELOPE_BYTES + 1),
    )
    with pytest.raises(ValueError, match="too large"):
        store.create_backup_object(user["session_token"], oversized)

    sensitive_summary = dict(valid)
    sensitive_summary["redacted_summary"] = {
        "entry_count": 1,
        "date_min": "2026-05-01",
        "date_max": "2026-05-10",
        "diary_text": "server must never accept this summary field",
    }
    with pytest.raises(ValueError, match="redacted_summary"):
        store.create_backup_object(user["session_token"], sensitive_summary)


def test_remote_backend_deleted_user_cannot_access_prior_backups(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "owner@example.com")
    envelope = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext="opaque encrypted content",
    )
    created = store.create_backup_object(user["session_token"], envelope)

    store.disable_user(user["session_token"])

    with pytest.raises(PermissionError):
        store.list_backup_objects(user["session_token"])
    with pytest.raises(PermissionError):
        store.get_backup_object(user["session_token"], created["object_id"])


def test_remote_backend_restore_manifest_and_download_require_owner(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user_a = _registered(store, "a@example.com")
    user_b = _registered(store, "b@example.com")
    ciphertext = "opaque encrypted restore payload"
    envelope = make_backup_envelope(
        namespace_id=user_a["namespace_id"],
        device_id=user_a["device_id"],
        ciphertext=ciphertext,
    )
    created = store.create_backup_object(user_a["session_token"], envelope)

    manifest = store.restore_manifest(user_a["session_token"])

    assert manifest["schema_version"] == "life_load_restore_manifest_v1"
    assert manifest["object_count"] == 1
    assert manifest["objects"][0]["id"] == created["object_id"]
    assert "ciphertext" not in manifest["objects"][0]

    restored = store.download_restore_object(user_a["session_token"], created["object_id"])
    assert restored["ciphertext"] == ciphertext

    with pytest.raises(PermissionError):
        store.download_restore_object(user_b["session_token"], created["object_id"])


def test_remote_backend_recovery_placeholders_do_not_return_secret_material(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "owner@example.com")

    recovery = store.create_recovery_material_placeholder(
        user["session_token"],
        material_type="recovery-key",
    )

    assert recovery == {
        "material_id": recovery["material_id"],
        "material_type": "recovery_key",
        "status": "placeholder",
        "public_hint": "recovery_key_configured",
    }
    serialized = str(recovery).lower()
    assert "secret" not in serialized
    assert "phrase" not in serialized
    assert "private" not in serialized


def test_remote_backend_password_reset_does_not_recover_private_history(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "private.person@example.com")
    store.create_recovery_material_placeholder(user["session_token"], material_type="trusted_device")
    envelope = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext="opaque encrypted content that must remain encrypted",
    )
    created = store.create_backup_object(user["session_token"], envelope)

    reset = store.password_reset_account_access_only(email="private.person@example.com")

    assert reset == {
        "schema_version": "life_load_password_reset_contract_v1",
        "ok": True,
        "account_access_only": True,
        "private_history_recovered": False,
        "recovery_material_returned": False,
        "backup_key_returned": False,
    }
    assert store.download_restore_object(user["session_token"], created["object_id"])["ciphertext"] == envelope["ciphertext"]
    assert "private.person@example.com" not in store.audit_text()


def test_remote_backend_audit_logs_exclude_sensitive_values(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "private.person@example.com")
    ciphertext = "dear diary health family work token-shaped-secret"
    envelope = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext=ciphertext,
    )
    store.create_backup_object(user["session_token"], envelope)
    with pytest.raises(PermissionError):
        store.login(email="private.person@example.com", password="wrong-password")

    audit_text = store.audit_text()
    forbidden = (
        "private.person@example.com",
        user["session_token"],
        ciphertext,
        "wrong-password",
        envelope["ciphertext_sha256"],
        "recovery phrase",
        "recovery key secret",
    )
    for value in forbidden:
        assert value not in audit_text

    assert "/v1/backups/objects" in audit_text
    assert "invalid_credentials" in audit_text


def test_remote_backend_health_readiness_and_metrics_are_local_dev(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "metrics@example.com")
    envelope = make_backup_envelope(
        namespace_id=user["namespace_id"],
        device_id=user["device_id"],
        ciphertext="opaque metrics payload",
    )
    store.create_backup_object(user["session_token"], envelope)
    store.record_request_observation(
        endpoint="/v1/backups/objects",
        status_code=201,
        timing_ms=12,
        user_id=user["user_id"],
        object_count=1,
        byte_size=22,
    )
    store.record_request_observation(
        endpoint="/v1/backups/objects",
        status_code=400,
        timing_ms=5,
        user_id=user["user_id"],
        redacted_error_category="malformed envelope",
    )

    assert store.health()["ok"] is True
    assert store.health()["metadata_store"] == "sqlite"
    readiness = store.readiness()
    assert readiness["ok"] is True
    assert readiness["mode"] == "local_dev"
    assert readiness["metadata_store"] == "sqlite"

    metrics = store.metrics_snapshot()
    assert metrics["schema_version"] == "life_load_remote_backend_metrics_v1"
    assert metrics["active_backup_object_count"] == 1
    assert metrics["request_count"] == 2
    assert metrics["error_count"] == 1


def test_remote_backend_store_mode_is_explicit_and_postgres_requires_driver_and_url(tmp_path) -> None:
    sqlite_store = remote_backend_store_from_environment(
        repo_root=tmp_path,
        environ={"LIFE_LOAD_REMOTE_BACKEND_STORE_MODE": "sqlite"},
    )
    assert isinstance(sqlite_store, RemoteBackendStore)

    capability = remote_backend_metadata_store_capability({"LIFE_LOAD_REMOTE_BACKEND_STORE_MODE": "postgres"})
    assert capability["selected_mode"] == "postgres"
    assert capability["implemented"] is False
    assert capability["safe_for_backend_benchmark"] is False
    assert capability["database_url_configured"] is False

    postgres_store = remote_backend_store_from_environment(
        repo_root=tmp_path,
        environ={
            "LIFE_LOAD_REMOTE_BACKEND_STORE_MODE": "postgres",
            "LIFE_LOAD_DATABASE_URL": "postgresql://life_load:secret@127.0.0.1:1/life_load_alpha",
        },
    )
    assert isinstance(postgres_store, PostgresRemoteBackendStore)

    if not capability["postgres_adapter_available"]:
        with pytest.raises(PostgresRemoteBackendUnavailable, match="psycopg"):
            postgres_store.health()


def test_remote_backend_operational_events_are_redacted_and_scannable(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "logs@example.com")
    token = user["session_token"]
    ciphertext = "diary health family work ciphertext should not be logged"

    event = store.record_request_observation(
        endpoint="/v1/backups/objects?email=logs@example.com&token=secret",
        status_code=500,
        timing_ms=44,
        user_id=user["user_id"],
        object_count=1,
        byte_size=123,
        redacted_error_category="ciphertext parse failed " + ciphertext,
        request_id="req_test_1",
    )

    assert event["request_id"] == "req_test_1"
    assert event["endpoint"] == "/v1/backups/objects_email_logs_example_com_token_secret"
    assert event["user_id_hash"] != user["user_id"]
    assert event["redacted_error_category"] == "ciphertext_parse_failed"

    log_text = store.operational_log_text()
    for forbidden in ("logs@example.com", token, user["user_id"], "?email=", "&token="):
        assert forbidden not in log_text

    assert store.scan_logs_for_sensitive_values([token, "logs@example.com", ciphertext, "missing"]) == []

    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO operational_events(
                id, request_id, endpoint, status_code, timing_ms,
                redacted_error_category, created_at
            ) VALUES ('opv_bad', 'req_bad', '/bad', 500, 1, ?, '2026-05-10T00:00:00Z')
            """,
            (ciphertext,),
        )
    assert store.scan_logs_for_sensitive_values([ciphertext]) == [ciphertext]


def test_remote_backend_environment_model_allows_local_only_and_blocks_public_local(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)

    local = store.deployment_environment_status({"mode": "local"})
    assert local["ok"] is True
    assert local["local_only"] is True
    assert local["public_endpoints_enabled"] is False

    public_local = store.deployment_environment_status(
        {"mode": "dev", "public_endpoints_enabled": True, "domain": "example.test"}
    )
    assert public_local["ok"] is False
    assert public_local["public_endpoints_enabled"] is False
    assert "local_dev_public_endpoints_disabled" in public_local["warnings"]


def test_remote_backend_environment_model_fails_closed_for_production_without_secrets() -> None:
    status = deployment_environment_status(
        {
            "mode": "production",
            "public_endpoints_enabled": True,
            "tls_enabled": True,
            "domain": "api.example.test",
            "object_store": "s3_compatible",
            "secret_refs": {
                "database_url": "prod/db/url/secret",
                "session_secret": "prod/session/secret",
            },
        }
    )

    assert status["ok"] is False
    assert "secret_ref:object_store_secret" in status["missing"]
    assert "secret_ref:password_pepper" in status["missing"]
    assert "secret_ref:tls_private_key_ref" in status["missing"]
    serialized = str(status)
    assert "prod/db/url/secret" not in serialized
    assert "prod/session/secret" not in serialized


def test_remote_backend_environment_model_accepts_complete_production_shape() -> None:
    status = deployment_environment_status(
        {
            "mode": "production",
            "public_endpoints_enabled": True,
            "tls_enabled": True,
            "domain": "api.example.test",
            "object_store": "managed_object_store",
            "secret_refs": {
                "database_url": "secret/database",
                "session_secret": "secret/session",
                "password_pepper": "secret/pepper",
                "object_store_secret": "secret/object-store",
                "tls_private_key_ref": "secret/tls-key",
            },
        }
    )

    assert status["ok"] is True
    assert status["local_only"] is False
    assert status["public_endpoints_enabled"] is True
    assert status["secret_refs_configured"] == [
        "database_url",
        "object_store_secret",
        "password_pepper",
        "session_secret",
        "tls_private_key_ref",
    ]


def test_remote_backend_local_web_portal_shows_only_owner_metadata_and_can_delete(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user_a = _registered(store, "a@example.com")
    user_b = _registered(store, "b@example.com")
    ciphertext = "opaque web export payload"
    envelope = make_backup_envelope(
        namespace_id=user_a["namespace_id"],
        device_id=user_a["device_id"],
        ciphertext=ciphertext,
    )
    created = store.create_backup_object(user_a["session_token"], envelope)

    account = store.web_account_page(user_a["session_token"])
    status_page = store.web_backup_status_page(user_a["session_token"])

    assert account["schema_version"] == "life_load_local_web_account_v1"
    assert account["product_claim"] == "local_backend_foundation_only"
    assert status_page["objects"][0]["id"] == created["object_id"]
    assert "ciphertext" not in status_page["objects"][0]

    with pytest.raises(PermissionError):
        store.web_export_encrypted_object(user_b["session_token"], created["object_id"])

    exported = store.web_export_encrypted_object(user_a["session_token"], created["object_id"])
    assert exported["ciphertext"] == ciphertext

    delete = store.web_delete_backup_object(user_a["session_token"], created["object_id"])
    assert delete["ok"] is True
    assert store.web_backup_status_page(user_a["session_token"])["objects"] == []


def test_remote_backend_local_web_portal_blocks_nonlocal_config_and_logout(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "owner@example.com")

    with pytest.raises(PermissionError):
        store.web_account_page(user["session_token"], {"mode": "production", "public_endpoints_enabled": True})

    placeholder = store.web_account_deletion_placeholder(user["session_token"])
    assert placeholder["implemented"] is False
    assert placeholder["reason"] == "future_account_deletion_flow_requires_mvp4_disclosure_and_drills"

    store.logout(user["session_token"])
    with pytest.raises(PermissionError):
        store.web_backup_status_page(user["session_token"])


def test_remote_backend_plan_capability_registry_keeps_free_core_available() -> None:
    registry = plan_capability_registry()

    assert "local_free_core" in registry["free"]
    assert "manual_export_import" in registry["free"]
    assert "plus_encrypted_backup" not in registry["free"]
    assert "pro_interpretation_preview" in registry["pro"]
    assert "plus_encrypted_backup" in registry["plus"]
    assert "premium_integrations" in registry["premium"]


def test_remote_backend_fake_entitlement_provider_keeps_plan_boundaries_separate(tmp_path) -> None:
    store = RemoteBackendStore(repo_root=tmp_path)
    user = _registered(store, "owner@example.com")
    entitlements = FakeEntitlementProvider()

    free = entitlements.capabilities_for_user(user["user_id"])
    assert free["provider"] == "fake_local_only"
    assert entitlements.capability_enabled(user["user_id"], "manual_export_import") is True
    assert entitlements.capability_enabled(user["user_id"], "plus_encrypted_backup") is False

    entitlements.set_plan(user["user_id"], "pro")
    assert entitlements.capability_enabled(user["user_id"], "pro_interpretation_preview") is True
    assert entitlements.capability_enabled(user["user_id"], "plus_encrypted_backup") is False

    entitlements.enable_capability(user["user_id"], "plus_encrypted_backup")
    assert entitlements.capability_enabled(user["user_id"], "plus_encrypted_backup") is True
    assert entitlements.capability_enabled(user["user_id"], "premium_integrations") is False

    entitlements.set_plan(user["user_id"], "premium")
    assert entitlements.capability_enabled(user["user_id"], "premium_integrations") is True


def test_remote_backend_fake_entitlement_provider_rejects_unknown_plans_and_capabilities() -> None:
    entitlements = FakeEntitlementProvider()

    with pytest.raises(ValueError, match="unsupported plan"):
        entitlements.set_plan("user", "enterprise")
    with pytest.raises(ValueError, match="unsupported capability"):
        entitlements.enable_capability("user", "cloud_ai_now")


def test_remote_backend_cloud_ai_control_plane_placeholder_defaults_off() -> None:
    control = cloud_ai_control_plane_placeholder()

    assert control["schema_version"] == "life_load_cloud_ai_control_plane_placeholder_v1"
    assert control["enabled"] is False
    assert control["provider"] == "none"
    assert control["sends_user_payloads"] is False
    assert control["android_connected"] is False
    assert control["disclosure_required"] is True


def test_remote_backend_cloud_ai_control_plane_requires_retention_budget_limits_and_disclosure() -> None:
    incomplete = cloud_ai_control_plane_placeholder({"enabled": True, "provider": "openai"})
    assert incomplete["enabled"] is False
    assert "monthly_budget_cents" in incomplete["missing"]
    assert "request_limit_per_day" in incomplete["missing"]
    assert "explicit_user_disclosure" in incomplete["missing"]

    complete = cloud_ai_control_plane_placeholder(
        {
            "enabled": True,
            "provider": "openai",
            "retention_days": 0,
            "monthly_budget_cents": 2500,
            "request_limit_per_day": 50,
            "explicit_user_disclosure": True,
        }
    )
    assert complete["enabled"] is True
    assert complete["retention_days"] == 0
    assert complete["monthly_budget_cents"] == 2500


def test_remote_backend_cloud_ai_payload_placeholder_rejects_sensitive_fields() -> None:
    safe = validate_cloud_ai_payload_placeholder({"request_type": "capability_check"})
    assert safe["ok"] is True
    assert safe["payload_sent"] is False

    with pytest.raises(ValueError, match="diary_text"):
        validate_cloud_ai_payload_placeholder({"diary_text": "private diary should not leave local app"})
    with pytest.raises(ValueError, match="family_notes"):
        validate_cloud_ai_payload_placeholder({"family_notes": "private family detail"})
    with pytest.raises(ValueError, match="token"):
        validate_cloud_ai_payload_placeholder({"redacted_context": [{"token": "secret-session-token"}]})
