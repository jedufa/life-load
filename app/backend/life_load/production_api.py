"""Production-shaped fixture API wrapper for P-INFRA rehearsals.

This module is deliberately not a public HTTP server. It wraps the existing
local/dev dispatcher in versioned success/error envelopes so middleware
contracts can be tested before MVP4 without exposing production endpoints.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from life_load.rate_limit import decide_rate_limit
from life_load.remote_backend import RemoteBackendStore, deployment_environment_status
from life_load.remote_backend_api import MAX_REQUEST_BODY_BYTES, dispatch_remote_backend_request

API_VERSION = "v1"


@dataclass(frozen=True)
class ProductionApiResponse:
    status_code: int
    body: dict[str, Any]


ROUTE_ALIASES: Mapping[tuple[str, str], tuple[str, str]] = {
    ("GET", "/v1/backup/status"): ("GET", "/v1/backups/status"),
    ("POST", "/v1/backup/objects"): ("POST", "/v1/backups/objects"),
    ("GET", "/v1/backup/objects"): ("GET", "/v1/backups/objects"),
    ("GET", "/v1/backup/manifest"): ("GET", "/v1/restore/objects"),
    ("DELETE", "/v1/backup/delete-all"): ("DELETE", "/v1/backups/all"),
    ("POST", "/v1/recovery/state"): ("POST", "/v1/testing/recovery-state"),
    ("GET", "/v1/support/summary"): ("GET", "/v1/account/support-summary"),
}


def dispatch_production_shaped_api_request(
    store: RemoteBackendStore,
    *,
    method: str,
    path: str,
    body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ProductionApiResponse:
    request_headers = {str(key).lower(): str(value) for key, value in dict(headers or {}).items()}
    request_id = _request_id(request_headers)
    environment = deployment_environment_status(config or {"mode": "local"})
    if not environment["ok"] or not environment["local_only"]:
        return _error(403, "dev_only", "Fixture API is blocked outside local/dev.", request_id=request_id)

    payload = dict(body or {})
    if len(_canonical_body_bytes(payload)) > MAX_REQUEST_BODY_BYTES:
        return _error(413, "request_too_large", "Request body is too large.", request_id=request_id)

    route_class = _route_class(str(path or ""))
    rate_count = int((config or {}).get("rate_limit_count") or 0)
    rate_mode = str((config or {}).get("rate_limit_mode") or "observe")
    rate = decide_rate_limit(route_class=route_class, count=rate_count, mode=rate_mode)
    store.record_request_observation(
        endpoint=f"/fixture-api/{route_class}",
        status_code=429 if not rate.allowed else 200,
        timing_ms=1,
        redacted_error_category=rate.reason,
    )
    if not rate.allowed:
        return _error(429, "rate_limited", "Request was rate limited.", request_id=request_id)

    method_name = str(method or "").strip().upper()
    request_path = str(path or "").strip()
    mapped_method, mapped_path = _map_route(method_name, request_path)
    forwarded_headers = dict(request_headers)
    forwarded_headers["x-request-id"] = request_id
    try:
        response = dispatch_remote_backend_request(
            store,
            method=mapped_method,
            path=mapped_path,
            body=payload,
            headers=forwarded_headers,
            config={"mode": "local"},
        )
    except Exception:
        return _error(500, "internal_error", "Internal error.", request_id=request_id)

    if 200 <= response.status_code < 300:
        return ProductionApiResponse(
            status_code=response.status_code,
            body={
                "ok": True,
                "data": _safe_data(response.body),
                "request_id": request_id,
                "api_version": API_VERSION,
            },
        )
    code = str(response.body.get("error") or "request_failed")
    return _error(response.status_code, code, _safe_message(code), request_id=request_id)


def _map_route(method: str, path: str) -> tuple[str, str]:
    direct = ROUTE_ALIASES.get((method, path))
    if direct is not None:
        return direct
    object_prefix = "/v1/backup/objects/"
    if path.startswith(object_prefix):
        return method, "/v1/backups/objects/" + path[len(object_prefix) :]
    device_revoke_prefix = "/v1/devices/revoke/"
    if method == "POST" and path.startswith(device_revoke_prefix):
        return "DELETE", "/v1/devices/" + path[len(device_revoke_prefix) :]
    return method, path


def _error(status_code: int, code: str, message: str, *, request_id: str) -> ProductionApiResponse:
    return ProductionApiResponse(
        status_code=status_code,
        body={
            "ok": False,
            "error": {
                "code": _safe_code(code),
                "message": message,
                "request_id": request_id,
            },
            "request_id": request_id,
            "api_version": API_VERSION,
        },
    )


def _request_id(headers: Mapping[str, str]) -> str:
    supplied = str(headers.get("x-request-id") or "").strip()
    if supplied:
        return _safe_code(supplied)[:40] or f"req_{uuid.uuid4().hex}"
    return f"req_{uuid.uuid4().hex}"


def _safe_code(value: str) -> str:
    text = str(value or "error").lower().replace("-", "_").split()
    return "".join(char if char.isalnum() or char == "_" else "_" for char in "_".join(text)[:80]) or "error"


def _safe_message(code: str) -> str:
    return {
        "forbidden": "Request is not allowed.",
        "bad_request": "Request is invalid.",
        "not_found": "Route or object was not found.",
        "dev_only": "Fixture API is blocked outside local/dev.",
        "request_too_large": "Request body is too large.",
        "unsupported_media_type": "Unsupported media type.",
        "internal_error": "Internal error.",
    }.get(_safe_code(code), "Request failed.")


def _route_class(path: str) -> str:
    if "/auth/" in path:
        return "auth_failure"
    if "/backup/objects" in path or "/backups/objects" in path:
        return "backup_upload"
    if "/manifest" in path or "/restore/" in path:
        return "restore_manifest"
    if "delete" in path:
        return "delete"
    return "api_request"


def _canonical_body_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
    except Exception:
        return str(payload).encode("utf-8", errors="replace")


def _safe_data(data: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(data)
    return copied
