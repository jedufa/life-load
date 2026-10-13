from __future__ import annotations

from life_load.remote_backend import make_backup_envelope
from life_load.remote_backend_api import dispatch_remote_backend_request


def test_remote_backend_dev_api_register_login_backup_and_delete(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)

    registered = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "device_label": "Pixel",
            "platform": "android",
        },
    )

    assert registered.status_code == 201
    token = registered.body["session_token"]
    auth = {"authorization": f"Bearer {token}"}

    envelope = make_backup_envelope(
        namespace_id=registered.body["namespace_id"],
        device_id=registered.body["device_id"],
        ciphertext="opaque encrypted API payload",
    )
    created = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/backups/objects",
        body=envelope,
        headers=auth,
    )

    assert created.status_code == 201
    object_id = created.body["object_id"]
    listed = dispatch_remote_backend_request(store, method="GET", path="/v1/backups/objects", headers=auth)
    assert listed.body["objects"][0]["id"] == object_id
    assert "ciphertext" not in listed.body["objects"][0]

    fetched = dispatch_remote_backend_request(
        store,
        method="GET",
        path=f"/v1/backups/objects/{object_id}",
        headers=auth,
    )
    assert fetched.body["ciphertext"] == "opaque encrypted API payload"

    deleted = dispatch_remote_backend_request(
        store,
        method="DELETE",
        path=f"/v1/backups/objects/{object_id}",
        headers=auth,
    )
    assert deleted.status_code == 200
    assert dispatch_remote_backend_request(store, method="GET", path="/v1/backups/status", headers=auth).body[
        "object_count"
    ] == 0


def test_remote_backend_dev_api_blocks_nonlocal_config_and_cross_user_access(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    user_a = store.register_user(
        email="a@example.com",
        password="correct horse battery staple",
        device_label="Pixel A",
        platform="android",
    )
    user_b = store.register_user(
        email="b@example.com",
        password="correct horse battery staple",
        device_label="Pixel B",
        platform="android",
    )
    created = store.create_backup_object(
        user_a["session_token"],
        make_backup_envelope(
            namespace_id=user_a["namespace_id"],
            device_id=user_a["device_id"],
            ciphertext="opaque encrypted owner payload",
        ),
    )

    blocked = dispatch_remote_backend_request(
        store,
        method="GET",
        path="/v1/backups/status",
        headers={"authorization": f"Bearer {user_a['session_token']}"},
        config={"mode": "production", "public_endpoints_enabled": True},
    )
    assert blocked.status_code == 403
    assert blocked.body["error"] == "dev_only"
    assert blocked.body["request_id"]

    cross_user = dispatch_remote_backend_request(
        store,
        method="GET",
        path=f"/v1/backups/objects/{created['object_id']}",
        headers={"authorization": f"Bearer {user_b['session_token']}"},
    )
    assert cross_user.status_code == 403
    assert cross_user.body["error"] == "forbidden"
    assert cross_user.body["request_id"]


def test_remote_backend_dev_api_allows_explicit_staging_fixture_only_config(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    blocked = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "staging-fixture@example.com",
            "password": "correct horse battery staple",
            "device_label": "Staging fixture",
            "platform": "android_backend_test_app",
        },
        config={"mode": "staging"},
    )
    allowed = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "staging-fixture@example.com",
            "password": "correct horse battery staple",
            "device_label": "Staging fixture",
            "platform": "android_backend_test_app",
        },
        config={"mode": "staging", "fixture_only_staging": True, "public_endpoints_enabled": False},
    )

    assert blocked.status_code == 403
    assert blocked.body["error"] == "dev_only"
    assert allowed.status_code == 201
    assert allowed.body["session_token"]
    assert allowed.body["device_id"]


def test_remote_backend_dev_api_redacts_error_text(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)

    response = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "not-an-email",
            "password": "secret-password-value",
            "device_label": "Pixel",
            "platform": "android",
        },
    )

    assert response.status_code == 400
    assert response.body["error"] == "bad_request"
    assert response.body["request_id"]
    assert "secret-password-value" not in str(response.body)


