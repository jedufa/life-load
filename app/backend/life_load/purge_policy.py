"""Purge and deletion policy skeleton for P-INFRA."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from life_load.sqlite_core import utc_now_iso

PURGE_IMPLEMENTED = False
PURGE_JOB_STATES = {
    "purge_requested",
    "purge_pending",
    "purge_in_progress",
    "purge_complete",
    "purge_failed",
    "purge_not_implemented",
}
PROHIBITED_DELETION_CLAIMS = (
    "deleted from our servers",
    "permanently deleted from our servers",
    "fully purged",
)
ALLOWED_DELETION_WORDING = (
    "removed from active restore, list, and download views",
    "marked deleted and excluded from restore/download; full purge is a future production feature",
)


@dataclass(frozen=True)
class DeletionContract:
    current_mode: str = "soft_delete_tombstone"
    soft_delete: bool = True
    active_list_excluded: bool = True
    restore_manifest_excluded: bool = True
    direct_download_blocked: bool = True
    deletion_event_recorded: bool = True
    purge_implemented: bool = PURGE_IMPLEMENTED

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_purge_policy_contract_v1",
            "current_mode": self.current_mode,
            "soft_delete": self.soft_delete,
            "active_list_excluded": self.active_list_excluded,
            "restore_manifest_excluded": self.restore_manifest_excluded,
            "direct_download_blocked": self.direct_download_blocked,
            "deletion_event_recorded": self.deletion_event_recorded,
            "purge_implemented": self.purge_implemented,
            "allowed_wording": list(ALLOWED_DELETION_WORDING),
            "prohibited_claims": list(PROHIBITED_DELETION_CLAIMS),
        }


@dataclass(frozen=True)
class PurgeIntent:
    scope: str
    user_id_hash: str
    object_id_hash: str
    requested_at: str
    status: str = "recorded"
    purge_implemented: bool = PURGE_IMPLEMENTED

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_purge_intent_v1",
            "scope": self.scope,
            "user_id_hash": self.user_id_hash,
            "object_id_hash": self.object_id_hash,
            "requested_at": self.requested_at,
            "status": self.status,
            "purge_implemented": self.purge_implemented,
        }


@dataclass(frozen=True)
class PurgeJob:
    job_id: str
    user_id_hash: str
    scope: str
    object_id_hash: str
    status: str
    retry_count: int
    requested_at: str
    completed_at: str = ""
    failed_at: str = ""
    last_error_code: str = ""
    deletion_receipt_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_purge_job_v1",
            "job_id": self.job_id,
            "user_id_hash": self.user_id_hash,
            "scope": self.scope,
            "object_id_hash": self.object_id_hash,
            "status": self.status,
            "retry_count": self.retry_count,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "failed_at": self.failed_at,
            "last_error_code": self.last_error_code,
            "deletion_receipt_id": self.deletion_receipt_id,
            "purge_implemented": self.status == "purge_complete",
        }


class SQLitePurgeJobStore:
    """Local/dev purge-job lifecycle model for production-shaped drills."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def request_purge(self, *, user_id: str, scope: str, object_id: str = "") -> dict[str, Any]:
        safe_scope = _safe_scope(scope)
        now = utc_now_iso()
        job = PurgeJob(
            job_id=f"pur_{_hash_identifier(user_id + ':' + safe_scope + ':' + object_id + ':' + now)}",
            user_id_hash=_hash_identifier(user_id),
            scope=safe_scope,
            object_id_hash=_hash_identifier(object_id),
            status="purge_requested",
            retry_count=0,
            requested_at=now,
        )
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO purge_jobs(
                    job_id, user_id_hash, scope, object_id_hash, status, retry_count,
                    requested_at, completed_at, failed_at, last_error_code, deletion_receipt_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', '', '')
                """,
                (
                    job.job_id,
                    job.user_id_hash,
                    job.scope,
                    job.object_id_hash,
                    job.status,
                    job.retry_count,
                    job.requested_at,
                ),
            )
        return job.as_dict()

    def mark_pending(self, job_id: str) -> dict[str, Any]:
        return self._transition(job_id, status="purge_pending")

    def mark_in_progress(self, job_id: str) -> dict[str, Any]:
        return self._transition(job_id, status="purge_in_progress")

    def mark_not_implemented(self, job_id: str, *, error_code: str = "purge_not_implemented") -> dict[str, Any]:
        return self._transition(job_id, status="purge_not_implemented", error_code=error_code, failed=True)

    def mark_failed(self, job_id: str, *, error_code: str) -> dict[str, Any]:
        return self._transition(job_id, status="purge_failed", error_code=error_code, failed=True, increment_retry=True)

    def mark_complete(self, job_id: str, *, deletion_receipt_id: str | None = None) -> dict[str, Any]:
        receipt_id = deletion_receipt_id or f"drp_{_hash_identifier(job_id + ':' + utc_now_iso())}"
        return self._transition(job_id, status="purge_complete", completed=True, receipt_id=receipt_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM purge_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("purge job not found")
        return _purge_job_from_row(row).as_dict()

    def report(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM purge_jobs
                GROUP BY status
                ORDER BY status ASC
                """
            ).fetchall()
        return {
            "schema_version": "life_load_purge_job_report_v1",
            "counts_by_status": {str(row["status"]): int(row["count"]) for row in rows},
            "redacted": True,
            "contains_raw_user_id": False,
            "contains_raw_object_id": False,
            "production_hard_purge_claim": False,
        }

    def _transition(
        self,
        job_id: str,
        *,
        status: str,
        error_code: str = "",
        failed: bool = False,
        completed: bool = False,
        increment_retry: bool = False,
        receipt_id: str = "",
    ) -> dict[str, Any]:
        if status not in PURGE_JOB_STATES:
            raise ValueError("unsupported purge status")
        now = utc_now_iso()
        with self.connect() as conn, conn:
            existing = conn.execute("SELECT * FROM purge_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if existing is None:
                raise KeyError("purge job not found")
            retry_count = int(existing["retry_count"] or 0) + (1 if increment_retry else 0)
            conn.execute(
                """
                UPDATE purge_jobs
                SET status = ?, retry_count = ?, completed_at = ?, failed_at = ?,
                    last_error_code = ?, deletion_receipt_id = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    retry_count,
                    now if completed else str(existing["completed_at"] or ""),
                    now if failed else str(existing["failed_at"] or ""),
                    _safe_error_code(error_code),
                    receipt_id or str(existing["deletion_receipt_id"] or ""),
                    job_id,
                ),
            )
        return self.get_job(job_id)

    def _migrate(self) -> None:
        with self.connect() as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS purge_jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id_hash TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    object_id_hash TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    requested_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    failed_at TEXT NOT NULL DEFAULT '',
                    last_error_code TEXT NOT NULL DEFAULT '',
                    deletion_receipt_id TEXT NOT NULL DEFAULT ''
                )
                """
            )


def current_deletion_contract() -> dict[str, Any]:
    return DeletionContract().as_dict()


def record_purge_intent(*, user_id: str, scope: str, object_id: str = "") -> dict[str, Any]:
    return PurgeIntent(
        scope=_safe_scope(scope),
        user_id_hash=_hash_identifier(user_id),
        object_id_hash=_hash_identifier(object_id),
        requested_at=utc_now_iso(),
    ).as_dict()


def deletion_receipt_placeholder(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "life_load_deletion_receipt_placeholder_v1",
        "purge_implemented": False,
        "receipt_issued": False,
        "purge_intent_status": str(intent.get("status") or ""),
        "reason": "full object-store purge is a future production feature",
    }


def failed_purge_simulation(*, user_id: str, scope: str, object_id: str = "") -> dict[str, Any]:
    intent = record_purge_intent(user_id=user_id, scope=scope, object_id=object_id)
    return {
        "schema_version": "life_load_failed_purge_simulation_v1",
        "purge_implemented": False,
        "retry_required": True,
        "user_id_hash": intent["user_id_hash"],
        "object_id_hash": intent["object_id_hash"],
        "redacted_error_category": "purge_not_implemented",
    }


def assert_no_false_deletion_claim(text: str) -> None:
    normalized = text.lower()
    for claim in PROHIBITED_DELETION_CLAIMS:
        if claim in normalized:
            raise ValueError("false deletion claim before purge implementation")


def _safe_scope(scope: str) -> str:
    value = scope.strip().lower().replace(" ", "_")
    if value not in {"object", "all_backups", "account"}:
        raise ValueError("unsupported purge scope")
    return value


def _hash_identifier(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_error_code(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(value or "").strip().lower())[:80]


def _purge_job_from_row(row: sqlite3.Row) -> PurgeJob:
    return PurgeJob(
        job_id=str(row["job_id"]),
        user_id_hash=str(row["user_id_hash"]),
        scope=str(row["scope"]),
        object_id_hash=str(row["object_id_hash"] or ""),
        status=str(row["status"]),
        retry_count=int(row["retry_count"] or 0),
        requested_at=str(row["requested_at"]),
        completed_at=str(row["completed_at"] or ""),
        failed_at=str(row["failed_at"] or ""),
        last_error_code=str(row["last_error_code"] or ""),
        deletion_receipt_id=str(row["deletion_receipt_id"] or ""),
    )
