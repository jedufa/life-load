"""Local/dev observability sink for backend production-approximation drills."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from life_load.sqlite_core import utc_now_iso

OBSERVABILITY_SCHEMA_VERSION = "life_load_observability_event_v1"
SUMMARY_SCHEMA_VERSION = "life_load_observability_summary_v1"
EVENT_CATEGORIES = {
    "auth_failure",
    "rate_limit_hit",
    "backup_upload",
    "restore_manifest",
    "restore_failure",
    "delete_request",
    "purge_request",
    "purge_failure",
    "object_store_error",
    "crypto_validation_failure",
    "redaction_failure",
    "migration_failure",
    "scenario_failure",
}
FORBIDDEN_EVENT_KEYS = {
    "token",
    "session_token",
    "authorization",
    "password",
    "recovery_key",
    "recovery_phrase",
    "backup_key",
    "ciphertext",
    "payload",
    "diary",
    "health_payload",
    "garmin",
    "ai_prompt",
}


@dataclass(frozen=True)
class ObservabilityEvent:
    category: str
    request_id: str
    status_code: int
    user_id_hash: str = ""
    redacted_error_category: str = ""
    object_count: int = 0
    byte_size: int = 0
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "category": _safe_category(self.category),
            "request_id": _safe_text(self.request_id),
            "status_code": int(self.status_code),
            "user_id_hash": self.user_id_hash,
            "redacted_error_category": _safe_text(self.redacted_error_category),
            "object_count": int(self.object_count),
            "byte_size": int(self.byte_size),
            "created_at": self.created_at or utc_now_iso(),
        }


class JsonlObservabilitySink:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def record_event(
        self,
        *,
        category: str,
        request_id: str,
        status_code: int,
        user_id: str = "",
        redacted_error_category: str = "",
        object_count: int = 0,
        byte_size: int = 0,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if extra:
            _reject_sensitive_extra(extra)
        event = ObservabilityEvent(
            category=category,
            request_id=request_id,
            status_code=status_code,
            user_id_hash=_hash_user_id(user_id),
            redacted_error_category=redacted_error_category,
            object_count=object_count,
            byte_size=byte_size,
        ).as_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                events.append(parsed)
        return events

    def write_summary(self, *, output_json: Path, output_md: Path | None = None) -> dict[str, Any]:
        summary = observability_summary(self.read_events())
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output_md is not None:
            output_md.parent.mkdir(parents=True, exist_ok=True)
            output_md.write_text(_summary_markdown(summary), encoding="utf-8")
        return summary


def observability_summary(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_list = [dict(event) for event in events]
    categories = Counter(str(event.get("category") or "") for event in event_list)
    errors = Counter(str(event.get("redacted_error_category") or "") for event in event_list if event.get("redacted_error_category"))
    text = json.dumps(event_list, sort_keys=True).lower()
    forbidden_terms = sorted(term for term in FORBIDDEN_EVENT_KEYS if term in text and term not in {"user_id_hash"})
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "event_count": len(event_list),
        "category_counts": dict(sorted(categories.items())),
        "error_counts": dict(errors.most_common(20)),
        "privacy_scan": {
            "ok": not forbidden_terms,
            "forbidden_term_count": len(forbidden_terms),
            "redacted": True,
        },
        "contains_raw_user_id": False,
        "redacted": True,
    }


def _summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Observability Summary",
        "",
        f"- Schema: `{summary['schema_version']}`",
        f"- Events: `{summary['event_count']}`",
        f"- Privacy scan: `{'PASS' if summary['privacy_scan']['ok'] else 'FAIL'}`",
        "",
        "## Categories",
        "",
    ]
    for key, value in summary["category_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Error Classes", ""])
    for key, value in summary["error_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return "\n".join(lines)


def _reject_sensitive_extra(extra: Mapping[str, Any]) -> None:
    keys = {str(key).lower() for key in extra}
    if keys & FORBIDDEN_EVENT_KEYS:
        raise ValueError("observability event extra contains forbidden sensitive field")


def _hash_user_id(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_category(value: str) -> str:
    normalized = _safe_text(value)
    if normalized not in EVENT_CATEGORIES:
        return "scenario_failure"
    return normalized


def _safe_text(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(value or "").strip().lower())[:80]