def test_remote_backend_dev_api_testing_disable_and_corrupt_routes_are_owner_scoped(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    owner = store.register_user(
        email="android-owner@example.com",
        password="correct horse battery staple",
        device_label="Owner Pixel",
        platform="android_backend_test_app",
    )
    other = store.register_user(
        email="android-other@example.com",
        password="correct horse battery staple",
        device_label="Other Pixel",
        platform="android_backend_test_app",
    )
    created = store.create_backup_object(
        owner["session_token"],
        make_backup_envelope(
            namespace_id=owner["namespace_id"],
            device_id=owner["device_id"],
            ciphertext="opaque encrypted restore payload",
        ),
    )

    cross_user_corrupt = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/testing/backups/objects/{created['object_id']}/corrupt",
        headers={"authorization": f"Bearer {other['session_token']}"},
    )
    assert cross_user_corrupt.status_code == 403

    corrupted = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/testing/backups/objects/{created['object_id']}/corrupt",
        headers={"authorization": f"Bearer {owner['session_token']}"},
    )
    assert corrupted.status_code == 200

    restore = dispatch_remote_backend_request(
        store,
        method="GET",
        path=f"/v1/restore/objects/{created['object_id']}",
        headers={"authorization": f"Bearer {owner['session_token']}"},
    )
    assert restore.status_code == 400
    assert restore.body["error"] == "bad_request"
    assert restore.body["request_id"]
    assert "not-json" not in str(restore.body)

    disabled = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/testing/account/disable",
        headers={"authorization": f"Bearer {owner['session_token']}"},
    )
    assert disabled.status_code == 200

    blocked_restore = dispatch_remote_backend_request(
        store,
        method="GET",
        path="/v1/restore/objects",
        headers={"authorization": f"Bearer {owner['session_token']}"},
    )
    assert blocked_restore.status_code == 403


def test_remote_backend_dev_api_restore_device_revoke_and_password_reset_routes(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    registered = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "android-routes@example.com",
            "password": "correct horse battery staple",
            "device_label": "Pixel",
            "platform": "android",
        },
    )
    assert registered.status_code == 201
    token = registered.body["session_token"]
    auth = {"authorization": f"Bearer {token}"}

    second_device = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/devices/register",
        body={"device_label": "Tablet", "platform": "android"},
        headers=auth,
    )
    assert second_device.status_code == 201
    assert second_device.body["device_id"].startswith("dev_")

    created = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/backups/objects",
        body=make_backup_envelope(
            namespace_id=registered.body["namespace_id"],
            device_id=registered.body["device_id"],
            ciphertext="opaque restore route payload",
        ),
        headers=auth,
    )
    assert created.status_code == 201

    manifest = dispatch_remote_backend_request(store, method="GET", path="/v1/restore/objects", headers=auth)
    assert manifest.status_code == 200
    assert manifest.body["object_count"] == 1
    restored = dispatch_remote_backend_request(
        store,
        method="GET",
        path=f"/v1/restore/objects/{created.body['object_id']}",
        headers=auth,
    )
    assert restored.status_code == 200
    assert restored.body["ciphertext"] == "opaque restore route payload"

    reset = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/password-reset",
        body={"email": "android-routes@example.com"},
    )
    assert reset.status_code == 200
    assert reset.body["account_access_only"] is True
    assert reset.body["private_history_recovered"] is False
    assert reset.body["backup_key_returned"] is False

    revoked = dispatch_remote_backend_request(
        store,
        method="DELETE",
        path=f"/v1/devices/{second_device.body['device_id']}",
        headers=auth,
    )
    assert revoked.status_code == 200


