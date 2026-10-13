"""Local-development remote backend foundation for future encrypted backup.

This module is deliberately not wired to Android or the developer HTTP server.
It provides P-INFRA account namespace, auth/session, device, and opaque backup
object primitives with regression-testable privacy boundaries.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from life_load.auth_policy import hash_password_for_storage, hash_session_token, verify_password
from life_load.rate_limit import decide_rate_limit, hashed_dimension
from life_load.recovery_state import RecoveryContext, determine_recovery_state, redacted_recovery_state_report
from life_load.sqlite_core import utc_now_iso

REMOTE_BACKEND_DB_FILENAME = "remote_backend.sqlite"
REMOTE_BACKEND_SCHEMA_VERSION = "life_load_remote_backend_v0.1"
REMOTE_BACKEND_STORE_MODES = {"sqlite", "postgres"}
MAX_BACKUP_ENVELOPE_BYTES = 256 * 1024
MAX_IDEMPOTENCY_KEY_BYTES = 128
PASSWORD_HASH_ITERATIONS = 210_000
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30

_ALLOWED_REDACTED_SUMMARY_KEYS = {"entry_count", "date_min", "date_max"}
_ALLOWED_ENVIRONMENT_MODES = {"local", "dev", "staging", "production"}
_LOCAL_ENVIRONMENT_MODES = {"local", "dev"}
_SECRET_CONFIG_KEYS = {
    "database_url",
    "session_secret",
    "password_pepper",
    "object_store_secret",
    "tls_private_key_ref",
}
PLAN_CAPABILITY_REGISTRY: Mapping[str, tuple[str, ...]] = {
    "free": ("local_free_core", "manual_export_import"),
    "pro": ("local_free_core", "manual_export_import", "pro_interpretation_preview"),
    "plus": ("local_free_core", "manual_export_import", "plus_encrypted_backup"),
    "premium": (
        "local_free_core",
        "manual_export_import",
        "pro_interpretation_preview",
        "plus_encrypted_backup",
        "premium_integrations",
    ),
}
_AI_PAYLOAD_FORBIDDEN_KEYS = {
    "auth_token",
    "behavior_fields",
    "check_in_answers",
    "ciphertext",
    "diary_text",
    "family_notes",
    "guidance_context",
    "health_payload",
    "mood",
    "password",
    "recovery_key",
    "recovery_phrase",
    "sleep_context",
    "stress",
    "token",
    "wearable_summary",
    "work_notes",
}


REMOTE_BACKEND_MIGRATIONS: Sequence[tuple[str, Sequence[str]]] = (
    (
        "0001_remote_backend_foundation",
        (
            """
            CREATE TABLE IF NOT EXISTS remote_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email_normalized TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                external_auth_subject TEXT,
                created_at TEXT NOT NULL,
                disabled_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_label TEXT NOT NULL,
                platform TEXT NOT NULL,
                public_key TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS backup_namespaces (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                namespace_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS backup_objects (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                namespace_id TEXT NOT NULL,
                object_type TEXT NOT NULL,
                object_version INTEGER NOT NULL,
                encrypted_blob_ref TEXT,
                encrypted_blob TEXT NOT NULL,
                encrypted_blob_sha256 TEXT NOT NULL,
                encrypted_size_bytes INTEGER NOT NULL,
                client_created_at TEXT NOT NULL,
                server_received_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(namespace_id) REFERENCES backup_namespaces(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS backup_metadata (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                namespace_id TEXT NOT NULL,
                latest_backup_at TEXT,
                latest_backup_version INTEGER,
                object_count INTEGER NOT NULL DEFAULT 0,
                total_encrypted_size_bytes INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, namespace_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(namespace_id) REFERENCES backup_namespaces(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS deletion_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                completed_at TEXT,
                result TEXT NOT NULL,
                redacted_reason TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(device_id) REFERENCES devices(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                endpoint TEXT NOT NULL,
                result_code TEXT NOT NULL,
                object_count INTEGER,
                byte_size INTEGER,
                redacted_error_category TEXT,
                created_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "0002_restore_recovery_contract",
        (
            """
            CREATE TABLE IF NOT EXISTS recovery_material (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                material_type TEXT NOT NULL,
                status TEXT NOT NULL,
                public_hint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS recovery_events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                event_type TEXT NOT NULL,
                result TEXT NOT NULL,
                redacted_reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
        ),
    ),
    (
        "0003_observability_without_sensitive_logs",
        (
            """
            CREATE TABLE IF NOT EXISTS operational_events (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                timing_ms INTEGER NOT NULL,
                object_count INTEGER,
                byte_size INTEGER,
                user_id_hash TEXT,
                redacted_error_category TEXT,
                created_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "0004_backup_idempotency",
        (
            """
            CREATE TABLE IF NOT EXISTS backup_upload_idempotency (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,
                object_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, idempotency_key),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(object_id) REFERENCES backup_objects(id)
            )
            """,
        ),
    ),
    (
        "0005_auth_hardening_skeleton",
        (
            """
            CREATE TABLE IF NOT EXISTS auth_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                user_id_hash TEXT,
                result TEXT NOT NULL,
                redacted_category TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                id TEXT PRIMARY KEY,
                email_hash TEXT NOT NULL,
                user_id_hash TEXT,
                result TEXT NOT NULL,
                redacted_category TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS token_families (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(device_id) REFERENCES devices(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS account_recovery_events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                event_type TEXT NOT NULL,
                result TEXT NOT NULL,
                recovery_state TEXT NOT NULL,
                private_key_material_returned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
            "ALTER TABLE sessions ADD COLUMN token_family_id TEXT",
        ),
    ),
    (
        "0006_continuity_rehearsal_contracts",
        (
            """
            CREATE TABLE IF NOT EXISTS vault_key_packages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                package_type TEXT NOT NULL,
                key_version INTEGER NOT NULL,
                wrapping_mode TEXT NOT NULL,
                wrapped_key_hash TEXT NOT NULL,
                package_metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(device_id) REFERENCES devices(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trusted_device_requests (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                requesting_device_id TEXT NOT NULL,
                approving_device_id TEXT,
                status TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                decided_at TEXT,
                redacted_reason TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(requesting_device_id) REFERENCES devices(id),
                FOREIGN KEY(approving_device_id) REFERENCES devices(id)
            )
            """,
        ),
    ),
    (
        "0007_fake_user_simulation_indexes",
        (
            """
            CREATE INDEX IF NOT EXISTS idx_backup_objects_user_namespace_deleted
            ON backup_objects(user_id, namespace_id, deleted_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_backup_objects_user_deleted
            ON backup_objects(user_id, deleted_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_backup_objects_user_object_deleted
            ON backup_objects(user_id, id, deleted_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_backup_idempotency_user_key
            ON backup_upload_idempotency(user_id, idempotency_key)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_operational_events_error_category
            ON operational_events(redacted_error_category)
            """,
        ),
    ),
)


@dataclass(frozen=True)
class AuthSession:
    user_id: str
    device_id: str | None
    session_id: str


@dataclass
class RemoteBackendStore:
    repo_root: Path
    _migrations_checked: bool = field(default=False, init=False, repr=False)
    _write_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _failure_injections: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    @property
    def db_root(self) -> Path:
        return self.repo_root / "runtime" / "state" / "life_load_remote"

    @property
    def db_path(self) -> Path:
        override = str(os.environ.get("LIFE_LOAD_REMOTE_BACKEND_DB_PATH") or "").strip()
        if override:
            return Path(override).expanduser().resolve()
        return self.db_root / REMOTE_BACKEND_DB_FILENAME

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def migrate(self) -> list[str]:
        if self._migrations_checked:
            return []
        applied: list[str] = []
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS remote_schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            existing = {row[0] for row in conn.execute("SELECT version FROM remote_schema_migrations").fetchall()}
            for version, statements in REMOTE_BACKEND_MIGRATIONS:
                if version in existing:
                    continue
                with conn:
                    for statement in statements:
                        conn.execute(statement)
                    conn.execute(
                        "INSERT INTO remote_schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, utc_now_iso()),
                    )
                applied.append(version)
        self._migrations_checked = True
        return applied

    def register_user(self, *, email: str, password: str, device_label: str, platform: str) -> dict[str, str]:
        self.migrate()
        email_normalized = _normalize_email(email)
        password_hash = _hash_password(password)
        user_id = _new_id("usr")
        device_id = _new_id("dev")
        namespace_id = _new_id("bns")
        now = utc_now_iso()
        with self._write_lock, self.connect() as conn, conn:
            conn.execute(
                "INSERT INTO users(id, email_normalized, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, email_normalized, password_hash, now),
            )
            conn.execute(
                "INSERT INTO devices(id, user_id, device_label, platform, created_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, user_id, _short_label(device_label), _short_label(platform), now),
            )
            conn.execute(
                "INSERT INTO backup_namespaces(id, user_id, namespace_version, created_at) VALUES (?, ?, ?, ?)",
                (namespace_id, user_id, 1, now),
            )
            conn.execute(
                """
                INSERT INTO backup_metadata(
                    id, user_id, namespace_id, latest_backup_at, latest_backup_version,
                    object_count, total_encrypted_size_bytes
                ) VALUES (?, ?, ?, NULL, NULL, 0, 0)
                """,
                (_new_id("bmd"), user_id, namespace_id),
            )
            self._record_audit(conn, "auth.register", user_id=user_id, endpoint="/v1/auth/register", result_code="ok")
            self._record_auth_event(
                conn,
                "auth.register",
                user_id=user_id,
                result="ok",
                redacted_category="account_created",
            )
        token = self._create_session(user_id=user_id, device_id=device_id)
        return {"user_id": user_id, "device_id": device_id, "namespace_id": namespace_id, "session_token": token}

    def login(self, *, email: str, password: str, device_id: str | None = None) -> dict[str, str]:
        self.migrate()
        email_normalized = _normalize_email(email)
        with self.connect() as conn:
            recent_failures = self._recent_login_failure_count(conn, email_normalized)
            decision = decide_rate_limit(route_class="auth_failure", count=recent_failures)
            if not decision.allowed:
                self._record_login_attempt(
                    conn,
                    email_normalized=email_normalized,
                    user_id=None,
                    result="rate_limited",
                    redacted_category=decision.reason,
                )
                self._record_auth_event(
                    conn,
                    "auth.login",
                    user_id=None,
                    result="denied",
                    redacted_category=decision.reason,
                )
                conn.commit()
                raise PermissionError("rate limited")
            user = conn.execute(
                "SELECT * FROM users WHERE email_normalized = ? AND disabled_at IS NULL", (email_normalized,)
            ).fetchone()
            if user is None or not _verify_password(password, str(user["password_hash"] or "")):
                self._record_login_attempt(
                    conn,
                    email_normalized=email_normalized,
                    user_id=str(user["id"]) if user is not None else None,
                    result="denied",
                    redacted_category="invalid_credentials",
                )
                self._record_audit(
                    conn,
                    "auth.login",
                    user_id=str(user["id"]) if user is not None else None,
                    endpoint="/v1/auth/login",
                    result_code="denied",
                    redacted_error_category="invalid_credentials",
                )
                self._record_auth_event(
                    conn,
                    "auth.login",
                    user_id=str(user["id"]) if user is not None else None,
                    result="denied",
                    redacted_category="invalid_credentials",
                )
                conn.commit()
                raise PermissionError("invalid credentials")
            resolved_device_id = device_id or self._first_active_device_id(conn, str(user["id"]))
            if resolved_device_id is None:
                raise PermissionError("no active device")
            if not self._device_belongs_to_user(conn, device_id=resolved_device_id, user_id=str(user["id"])):
                self._record_audit(
                    conn,
                    "auth.login",
                    user_id=str(user["id"]),
                    endpoint="/v1/auth/login",
                    result_code="denied",
                    redacted_error_category="invalid_device",
                )
                self._record_auth_event(
                    conn,
                    "auth.login",
                    user_id=str(user["id"]),
                    result="denied",
                    redacted_category="invalid_device",
                )
                conn.commit()
                raise PermissionError("invalid device")
            self._record_login_attempt(
                conn,
                email_normalized=email_normalized,
                user_id=str(user["id"]),
                result="ok",
                redacted_category="authenticated",
            )
            self._record_audit(conn, "auth.login", user_id=str(user["id"]), endpoint="/v1/auth/login", result_code="ok")
            self._record_auth_event(
                conn,
                "auth.login",
                user_id=str(user["id"]),
                result="ok",
                redacted_category="authenticated",
            )
            conn.commit()
        token = self._create_session(user_id=str(user["id"]), device_id=resolved_device_id)
        return {"user_id": str(user["id"]), "device_id": resolved_device_id, "session_token": token}

    def logout(self, session_token: str) -> None:
        self.migrate()
        token_hash = _hash_token(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            session = conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
            if session is None:
                return
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (now, str(session["id"])))
            if session["token_family_id"]:
                conn.execute("UPDATE token_families SET revoked_at = ? WHERE id = ?", (now, str(session["token_family_id"])))
            self._record_audit(
                conn, "auth.logout", user_id=str(session["user_id"]), endpoint="/v1/auth/logout", result_code="ok"
            )
            self._record_auth_event(
                conn,
                "auth.logout",
                user_id=str(session["user_id"]),
                result="ok",
                redacted_category="session_revoked",
            )

    def register_device(self, session_token: str, *, device_label: str, platform: str) -> dict[str, str]:
        session = self.authenticate(session_token)
        device_id = _new_id("dev")
        with self.connect() as conn, conn:
            conn.execute(
                "INSERT INTO devices(id, user_id, device_label, platform, created_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, session.user_id, _short_label(device_label), _short_label(platform), utc_now_iso()),
            )
            self._record_audit(
                conn,
                "devices.register",
                user_id=session.user_id,
                endpoint="/v1/devices/register",
                result_code="ok",
            )
        return {"device_id": device_id}

    def revoke_device(self, session_token: str, *, device_id: str) -> None:
        session = self.authenticate(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            device = conn.execute(
                "SELECT * FROM devices WHERE id = ? AND user_id = ?", (device_id, session.user_id)
            ).fetchone()
            if device is None:
                raise PermissionError("device not found")
            conn.execute("UPDATE devices SET revoked_at = ? WHERE id = ?", (now, device_id))
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE device_id = ? AND user_id = ?",
                (now, device_id, session.user_id),
            )
            self._record_audit(
                conn,
                "devices.revoke",
                user_id=session.user_id,
                endpoint="/v1/devices/revoke",
                result_code="ok",
            )

    def disable_user(self, session_token: str) -> None:
        session = self.authenticate(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            conn.execute("UPDATE users SET disabled_at = ? WHERE id = ?", (now, session.user_id))
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ?", (now, session.user_id))
            self._record_audit(
                conn,
                "account.disable",
                user_id=session.user_id,
                endpoint="/v1/account",
                result_code="ok",
            )

    def corrupt_backup_object_for_test(self, session_token: str, *, object_id: str) -> None:
        """Dev-only test helper for restore failure drills.

        This is intentionally not a product API. It lets the Android Backend
        Test App validate safe restore behavior when an opaque object is
        corrupted at rest.
        """

        session = self.authenticate(session_token)
        with self.connect() as conn, conn:
            row = conn.execute(
                "SELECT id FROM backup_objects WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (object_id, session.user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("backup object not found")
            conn.execute("UPDATE backup_objects SET encrypted_blob = ? WHERE id = ?", ("not-json", object_id))
            self._record_audit(
                conn,
                "testing.backups.objects.corrupt",
                user_id=session.user_id,
                endpoint="/v1/testing/backups/objects/{id}/corrupt",
                result_code="ok",
            )

    def authenticate(self, session_token: str) -> AuthSession:
        self.migrate()
        token_hash = _hash_token(session_token)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT sessions.id AS session_id, sessions.user_id, sessions.device_id,
                       sessions.revoked_at AS session_revoked_at,
                       sessions.token_family_id,
                       token_families.revoked_at AS token_family_revoked_at,
                       sessions.expires_at,
                       users.disabled_at AS user_disabled_at,
                       devices.id AS joined_device_id,
                       devices.revoked_at AS device_revoked_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                LEFT JOIN devices ON devices.id = sessions.device_id AND devices.user_id = sessions.user_id
                LEFT JOIN token_families ON token_families.id = sessions.token_family_id
                WHERE sessions.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            raise PermissionError("invalid session")
        if row["device_id"] and row["joined_device_id"] is None:
            raise PermissionError("invalid device")
        if row["session_revoked_at"] or row["user_disabled_at"] or row["device_revoked_at"] or row["token_family_revoked_at"]:
            raise PermissionError("revoked session")
        if str(row["expires_at"]) <= utc_now_iso():
            raise PermissionError("expired session")
        return AuthSession(
            user_id=str(row["user_id"]),
            device_id=row["device_id"],
            session_id=str(row["session_id"]),
        )

    def create_backup_object(
        self,
        session_token: str,
        envelope: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        strict_production_crypto: bool = False,
    ) -> dict[str, Any]:
        session = self.authenticate(session_token)
        validated = self._validate_envelope(session, envelope, strict_production_crypto=strict_production_crypto)
        self._consume_object_store_failure("put")
        object_id = _new_id("bko")
        envelope_text = json.dumps(validated, ensure_ascii=False, sort_keys=True)
        request_sha = hashlib.sha256(envelope_text.encode("utf-8")).hexdigest()
        normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
        now = utc_now_iso()
        with self._write_lock, self.connect() as conn, conn:
            if normalized_idempotency_key:
                prior = conn.execute(
                    """
                    SELECT object_id, request_sha256
                    FROM backup_upload_idempotency
                    WHERE user_id = ? AND idempotency_key = ?
                    """,
                    (session.user_id, normalized_idempotency_key),
                ).fetchone()
                if prior is not None:
                    if not hmac.compare_digest(str(prior["request_sha256"]), request_sha):
                        raise ValueError("idempotency key conflict")
                    return {
                        "object_id": str(prior["object_id"]),
                        "server_received_at": now,
                        "idempotent_replay": True,
                    }
            expected_latest = envelope.get("expected_latest_backup_version")
            if expected_latest is not None:
                row = conn.execute(
                    """
                    SELECT latest_backup_version
                    FROM backup_metadata
                    WHERE user_id = ? AND namespace_id = ?
                    """,
                    (session.user_id, str(validated["user_namespace_id"])),
                ).fetchone()
                current_latest = row["latest_backup_version"] if row is not None else None
                if expected_latest != current_latest:
                    raise ValueError("backup object version conflict")
            conn.execute(
                """
                INSERT INTO backup_objects(
                    id, user_id, namespace_id, object_type, object_version,
                    encrypted_blob_ref, encrypted_blob, encrypted_blob_sha256,
                    encrypted_size_bytes, client_created_at, server_received_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    object_id,
                    session.user_id,
                    str(validated["user_namespace_id"]),
                    str(validated["payload_type"]),
                    int(validated["payload_version"]),
                    envelope_text,
                    str(validated["ciphertext_sha256"]),
                    len(str(validated["ciphertext"]).encode("utf-8")),
                    str(validated["created_at"]),
                    now,
                ),
            )
            if normalized_idempotency_key:
                conn.execute(
                    """
                    INSERT INTO backup_upload_idempotency(
                        id, user_id, idempotency_key, request_sha256, object_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (_new_id("bid"), session.user_id, normalized_idempotency_key, request_sha, object_id, now),
                )
            self._record_created_object_metadata(
                conn,
                user_id=session.user_id,
                namespace_id=str(validated["user_namespace_id"]),
                object_version=int(validated["payload_version"]),
                encrypted_size_bytes=len(str(validated["ciphertext"]).encode("utf-8")),
                server_received_at=now,
            )
            self._record_audit(
                conn,
                "backups.objects.create",
                user_id=session.user_id,
                endpoint="/v1/backups/objects",
                result_code="ok",
                object_count=1,
                byte_size=len(str(validated["ciphertext"]).encode("utf-8")),
            )
        return {"object_id": object_id, "server_received_at": now}

    def list_backup_objects(self, session_token: str, *, namespace_id: str | None = None) -> list[dict[str, Any]]:
        session = self.authenticate(session_token)
        self._consume_object_store_failure("list")
        with self.connect() as conn:
            params: list[Any] = [session.user_id]
            where = "user_id = ? AND deleted_at IS NULL"
            if namespace_id is not None:
                where += " AND namespace_id = ?"
                params.append(namespace_id)
            rows = conn.execute(
                f"""
                SELECT id, namespace_id, object_type, object_version, encrypted_blob_sha256,
                       encrypted_size_bytes, client_created_at, server_received_at
                FROM backup_objects
                WHERE {where}
                ORDER BY server_received_at ASC, id ASC
                """,
                params,
            ).fetchall()
        return [_object_metadata(row) for row in rows]

    def get_backup_object(self, session_token: str, object_id: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        self._consume_object_store_failure("get")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT encrypted_blob FROM backup_objects WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (object_id, session.user_id),
            ).fetchone()
        if row is None:
            raise PermissionError("backup object not found")
        value = json.loads(str(row["encrypted_blob"]))
        if not isinstance(value, dict):
            raise ValueError("stored envelope is invalid")
        return value

    def restore_manifest(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        objects = self.list_backup_objects(session_token)
        status = self.backup_status(session_token)
        with self.connect() as conn, conn:
            self._record_audit(
                conn,
                "backups.restore.manifest",
                user_id=session.user_id,
                endpoint="/v1/restore/objects",
                result_code="ok",
                object_count=len(objects),
                byte_size=status["total_encrypted_size_bytes"],
            )
        return {
            "schema_version": "life_load_restore_manifest_v1",
            "user_id": session.user_id,
            "object_count": status["object_count"],
            "total_encrypted_size_bytes": status["total_encrypted_size_bytes"],
            "latest_backup_at": status["latest_backup_at"],
            "objects": objects,
        }

    def download_restore_object(self, session_token: str, object_id: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        envelope = self.get_backup_object(session_token, object_id)
        with self.connect() as conn, conn:
            self._record_audit(
                conn,
                "backups.restore.download",
                user_id=session.user_id,
                endpoint="/v1/restore/objects/{id}",
                result_code="ok",
                object_count=1,
                byte_size=len(str(envelope.get("ciphertext") or "").encode("utf-8")),
            )
        return envelope

    def create_recovery_material_placeholder(self, session_token: str, *, material_type: str) -> dict[str, str]:
        session = self.authenticate(session_token)
        normalized_type = _normalize_recovery_material_type(material_type)
        material_id = _new_id("rcv")
        public_hint = f"{normalized_type}_configured"
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO recovery_material(id, user_id, material_type, status, public_hint, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (material_id, session.user_id, normalized_type, "placeholder", public_hint, utc_now_iso()),
            )
            self._record_recovery_event(
                conn,
                user_id=session.user_id,
                event_type="recovery.material.placeholder",
                result="placeholder_created",
                redacted_reason=normalized_type,
            )
        return {
            "material_id": material_id,
            "material_type": normalized_type,
            "status": "placeholder",
            "public_hint": public_hint,
        }

    def create_vault_key_package(
        self,
        session_token: str,
        *,
        package_type: str,
        wrapping_mode: str,
        wrapped_key_hash: str,
        key_version: int = 1,
        device_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a wrapped vault-key package without storing plaintext keys.

        This is a backend continuity rehearsal contract. The backend stores
        package metadata plus a hash/reference for the already-wrapped key; it
        never receives or returns a plaintext Vault Key, recovery key, or device
        private key.
        """

        session = self.authenticate(session_token)
        normalized_type = _normalize_vault_package_type(package_type)
        normalized_wrapping = _normalize_wrapping_mode(wrapping_mode)
        normalized_hash = _normalize_wrapped_key_hash(wrapped_key_hash)
        normalized_version = _normalize_key_version(key_version)
        resolved_device_id = str(device_id or session.device_id or "").strip() or None
        safe_metadata = _redacted_package_metadata(metadata or {})
        package_id = _new_id("vkp")
        now = utc_now_iso()
        with self.connect() as conn, conn:
            if resolved_device_id is not None and not self._device_belongs_to_user(
                conn, device_id=resolved_device_id, user_id=session.user_id
            ):
                raise PermissionError("device not found")
            conn.execute(
                """
                INSERT INTO vault_key_packages(
                    id, user_id, device_id, package_type, key_version, wrapping_mode,
                    wrapped_key_hash, package_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package_id,
                    session.user_id,
                    resolved_device_id,
                    normalized_type,
                    normalized_version,
                    normalized_wrapping,
                    normalized_hash,
                    json.dumps(safe_metadata, sort_keys=True),
                    now,
                ),
            )
            if normalized_type == "recovery_wrap":
                self._record_recovery_event(
                    conn,
                    user_id=session.user_id,
                    event_type="vault.recovery_wrap.create",
                    result="ok",
                    redacted_reason="wrapped_key_package_only",
                )
            self._record_audit(
                conn,
                "vault.key_package.create",
                user_id=session.user_id,
                endpoint="/v1/vault/key-packages",
                result_code="ok",
            )
        return {
            "schema_version": "life_load_vault_key_package_v1",
            "package_id": package_id,
            "package_type": normalized_type,
            "device_id": resolved_device_id or "",
            "key_version": normalized_version,
            "wrapping_mode": normalized_wrapping,
            "wrapped_key_hash": normalized_hash,
            "created_at": now,
            "plaintext_vault_key_returned": False,
            "recovery_material_returned": False,
        }

    def list_vault_key_packages(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, device_id, package_type, key_version, wrapping_mode,
                       wrapped_key_hash, package_metadata_json, created_at, revoked_at
                FROM vault_key_packages
                WHERE user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session.user_id,),
            ).fetchall()
        packages = [_vault_package_metadata(row) for row in rows]
        return {
            "schema_version": "life_load_vault_key_packages_v1",
            "user_id_hash": _hash_user_id(session.user_id),
            "package_count": len(packages),
            "plaintext_vault_key_available": False,
            "packages": packages,
        }

    def revoke_vault_key_package(self, session_token: str, *, package_id: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            row = conn.execute(
                """
                SELECT id, package_type
                FROM vault_key_packages
                WHERE id = ? AND user_id = ? AND revoked_at IS NULL
                """,
                (package_id, session.user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("vault key package not found")
            conn.execute("UPDATE vault_key_packages SET revoked_at = ? WHERE id = ?", (now, package_id))
            self._record_audit(
                conn,
                "vault.key_package.revoke",
                user_id=session.user_id,
                endpoint="/v1/vault/key-packages/{id}/revoke",
                result_code="ok",
            )
            if str(row["package_type"]) == "recovery_wrap":
                self._record_recovery_event(
                    conn,
                    user_id=session.user_id,
                    event_type="vault.recovery_wrap.revoke",
                    result="ok",
                    redacted_reason="wrapped_key_package_revoked",
                )
        return {
            "schema_version": "life_load_vault_key_package_revoke_v1",
            "ok": True,
            "package_id": package_id,
            "revoked": True,
            "plaintext_vault_key_returned": False,
        }

    def rotate_recovery_package(
        self,
        session_token: str,
        *,
        old_package_id: str,
        wrapped_key_hash: str,
        wrapping_mode: str = "recovery_key_prototype",
        key_version: int = 1,
    ) -> dict[str, Any]:
        session = self.authenticate(session_token)
        normalized_wrapping = _normalize_wrapping_mode(wrapping_mode)
        normalized_hash = _normalize_wrapped_key_hash(wrapped_key_hash)
        normalized_version = _normalize_key_version(key_version)
        now = utc_now_iso()
        new_package_id = _new_id("vkp")
        with self._write_lock, self.connect() as conn, conn:
            old = conn.execute(
                """
                SELECT id
                FROM vault_key_packages
                WHERE id = ? AND user_id = ? AND package_type = 'recovery_wrap' AND revoked_at IS NULL
                """,
                (old_package_id, session.user_id),
            ).fetchone()
            if old is None:
                raise PermissionError("active recovery package not found")
            conn.execute("UPDATE vault_key_packages SET revoked_at = ? WHERE id = ?", (now, old_package_id))
            metadata = {"source": "recovery_package_rotation", "rotated_from_hash": _hash_user_id(old_package_id)}
            conn.execute(
                """
                INSERT INTO vault_key_packages(
                    id, user_id, device_id, package_type, key_version, wrapping_mode,
                    wrapped_key_hash, package_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_package_id,
                    session.user_id,
                    session.device_id,
                    "recovery_wrap",
                    normalized_version,
                    normalized_wrapping,
                    normalized_hash,
                    json.dumps(metadata, sort_keys=True),
                    now,
                ),
            )
            self._record_recovery_event(
                conn,
                user_id=session.user_id,
                event_type="vault.recovery_wrap.rotate",
                result="ok",
                redacted_reason="wrapped_key_package_rotated",
            )
            self._record_audit(
                conn,
                "vault.recovery_package.rotate",
                user_id=session.user_id,
                endpoint="/v1/vault/recovery-packages/rotate",
                result_code="ok",
            )
        return {
            "schema_version": "life_load_recovery_package_rotate_v1",
            "ok": True,
            "old_package_id": old_package_id,
            "old_package_revoked": True,
            "new_package_id": new_package_id,
            "active_recovery_package_count": 1,
            "plaintext_vault_key_returned": False,
            "recovery_material_returned": False,
        }

    def create_trusted_device_request(
        self,
        session_token: str,
        *,
        requesting_device_id: str,
        expires_in_seconds: int = 900,
    ) -> dict[str, Any]:
        session = self.authenticate(session_token)
        if session.device_id != requesting_device_id:
            raise PermissionError("requesting device mismatch")
        request_id = _new_id("tdr")
        now = utc_now_iso()
        expires_at = _iso_plus_seconds(max(60, min(int(expires_in_seconds), 3600)))
        with self.connect() as conn, conn:
            if not self._device_belongs_to_user(conn, device_id=requesting_device_id, user_id=session.user_id):
                raise PermissionError("device not found")
            conn.execute(
                """
                INSERT INTO trusted_device_requests(
                    id, user_id, requesting_device_id, status, requested_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, session.user_id, requesting_device_id, "pending_trust", now, expires_at),
            )
            self._record_audit(
                conn,
                "devices.trust_request.create",
                user_id=session.user_id,
                endpoint="/v1/devices/trust-requests",
                result_code="ok",
            )
        return {
            "schema_version": "life_load_trusted_device_request_v1",
            "request_id": request_id,
            "status": "pending_trust",
            "requesting_device_id": requesting_device_id,
            "expires_at": expires_at,
            "backend_can_approve_without_trusted_device": False,
        }

    def decide_trusted_device_request(
        self,
        session_token: str,
        *,
        request_id: str,
        decision: str,
        wrapped_key_hash: str | None = None,
    ) -> dict[str, Any]:
        session = self.authenticate(session_token)
        normalized_decision = _normalize_trust_decision(decision)
        now = utc_now_iso()
        with self._write_lock, self.connect() as conn, conn:
            request = conn.execute(
                """
                SELECT *
                FROM trusted_device_requests
                WHERE id = ? AND user_id = ?
                """,
                (request_id, session.user_id),
            ).fetchone()
            if request is None:
                raise PermissionError("trust request not found")
            if str(request["status"]) != "pending_trust":
                raise ValueError("trust request already decided")
            if str(request["expires_at"]) <= now:
                conn.execute(
                    """
                    UPDATE trusted_device_requests
                    SET status = ?, decided_at = ?, redacted_reason = ?
                    WHERE id = ?
                    """,
                    ("expired", now, "request_expired", request_id),
                )
                raise ValueError("trust request expired")
            if session.device_id == str(request["requesting_device_id"]):
                raise PermissionError("requesting device cannot approve itself")
            if session.device_id is None or not self._device_belongs_to_user(
                conn, device_id=session.device_id, user_id=session.user_id
            ):
                raise PermissionError("approving device revoked")
            status = "approved" if normalized_decision == "approve" else "denied"
            conn.execute(
                """
                UPDATE trusted_device_requests
                SET status = ?, approving_device_id = ?, decided_at = ?, redacted_reason = ?
                WHERE id = ?
                """,
                (status, session.device_id, now, "trusted_device_decision", request_id),
            )
            package_id = ""
            if normalized_decision == "approve":
                package_hash = _normalize_wrapped_key_hash(wrapped_key_hash or "")
                package_id = _new_id("vkp")
                metadata = {"source": "trusted_device_transfer", "request_id_hash": _hash_user_id(request_id)}
                conn.execute(
                    """
                    INSERT INTO vault_key_packages(
                        id, user_id, device_id, package_type, key_version, wrapping_mode,
                        wrapped_key_hash, package_metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        package_id,
                        session.user_id,
                        str(request["requesting_device_id"]),
                        "device_wrap",
                        1,
                        "trusted_device_transfer",
                        package_hash,
                        json.dumps(metadata, sort_keys=True),
                        now,
                    ),
                )
            self._record_audit(
                conn,
                "devices.trust_request.decide",
                user_id=session.user_id,
                endpoint="/v1/devices/trust-requests/{id}/decision",
                result_code=status,
            )
        return {
            "schema_version": "life_load_trusted_device_decision_v1",
            "request_id": request_id,
            "status": status,
            "wrapped_key_package_created": bool(package_id),
            "package_id": package_id,
            "plaintext_vault_key_returned": False,
        }

    def expire_trusted_device_request_for_test(self, session_token: str, *, request_id: str) -> dict[str, Any]:
        """Dev-only helper to make trust-request expiry deterministic in tests."""

        session = self.authenticate(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            row = conn.execute(
                """
                SELECT id
                FROM trusted_device_requests
                WHERE id = ? AND user_id = ? AND status = 'pending_trust'
                """,
                (request_id, session.user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("trust request not found")
            conn.execute(
                """
                UPDATE trusted_device_requests
                SET status = ?, decided_at = ?, redacted_reason = ?
                WHERE id = ?
                """,
                ("expired", now, "test_expired", request_id),
            )
            self._record_audit(
                conn,
                "testing.devices.trust_request.expire",
                user_id=session.user_id,
                endpoint="/v1/testing/devices/trust-requests/{id}/expire",
                result_code="ok",
            )
        return {
            "schema_version": "life_load_trusted_device_test_expire_v1",
            "ok": True,
            "request_id": request_id,
            "status": "expired",
        }

    def server_metadata_view(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        with self.connect() as conn:
            devices = conn.execute(
                """
                SELECT id, device_label, platform, created_at, revoked_at
                FROM devices
                WHERE user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session.user_id,),
            ).fetchall()
            objects = conn.execute(
                """
                SELECT id, namespace_id, object_type, object_version,
                       encrypted_blob_sha256, encrypted_size_bytes,
                       client_created_at, server_received_at, deleted_at
                FROM backup_objects
                WHERE user_id = ?
                ORDER BY server_received_at ASC, id ASC
                """,
                (session.user_id,),
            ).fetchall()
            recovery_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM vault_key_packages WHERE user_id = ? AND package_type = 'recovery_wrap' AND revoked_at IS NULL",
                    (session.user_id,),
                ).fetchone()[0]
            )
            trusted_request_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM trusted_device_requests WHERE user_id = ?",
                    (session.user_id,),
                ).fetchone()[0]
            )
        return {
            "schema_version": "life_load_server_visible_metadata_v1",
            "user_id_hash": _hash_user_id(session.user_id),
            "devices": [_device_metadata(row) for row in devices],
            "backup_objects": [_server_object_metadata(row) for row in objects],
            "recovery_package_exists": recovery_count > 0,
            "trusted_device_request_count": trusted_request_count,
            "server_can_read_private_payloads": False,
            "plaintext_key_material_available": False,
            "forbidden_payload_fields_absent": True,
        }

    def support_summary(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        status = self.backup_status(session_token)
        with self.connect() as conn:
            device_counts = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN revoked_at IS NULL THEN 1 ELSE 0 END), 0) AS active_devices,
                    COALESCE(SUM(CASE WHEN revoked_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS revoked_devices
                FROM devices
                WHERE user_id = ?
                """,
                (session.user_id,),
            ).fetchone()
            package_counts = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN package_type = 'recovery_wrap' AND revoked_at IS NULL THEN 1 ELSE 0 END), 0)
                        AS recovery_packages,
                    COALESCE(SUM(CASE WHEN package_type = 'device_wrap' AND revoked_at IS NULL THEN 1 ELSE 0 END), 0)
                        AS device_packages
                FROM vault_key_packages
                WHERE user_id = ?
                """,
                (session.user_id,),
            ).fetchone()
        recovery_available = int(package_counts["recovery_packages"] or 0) > 0
        trusted_available = int(package_counts["device_packages"] or 0) > 0 or int(device_counts["active_devices"] or 0) > 0
        recovery_state = determine_recovery_state(
            RecoveryContext(
                has_local_key=False,
                trusted_device_available=trusted_available,
                recovery_key_available=recovery_available,
            )
        )
        return {
            "schema_version": "life_load_support_summary_v1",
            "user_id_hash": _hash_user_id(session.user_id),
            "active_device_count": int(device_counts["active_devices"] or 0),
            "revoked_device_count": int(device_counts["revoked_devices"] or 0),
            "backup_object_count": int(status["object_count"]),
            "latest_backup_at": status["latest_backup_at"],
            "recovery_package_exists": recovery_available,
            "active_recovery_package_count": int(package_counts["recovery_packages"] or 0),
            "recovery_state": recovery_state.state,
            "support_can_decrypt_private_history": False,
            "support_can_bypass_recovery_material": False,
            "support_script": (
                "Life Load can help with account access and device revocation, "
                "but cannot decrypt private history without a trusted device or recovery key."
            ),
        }

    def password_reset_account_access_only(self, *, email: str) -> dict[str, Any]:
        self.migrate()
        email_normalized = _normalize_email(email)
        with self.connect() as conn, conn:
            user = conn.execute("SELECT id FROM users WHERE email_normalized = ?", (email_normalized,)).fetchone()
            user_id = str(user["id"]) if user is not None else None
            self._record_recovery_event(
                conn,
                user_id=user_id,
                event_type="auth.password_reset.request",
                result="account_access_only",
                redacted_reason="does_not_recover_private_history",
            )
            self._record_account_recovery_event(
                conn,
                user_id=user_id,
                event_type="auth.password_reset.request",
                result="account_access_only",
                recovery_state="recovery_required",
            )
            self._record_auth_event(
                conn,
                "auth.password_reset.request",
                user_id=user_id,
                result="account_access_only",
                redacted_category="does_not_recover_private_history",
            )
        return {
            "schema_version": "life_load_password_reset_contract_v1",
            "ok": True,
            "account_access_only": True,
            "private_history_recovered": False,
            "recovery_material_returned": False,
            "backup_key_returned": False,
        }

    def auth_policy_status(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_auth_policy_status_v1",
            "session_token_hash": "hmac_sha256" if os.environ.get("LIFE_LOAD_SESSION_TOKEN_HMAC_SECRET") else "sha256",
            "password_hash": "pbkdf2_sha256_peppered" if os.environ.get("LIFE_LOAD_PASSWORD_PEPPER") else "pbkdf2_sha256",
            "refresh_token_rotation": "placeholder",
            "device_bound_sessions": True,
            "password_reset_recovers_private_history": False,
        }

    def revoke_token_family(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            row = conn.execute("SELECT token_family_id FROM sessions WHERE id = ?", (session.session_id,)).fetchone()
            family_id = str(row["token_family_id"] or "") if row is not None else ""
            if not family_id:
                raise PermissionError("token family not found")
            conn.execute("UPDATE token_families SET revoked_at = ? WHERE id = ?", (now, family_id))
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE token_family_id = ?", (now, family_id))
            self._record_auth_event(
                conn,
                "auth.token_family.revoke",
                user_id=session.user_id,
                result="ok",
                redacted_category="token_family_revoked",
            )
        return {"schema_version": "life_load_token_family_revoke_v1", "ok": True, "token_family_revoked": True}

    def refresh_session_placeholder(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        with self.connect() as conn:
            row = conn.execute("SELECT token_family_id FROM sessions WHERE id = ?", (session.session_id,)).fetchone()
        return {
            "schema_version": "life_load_refresh_token_rotation_placeholder_v1",
            "implemented": False,
            "token_family_id_hash": _hash_user_id(str(row["token_family_id"] or "")) if row is not None else "",
            "rotates_refresh_token": False,
            "reason": "future_production_auth_hardening",
        }

    def rotate_refresh_session(self, session_token: str, *, device_id: str | None = None) -> dict[str, Any]:
        """Rotate a local/dev refresh-style session within the existing token family.

        This is production-shaped scaffolding for tests only. It revokes the
        presented session token, creates a replacement token bound to the same
        device and token family, and records only redacted auth events.
        """

        session = self.authenticate(session_token)
        if device_id and session.device_id and device_id != session.device_id:
            raise PermissionError("device mismatch")
        now = utc_now_iso()
        new_token = secrets.token_urlsafe(32)
        new_session_id = _new_id("ses")
        with self._write_lock, self.connect() as conn, conn:
            row = conn.execute(
                "SELECT token_family_id FROM sessions WHERE id = ?",
                (session.session_id,),
            ).fetchone()
            family_id = str(row["token_family_id"] or "") if row is not None else ""
            if not family_id:
                raise PermissionError("token family not found")
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (now, session.session_id))
            conn.execute(
                """
                INSERT INTO sessions(id, user_id, device_id, token_hash, created_at, expires_at, token_family_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_session_id,
                    session.user_id,
                    session.device_id,
                    _hash_token(new_token),
                    now,
                    _iso_plus_seconds(SESSION_TTL_SECONDS),
                    family_id,
                ),
            )
            self._record_auth_event(
                conn,
                "auth.refresh.rotate",
                user_id=session.user_id,
                result="ok",
                redacted_category="refresh_rotated",
            )
        return {
            "schema_version": "life_load_refresh_token_rotation_skeleton_v1",
            "ok": True,
            "rotates_refresh_token": True,
            "old_token_revoked": True,
            "session_token": new_token,
            "token_family_id_hash": _hash_user_id(family_id),
        }

    def simulate_rate_limit_decision(self, *, route_class: str, count: int, mode: str | None = None) -> dict[str, Any]:
        decision = decide_rate_limit(route_class=route_class, count=count, mode=mode)
        self.record_request_observation(
            endpoint=f"/v1/testing/rate-limit/{route_class}",
            status_code=429 if not decision.allowed else 200,
            timing_ms=1,
            redacted_error_category=decision.reason,
        )
        return decision.as_dict()

    def recovery_state_for_test(self, context: Mapping[str, Any]) -> dict[str, Any]:
        result = determine_recovery_state(
            RecoveryContext(
                has_local_key=bool(context.get("has_local_key")),
                trusted_device_available=bool(context.get("trusted_device_available")),
                recovery_key_available=bool(context.get("recovery_key_available")),
                account_password_reset=bool(context.get("account_password_reset")),
                current_device_revoked=bool(context.get("current_device_revoked")),
                all_recovery_material_lost=bool(context.get("all_recovery_material_lost")),
                new_vault_created=bool(context.get("new_vault_created")),
            )
        )
        return redacted_recovery_state_report(
            result,
            user_id=str(context.get("user_id") or ""),
            device_id=str(context.get("device_id") or ""),
        )

    def inject_object_store_failure_for_test(self, operation: str, *, count: int = 1) -> dict[str, Any]:
        normalized = _safe_error_category(operation) or ""
        if normalized not in {"put", "get", "list", "delete"}:
            raise ValueError("unsupported object-store failure operation")
        self._failure_injections[normalized] = self._failure_injections.get(normalized, 0) + max(1, int(count))
        return {
            "schema_version": "life_load_object_store_failure_injection_v1",
            "ok": True,
            "operation": normalized,
            "remaining": self._failure_injections[normalized],
        }

    def _consume_object_store_failure(self, operation: str) -> None:
        remaining = self._failure_injections.get(operation, 0)
        if remaining <= 0:
            return
        self._failure_injections[operation] = remaining - 1
        self.record_request_observation(
            endpoint=f"/v1/testing/object-store/{operation}",
            status_code=500,
            timing_ms=1,
            redacted_error_category="object_store_failure",
        )
        raise RuntimeError("object store failure")

    def delete_backup_object(self, session_token: str, object_id: str) -> None:
        session = self.authenticate(session_token)
        self._consume_object_store_failure("delete")
        now = utc_now_iso()
        with self.connect() as conn, conn:
            row = conn.execute(
                "SELECT namespace_id FROM backup_objects WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (object_id, session.user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("backup object not found")
            conn.execute("UPDATE backup_objects SET deleted_at = ? WHERE id = ?", (now, object_id))
            self._refresh_metadata(conn, user_id=session.user_id, namespace_id=str(row["namespace_id"]))
            self._record_deletion(conn, user_id=session.user_id, scope=f"object:{object_id}", result="tombstoned")
            self._record_audit(
                conn,
                "backups.objects.delete",
                user_id=session.user_id,
                endpoint="/v1/backups/objects/{id}",
                result_code="ok",
                object_count=1,
            )

    def delete_all_backups(self, session_token: str) -> dict[str, int]:
        session = self.authenticate(session_token)
        now = utc_now_iso()
        with self.connect() as conn, conn:
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM backup_objects WHERE user_id = ? AND deleted_at IS NULL", (session.user_id,)
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE backup_objects SET deleted_at = ? WHERE user_id = ? AND deleted_at IS NULL",
                (now, session.user_id),
            )
            namespaces = conn.execute(
                "SELECT id FROM backup_namespaces WHERE user_id = ?",
                (session.user_id,),
            ).fetchall()
            for namespace in namespaces:
                self._refresh_metadata(conn, user_id=session.user_id, namespace_id=str(namespace["id"]))
            self._record_deletion(conn, user_id=session.user_id, scope="all_backups", result="tombstoned")
            self._record_audit(
                conn,
                "backups.all.delete",
                user_id=session.user_id,
                endpoint="/v1/backups/all",
                result_code="ok",
                object_count=count,
            )
        return {"deleted_count": count}

    def deletion_contract(self) -> dict[str, Any]:
        return {
            "schema_version": "life_load_remote_backend_deletion_contract_v1",
            "current_mode": "soft_delete_tombstone",
            "object_delete": "sets deleted_at and removes object from list, restore, and download results",
            "delete_all": "sets deleted_at on active objects for the authenticated user only",
            "future_hard_delete": "requires MVP4 purge policy, object-store proof, disclosure, and failure drills",
            "purge_implemented": False,
        }

    def backup_status(self, session_token: str) -> dict[str, Any]:
        session = self.authenticate(session_token)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(object_count), 0) AS object_count,
                       COALESCE(SUM(total_encrypted_size_bytes), 0) AS total_encrypted_size_bytes,
                       MAX(latest_backup_at) AS latest_backup_at
                FROM backup_metadata
                WHERE user_id = ?
                """,
                (session.user_id,),
            ).fetchone()
        return {
            "object_count": int(row["object_count"] or 0),
            "total_encrypted_size_bytes": int(row["total_encrypted_size_bytes"] or 0),
            "latest_backup_at": row["latest_backup_at"] or "",
        }

    def audit_events(self) -> list[dict[str, Any]]:
        self.migrate()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, user_id, endpoint, result_code, object_count, byte_size,
                       redacted_error_category, created_at
                FROM audit_events
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def audit_text(self) -> str:
        return json.dumps(self.audit_events(), sort_keys=True)

    def health(self) -> dict[str, Any]:
        self.migrate()
        started = time.monotonic()
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {
            "schema_version": "life_load_remote_backend_health_v1",
            "ok": True,
            "service": "life-load-remote-backend-local",
            "mode": "local_dev",
            "metadata_store": "sqlite",
            "db": "ok",
            "timing_ms": _elapsed_ms(started),
        }

    def readiness(self) -> dict[str, Any]:
        self.migrate()
        with self.connect() as conn:
            migrations = {
                row["version"]
                for row in conn.execute("SELECT version FROM remote_schema_migrations").fetchall()
            }
        expected = {version for version, _statements in REMOTE_BACKEND_MIGRATIONS}
        missing = sorted(expected.difference(migrations))
        return {
            "schema_version": "life_load_remote_backend_readiness_v1",
            "ok": not missing,
            "mode": "local_dev",
            "metadata_store": "sqlite",
            "missing_migrations": missing,
        }

    def record_request_observation(
        self,
        *,
        endpoint: str,
        status_code: int,
        timing_ms: int,
        user_id: str | None = None,
        object_count: int | None = None,
        byte_size: int | None = None,
        redacted_error_category: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        self.migrate()
        event = {
            "request_id": request_id or _new_id("req"),
            "endpoint": _safe_endpoint(endpoint),
            "status_code": int(status_code),
            "timing_ms": max(0, int(timing_ms)),
            "object_count": object_count,
            "byte_size": byte_size,
            "user_id_hash": _hash_user_id(user_id) if user_id else None,
            "redacted_error_category": _safe_error_category(redacted_error_category),
            "created_at": utc_now_iso(),
        }
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO operational_events(
                    id, request_id, endpoint, status_code, timing_ms, object_count,
                    byte_size, user_id_hash, redacted_error_category, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id("opv"),
                    event["request_id"],
                    event["endpoint"],
                    event["status_code"],
                    event["timing_ms"],
                    event["object_count"],
                    event["byte_size"],
                    event["user_id_hash"],
                    event["redacted_error_category"],
                    event["created_at"],
                ),
            )
        return event

    def operational_events(self) -> list[dict[str, Any]]:
        self.migrate()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT request_id, endpoint, status_code, timing_ms, object_count,
                       byte_size, user_id_hash, redacted_error_category, created_at
                FROM operational_events
                ORDER BY created_at ASC, request_id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def operational_log_text(self) -> str:
        return json.dumps(self.operational_events(), sort_keys=True)

    def metrics_snapshot(self) -> dict[str, Any]:
        self.migrate()
        with self.connect() as conn:
            object_row = conn.execute(
                """
                SELECT COUNT(*) AS active_objects, COALESCE(SUM(encrypted_size_bytes), 0) AS active_bytes
                FROM backup_objects
                WHERE deleted_at IS NULL
                """
            ).fetchone()
            event_row = conn.execute(
                """
                SELECT COUNT(*) AS request_count,
                       COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) AS error_count,
                       COALESCE(AVG(timing_ms), 0) AS avg_timing_ms
                FROM operational_events
                """
            ).fetchone()
            auth_failure_count = int(
                conn.execute("SELECT COUNT(*) FROM login_attempts WHERE result IN ('denied', 'rate_limited')").fetchone()[0]
            )
            rate_limit_hit_count = int(
                conn.execute("SELECT COUNT(*) FROM login_attempts WHERE result = 'rate_limited'").fetchone()[0]
            )
            upload_count = int(
                conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type = 'backups.objects.create'").fetchone()[0]
            )
            restore_manifest_count = int(
                conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type = 'backups.restore.manifest'").fetchone()[0]
            )
            restore_download_count = int(
                conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type = 'backups.restore.download'").fetchone()[0]
            )
            delete_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE event_type IN ('backups.objects.delete', 'backups.all.delete')"
                ).fetchone()[0]
            )
            crypto_failure_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM operational_events WHERE redacted_error_category = 'crypto_validation_failure'"
                ).fetchone()[0]
            )
            db_failure_count = int(
                conn.execute("SELECT COUNT(*) FROM operational_events WHERE redacted_error_category = 'db_failure'").fetchone()[0]
            )
            object_store_failure_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM operational_events WHERE redacted_error_category = 'object_store_failure'"
                ).fetchone()[0]
            )
            restore_failure_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM operational_events WHERE redacted_error_category = 'restore_failure'"
                ).fetchone()[0]
            )
            redaction_failure_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM operational_events WHERE redacted_error_category = 'redaction_failure'"
                ).fetchone()[0]
            )
        return {
            "schema_version": "life_load_remote_backend_metrics_v1",
            "mode": "local_dev",
            "active_backup_object_count": int(object_row["active_objects"] or 0),
            "active_encrypted_size_bytes": int(object_row["active_bytes"] or 0),
            "request_count": int(event_row["request_count"] or 0),
            "error_count": int(event_row["error_count"] or 0),
            "avg_timing_ms": int(float(event_row["avg_timing_ms"] or 0)),
            "auth_failure_count": auth_failure_count,
            "rate_limit_hit_count": rate_limit_hit_count,
            "backup_upload_count": upload_count,
            "restore_manifest_request_count": restore_manifest_count,
            "restore_download_count": restore_download_count,
            "restore_failure_count": restore_failure_count,
            "delete_request_count": delete_count,
            "purge_request_count": 0,
            "object_store_failure_count": object_store_failure_count,
            "db_failure_count": db_failure_count,
            "crypto_validation_failure_count": crypto_failure_count,
            "redaction_failure_count": redaction_failure_count,
        }

    def metadata_consistency_report(self, session_token: str) -> dict[str, Any]:
        """Compare per-namespace metadata with active objects without exposing payloads."""

        session = self.authenticate(session_token)
        with self.connect() as conn:
            metadata_rows = conn.execute(
                """
                SELECT namespace_id, latest_backup_at, latest_backup_version,
                       object_count, total_encrypted_size_bytes
                FROM backup_metadata
                WHERE user_id = ?
                """,
                (session.user_id,),
            ).fetchall()
            object_rows = conn.execute(
                """
                SELECT namespace_id,
                       COUNT(*) AS object_count,
                       COALESCE(SUM(encrypted_size_bytes), 0) AS total_encrypted_size_bytes,
                       MAX(server_received_at) AS latest_backup_at,
                       MAX(object_version) AS latest_backup_version
                FROM backup_objects
                WHERE user_id = ? AND deleted_at IS NULL
                GROUP BY namespace_id
                """,
                (session.user_id,),
            ).fetchall()
        actual_by_namespace = {str(row["namespace_id"]): row for row in object_rows}
        mismatches: list[dict[str, Any]] = []
        for metadata in metadata_rows:
            namespace_id = str(metadata["namespace_id"])
            actual = actual_by_namespace.get(namespace_id)
            expected_count = int(actual["object_count"] or 0) if actual is not None else 0
            expected_size = int(actual["total_encrypted_size_bytes"] or 0) if actual is not None else 0
            expected_latest_at = actual["latest_backup_at"] if actual is not None else None
            expected_latest_version = actual["latest_backup_version"] if actual is not None else None
            observed = {
                "object_count": int(metadata["object_count"] or 0),
                "total_encrypted_size_bytes": int(metadata["total_encrypted_size_bytes"] or 0),
                "latest_backup_at": metadata["latest_backup_at"],
                "latest_backup_version": metadata["latest_backup_version"],
            }
            expected = {
                "object_count": expected_count,
                "total_encrypted_size_bytes": expected_size,
                "latest_backup_at": expected_latest_at,
                "latest_backup_version": expected_latest_version,
            }
            if observed != expected:
                mismatches.append(
                    {
                        "namespace_id": namespace_id,
                        "observed": observed,
                        "expected": expected,
                    }
                )
        return {
            "schema_version": "life_load_remote_backend_metadata_consistency_v1",
            "ok": not mismatches,
            "user_id": session.user_id,
            "namespace_count": len(metadata_rows),
            "mismatches": mismatches,
        }

    def scan_logs_for_sensitive_values(self, values: Sequence[str]) -> list[str]:
        haystack = self.audit_text() + "\n" + self.operational_log_text()
        found: list[str] = []
        for value in values:
            text = str(value or "")
            if text and text in haystack:
                found.append(text)
        return found

    def deployment_environment_status(self, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return deployment_environment_status(config or {})

    def web_account_page(self, session_token: str, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        session = self.authenticate(session_token)
        self._require_local_portal(config)
        status = self.backup_status(session_token)
        return {
            "schema_version": "life_load_local_web_account_v1",
            "mode": "local_dev",
            "page": "account",
            "user_id": session.user_id,
            "backup_status": status,
            "actions": ["backup_status", "list_encrypted_objects", "export_encrypted_object", "delete_backup_object"],
            "product_claim": "local_backend_foundation_only",
        }

    def web_backup_status_page(self, session_token: str, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        session = self.authenticate(session_token)
        self._require_local_portal(config)
        return {
            "schema_version": "life_load_local_web_backup_status_v1",
            "mode": "local_dev",
            "user_id": session.user_id,
            "status": self.backup_status(session_token),
            "objects": self.list_backup_objects(session_token),
        }

    def web_export_encrypted_object(
        self,
        session_token: str,
        object_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_local_portal(config)
        return self.download_restore_object(session_token, object_id)

    def web_delete_backup_object(
        self,
        session_token: str,
        object_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_local_portal(config)
        self.delete_backup_object(session_token, object_id)
        return {"schema_version": "life_load_local_web_delete_result_v1", "ok": True, "deleted_object_id": object_id}

    def web_account_deletion_placeholder(
        self,
        session_token: str,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.authenticate(session_token)
        self._require_local_portal(config)
        return {
            "schema_version": "life_load_local_web_account_deletion_placeholder_v1",
            "ok": True,
            "user_id": session.user_id,
            "implemented": False,
            "reason": "future_account_deletion_flow_requires_mvp4_disclosure_and_drills",
        }

    def _require_local_portal(self, config: Mapping[str, Any] | None = None) -> None:
        environment = deployment_environment_status(config or {"mode": "local"})
        if not environment["ok"] or not environment["local_only"]:
            raise PermissionError("web portal skeleton is local-development only")

    def _create_session(self, *, user_id: str, device_id: str | None) -> str:
        self.migrate()
        token = secrets.token_urlsafe(32)
        now = utc_now_iso()
        expires_at = _iso_plus_seconds(SESSION_TTL_SECONDS)
        family_id = _new_id("tfm")
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO token_families(id, user_id, device_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_id, user_id, device_id, now),
            )
            conn.execute(
                """
                INSERT INTO sessions(id, user_id, device_id, token_hash, created_at, expires_at, token_family_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_new_id("ses"), user_id, device_id, _hash_token(token), now, expires_at, family_id),
            )
            self._record_audit(
                conn,
                "sessions.create",
                user_id=user_id,
                endpoint="/v1/auth/session",
                result_code="ok",
            )
            self._record_auth_event(
                conn,
                "auth.session.create",
                user_id=user_id,
                result="ok",
                redacted_category="session_created",
            )
        return token

    def _validate_envelope(
        self,
        session: AuthSession,
        envelope: Mapping[str, Any],
        *,
        strict_production_crypto: bool = False,
    ) -> dict[str, Any]:
        envelope_text = json.dumps(dict(envelope), ensure_ascii=False, sort_keys=True)
        if len(envelope_text.encode("utf-8")) > MAX_BACKUP_ENVELOPE_BYTES:
            raise ValueError("backup envelope is too large")
        required = {
            "envelope_version",
            "app",
            "payload_type",
            "payload_version",
            "user_namespace_id",
            "device_id",
            "created_at",
            "encryption",
            "ciphertext",
            "ciphertext_sha256",
            "redacted_summary",
        }
        missing = sorted(required.difference(envelope))
        if missing:
            raise ValueError(f"backup envelope missing fields: {', '.join(missing)}")
        if envelope.get("envelope_version") != 1:
            raise ValueError("unsupported envelope_version")
        if envelope.get("app") != "life_load":
            raise ValueError("unsupported app")
        if not str(envelope.get("payload_type") or "").strip():
            raise ValueError("payload_type is required")
        if not isinstance(envelope.get("payload_version"), int):
            raise ValueError("payload_version must be an integer")
        if str(envelope.get("device_id")) != str(session.device_id):
            raise PermissionError("envelope device does not match session")
        namespace_id = str(envelope.get("user_namespace_id") or "")
        if not self._namespace_belongs_to_user(namespace_id=namespace_id, user_id=session.user_id):
            raise PermissionError("namespace does not belong to user")
        encryption = envelope.get("encryption")
        if not isinstance(encryption, dict) or not encryption:
            raise ValueError("encryption metadata is required")
        if strict_production_crypto:
            placeholder_values = {"", "TBD", "test-nonce", "test-salt"}
            for field in ("scheme", "kdf", "key_wrapping", "nonce", "salt", "aad", "crypto_suite"):
                if str(encryption.get(field) or "").strip() in placeholder_values:
                    raise ValueError("production envelope contains placeholder crypto metadata")
            if str(encryption.get("prototype_only") or "").lower() == "true":
                raise ValueError("production envelope contains prototype crypto metadata")
        ciphertext = envelope.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext:
            raise ValueError("ciphertext is required")
        expected_sha = hashlib.sha256(ciphertext.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(str(envelope.get("ciphertext_sha256") or ""), expected_sha):
            raise ValueError("ciphertext checksum mismatch")
        redacted_summary = envelope.get("redacted_summary")
        if not isinstance(redacted_summary, dict):
            raise ValueError("redacted_summary must be an object")
        extra_summary_keys = set(redacted_summary).difference(_ALLOWED_REDACTED_SUMMARY_KEYS)
        if extra_summary_keys:
            raise ValueError("redacted_summary contains unsupported fields")
        return dict(envelope)

    def _namespace_belongs_to_user(self, *, namespace_id: str, user_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM backup_namespaces WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (namespace_id, user_id),
            ).fetchone()
        return row is not None

    def _first_active_device_id(self, conn: sqlite3.Connection, user_id: str) -> str | None:
        row = conn.execute(
            "SELECT id FROM devices WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        return str(row["id"]) if row is not None else None

    def _device_belongs_to_user(self, conn: sqlite3.Connection, *, device_id: str, user_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM devices WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (device_id, user_id),
        ).fetchone()
        return row is not None

    def _refresh_metadata(self, conn: sqlite3.Connection, *, user_id: str, namespace_id: str) -> None:
        row = conn.execute(
            """
            SELECT COUNT(*) AS object_count,
                   COALESCE(SUM(encrypted_size_bytes), 0) AS total_size,
                   MAX(server_received_at) AS latest_backup_at,
                   MAX(object_version) AS latest_backup_version
            FROM backup_objects
            WHERE user_id = ? AND namespace_id = ? AND deleted_at IS NULL
            """,
            (user_id, namespace_id),
        ).fetchone()
        conn.execute(
            """
            UPDATE backup_metadata
            SET latest_backup_at = ?, latest_backup_version = ?,
                object_count = ?, total_encrypted_size_bytes = ?
            WHERE user_id = ? AND namespace_id = ?
            """,
            (
                row["latest_backup_at"],
                row["latest_backup_version"],
                int(row["object_count"] or 0),
                int(row["total_size"] or 0),
                user_id,
                namespace_id,
            ),
        )

    def _record_created_object_metadata(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        namespace_id: str,
        object_version: int,
        encrypted_size_bytes: int,
        server_received_at: str,
    ) -> None:
        self._refresh_metadata(conn, user_id=user_id, namespace_id=namespace_id)

    def _record_deletion(self, conn: sqlite3.Connection, *, user_id: str, scope: str, result: str) -> None:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO deletion_events(id, user_id, scope, requested_at, completed_at, result, redacted_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_new_id("del"), user_id, scope[:128], now, now, result, "user_requested"),
        )

    def _record_recovery_event(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str | None,
        event_type: str,
        result: str,
        redacted_reason: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO recovery_events(id, user_id, event_type, result, redacted_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_new_id("rev"), user_id, event_type, result, redacted_reason, utc_now_iso()),
        )
        self._record_audit(
            conn,
            event_type,
            user_id=user_id,
            endpoint="/v1/auth/recovery",
            result_code=result,
            redacted_error_category=redacted_reason,
        )

    def _record_audit(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        *,
        user_id: str | None,
        endpoint: str,
        result_code: str,
        object_count: int | None = None,
        byte_size: int | None = None,
        redacted_error_category: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_events(
                id, event_type, user_id, endpoint, result_code, object_count,
                byte_size, redacted_error_category, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("aud"),
                event_type,
                user_id,
                endpoint,
                result_code,
                object_count,
                byte_size,
                redacted_error_category,
                utc_now_iso(),
            ),
        )

    def _record_auth_event(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        *,
        user_id: str | None,
        result: str,
        redacted_category: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO auth_events(id, event_type, user_id, user_id_hash, result, redacted_category, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("aue"),
                event_type,
                user_id,
                _hash_user_id(user_id),
                _safe_error_category(result) or "unknown",
                _safe_error_category(redacted_category) or "unspecified",
                utc_now_iso(),
            ),
        )

    def _record_login_attempt(
        self,
        conn: sqlite3.Connection,
        *,
        email_normalized: str,
        user_id: str | None,
        result: str,
        redacted_category: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO login_attempts(id, email_hash, user_id_hash, result, redacted_category, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("lat"),
                hashed_dimension(email_normalized),
                _hash_user_id(user_id),
                _safe_error_category(result) or "unknown",
                _safe_error_category(redacted_category) or "unspecified",
                utc_now_iso(),
            ),
        )

    def _recent_login_failure_count(self, conn: sqlite3.Connection, email_normalized: str) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM login_attempts
            WHERE email_hash = ? AND result IN ('denied', 'rate_limited')
            """,
            (hashed_dimension(email_normalized),),
        ).fetchone()
        return int(row["count"] or 0) if row is not None else 0

    def _record_account_recovery_event(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str | None,
        event_type: str,
        result: str,
        recovery_state: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO account_recovery_events(
                id, user_id, event_type, result, recovery_state, private_key_material_returned, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                _new_id("are"),
                user_id,
                event_type,
                _safe_error_category(result) or "unknown",
                _safe_error_category(recovery_state) or "unknown",
                utc_now_iso(),
            ),
        )


@dataclass
class FakeEntitlementProvider:
    """Local-only capability provider for future plan-boundary tests."""

    user_plans: dict[str, str] = field(default_factory=dict)
    forced_capabilities: dict[str, set[str]] = field(default_factory=dict)

    def set_plan(self, user_id: str, plan: str) -> None:
        self.user_plans[str(user_id)] = _normalize_plan(plan)

    def enable_capability(self, user_id: str, capability: str) -> None:
        normalized = _normalize_capability(capability)
        self.forced_capabilities.setdefault(str(user_id), set()).add(normalized)

    def capabilities_for_user(self, user_id: str) -> dict[str, Any]:
        plan = self.user_plans.get(str(user_id), "free")
        capabilities = set(PLAN_CAPABILITY_REGISTRY[plan])
        capabilities.update(self.forced_capabilities.get(str(user_id), set()))
        return {
            "schema_version": "life_load_fake_entitlements_v1",
            "provider": "fake_local_only",
            "plan": plan,
            "capabilities": sorted(capabilities),
        }

    def capability_enabled(self, user_id: str, capability: str) -> bool:
        normalized = _normalize_capability(capability)
        return normalized in self.capabilities_for_user(user_id)["capabilities"]


def make_backup_envelope(
    *,
    namespace_id: str,
    device_id: str,
    ciphertext: str,
    created_at: str = "2026-05-10T00:00:00Z",
    entry_count: int = 1,
) -> dict[str, Any]:
    """Build a valid opaque backup envelope for tests and fake clients."""

    return {
        "envelope_version": 1,
        "app": "life_load",
        "payload_type": "life_load_backup",
        "payload_version": 1,
        "user_namespace_id": namespace_id,
        "device_id": device_id,
        "created_at": created_at,
        "encryption": {
            "scheme": "TBD",
            "kdf": "TBD",
            "key_wrapping": "TBD",
            "nonce": "test-nonce",
            "salt": "test-salt",
            "aad": "life_load_backup_v1",
        },
        "ciphertext": ciphertext,
        "ciphertext_sha256": hashlib.sha256(ciphertext.encode("utf-8")).hexdigest(),
        "redacted_summary": {
            "entry_count": entry_count,
            "date_min": "2026-05-01",
            "date_max": "2026-05-10",
        },
    }


def _object_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "namespace_id": row["namespace_id"],
        "object_type": row["object_type"],
        "object_version": int(row["object_version"]),
        "encrypted_blob_sha256": row["encrypted_blob_sha256"],
        "encrypted_size_bytes": int(row["encrypted_size_bytes"]),
        "client_created_at": row["client_created_at"],
        "server_received_at": row["server_received_at"],
    }


def _vault_package_metadata(row: sqlite3.Row) -> dict[str, Any]:
    metadata = {}
    try:
        parsed = json.loads(str(row["package_metadata_json"] or "{}"))
        metadata = parsed if isinstance(parsed, dict) else {}
    except Exception:
        metadata = {}
    return {
        "package_id": row["id"],
        "device_id": row["device_id"] or "",
        "package_type": row["package_type"],
        "key_version": int(row["key_version"]),
        "wrapping_mode": row["wrapping_mode"],
        "wrapped_key_hash": row["wrapped_key_hash"],
        "metadata": _redacted_package_metadata(metadata),
        "created_at": row["created_at"],
        "revoked": bool(row["revoked_at"]),
        "plaintext_vault_key_available": False,
    }


def _device_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "device_id": row["id"],
        "device_label": row["device_label"],
        "platform": row["platform"],
        "created_at": row["created_at"],
        "revoked": bool(row["revoked_at"]),
    }


def _server_object_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "object_id": row["id"],
        "namespace_id": row["namespace_id"],
        "object_type": row["object_type"],
        "object_version": int(row["object_version"]),
        "schema_version": "life_load_backup_envelope_v1",
        "encrypted_size_bytes": int(row["encrypted_size_bytes"]),
        "checksum": row["encrypted_blob_sha256"],
        "client_created_at": row["client_created_at"],
        "server_received_at": row["server_received_at"],
        "deleted": bool(row["deleted_at"]),
        "opaque_payload_body_visible": False,
    }


def _normalize_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value or len(value) > 254:
        raise ValueError("valid email is required")
    return value


def _normalize_idempotency_key(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text.encode("utf-8")) > MAX_IDEMPOTENCY_KEY_BYTES:
        raise ValueError("idempotency key is too large")
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)


def _normalize_recovery_material_type(material_type: str) -> str:
    value = str(material_type or "").strip().lower().replace("-", "_")
    allowed = {"trusted_device", "recovery_key", "recovery_phrase"}
    if value not in allowed:
        raise ValueError("unsupported recovery material type")
    return value


def _normalize_vault_package_type(package_type: str) -> str:
    value = str(package_type or "").strip().lower().replace("-", "_")
    allowed = {"device_wrap", "recovery_wrap", "vault_rotation"}
    if value not in allowed:
        raise ValueError("unsupported vault package type")
    return value


def _normalize_wrapping_mode(wrapping_mode: str) -> str:
    value = str(wrapping_mode or "").strip().lower().replace("-", "_")
    allowed = {
        "android_keystore_simulated",
        "recovery_key_prototype",
        "trusted_device_transfer",
        "local_dev_fixture_wrapping",
    }
    if value not in allowed:
        raise ValueError("unsupported vault wrapping mode")
    return value


def _normalize_trust_decision(decision: str) -> str:
    value = str(decision or "").strip().lower().replace("-", "_")
    if value not in {"approve", "deny"}:
        raise ValueError("unsupported trust decision")
    return value


def _normalize_key_version(key_version: int) -> int:
    try:
        version = int(key_version)
    except Exception as exc:
        raise ValueError("invalid key version") from exc
    if version < 1 or version > 1000:
        raise ValueError("invalid key version")
    return version


def _normalize_wrapped_key_hash(value: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128:
        raise ValueError("wrapped key hash is required")
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)
    if safe != text:
        raise ValueError("wrapped key hash contains unsupported characters")
    return safe


def _redacted_package_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key in ("key_security_level", "created_by", "source", "request_id_hash", "key_version"):
        if key in metadata:
            value = metadata[key]
            allowed[key] = str(value)[:80] if not isinstance(value, (int, bool)) else value
    return allowed


def _safe_endpoint(endpoint: str) -> str:
    text = str(endpoint or "").strip()
    if not text.startswith("/"):
        text = f"/{text}"
    safe = []
    for char in text[:120]:
        safe.append(char if char.isalnum() or char in {"/", "-", "_", "{", "}"} else "_")
    return "".join(safe)


def _safe_error_category(value: str | None) -> str | None:
    if value is None:
        return None
    words = str(value or "").strip().lower().replace("-", "_").split()
    text = "_".join(words[:3])
    if not text:
        return None
    safe = []
    for char in text[:80]:
        safe.append(char if char.isalnum() or char in {"_", "-"} else "_")
    return "".join(safe)


def _hash_user_id(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16]


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def deployment_environment_status(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate local/dev/staging/production deployment shape without launching it."""

    values = dict(config or {})
    mode = str(values.get("mode") or "local").strip().lower()
    if mode not in _ALLOWED_ENVIRONMENT_MODES:
        mode = "invalid"
    public_endpoints_enabled = bool(values.get("public_endpoints_enabled"))
    tls_enabled = bool(values.get("tls_enabled"))
    domain = str(values.get("domain") or "").strip()
    object_store = str(values.get("object_store") or "").strip()
    secret_refs = values.get("secret_refs") if isinstance(values.get("secret_refs"), Mapping) else {}
    missing: list[str] = []
    warnings: list[str] = []

    if mode == "invalid":
        missing.append("valid_mode")
    if mode in _LOCAL_ENVIRONMENT_MODES:
        if public_endpoints_enabled:
            warnings.append("local_dev_public_endpoints_disabled")
    else:
        if not public_endpoints_enabled:
            missing.append("public_endpoint_decision")
        if not tls_enabled:
            missing.append("tls_enabled")
        if not domain:
            missing.append("domain")
        if object_store not in {"s3_compatible", "managed_object_store"}:
            missing.append("object_store")
        for key in sorted(_SECRET_CONFIG_KEYS):
            if not str(secret_refs.get(key) or "").strip():
                missing.append(f"secret_ref:{key}")

    ok = not missing and not (mode in _LOCAL_ENVIRONMENT_MODES and public_endpoints_enabled)
    return {
        "schema_version": "life_load_remote_backend_environment_v1",
        "mode": mode,
        "ok": ok,
        "local_only": mode in _LOCAL_ENVIRONMENT_MODES,
        "public_endpoints_enabled": public_endpoints_enabled if mode not in _LOCAL_ENVIRONMENT_MODES else False,
        "tls_enabled": tls_enabled,
        "domain_configured": bool(domain),
        "object_store_configured": bool(object_store),
        "secret_refs_configured": sorted(str(key) for key in secret_refs if str(secret_refs.get(key) or "").strip()),
        "missing": missing,
        "warnings": warnings,
    }


class PostgresRemoteBackendNotImplemented(RuntimeError):
    """Raised when Postgres metadata storage is selected before the adapter exists."""


class PostgresRemoteBackendUnavailable(RuntimeError):
    """Raised when Postgres mode is selected without a usable driver or DSN."""


class _PostgresRow:
    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        self._columns = list(columns)
        self._values = list(values)
        self._by_name = dict(zip(self._columns, self._values, strict=False))

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._by_name[key]

    def keys(self) -> list[str]:
        return list(self._columns)

    def items(self) -> list[tuple[str, Any]]:
        return [(key, self._by_name[key]) for key in self._columns]


class _PostgresCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> _PostgresRow | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return _PostgresRow(self._columns(), row)

    def fetchall(self) -> list[_PostgresRow]:
        columns = self._columns()
        return [_PostgresRow(columns, row) for row in self._cursor.fetchall()]

    def _columns(self) -> list[str]:
        return [str(column.name) for column in self._cursor.description or ()]


class _PostgresConnection:
    def __init__(self, connection: Any, *, release: Any | None = None) -> None:
        self._connection = connection
        self._release = release
        self._context_depth = 0
        self._released = False

    def __enter__(self) -> "_PostgresConnection":
        self._context_depth += 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        self._context_depth = max(0, self._context_depth - 1)
        if self._context_depth == 0:
            try:
                if exc_type is None:
                    self._connection.commit()
                else:
                    self._connection.rollback()
            finally:
                self.close()
        return False

    def execute(self, statement: str, params: Sequence[Any] | None = None) -> _PostgresCursor:
        psycopg = _import_psycopg()
        sql = _sqlite_placeholders_to_postgres(statement)
        try:
            return _PostgresCursor(self._connection.execute(sql, tuple(params or ())))
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc
        except psycopg.Error as exc:
            raise RuntimeError("postgres metadata store error") from exc

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        if self._released:
            return
        self._released = True
        if self._release is not None:
            self._release(self._connection)
        else:
            self._connection.close()


@dataclass
class PostgresRemoteBackendStore(RemoteBackendStore):
    database_url: str = ""
    _pg_pool: list[Any] = field(default_factory=list, init=False, repr=False)
    _pg_pool_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def connect(self) -> _PostgresConnection:
        dsn = self.database_url or _postgres_database_url_from_environment()
        if not dsn:
            raise PostgresRemoteBackendUnavailable("LIFE_LOAD_DATABASE_URL or DATABASE_URL is required for Postgres mode")
        return _PostgresConnection(self._checkout_connection(dsn), release=self._release_connection)

    def _checkout_connection(self, dsn: str) -> Any:
        psycopg = _import_psycopg()
        with self._pg_pool_lock:
            while self._pg_pool:
                connection = self._pg_pool.pop()
                if not bool(getattr(connection, "closed", False)):
                    return connection
        return psycopg.connect(dsn)

    def _release_connection(self, connection: Any) -> None:
        if bool(getattr(connection, "closed", False)):
            return
        pool_size = int(os.environ.get("LIFE_LOAD_POSTGRES_POOL_SIZE") or "16")
        with self._pg_pool_lock:
            if len(self._pg_pool) < max(1, pool_size):
                self._pg_pool.append(connection)
                return
        connection.close()

    def migrate(self) -> list[str]:
        if self._migrations_checked:
            return []
        applied: list[str] = []
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS remote_schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            existing = {row[0] for row in conn.execute("SELECT version FROM remote_schema_migrations").fetchall()}
            for version, statements in REMOTE_BACKEND_MIGRATIONS:
                if version in existing:
                    continue
                for statement in statements:
                    try:
                        conn.execute(statement)
                    except RuntimeError as exc:
                        if "token_family_id" in statement and "already exists" in str(exc.__cause__ or exc).lower():
                            continue
                        raise
                conn.execute(
                    "INSERT INTO remote_schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utc_now_iso()),
                )
                applied.append(version)
        self._migrations_checked = True
        return applied

    def health(self) -> dict[str, Any]:
        self.migrate()
        started = time.monotonic()
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {
            "schema_version": "life_load_remote_backend_health_v1",
            "ok": True,
            "service": "life-load-remote-backend-alpha",
            "mode": "staging_fixture",
            "metadata_store": "postgres",
            "db": "ok",
            "timing_ms": _elapsed_ms(started),
        }

    def readiness(self) -> dict[str, Any]:
        self.migrate()
        with self.connect() as conn:
            migrations = {
                row["version"]
                for row in conn.execute("SELECT version FROM remote_schema_migrations").fetchall()
            }
        expected = {version for version, _statements in REMOTE_BACKEND_MIGRATIONS}
        missing = sorted(expected.difference(migrations))
        return {
            "schema_version": "life_load_remote_backend_readiness_v1",
            "ok": not missing,
            "mode": "staging_fixture",
            "metadata_store": "postgres",
            "missing_migrations": missing,
        }


def remote_backend_store_mode_from_environment(environ: Mapping[str, str] | None = None) -> str:
    env = environ or os.environ
    mode = str(env.get("LIFE_LOAD_REMOTE_BACKEND_STORE_MODE") or "sqlite").strip().lower()
    if mode not in REMOTE_BACKEND_STORE_MODES:
        raise ValueError("unsupported remote backend metadata store mode")
    return mode


def remote_backend_store_from_environment(
    *,
    repo_root: Path,
    environ: Mapping[str, str] | None = None,
) -> RemoteBackendStore:
    env = environ or os.environ
    mode = remote_backend_store_mode_from_environment(env)
    if mode == "sqlite":
        return RemoteBackendStore(repo_root=repo_root)
    return PostgresRemoteBackendStore(repo_root=repo_root, database_url=_postgres_database_url_from_environment(env))


def remote_backend_metadata_store_capability(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = environ or os.environ
    mode = remote_backend_store_mode_from_environment(env)
    database_url_configured = bool(str(env.get("DATABASE_URL") or env.get("LIFE_LOAD_DATABASE_URL") or "").strip())
    postgres_driver_available = _psycopg_available()
    return {
        "schema_version": "life_load_remote_backend_metadata_store_capability_v1",
        "selected_mode": mode,
        "implemented": mode == "sqlite" or (mode == "postgres" and database_url_configured and postgres_driver_available),
        "postgres_adapter_available": postgres_driver_available,
        "sqlite_adapter_available": True,
        "database_url_configured": database_url_configured,
        "safe_for_backend_benchmark": mode == "sqlite" or (mode == "postgres" and database_url_configured and postgres_driver_available),
        "warning": ""
        if mode == "sqlite"
        else (
            ""
            if database_url_configured and postgres_driver_available
            else "Postgres mode requires psycopg and LIFE_LOAD_DATABASE_URL or DATABASE_URL."
        ),
        "redacted": True,
    }


def _postgres_database_url_from_environment(environ: Mapping[str, str] | None = None) -> str:
    env = environ or os.environ
    return str(env.get("LIFE_LOAD_DATABASE_URL") or env.get("DATABASE_URL") or "").strip()


def _import_psycopg() -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except Exception as exc:
        raise PostgresRemoteBackendUnavailable("psycopg is required for Postgres metadata store mode") from exc
    return psycopg


def _psycopg_available() -> bool:
    try:
        _import_psycopg()
    except PostgresRemoteBackendUnavailable:
        return False
    return True


def _sqlite_placeholders_to_postgres(statement: str) -> str:
    return statement.replace("?", "%s")


def plan_capability_registry() -> dict[str, list[str]]:
    return {plan: list(capabilities) for plan, capabilities in PLAN_CAPABILITY_REGISTRY.items()}


def cloud_ai_control_plane_placeholder(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = dict(config or {})
    enabled = bool(values.get("enabled"))
    provider = str(values.get("provider") or "none").strip().lower()
    if provider not in {"none", "openai", "local_stub"}:
        provider = "unsupported"
    retention_days = int(values.get("retention_days") or 0)
    monthly_budget_cents = int(values.get("monthly_budget_cents") or 0)
    request_limit_per_day = int(values.get("request_limit_per_day") or 0)
    missing: list[str] = []
    if enabled:
        if provider in {"none", "unsupported"}:
            missing.append("provider")
        if retention_days != 0:
            missing.append("zero_retention_default")
        if monthly_budget_cents <= 0:
            missing.append("monthly_budget_cents")
        if request_limit_per_day <= 0:
            missing.append("request_limit_per_day")
        if not bool(values.get("explicit_user_disclosure")):
            missing.append("explicit_user_disclosure")
    return {
        "schema_version": "life_load_cloud_ai_control_plane_placeholder_v1",
        "enabled": enabled and not missing,
        "provider": provider,
        "retention_days": retention_days,
        "monthly_budget_cents": monthly_budget_cents,
        "request_limit_per_day": request_limit_per_day,
        "sends_user_payloads": False,
        "android_connected": False,
        "missing": missing,
        "disclosure_required": True,
    }


def validate_cloud_ai_payload_placeholder(payload: Mapping[str, Any]) -> dict[str, Any]:
    forbidden = _find_forbidden_ai_payload_keys(payload)
    if forbidden:
        raise ValueError(f"cloud AI payload contains forbidden fields: {', '.join(forbidden)}")
    return {
        "schema_version": "life_load_cloud_ai_payload_validation_v1",
        "ok": True,
        "payload_sent": False,
        "accepted_fields": sorted(str(key) for key in payload),
    }


def _find_forbidden_ai_payload_keys(value: Any) -> list[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).strip().lower()
            if key_text in _AI_PAYLOAD_FORBIDDEN_KEYS:
                found.add(key_text)
            found.update(_find_forbidden_ai_payload_keys(nested))
    elif isinstance(value, list | tuple):
        for nested in value:
            found.update(_find_forbidden_ai_payload_keys(nested))
    return sorted(found)


def _normalize_plan(plan: str) -> str:
    value = str(plan or "").strip().lower()
    if value not in PLAN_CAPABILITY_REGISTRY:
        raise ValueError("unsupported plan")
    return value


def _normalize_capability(capability: str) -> str:
    value = str(capability or "").strip().lower()
    known = {item for capabilities in PLAN_CAPABILITY_REGISTRY.values() for item in capabilities}
    if value not in known:
        raise ValueError("unsupported capability")
    return value


def _short_label(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("label is required")
    return text[:80]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _hash_password(password: str) -> str:
    return hash_password_for_storage(password)


def _verify_password(password: str, stored_hash: str) -> bool:
    return verify_password(password, stored_hash)


def _hash_token(token: str) -> str:
    return hash_session_token(token)


def _iso_plus_seconds(seconds: int) -> str:
    import datetime as dt

    expires_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) + dt.timedelta(seconds=seconds)
    return expires_at.isoformat().replace("+00:00", "Z")
