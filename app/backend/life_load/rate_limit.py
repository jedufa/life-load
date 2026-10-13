"""Rate limiting scaffolding for P-INFRA2 backend hardening."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RateLimitRule:
    route_class: str
    limit: int
    window_seconds: int
    mode: str = "observe"


@dataclass(frozen=True)
class AbuseGuardDecision:
    allowed: bool
    mode: str
    route_class: str
    count: int
    limit: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_abuse_guard_decision_v1",
            "allowed": self.allowed,
            "mode": self.mode,
            "route_class": self.route_class,
            "count": self.count,
            "limit": self.limit,
            "reason": self.reason,
        }


DEFAULT_RULES: dict[str, RateLimitRule] = {
    "auth_failure": RateLimitRule("auth_failure", limit=5, window_seconds=15 * 60, mode="enforce"),
    "backup_upload": RateLimitRule("backup_upload", limit=120, window_seconds=60, mode="observe"),
    "restore_manifest": RateLimitRule("restore_manifest", limit=60, window_seconds=60, mode="observe"),
    "delete": RateLimitRule("delete", limit=30, window_seconds=60, mode="observe"),
}


def hashed_dimension(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def decide_rate_limit(*, route_class: str, count: int, mode: str | None = None) -> AbuseGuardDecision:
    rule = DEFAULT_RULES.get(route_class, RateLimitRule(route_class, limit=60, window_seconds=60, mode="observe"))
    active_mode = (mode or rule.mode).strip().lower()
    over_limit = int(count) >= rule.limit
    allowed = not (active_mode == "enforce" and over_limit)
    return AbuseGuardDecision(
        allowed=allowed,
        mode=active_mode,
        route_class=route_class,
        count=max(0, int(count)),
        limit=rule.limit,
        reason="rate_limited" if not allowed else ("over_limit_observed" if over_limit else "within_limit"),
    )