def test_remote_backend_dev_api_refresh_rate_recovery_and_failure_injection_routes(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    created = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "android-contract@example.invalid",
            "password": "correct horse battery staple",
            "device_label": "Pixel",
            "platform": "android",
        },
    )
    token = created.body["session_token"]
    device_id = created.body["device_id"]

    rotated = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/refresh",
        body={"device_id": device_id},
        headers={"authorization": f"Bearer {token}"},
    )
    assert rotated.status_code == 200
    assert rotated.body["rotates_refresh_token"] is True
    assert rotated.body["old_token_revoked"] is True
    assert "tfm_" not in str(rotated.body)

    old_reuse = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/refresh",
        body={"device_id": device_id},
        headers={"authorization": f"Bearer {token}"},
    )
    assert old_reuse.status_code == 403

    mismatch = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/refresh",
        body={"device_id": "dev_wrong"},
        headers={"authorization": f"Bearer {rotated.body['session_token']}"},
    )
    assert mismatch.status_code == 403

    rate = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/testing/rate-limit/simulate",
        body={"route_class": "restore_manifest", "count": 99, "mode": "enforce"},
    )
    assert rate.status_code == 200
    assert rate.body["allowed"] is False
    assert rate.body["reason"] == "rate_limited"

    recovery = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/testing/recovery-state",
        body={"account_password_reset": True, "has_local_key": False, "user_id": "usr_raw"},
    )
    assert recovery.status_code == 200
    assert recovery.body["state"] == "recovery_required"
    assert recovery.body["contains_private_key_material"] is False
    assert "usr_raw" not in str(recovery.body)

    fail_next = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/testing/object-store/fail-next",
        body={"operation": "put"},
    )
    assert fail_next.status_code == 200

    failed_upload = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/backups/objects",
        body=make_backup_envelope(
            namespace_id=created.body["namespace_id"],
            device_id=device_id,
            ciphertext="opaque fixture",
        ),
        headers={"authorization": f"Bearer {rotated.body['session_token']}"},
    )
    assert failed_upload.status_code == 500
    assert failed_upload.body["error"] == "internal_error"


