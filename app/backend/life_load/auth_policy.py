"""Production-shaped auth policy helpers for P-INFRA2.

These helpers are backend-only scaffolding. They harden local/dev auth contracts
without creating production accounts or Android login UX.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any


DEFAULT_PASSWORD_HASH_ITERATIONS = 210_000
DEFAULT_LOGIN_FAILURE_LIMIT = 5
DEFAULT_LOGIN_WINDOW_SECONDS = 15 * 60


@dataclass(frozen=True)
class PasswordHashPolicy:
    iterations: int = DEFAULT_PASSWORD_HASH_ITERATIONS
    pepper: str = ""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str
    failure_count: int
    retry_after_seconds: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_rate_limit_decision_v1",
            "allowed": self.allowed,
            "reason": self.reason,
            "failure_count": self.failure_count,
            "retry_after_seconds": self.retry_after_seconds,
        }


def hash_session_token(token: str, *, secret: str | None = None) -> str:
    value = str(token or "")
    key = str(secret or os.environ.get("LIFE_LOAD_SESSION_TOKEN_HMAC_SECRET") or "").encode("utf-8")
    if key:
        digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac_sha256${digest}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password_for_storage(password: str, *, policy: PasswordHashPolicy | None = None) -> str:
    text = str(password or "")
    if len(text) < 8:
        raise ValueError("password must be at least 8 characters")
    active_policy = policy or PasswordHashPolicy(pepper=os.environ.get("LIFE_LOAD_PASSWORD_PEPPER", ""))
    salt = secrets.token_hex(16)
    material = _password_material(text, active_policy.pepper)
    digest = hashlib.pbkdf2_hmac("sha256", material, salt.encode("ascii"), active_policy.iterations)
    prefix = "pbkdf2_sha256_peppered" if active_policy.pepper else "pbkdf2_sha256"
    return f"{prefix}${active_policy.iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str, *, pepper: str | None = None) -> bool:
    try:
        algorithm, iterations_text, salt, expected = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except Exception:
        return False
    if algorithm not in {"pbkdf2_sha256", "pbkdf2_sha256_peppered"}:
        return False
    active_pepper = str(pepper if pepper is not None else os.environ.get("LIFE_LOAD_PASSWORD_PEPPER", ""))
    material = _password_material(str(password or ""), active_pepper if algorithm.endswith("_peppered") else "")
    digest = hashlib.pbkdf2_hmac("sha256", material, salt.encode("ascii"), iterations)
    return hmac.compare_digest(digest.hex(), expected)


def login_rate_limit_decision(
    *,
    recent_failure_count: int,
    limit: int = DEFAULT_LOGIN_FAILURE_LIMIT,
    window_seconds: int = DEFAULT_LOGIN_WINDOW_SECONDS,
) -> RateLimitDecision:
    count = max(0, int(recent_failure_count))
    if count >= limit:
        return RateLimitDecision(
            allowed=False,
            reason="too_many_failed_login_attempts",
            failure_count=count,
            retry_after_seconds=window_seconds,
        )
    return RateLimitDecision(allowed=True, reason="within_limit", failure_count=count)


def redacted_auth_event(
    *,
    event_type: str,
    user_id_hash: str | None = None,
    result: str,
    category: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "life_load_auth_event_v1",
        "event_type": event_type,
        "user_id_hash": user_id_hash,
        "result": result,
        "redacted_category": category,
    }


def _password_material(password: str, pepper: str) -> bytes:
    return f"{password}\0{pepper}".encode("utf-8") if pepper else password.encode("utf-8")
