"""Dev-only API contract dispatcher for the remote backend foundation.

This is not a public HTTP server and is not connected to Android. It provides a
small request dispatcher so P-INFRA endpoint contracts can be regression-tested
against the local RemoteBackendStore without exposing production endpoints.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from life_load.remote_backend import RemoteBackendStore, deployment_environment_status

MAX_REQUEST_BODY_BYTES = 256 * 1024


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    body: dict[str, Any]


def dispatch_remote_backend_request(
    store: RemoteBackendStore,
    *,
    method: str,
    path: str,
    body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ApiResponse:
    request_id = _request_id(headers)
    environment = deployment_environment_status(config or {"mode": "local"})
    staging_fixture_allowed = _staging_fixture_allowed(config or {})
    if (not environment["ok"] or not environment["local_only"]) and not staging_fixture_allowed:
        return _error(403, "dev_only", request_id=request_id)

    method_name = str(method or "").strip().upper()
    request_path = str(path or "").strip()
    payload = dict(body or {})
    request_headers = {str(key).lower(): str(value) for key, value in dict(headers or {}).items()}
    request_id = _request_id(request_headers)
    content_type = str(request_headers.get("content-type") or "").strip().lower()
    if payload and content_type and "application/json" not in content_type:
        return _error(415, "unsupported_media_type", request_id=request_id)
    if len(_canonical_body_bytes(payload)) > MAX_REQUEST_BODY_BYTES:
        return _error(413, "request_too_large", request_id=request_id)

    try:
        if method_name == "POST" and request_path == "/v1/auth/register":
            return _ok(
                201,
                store.register_user(
                    email=str(payload.get("email") or ""),
                    password=str(payload.get("password") or ""),
                    device_label=str(payload.get("device_label") or "Dev device"),
                    platform=str(payload.get("platform") or "local_dev"),
                ),
            )
        if method_name == "POST" and request_path == "/v1/auth/login":
            return _ok(
                200,
                store.login(
                    email=str(payload.get("email") or ""),
                    password=str(payload.get("password") or ""),
                    device_id=str(payload.get("device_id") or "") or None,
                ),
            )
        if method_name == "POST" and request_path == "/v1/auth/logout":
            store.logout(_bearer_token(request_headers))
            return _ok(200, {"ok": True})
        if method_name == "POST" and request_path == "/v1/auth/refresh":
            return _ok(
                200,
                store.rotate_refresh_session(
                    _bearer_token(request_headers),
                    device_id=str(payload.get("device_id") or "") or None,
                ),
            )
        if method_name == "POST" and request_path == "/v1/auth/password-reset":
            return _ok(200, store.password_reset_account_access_only(email=str(payload.get("email") or "")))
        if method_name == "POST" and request_path == "/v1/testing/account/disable":
            store.disable_user(_bearer_token(request_headers))
            return _ok(200, {"ok": True})
        if method_name == "POST" and request_path == "/v1/testing/auth/revoke-token-family":
            return _ok(200, store.revoke_token_family(_bearer_token(request_headers)))
        if method_name == "POST" and request_path == "/v1/testing/rate-limit/simulate":
            return _ok(
                200,
                store.simulate_rate_limit_decision(
                    route_class=str(payload.get("route_class") or ""),
                    count=int(payload.get("count") or 0),
                    mode=str(payload.get("mode") or "") or None,
                ),
            )
        if method_name == "POST" and request_path == "/v1/testing/recovery-state":
            return _ok(200, store.recovery_state_for_test(payload))
        if method_name == "POST" and request_path == "/v1/testing/object-store/fail-next":
            return _ok(
                200,
                store.inject_object_store_failure_for_test(
                    str(payload.get("operation") or ""),
                    count=int(payload.get("count") or 1),
                ),
            )
        if method_name == "GET" and request_path == "/v1/testing/staging-like/status":
            return _ok(
                200,
                {
                    "schema_version": "life_load_staging_like_android_test_status_v1",
                    "fixture_only": True,
                    "android_product_connected": False,
                    "public_backend_enabled": False,
                    "production_gate_blocks_public_mode": True,
                    "strict_crypto_available": True,
                    "dev_console_expected_off": True,
                },
            )
        if method_name == "POST" and request_path == "/v1/devices/register":
            return _ok(
                201,
                store.register_device(
                    _bearer_token(request_headers),
                    device_label=str(payload.get("device_label") or ""),
                    platform=str(payload.get("platform") or ""),
                ),
            )
        if method_name == "POST" and request_path == "/v1/vault/key-packages":
            return _ok(
                201,
                store.create_vault_key_package(
                    _bearer_token(request_headers),
                    package_type=str(payload.get("package_type") or ""),
                    wrapping_mode=str(payload.get("wrapping_mode") or ""),
                    wrapped_key_hash=str(payload.get("wrapped_key_hash") or ""),
                    key_version=int(payload.get("key_version") or 1),
                    device_id=str(payload.get("device_id") or "") or None,
                    metadata=payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {},
                ),
            )
        if method_name == "GET" and request_path == "/v1/vault/key-packages":
            return _ok(200, store.list_vault_key_packages(_bearer_token(request_headers)))
        package_revoke_prefix = "/v1/vault/key-packages/"
        package_revoke_suffix = "/revoke"
        if (
            method_name == "POST"
            and request_path.startswith(package_revoke_prefix)
            and request_path.endswith(package_revoke_suffix)
        ):
            package_id_value = request_path[len(package_revoke_prefix) : -len(package_revoke_suffix)]
            return _ok(
                200,
                store.revoke_vault_key_package(_bearer_token(request_headers), package_id=package_id_value),
            )
        if method_name == "POST" and request_path == "/v1/vault/recovery-packages/rotate":
            return _ok(
                200,
                store.rotate_recovery_package(
                    _bearer_token(request_headers),
                    old_package_id=str(payload.get("old_package_id") or ""),
                    wrapped_key_hash=str(payload.get("wrapped_key_hash") or ""),
                    wrapping_mode=str(payload.get("wrapping_mode") or "recovery_key_prototype"),
                    key_version=int(payload.get("key_version") or 1),
                ),
            )
        if method_name == "POST" and request_path == "/v1/devices/trust-requests":
            return _ok(
                201,
                store.create_trusted_device_request(
                    _bearer_token(request_headers),
                    requesting_device_id=str(payload.get("requesting_device_id") or ""),
                    expires_in_seconds=int(payload.get("expires_in_seconds") or 900),
                ),
            )
        trust_decision_prefix = "/v1/devices/trust-requests/"
        trust_decision_suffix = "/decision"
        if (
            method_name == "POST"
            and request_path.startswith(trust_decision_prefix)
            and request_path.endswith(trust_decision_suffix)
        ):
            request_id_value = request_path[len(trust_decision_prefix) : -len(trust_decision_suffix)]
            return _ok(
                200,
                store.decide_trusted_device_request(
                    _bearer_token(request_headers),
                    request_id=request_id_value,
                    decision=str(payload.get("decision") or ""),
                    wrapped_key_hash=str(payload.get("wrapped_key_hash") or ""),
                ),
            )
        trust_expire_prefix = "/v1/testing/devices/trust-requests/"
        trust_expire_suffix = "/expire"
        if (
            method_name == "POST"
            and request_path.startswith(trust_expire_prefix)
            and request_path.endswith(trust_expire_suffix)
        ):
            request_id_value = request_path[len(trust_expire_prefix) : -len(trust_expire_suffix)]
            return _ok(
                200,
                store.expire_trusted_device_request_for_test(
                    _bearer_token(request_headers),
                    request_id=request_id_value,
                ),
            )
        if method_name == "GET" and request_path == "/v1/account/server-metadata":
            return _ok(200, store.server_metadata_view(_bearer_token(request_headers)))
        if method_name == "GET" and request_path == "/v1/account/support-summary":
            return _ok(200, store.support_summary(_bearer_token(request_headers)))
        device_prefix = "/v1/devices/"
        if method_name == "DELETE" and request_path.startswith(device_prefix):
            store.revoke_device(_bearer_token(request_headers), device_id=request_path[len(device_prefix) :])
            return _ok(200, {"ok": True})
        if method_name == "GET" and request_path == "/v1/backups/status":
            return _ok(200, store.backup_status(_bearer_token(request_headers)))
        if method_name == "POST" and request_path == "/v1/backups/objects":
            return _ok(
                201,
                store.create_backup_object(
                    _bearer_token(request_headers),
                    payload,
                    idempotency_key=request_headers.get("idempotency-key"),
                    strict_production_crypto=bool((config or {}).get("strict_production_envelope")),
                ),
            )
        if method_name == "GET" and request_path == "/v1/backups/objects":
            return _ok(200, {"objects": store.list_backup_objects(_bearer_token(request_headers))})
        if method_name == "DELETE" and request_path == "/v1/backups/all":
            return _ok(200, store.delete_all_backups(_bearer_token(request_headers)))
        if method_name == "GET" and request_path == "/v1/restore/objects":
            return _ok(200, store.restore_manifest(_bearer_token(request_headers)))
        restore_prefix = "/v1/restore/objects/"
        if method_name == "GET" and request_path.startswith(restore_prefix):
            return _ok(200, store.download_restore_object(_bearer_token(request_headers), request_path[len(restore_prefix) :]))
        testing_corrupt_suffix = "/corrupt"
        testing_object_prefix = "/v1/testing/backups/objects/"
        if method_name == "POST" and request_path.startswith(testing_object_prefix) and request_path.endswith(
            testing_corrupt_suffix
        ):
            object_id = request_path[len(testing_object_prefix) : -len(testing_corrupt_suffix)]
            store.corrupt_backup_object_for_test(_bearer_token(request_headers), object_id=object_id)
            return _ok(200, {"ok": True, "corrupted_object_id": object_id})
        object_prefix = "/v1/backups/objects/"
        if request_path.startswith(object_prefix):
            object_id = request_path[len(object_prefix) :]
            if method_name == "GET":
                return _ok(200, store.get_backup_object(_bearer_token(request_headers), object_id))
            if method_name == "DELETE":
                store.delete_backup_object(_bearer_token(request_headers), object_id)
                return _ok(200, {"ok": True, "deleted_object_id": object_id})
        return _error(404, "not_found", request_id=request_id)
    except PermissionError:
        return _error(403, "forbidden", request_id=request_id)
    except sqlite3.IntegrityError:
        return _error(409, "already_exists", request_id=request_id)
    except ValueError:
        return _error(400, "bad_request", request_id=request_id)
    except Exception:
        return _error(500, "internal_error", request_id=request_id)


def dispatch_remote_backend_raw_request(
    store: RemoteBackendStore,
    *,
    method: str,
    path: str,
    raw_body: str | bytes,
    headers: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ApiResponse:
    request_headers = {str(key).lower(): str(value) for key, value in dict(headers or {}).items()}
    request_id = _request_id(request_headers)
    content_type = str(request_headers.get("content-type") or "").strip().lower()
    if content_type and "application/json" not in content_type:
        return _error(415, "unsupported_media_type", request_id=request_id)
    raw = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode("utf-8", errors="replace")
    if len(raw) > MAX_REQUEST_BODY_BYTES:
        return _error(413, "request_too_large", request_id=request_id)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        return _error(400, "malformed_json", request_id=request_id)
    if not isinstance(parsed, dict):
        return _error(400, "bad_request", request_id=request_id)
    return dispatch_remote_backend_request(
        store,
        method=method,
        path=path,
        body=parsed,
        headers=request_headers,
        config=config,
    )


def _bearer_token(headers: Mapping[str, str]) -> str:
    value = str(headers.get("authorization") or "").strip()
    prefix = "Bearer "
    if not value.startswith(prefix):
        raise PermissionError("missing bearer token")
    token = value[len(prefix) :].strip()
    if not token:
        raise PermissionError("missing bearer token")
    return token


def _ok(status_code: int, body: Mapping[str, Any]) -> ApiResponse:
    return ApiResponse(status_code=status_code, body=dict(body))


def _error(status_code: int, code: str, *, request_id: str) -> ApiResponse:
    return ApiResponse(status_code=status_code, body={"error": _safe_error(code), "request_id": request_id})


def _request_id(headers: Mapping[str, str] | None) -> str:
    values = {str(key).lower(): str(value) for key, value in dict(headers or {}).items()}
    supplied = str(values.get("x-request-id") or "").strip()
    if supplied:
        return _safe_error(supplied)[:40] or uuid.uuid4().hex
    return f"req_{uuid.uuid4().hex}"


def _staging_fixture_allowed(config: Mapping[str, Any]) -> bool:
    mode = str(config.get("mode") or "").strip().lower()
    return (
        mode == "staging"
        and bool(config.get("fixture_only_staging"))
        and not bool(config.get("public_endpoints_enabled"))
    )


def _canonical_body_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
    except Exception:
        return str(payload).encode("utf-8", errors="replace")


def _safe_error(value: str) -> str:
    words = str(value or "error").lower().replace("-", "_").split()
    text = "_".join(words[:4]) or "error"
    return "".join(char if char.isalnum() or char == "_" else "_" for char in text[:80])