def test_remote_backend_dev_api_staging_like_status_is_guarded_local_fixture_contract(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    response = dispatch_remote_backend_request(
        store,
        method="GET",
        path="/v1/testing/staging-like/status",
    )
    assert response.status_code == 200
    assert response.body["fixture_only"] is True
    assert response.body["android_product_connected"] is False
    assert response.body["public_backend_enabled"] is False


def test_remote_backend_dev_api_vault_trust_support_and_metadata_are_opaque(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    owner = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "continuity-owner@example.invalid",
            "password": "correct horse battery staple",
            "device_label": "Device A",
            "platform": "android_backend_test_app",
        },
    )
    assert owner.status_code == 201
    token_a = owner.body["session_token"]
    device_a = owner.body["device_id"]
    auth_a = {"authorization": f"Bearer {token_a}"}

    recovery_package = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/vault/key-packages",
        headers=auth_a,
        body={
            "package_type": "recovery_wrap",
            "wrapping_mode": "recovery_key_prototype",
            "wrapped_key_hash": "hash_recovery_wrap_only",
            "key_version": 1,
            "metadata": {
                "key_security_level": "simulated_in_test_app",
                "private_vault_key": "raw-vault-key-must-not-return",
            },
        },
    )
    assert recovery_package.status_code == 201
    assert recovery_package.body["plaintext_vault_key_returned"] is False
    assert "raw-vault-key-must-not-return" not in str(recovery_package.body)

    device_b = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/devices/register",
        headers=auth_a,
        body={"device_label": "Device B", "platform": "android_backend_test_app"},
    )
    assert device_b.status_code == 201
    login_b = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/login",
        body={
            "email": "continuity-owner@example.invalid",
            "password": "correct horse battery staple",
            "device_id": device_b.body["device_id"],
        },
    )
    assert login_b.status_code == 200
    auth_b = {"authorization": f"Bearer {login_b.body['session_token']}"}

    trust_request = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/devices/trust-requests",
        headers=auth_b,
        body={"requesting_device_id": device_b.body["device_id"]},
    )
    assert trust_request.status_code == 201
    assert trust_request.body["status"] == "pending_trust"
    assert trust_request.body["backend_can_approve_without_trusted_device"] is False

    self_approval = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/devices/trust-requests/{trust_request.body['request_id']}/decision",
        headers=auth_b,
        body={"decision": "approve", "wrapped_key_hash": "hash_device_b_wrap"},
    )
    assert self_approval.status_code == 403

    approved = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/devices/trust-requests/{trust_request.body['request_id']}/decision",
        headers=auth_a,
        body={"decision": "approve", "wrapped_key_hash": "hash_device_b_wrap"},
    )
    assert approved.status_code == 200
    assert approved.body["wrapped_key_package_created"] is True
    assert approved.body["plaintext_vault_key_returned"] is False

    packages = dispatch_remote_backend_request(store, method="GET", path="/v1/vault/key-packages", headers=auth_a)
    assert packages.status_code == 200
    assert packages.body["package_count"] == 2
    assert packages.body["plaintext_vault_key_available"] is False
    assert "raw-vault-key" not in str(packages.body)

    created = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/backups/objects",
        headers=auth_a,
        body=make_backup_envelope(
            namespace_id=owner.body["namespace_id"],
            device_id=device_a,
            ciphertext="opaque encrypted continuity payload",
        ),
    )
    assert created.status_code == 201

    metadata = dispatch_remote_backend_request(store, method="GET", path="/v1/account/server-metadata", headers=auth_a)
    assert metadata.status_code == 200
    assert metadata.body["server_can_read_private_payloads"] is False
    assert metadata.body["plaintext_key_material_available"] is False
    assert metadata.body["recovery_package_exists"] is True
    assert "ciphertext" not in str(metadata.body)
    assert "opaque encrypted continuity payload" not in str(metadata.body)
    assert owner.body["user_id"] not in str(metadata.body)

    support = dispatch_remote_backend_request(store, method="GET", path="/v1/account/support-summary", headers=auth_a)
    assert support.status_code == 200
    assert support.body["support_can_decrypt_private_history"] is False
    assert support.body["support_can_bypass_recovery_material"] is False
    assert support.body["backup_object_count"] == 1
    assert owner.body["user_id"] not in str(support.body)


def test_remote_backend_dev_api_trusted_device_negative_paths_are_safe(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    owner = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "trust-negative@example.invalid",
            "password": "correct horse battery staple",
            "device_label": "Device A",
            "platform": "android_backend_test_app",
        },
    )
    other = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "trust-other@example.invalid",
            "password": "correct horse battery staple",
            "device_label": "Other Device",
            "platform": "android_backend_test_app",
        },
    )
    token_a = owner.body["session_token"]
    auth_a = {"authorization": f"Bearer {token_a}"}
    auth_other = {"authorization": f"Bearer {other.body['session_token']}"}

    device_b = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/devices/register",
        headers=auth_a,
        body={"device_label": "Device B", "platform": "android_backend_test_app"},
    )
    login_b = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/login",
        body={
            "email": "trust-negative@example.invalid",
            "password": "correct horse battery staple",
            "device_id": device_b.body["device_id"],
        },
    )
    auth_b = {"authorization": f"Bearer {login_b.body['session_token']}"}

    denied_request = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/devices/trust-requests",
        headers=auth_b,
        body={"requesting_device_id": device_b.body["device_id"]},
    )
    assert denied_request.status_code == 201
    wrong_user_decision = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/devices/trust-requests/{denied_request.body['request_id']}/decision",
        headers=auth_other,
        body={"decision": "approve", "wrapped_key_hash": "hash_should_not_work"},
    )
    assert wrong_user_decision.status_code == 403

    denied = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/devices/trust-requests/{denied_request.body['request_id']}/decision",
        headers=auth_a,
        body={"decision": "deny", "wrapped_key_hash": "hash_not_used"},
    )
    assert denied.status_code == 200
    assert denied.body["status"] == "denied"
    assert denied.body["wrapped_key_package_created"] is False
    packages_after_denial = dispatch_remote_backend_request(
        store,
        method="GET",
        path="/v1/vault/key-packages",
        headers=auth_a,
    )
    assert packages_after_denial.body["package_count"] == 0

    expiring_request = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/devices/trust-requests",
        headers=auth_b,
        body={"requesting_device_id": device_b.body["device_id"]},
    )
    assert expiring_request.status_code == 201
    expired = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/testing/devices/trust-requests/{expiring_request.body['request_id']}/expire",
        headers=auth_a,
    )
    assert expired.status_code == 200
    approval_after_expire = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/devices/trust-requests/{expiring_request.body['request_id']}/decision",
        headers=auth_a,
        body={"decision": "approve", "wrapped_key_hash": "hash_after_expire"},
    )
    assert approval_after_expire.status_code == 400
    assert approval_after_expire.body["request_id"]
    assert "hash_after_expire" not in str(approval_after_expire.body)


