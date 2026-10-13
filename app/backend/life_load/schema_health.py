"""Schema and storage health checks for the Life Load SQLite stores."""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from life_load.sqlite_core import DEFAULT_ROOT_REL, MIGRATIONS, HealthObservabilityStore

SCHEMA_HEALTH_VERSION = "life_load_schema_health_v1"


def _row(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    result = conn.execute(sql, tuple(params)).fetchone()
    return dict(result) if result else None


def _rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in _rows(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {str(row["name"]) for row in _rows(conn, f"PRAGMA table_info({table})")}


def _count(conn: sqlite3.Connection, table: str) -> int:
    if table not in _tables(conn):
        return 0
    return int((_row(conn, f"SELECT COUNT(*) AS n FROM {table}") or {}).get("n") or 0)


def _duplicate_count(conn: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> int:
    if table not in _tables(conn) or not set(columns).issubset(_columns(conn, table)):
        return 0
    joined = ", ".join(columns)
    row = _row(
        conn,
        f"""
        SELECT COUNT(*) AS n
        FROM (
          SELECT {joined}
          FROM {table}
          GROUP BY {joined}
          HAVING COUNT(*) > 1
        )
        """,
    )
    return int((row or {}).get("n") or 0)


def _dbstat(conn: sqlite3.Connection) -> Dict[str, int]:
    try:
        return {
            str(row["name"]): int(row["bytes"] or 0)
            for row in _rows(
                conn,
                "SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name ORDER BY bytes DESC LIMIT 20",
            )
        }
    except sqlite3.Error:
        return {}


def _latest_live_import(conn: sqlite3.Connection) -> Dict[str, Any] | None:
    if "garmin_live_import_batch" not in _tables(conn):
        return None
    return _row(
        conn,
        """
        SELECT batch_id, completed_at, mode, requested_start_date, requested_end_date,
               days_imported, passive_created, passive_updated, activity_created,
               activity_updated, skipped, skipped_reason, ok, error
        FROM garmin_live_import_batch
        ORDER BY completed_at DESC, batch_id DESC
        LIMIT 1
        """,
    )


def _recent_stale_garmin_dates(conn: sqlite3.Connection) -> List[str]:
    if "garmin_daily_passive_summary" not in _tables(conn):
        return []
    today = dt.date.today()
    start = (today - dt.timedelta(days=10)).isoformat()
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=30)).isoformat(timespec="seconds")
    return [
        str(row["date"])
        for row in _rows(
            conn,
            """
            SELECT date
            FROM garmin_daily_passive_summary
            WHERE date >= ? AND (updated_at IS NULL OR updated_at = '' OR updated_at < ?)
            ORDER BY date DESC
            LIMIT 10
            """,
            (start, cutoff),
        )
    ]


def _inspect_db(path: Path, *, label: str) -> Dict[str, Any]:
    exists = path.exists()
    payload: Dict[str, Any] = {
        "label": label,
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
    }
    if not exists:
        return payload
    expected = [version for version, _ in MIGRATIONS]
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        tables = _tables(conn)
        applied = [
            str(row["version"])
            for row in _rows(conn, "SELECT version FROM schema_migrations ORDER BY version")
        ] if "schema_migrations" in tables else []
        daily_columns = _columns(conn, "daily_log")
        payload.update(
            {
                "tables": sorted(tables),
                "applied_migrations": applied,
                "expected_migrations": expected,
                "pending_migrations": [version for version in expected if version not in set(applied)],
                "row_counts": {
                    table: _count(conn, table)
                    for table in (
                        "daily_log",
                        "daily_log_draft",
                        "draft_entry",
                        "garmin_uploaded_files_manifest",
                        "garmin_daily_passive_summary",
                        "garmin_daily_wellness",
                        "garmin_sleep_session_raw",
                        "garmin_sleep_session",
                        "garmin_activity",
                        "garmin_live_import_batch",
                    )
                },
                "storage_top_bytes": _dbstat(conn),
                "latest_garmin_live_import_batch": _latest_live_import(conn),
                "recent_stale_garmin_dates": _recent_stale_garmin_dates(conn),
                "schema_flags": {
                    "has_daily_log_draft": "daily_log_draft" in tables,
                    "has_draft_entry": "draft_entry" in tables,
                    "has_user_approved_at": "user_approved_at" in daily_columns,
                    "has_approved_at": "approved_at" in daily_columns,
                    "has_coffee_cups": "coffee_cups" in daily_columns,
                    "has_garmin_live_import_batch": "garmin_live_import_batch" in tables,
                },
                "duplicate_risk": {
                    "garmin_passive_duplicate_dates": _duplicate_count(conn, "garmin_daily_passive_summary", ("date",)),
                    "garmin_wellness_duplicate_dates": _duplicate_count(conn, "garmin_daily_wellness", ("date",)),
                    "garmin_sleep_duplicate_sessions": _duplicate_count(conn, "garmin_sleep_session", ("date", "sleep_start_gmt", "sleep_end_gmt")),
                    "garmin_activity_duplicate_shape": _duplicate_count(conn, "garmin_activity", ("date", "activity_type", "start_time_local_iso", "duration_min", "distance_km")),
                },
            }
        )
    return payload


def ensure_runtime_schema(repo_root: Path) -> Dict[str, Any]:
    """Run the SQLite-core migrations against the active Life Load stores."""

    stores = [HealthObservabilityStore(repo_root=repo_root, root_rel=DEFAULT_ROOT_REL)]
    applied: Dict[str, List[str]] = {}
    reconciled: Dict[str, Dict[str, int]] = {}
    for store in stores:
        if store.root_rel == DEFAULT_ROOT_REL or store.db_path.exists() or store.root.exists():
            store.ensure_layout()
            applied[str(store.db_path)] = store.migrate()
            reconciled[str(store.db_path)] = reconcile_compatibility_tables(store.db_path)
    return {
        "schema_version": "life_load_schema_ensure_v1",
        "applied": applied,
        "reconciled": reconciled,
        "live_import_batches_copied_to_health": 0,
    }


def copy_live_import_batches_to_health(repo_root: Path) -> int:
    """Copy historical live-import audit rows from the default DB to health.sqlite."""

    source = repo_root / "data/life_load.sqlite"
    target = repo_root / "data/health.sqlite"
    if not source.exists() or not target.exists():
        return 0
    with sqlite3.connect(source) as src:
        src.row_factory = sqlite3.Row
        if "garmin_live_import_batch" not in _tables(src):
            return 0
        rows = _rows(
            src,
            """
            SELECT batch_id, started_at, completed_at, mode, requested_start_date, requested_end_date,
                   stale_dates_json, days_requested, days_imported, passive_created, passive_updated,
                   passive_unchanged, activity_created, activity_updated, activity_unchanged,
                   skipped, skipped_reason, ok, error, source_hashes_json, endpoint_status_json, result_json
            FROM garmin_live_import_batch
            """,
        )
    if not rows:
        return 0
    columns = (
        "batch_id",
        "started_at",
        "completed_at",
        "mode",
        "requested_start_date",
        "requested_end_date",
        "stale_dates_json",
        "days_requested",
        "days_imported",
        "passive_created",
        "passive_updated",
        "passive_unchanged",
        "activity_created",
        "activity_updated",
        "activity_unchanged",
        "skipped",
        "skipped_reason",
        "ok",
        "error",
        "source_hashes_json",
        "endpoint_status_json",
        "result_json",
    )
    placeholders = ", ".join("?" for _ in columns)
    with sqlite3.connect(target) as conn, conn:
        conn.row_factory = sqlite3.Row
        if "garmin_live_import_batch" not in _tables(conn):
            return 0
        before = _count(conn, "garmin_live_import_batch")
        conn.executemany(
            f"""
            INSERT OR IGNORE INTO garmin_live_import_batch({", ".join(columns)})
            VALUES ({placeholders})
            """,
            (
                tuple(row.get(column) for column in columns)
                for row in rows
            ),
        )
        after = _count(conn, "garmin_live_import_batch")
        return max(0, after - before)


def reconcile_compatibility_tables(db_path: Path) -> Dict[str, int]:
    """Bridge old/new Life Load tables without dropping old compatibility surfaces."""

    if not db_path.exists():
        return {"drafts_copied_to_core": 0, "approved_at_filled": 0, "user_approved_at_filled": 0}
    with sqlite3.connect(db_path) as conn, conn:
        conn.row_factory = sqlite3.Row
        tables = _tables(conn)
        drafts_copied = 0
        if {"daily_log_draft", "draft_entry"}.issubset(tables):
            rows = _rows(
                conn,
                """
                SELECT date, draft_payload, created_at, updated_at
                FROM daily_log_draft
                ORDER BY date
                """,
            )
            for row in rows:
                existing = _row(conn, "SELECT updated_at FROM draft_entry WHERE date = ?", (row["date"],))
                if existing and str(existing.get("updated_at") or "") >= str(row.get("updated_at") or ""):
                    continue
                try:
                    structured = row.get("draft_payload") if isinstance(row.get("draft_payload"), dict) else {}
                    if isinstance(row.get("draft_payload"), str):
                        import json

                        structured = json.loads(row["draft_payload"] or "{}")
                except Exception:
                    structured = {}
                if not isinstance(structured, Mapping):
                    structured = {}
                import json

                conn.execute(
                    """
                    INSERT INTO draft_entry(date, diary_text, structured_json, summary, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                      diary_text=excluded.diary_text,
                      structured_json=excluded.structured_json,
                      summary=excluded.summary,
                      updated_at=excluded.updated_at
                    """,
                    (
                        row["date"],
                        str(structured.get("diary_text") or ""),
                        json.dumps(structured, sort_keys=True),
                        str(structured.get("diary_summary") or "")[:180],
                        row.get("updated_at") or row.get("created_at") or "",
                    ),
                )
                drafts_copied += 1

        approved_at_filled = 0
        user_approved_at_filled = 0
        daily_columns = _columns(conn, "daily_log")
        if {"approved_at", "user_approved_at"}.issubset(daily_columns):
            approved_at_filled = conn.execute(
                """
                UPDATE daily_log
                SET approved_at = user_approved_at
                WHERE (approved_at IS NULL OR TRIM(approved_at) = '')
                  AND user_approved_at IS NOT NULL AND TRIM(user_approved_at) != ''
                """
            ).rowcount
            user_approved_at_filled = conn.execute(
                """
                UPDATE daily_log
                SET user_approved_at = approved_at
                WHERE (user_approved_at IS NULL OR TRIM(user_approved_at) = '')
                  AND approved_at IS NOT NULL AND TRIM(approved_at) != ''
                """
            ).rowcount
    return {
        "drafts_copied_to_core": int(drafts_copied),
        "approved_at_filled": int(approved_at_filled),
        "user_approved_at_filled": int(user_approved_at_filled),
    }


def schema_health_payload(repo_root: Path, *, ensure: bool = False) -> Dict[str, Any]:
    ensure_payload = ensure_runtime_schema(repo_root) if ensure else None
    default_db = HealthObservabilityStore(repo_root=repo_root, root_rel=DEFAULT_ROOT_REL).db_path
    configured_db = str(os.environ.get("LIFE_LOAD_DB_PATH") or "").strip()
    dbs = [
        *([_inspect_db(Path(configured_db).expanduser().resolve(), label="configured")] if configured_db else []),
        _inspect_db(default_db, label="default"),
    ]
    primary = (
        next((db for db in dbs if db.get("label") == "configured" and db.get("exists")), None)
        or next((db for db in dbs if db.get("label") == "default" and db.get("exists")), None)
        or dbs[0]
    )
    correctness_flags = []
    compatibility_flags = []
    flags = primary.get("schema_flags") if isinstance(primary.get("schema_flags"), Mapping) else {}
    if primary.get("pending_migrations"):
        correctness_flags.append("pending_migrations")
    if flags.get("has_daily_log_draft") and flags.get("has_draft_entry"):
        compatibility_flags.append("dual_draft_tables")
    if flags.get("has_user_approved_at") and flags.get("has_approved_at"):
        compatibility_flags.append("dual_approval_timestamps")
    if not flags.get("has_coffee_cups"):
        correctness_flags.append("missing_coffee_cups")
    if not flags.get("has_garmin_live_import_batch"):
        correctness_flags.append("missing_garmin_live_import_batch")
    return {
        "schema_version": SCHEMA_HEALTH_VERSION,
        "primary_db": primary.get("label"),
        "configured_db_path": str(Path(configured_db).expanduser().resolve()) if configured_db else "",
        "ok": not correctness_flags,
        "correctness_flags": correctness_flags,
        "compatibility_flags": compatibility_flags,
        "ensure": ensure_payload,
        "databases": dbs,
    }