def test_remote_backend_dev_api_recovery_package_revoke_and_rotate_lifecycle_is_redacted(tmp_path) -> None:
    from life_load.remote_backend import RemoteBackendStore

    store = RemoteBackendStore(repo_root=tmp_path)
    user = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/auth/register",
        body={
            "email": "recovery-lifecycle@example.invalid",
            "password": "correct horse battery staple",
            "device_label": "Recovery Device",
            "platform": "android_backend_test_app",
        },
    )
    assert user.status_code == 201
    auth = {"authorization": f"Bearer {user.body['session_token']}"}

    first = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/vault/key-packages",
        headers=auth,
        body={
            "package_type": "recovery_wrap",
            "wrapping_mode": "recovery_key_prototype",
            "wrapped_key_hash": "hash_recovery_lifecycle_old",
            "device_id": user.body["device_id"],
        },
    )
    assert first.status_code == 201

    rotated = dispatch_remote_backend_request(
        store,
        method="POST",
        path="/v1/vault/recovery-packages/rotate",
        headers=auth,
        body={
            "old_package_id": first.body["package_id"],
            "wrapped_key_hash": "hash_recovery_lifecycle_new",
            "wrapping_mode": "recovery_key_prototype",
        },
    )
    assert rotated.status_code == 200
    assert rotated.body["old_package_revoked"] is True
    assert rotated.body["active_recovery_package_count"] == 1
    assert rotated.body["plaintext_vault_key_returned"] is False
    assert rotated.body["recovery_material_returned"] is False

    packages = dispatch_remote_backend_request(store, method="GET", path="/v1/vault/key-packages", headers=auth)
    assert packages.status_code == 200
    assert packages.body["package_count"] == 2
    revoked_count = sum(1 for package in packages.body["packages"] if package["revoked"])
    active_count = sum(1 for package in packages.body["packages"] if not package["revoked"])
    assert revoked_count == 1
    assert active_count == 1

    support = dispatch_remote_backend_request(store, method="GET", path="/v1/account/support-summary", headers=auth)
    assert support.status_code == 200
    assert support.body["recovery_package_exists"] is True
    assert support.body["active_recovery_package_count"] == 1
    assert support.body["support_can_decrypt_private_history"] is False
    assert "recovery-lifecycle@example.invalid" not in str(support.body)
    assert "hash_recovery_lifecycle" not in str(support.body)

    revoked = dispatch_remote_backend_request(
        store,
        method="POST",
        path=f"/v1/vault/key-packages/{rotated.body['new_package_id']}/revoke",
        headers=auth,
    )
    assert revoked.status_code == 200
    support_after_revoke = dispatch_remote_backend_request(
        store,
        method="GET",
        path="/v1/account/support-summary",
        headers=auth,
    )
    assert support_after_revoke.body["recovery_package_exists"] is False
    assert support_after_revoke.body["active_recovery_package_count"] == 0
