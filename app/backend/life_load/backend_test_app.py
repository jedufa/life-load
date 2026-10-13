"""Local-only simulated client for backend lifecycle testing.

This harness is intentionally separate from the Android app. It stores fixture
client state under runtime state, talks to the local P-INFRA backend store, and
returns redacted views suitable for the Backend Test App GUI.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from life_load.object_store import S3ObjectStore
from life_load.remote_backend import RemoteBackendStore, make_backup_envelope
from life_load.sqlite_core import utc_now_iso


SCHEMA_VERSION = "life_load_backend_test_client_state_v1"
REPORT_SCHEMA_VERSION = "life_load_backend_test_report_v1"
DEFAULT_FIXTURE_PASSWORD = "fixture-password-not-for-production"
SAFE_NETWORK_MODES = {"online", "offline", "flaky", "timeout", "partial_failure"}
VIEW_MODES = {"redacted_default", "operator_debug"}
RAW_OPERATIONAL_ID_KEYS = {
    "active_device_id",
    "active_user_id",
    "device_id",
    "entity_id",
    "encrypted_payload_placeholder",
    "id",
    "idempotency_key",
    "install_id",
    "local_id",
    "namespace_id",
    "object_id",
    "payload_ref",
    "server_object_id",
    "user_id",
    "user_namespace_id",
}


@dataclass
class BackendTestAppHarness:
    repo_root: Path
    store: RemoteBackendStore

    @property
    def state_path(self) -> Path:
        return self.repo_root / "runtime" / "backend_test_app" / "state.json"

    @property
    def reports_dir(self) -> Path:
        return self.repo_root / "runtime" / "backend_test_app" / "reports"

    @property
    def local_db_path(self) -> Path:
        return self.repo_root / "runtime" / "backend_test_app" / "client.sqlite"

    def connect_local(self) -> sqlite3.Connection:
        self.local_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.local_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate_local(self) -> None:
        with self.connect_local() as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_entries (
                    local_id TEXT PRIMARY KEY,
                    entry_date TEXT NOT NULL,
                    state TEXT NOT NULL,
                    encrypted_payload_placeholder TEXT NOT NULL,
                    redacted_summary_json TEXT NOT NULL,
                    canary_hash TEXT,
                    local_version INTEGER NOT NULL,
                    server_object_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_outbox (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    base_version INTEGER,
                    payload_ref TEXT NOT NULL,
                    state TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_backup_manifest (
                    object_id TEXT PRIMARY KEY,
                    namespace_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_version INTEGER NOT NULL,
                    encrypted_blob_sha256 TEXT NOT NULL,
                    encrypted_size_bytes INTEGER NOT NULL,
                    client_created_at TEXT NOT NULL,
                    server_received_at TEXT NOT NULL
                )
                """
            )

    def state(self, *, view_mode: str = "redacted_default") -> dict[str, Any]:
        self.migrate_local()
        if not self.state_path.exists():
            state = _empty_state()
            self._write_state(state)
            return _redacted_state(state, view_mode=view_mode)
        return _redacted_state(self._read_state(), local=self._local_snapshot(), view_mode=view_mode)

    def reset_state(self) -> dict[str, Any]:
        state = _empty_state()
        self._reset_local_db()
        self._write_state(state)
        return _redacted_state(state, local=self._local_snapshot())

    def register_fixture_user(self, *, label: str = "fixture") -> dict[str, Any]:
        state = self._read_state()
        email = _fixture_email(label)
        try:
            created = self.store.register_user(
                email=email,
                password=DEFAULT_FIXTURE_PASSWORD,
                device_label="Backend Test App simulated device",
                platform="backend_test_app",
            )
            namespace_id = created["namespace_id"]
        except Exception:
            created = self.store.login(email=email, password=DEFAULT_FIXTURE_PASSWORD)
            namespace_id = _namespace_for_user(self.store, created["user_id"])
        state.update(
            {
                "active_user_id": created["user_id"],
                "fixture_label": label,
                "active_device_id": created["device_id"],
                "auth_session_token": created["session_token"],
                "auth_session_present": True,
                "auth_session_expiry": "server_managed",
                "namespace_id": namespace_id,
                "key_state": {"state": "present"},
                "last_error": "",
                "updated_at": utc_now_iso(),
            }
        )
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state)}

    def login(self) -> dict[str, Any]:
        state = self._read_state()
        label = str(state.get("fixture_label") or "fixture")
        device_id = str(state.get("active_device_id") or "") or None
        logged_in = self.store.login(
            email=_fixture_email(label),
            password=DEFAULT_FIXTURE_PASSWORD,
            device_id=device_id,
        )
        state["active_user_id"] = logged_in["user_id"]
        state["active_device_id"] = logged_in["device_id"]
        state["auth_session_token"] = logged_in["session_token"]
        state["auth_session_present"] = True
        state["auth_session_expiry"] = "server_managed"
        state["last_error"] = ""
        state["updated_at"] = utc_now_iso()
        if not state.get("namespace_id"):
            state["namespace_id"] = _namespace_for_user(self.store, logged_in["user_id"])
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state)}

    def logout(self) -> dict[str, Any]:
        state = self._read_state()
        token = str(state.get("auth_session_token") or "")
        if token:
            self.store.logout(token)
        state["auth_session_token"] = ""
        state["auth_session_present"] = False
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state)}

    def register_device(self, *, label: str = "Simulated second device") -> dict[str, Any]:
        state = self._read_state()
        token = _require_token(state)
        device = self.store.register_device(token, device_label=label, platform="backend_test_app")
        login = self.store.login(
            email=_fixture_email(str(state.get("fixture_label") or "fixture")),
            password=DEFAULT_FIXTURE_PASSWORD,
            device_id=device["device_id"],
        )
        state["active_device_id"] = device["device_id"]
        state["auth_session_token"] = login["session_token"]
        state["auth_session_present"] = True
        state.setdefault("devices", []).append(
            {
                "device_id": device["device_id"],
                "label": label,
                "registered_at": utc_now_iso(),
                "revoked_at": "",
                "active": True,
            }
        )
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state)}

    def revoke_active_device(self) -> dict[str, Any]:
        state = self._read_state()
        token = _require_token(state)
        device_id = str(state.get("active_device_id") or "")
        self.store.revoke_device(token, device_id=device_id)
        for device in state.get("devices", []):
            if device.get("device_id") == device_id:
                device["revoked_at"] = utc_now_iso()
        state["auth_session_token"] = ""
        state["auth_session_present"] = False
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state)}

    def set_network_mode(self, mode: str) -> dict[str, Any]:
        state = self._read_state()
        normalized = str(mode or "").strip().lower()
        if normalized not in SAFE_NETWORK_MODES:
            raise ValueError("unsupported network mode")
        state["network_mode"] = normalized
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state)}

    def create_local_entry(self, *, entry_date: str = "2026-05-11", canary: str = "") -> dict[str, Any]:
        self.migrate_local()
        state = self._read_state()
        local_id = f"loc_{uuid.uuid4().hex}"
        now = utc_now_iso()
        entry = {
            "local_id": local_id,
            "entry_date": entry_date,
            "state": "approved",
            "encrypted_payload_placeholder": f"payload_ref_{_short_hash(local_id + canary)}",
            "redacted_summary": {"entry_count": 1, "date_min": entry_date, "date_max": entry_date},
            "canary_hash": _short_hash(canary) if canary else "",
            "local_version": 1,
            "server_object_id": "",
            "created_at": now,
            "updated_at": now,
        }
        event = {
            "id": f"out_{uuid.uuid4().hex}",
            "idempotency_key": f"idem_{uuid.uuid4().hex}",
            "operation": "upload_backup",
            "entity_type": "local_entry",
            "entity_id": local_id,
            "base_version": None,
            "payload_ref": entry["encrypted_payload_placeholder"],
            "state": "pending",
            "retry_count": 0,
            "last_error": "",
            "created_at": now,
            "updated_at": now,
        }
        with self.connect_local() as conn, conn:
            conn.execute(
                """
                INSERT INTO local_entries(
                    local_id, entry_date, state, encrypted_payload_placeholder,
                    redacted_summary_json, canary_hash, local_version,
                    server_object_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["local_id"],
                    entry["entry_date"],
                    entry["state"],
                    entry["encrypted_payload_placeholder"],
                    json.dumps(entry["redacted_summary"], sort_keys=True),
                    entry["canary_hash"],
                    entry["local_version"],
                    entry["server_object_id"],
                    entry["created_at"],
                    entry["updated_at"],
                ),
            )
            conn.execute(
                """
                INSERT INTO local_outbox(
                    id, idempotency_key, operation, entity_type, entity_id,
                    base_version, payload_ref, state, retry_count, last_error,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"],
                    event["idempotency_key"],
                    event["operation"],
                    event["entity_type"],
                    event["entity_id"],
                    event["base_version"],
                    event["payload_ref"],
                    event["state"],
                    event["retry_count"],
                    event["last_error"],
                    event["created_at"],
                    event["updated_at"],
                ),
            )
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "state": _redacted_state(state, local=self._local_snapshot())}

    def sync_outbox(self) -> dict[str, Any]:
        self.migrate_local()
        state = self._read_state()
        if state.get("network_mode") != "online":
            state["last_error"] = "network_offline"
            self._write_state(state)
            return {"ok": False, "state": _redacted_state(state, local=self._local_snapshot()), "error": "network_offline"}
        token = _require_token(state)
        uploaded = 0
        with self.connect_local() as conn, conn:
            events = conn.execute("SELECT * FROM local_outbox WHERE state = 'pending' ORDER BY created_at ASC").fetchall()
            for event in events:
                entry = conn.execute("SELECT * FROM local_entries WHERE local_id = ?", (event["entity_id"],)).fetchone()
                if entry is None:
                    continue
                envelope = make_backup_envelope(
                    namespace_id=str(state.get("namespace_id") or ""),
                    device_id=str(state.get("active_device_id") or ""),
                    ciphertext=f"fixture_ciphertext_{entry['local_id']}",
                    entry_count=1,
                    created_at=str(entry["created_at"] or utc_now_iso()),
                )
                created = self.store.create_backup_object(
                    token,
                    envelope,
                    idempotency_key=str(event["idempotency_key"]),
                )
                now = utc_now_iso()
                conn.execute(
                    "UPDATE local_outbox SET state = 'uploaded', updated_at = ? WHERE id = ?",
                    (now, event["id"]),
                )
                conn.execute(
                    "UPDATE local_entries SET server_object_id = ?, updated_at = ? WHERE local_id = ?",
                    (created["object_id"], now, entry["local_id"]),
                )
                uploaded += 1
        state["sync_cursor"] = f"sync_{utc_now_iso()}"
        state["last_sync_result"] = {"ok": True, "uploaded": uploaded}
        state["last_error"] = ""
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "uploaded": uploaded, "state": _redacted_state(state, local=self._local_snapshot())}

    def uninstall(self) -> dict[str, Any]:
        state = self._read_state()
        preserved = {
            "fixture_label": state.get("fixture_label") or "fixture",
            "active_user_id": state.get("active_user_id") or "",
            "namespace_id": state.get("namespace_id") or "",
        }
        new_state = _empty_state()
        new_state.update(preserved)
        new_state["install_id"] = ""
        new_state["active_device_id"] = ""
        new_state["auth_session_token"] = ""
        new_state["auth_session_present"] = False
        new_state["sync_cursor"] = ""
        new_state["key_state"] = {"state": "missing"}
        new_state["updated_at"] = utc_now_iso()
        self._reset_local_db()
        self._write_state(new_state)
        return {"ok": True, "state": _redacted_state(new_state, local=self._local_snapshot())}

    def reinstall_restore(self) -> dict[str, Any]:
        state = self._read_state()
        if not state.get("install_id"):
            state["install_id"] = f"inst_{uuid.uuid4().hex}"
        label = str(state.get("fixture_label") or "fixture")
        logged_in = self.store.login(email=_fixture_email(label), password=DEFAULT_FIXTURE_PASSWORD)
        state["active_user_id"] = logged_in["user_id"]
        state["active_device_id"] = logged_in["device_id"]
        state["auth_session_token"] = logged_in["session_token"]
        state["auth_session_present"] = True
        state["namespace_id"] = state.get("namespace_id") or _namespace_for_user(self.store, logged_in["user_id"])
        manifest = self.store.restore_manifest(logged_in["session_token"])
        self._replace_manifest(manifest["objects"])
        state["last_sync_result"] = {"ok": True, "restored_manifest_count": manifest["object_count"]}
        state["updated_at"] = utc_now_iso()
        self._write_state(state)
        return {"ok": True, "manifest": manifest, "state": _redacted_state(state, local=self._local_snapshot())}

    def export_local_state(self) -> dict[str, Any]:
        self.migrate_local()
        state = self._read_state()
        export = {
            "schema_version": "life_load_backend_test_local_export_v1",
            "created_at": utc_now_iso(),
            "redaction": "redacted",
            "state": _redacted_state(state, local=self._local_snapshot()),
            "entries": self._local_entries(),
            "outbox": self._local_outbox(),
            "manifest": self._local_manifest(),
        }
        export["checksum"] = hashlib.sha256(json.dumps(export, sort_keys=True).encode("utf-8")).hexdigest()
        return export

    def import_local_state(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        if bundle.get("schema_version") != "life_load_backend_test_local_export_v1":
            raise ValueError("unsupported backend test local export")
        self.migrate_local()
        with self.connect_local() as conn, conn:
            conn.execute("DELETE FROM local_entries")
            conn.execute("DELETE FROM local_outbox")
            conn.execute("DELETE FROM local_backup_manifest")
            for entry in bundle.get("entries", []):
                conn.execute(
                    """
                    INSERT INTO local_entries(
                        local_id, entry_date, state, encrypted_payload_placeholder,
                        redacted_summary_json, canary_hash, local_version,
                        server_object_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["local_id"],
                        entry["entry_date"],
                        entry["state"],
                        entry["encrypted_payload_placeholder"],
                        json.dumps(entry.get("redacted_summary") or {}, sort_keys=True),
                        entry.get("canary_hash") or "",
                        int(entry.get("local_version") or 1),
                        entry.get("server_object_id") or "",
                        entry["created_at"],
                        entry["updated_at"],
                    ),
                )
            for event in bundle.get("outbox", []):
                conn.execute(
                    """
                    INSERT INTO local_outbox(
                        id, idempotency_key, operation, entity_type, entity_id,
                        base_version, payload_ref, state, retry_count, last_error,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["id"],
                        event["idempotency_key"],
                        event["operation"],
                        event["entity_type"],
                        event["entity_id"],
                        event.get("base_version"),
                        event["payload_ref"],
                        event["state"],
                        int(event.get("retry_count") or 0),
                        event.get("last_error") or "",
                        event["created_at"],
                        event["updated_at"],
                    ),
                )
        return {"ok": True, "state": _redacted_state(self._read_state(), local=self._local_snapshot())}

    def privacy_scan(self, *, canary: str = "") -> dict[str, Any]:
        state_text = json.dumps(_redacted_state(self._read_state()), sort_keys=True)
        report_text = "\n".join(
            path.read_text(encoding="utf-8")
            for pattern in ("*.json", "*.md")
            for path in self.reports_dir.glob(pattern)
        )
        found = []
        if canary and (canary in state_text or canary in report_text):
            found.append("canary")
        found.extend(self.store.scan_logs_for_sensitive_values([canary] if canary else []))
        return {
            "schema_version": "life_load_backend_test_privacy_scan_v1",
            "ok": not found,
            "redaction": "redacted",
            "found": found,
        }

    def run_scenario(self, name: str) -> dict[str, Any]:
        scenario = str(name or "").strip().lower().replace("_", "-")
        steps: list[dict[str, Any]] = []
        try:
            if scenario == "fresh-install-to-sync":
                self.reset_state()
                registration = self.register_fixture_user(label="fresh-sync")
                steps.append(_step("fixture_user_registered", registration["ok"] and self._backend_user_count() == 1))
                steps.append(_step("session_created", self._backend_session_count() == 1))
                steps.append(_step("device_registered", self._backend_device_count() == 1))
                steps.append(_step("create_local_entry", self.create_local_entry()["ok"] and self._local_counts()["entries"] == 1))
                sync = self.sync_outbox()
                counts = self._local_counts()
                steps.append(_step("local_outbox_uploaded_once", sync["ok"] and counts["uploaded"] == 1))
                steps.append(_step("backend_active_object_count", self._backend_active_object_count() == 1))
                steps.append(_step("restore_manifest_count", self.store.restore_manifest(_require_token(self._read_state()))["object_count"] == 1))
            elif scenario == "offline-approval-then-resync":
                self.reset_state()
                self.register_fixture_user(label="offline-resync")
                self.set_network_mode("offline")
                steps.append(_step("offline_create", self.create_local_entry()["ok"]))
                offline = self.sync_outbox()
                steps.append(_step("offline_sync_blocked", offline["ok"] is False))
                steps.append(_step("offline_no_backend_object", self._backend_active_object_count(label="offline-resync") == 0))
                steps.append(_step("offline_outbox_pending", self._local_counts()["pending"] == 1))
                self.set_network_mode("online")
                steps.append(_step("online_resync", self.sync_outbox()["ok"]))
                steps.append(_step("online_uploaded_once", self._backend_active_object_count(label="offline-resync") == 1 and self._local_counts()["uploaded"] == 1))
                token = _require_token(self._read_state())
                event = self._local_outbox()[0]
                entry = self._local_entries()[0]
                envelope = make_backup_envelope(
                    namespace_id=str(self._read_state().get("namespace_id") or ""),
                    device_id=str(self._read_state().get("active_device_id") or ""),
                    ciphertext=f"fixture_ciphertext_{entry['local_id']}",
                    entry_count=1,
                    created_at=str(entry["created_at"] or utc_now_iso()),
                )
                replay = self.store.create_backup_object(token, envelope, idempotency_key=str(event["idempotency_key"]))
                steps.append(_step("idempotency_replay_no_duplicate", replay.get("idempotent_replay") is True and self._backend_active_object_count(label="offline-resync") == 1))
            elif scenario == "uninstall-reinstall-restore":
                self.reset_state()
                self.register_fixture_user(label="restore")
                self.create_local_entry()
                self.sync_outbox()
                before_install = str(self._read_state().get("install_id") or "")
                self.uninstall()
                steps.append(_step("uninstall_clears_local_db", self._local_counts() == {"entries": 0, "outbox": 0, "uploaded": 0, "pending": 0, "manifest": 0}))
                steps.append(_step("backend_objects_remain", self._backend_active_object_count(label="restore") == 1))
                restored = self.reinstall_restore()
                after_install = str(self._read_state().get("install_id") or "")
                steps.append(_step("restore_manifest", restored["manifest"]["object_count"] >= 1))
                steps.append(_step("new_install_id", bool(after_install) and after_install != before_install))
                steps.append(_step("local_manifest_persisted", self._local_counts()["manifest"] == restored["manifest"]["object_count"]))
                steps.append(_step("key_state_missing", restored["state"]["key_state"]["state"] == "missing"))
            elif scenario == "revoked-device-blocked":
                self.reset_state()
                self.register_fixture_user(label="revoked")
                self.create_local_entry()
                self.revoke_active_device()
                blocked = False
                try:
                    self.sync_outbox()
                except PermissionError:
                    blocked = True
                steps.append(_step("revoked_device_blocked", blocked))
                steps.append(_step("revocation_recorded", self._backend_revoked_device_count(label="revoked") == 1))
                steps.append(_step("no_object_created_after_revocation", self._backend_active_object_count(label="revoked") == 0))
                steps.append(_step("local_outbox_not_uploaded", self._local_counts()["uploaded"] == 0))
            elif scenario == "cross-user-isolation":
                self.reset_state()
                a = self.store.register_user(email=_fixture_email("isolation-a"), password=DEFAULT_FIXTURE_PASSWORD, device_label="A", platform="test")
                b = self.store.register_user(email=_fixture_email("isolation-b"), password=DEFAULT_FIXTURE_PASSWORD, device_label="B", platform="test")
                created = self.store.create_backup_object(a["session_token"], make_backup_envelope(namespace_id=a["namespace_id"], device_id=a["device_id"], ciphertext="fixture_cross_user_ciphertext"))
                steps.append(_step("b_cannot_list_a_objects", self.store.list_backup_objects(b["session_token"]) == []))
                steps.append(_step("b_restore_manifest_empty", self.store.restore_manifest(b["session_token"])["object_count"] == 0))
                steps.append(_step("b_cannot_read_a_object", _raises_permission(lambda: self.store.get_backup_object(b["session_token"], created["object_id"]))))
                steps.append(_step("b_cannot_download_a_object", _raises_permission(lambda: self.store.download_restore_object(b["session_token"], created["object_id"]))))
                steps.append(_step("b_cannot_delete_a_object", _raises_permission(lambda: self.store.delete_backup_object(b["session_token"], created["object_id"]))))
            elif scenario == "privacy-canary":
                self.reset_state()
                self.register_fixture_user(label="privacy")
                canary = "backend-test-sensitive-canary"
                self.create_local_entry(canary=canary)
                self.sync_outbox()
                scan = self.privacy_scan(canary=canary)
                steps.append(_step("privacy_canary_absent", scan["ok"]))
                steps.append(_step("operational_events_canary_absent", canary not in self.store.operational_log_text()))
            elif scenario == "multi-device-conflict":
                self.reset_state()
                first = self.store.register_user(
                    email=_fixture_email("conflict"),
                    password=DEFAULT_FIXTURE_PASSWORD,
                    device_label="Device A",
                    platform="backend_test_app",
                )
                second_device = self.store.register_device(
                    first["session_token"],
                    device_label="Device B",
                    platform="backend_test_app",
                )
                second = self.store.login(
                    email=_fixture_email("conflict"),
                    password=DEFAULT_FIXTURE_PASSWORD,
                    device_id=second_device["device_id"],
                )
                first_upload = make_backup_envelope(
                    namespace_id=first["namespace_id"],
                    device_id=first["device_id"],
                    ciphertext="fixture_conflict_v1",
                )
                first_created = self.store.create_backup_object(first["session_token"], first_upload, idempotency_key="conflict-idem")
                replay = self.store.create_backup_object(first["session_token"], first_upload, idempotency_key="conflict-idem")
                same_key_conflict = _raises_value_error(
                    lambda: self.store.create_backup_object(
                        first["session_token"],
                        make_backup_envelope(
                            namespace_id=first["namespace_id"],
                            device_id=first["device_id"],
                            ciphertext="fixture_conflict_v1_different",
                        ),
                        idempotency_key="conflict-idem",
                    )
                )
                second_upload = make_backup_envelope(
                    namespace_id=first["namespace_id"],
                    device_id=second_device["device_id"],
                    ciphertext="fixture_conflict_stale_v2",
                )
                second_upload["expected_latest_backup_version"] = None
                conflict = False
                try:
                    second_upload["expected_latest_backup_version"] = 99
                    self.store.create_backup_object(second["session_token"], second_upload)
                except ValueError:
                    conflict = True
                steps.append(_step("same_idempotency_replay_same_object", replay.get("object_id") == first_created["object_id"] and replay.get("idempotent_replay") is True))
                steps.append(_step("same_idempotency_different_payload_conflict", same_key_conflict))
                steps.append(_step("stale_device_conflict_detected", conflict))
                steps.append(_step("no_silent_overwrite", self._backend_active_object_count(label="conflict") == 1))
            elif scenario == "password-reset-boundary":
                self.reset_state()
                self.register_fixture_user(label="password-reset")
                self.create_local_entry()
                self.sync_outbox()
                reset = self.store.password_reset_account_access_only(email=_fixture_email("password-reset"))
                self.uninstall()
                restored = self.reinstall_restore()
                steps.append(_step("account_access_only", reset["account_access_only"] is True))
                steps.append(_step("private_history_not_recovered", reset["private_history_recovered"] is False))
                steps.append(_step("no_key_material_returned", reset["backup_key_returned"] is False and reset["recovery_material_returned"] is False))
                steps.append(_step("metadata_restorable", restored["manifest"]["object_count"] >= 1))
                steps.append(_step("key_missing_after_uninstall", restored["state"]["key_state"]["state"] == "missing"))
            elif scenario == "large-history-restore":
                self.reset_state()
                self.register_fixture_user(label="large-history")
                for day in range(1, 31):
                    self.create_local_entry(entry_date=f"2026-04-{day:02d}")
                self.sync_outbox()
                self.uninstall()
                restored = self.reinstall_restore()
                steps.append(_step("large_manifest_count", restored["manifest"]["object_count"] == 30))
                steps.append(_step("manifest_persisted_locally", restored["state"]["local_db"]["manifest_count"] == 30))
            elif scenario == "delete-restore-manifest":
                self.reset_state()
                self.register_fixture_user(label="delete-manifest")
                self.create_local_entry(entry_date="2026-05-01")
                self.create_local_entry(entry_date="2026-05-02")
                self.sync_outbox()
                state = self._read_state()
                token = _require_token(state)
                before = self.store.restore_manifest(token)
                first_object_id = before["objects"][0]["id"]
                self.store.delete_backup_object(token, first_object_id)
                after = self.store.restore_manifest(token)
                self._replace_manifest(after["objects"])
                download_blocked = _raises_permission(lambda: self.store.download_restore_object(token, first_object_id))
                deletion_contract = self.store.deletion_contract()
                steps.append(_step("two_objects_before_delete", before["object_count"] == 2))
                steps.append(_step("one_object_after_delete", after["object_count"] == 1))
                steps.append(_step("deleted_object_excluded", first_object_id not in {item["id"] for item in after["objects"]}))
                steps.append(_step("direct_download_after_delete_blocked", download_blocked))
                steps.append(_step("deletion_event_recorded", "backups.objects.delete" in self.store.audit_text()))
                steps.append(_step("purge_not_implemented", deletion_contract["purge_implemented"] is False))
            elif scenario == "corrupted-object-restore":
                self.reset_state()
                self.register_fixture_user(label="corrupt-restore")
                self.create_local_entry()
                self.sync_outbox()
                state = self._read_state()
                token = _require_token(state)
                manifest = self.store.restore_manifest(token)
                object_id = manifest["objects"][0]["id"]
                with self.store.connect() as conn, conn:
                    conn.execute("UPDATE backup_objects SET encrypted_blob = ? WHERE id = ?", ("not-json", object_id))
                restore_failed_safely = _raises_value_error(lambda: self.store.download_restore_object(token, object_id))
                steps.append(_step("manifest_survives_corrupt_object", manifest["object_count"] == 1))
                steps.append(_step("corrupt_download_fails_safely", restore_failed_safely))
                steps.append(_step("corrupt_payload_not_reported", "not-json" not in json.dumps(steps, sort_keys=True)))
            elif scenario == "partial-restore-failure":
                self.reset_state()
                self.register_fixture_user(label="partial-restore")
                self.create_local_entry(entry_date="2026-05-01")
                self.create_local_entry(entry_date="2026-05-02")
                self.sync_outbox()
                state = self._read_state()
                token = _require_token(state)
                manifest = self.store.restore_manifest(token)
                corrupt_id = manifest["objects"][0]["id"]
                with self.store.connect() as conn, conn:
                    conn.execute("UPDATE backup_objects SET encrypted_blob = ? WHERE id = ?", ("not-json", corrupt_id))
                successes = 0
                failures = 0
                for item in manifest["objects"]:
                    try:
                        self.store.download_restore_object(token, str(item["id"]))
                        successes += 1
                    except ValueError:
                        failures += 1
                steps.append(_step("partial_manifest_has_two_objects", manifest["object_count"] == 2))
                steps.append(_step("partial_restore_reports_one_failure", failures == 1))
                steps.append(_step("partial_restore_preserves_successful_object", successes == 1))
            elif scenario == "stale-cursor-restore":
                self.reset_state()
                self.register_fixture_user(label="stale-cursor")
                self.create_local_entry(entry_date="2026-05-01")
                self.sync_outbox()
                state = self._read_state()
                state["sync_cursor"] = "sync_stale_remote_generation"
                self._write_state(state)
                self.create_local_entry(entry_date="2026-05-02")
                self.sync_outbox()
                self.uninstall()
                restored = self.reinstall_restore()
                steps.append(_step("stale_cursor_does_not_hide_remote_objects", restored["manifest"]["object_count"] == 2))
                steps.append(_step("full_manifest_replaces_local_manifest", self._local_counts()["manifest"] == 2))
            elif scenario == "object-store-unavailable":
                placeholder = S3ObjectStore()
                readiness = placeholder.readiness()
                blocked = False
                try:
                    placeholder.put_object(  # type: ignore[attr-defined]
                        user_id="usr_fixture",
                        namespace_id="bns_fixture",
                        object_id="bko_fixture",
                        payload=b"opaque",
                        sha256=hashlib.sha256(b"opaque").hexdigest(),
                    )
                except Exception:
                    blocked = True
                steps.append(_step("production_object_store_placeholder_not_ready", readiness["production_ready"] is False))
                steps.append(_step("object_store_unavailable_fails_closed", blocked))
            elif scenario == "db-unavailable":
                blocked_root = self.repo_root / "runtime" / "backend_test_app" / "not_a_directory"
                blocked_root.parent.mkdir(parents=True, exist_ok=True)
                blocked_root.write_text("not a directory", encoding="utf-8")
                unavailable = RemoteBackendStore(repo_root=blocked_root)
                failed_safely = False
                try:
                    unavailable.health()
                except (NotADirectoryError, sqlite3.Error, OSError):
                    failed_safely = True
                steps.append(_step("db_unavailable_fails_closed", failed_safely))
            elif scenario == "schema-migration-restore":
                self.reset_state()
                self.register_fixture_user(label="schema-restore")
                self.create_local_entry()
                self.sync_outbox()
                reopened_store = RemoteBackendStore(repo_root=self.repo_root)
                migrations = reopened_store.migrate()
                login = reopened_store.login(email=_fixture_email("schema-restore"), password=DEFAULT_FIXTURE_PASSWORD)
                manifest = reopened_store.restore_manifest(login["session_token"])
                steps.append(_step("migration_idempotent_on_reopen", migrations == []))
                steps.append(_step("restore_after_reopen_preserves_manifest", manifest["object_count"] == 1))
            elif scenario == "disabled-account-restore":
                self.reset_state()
                self.register_fixture_user(label="disabled-restore")
                self.create_local_entry()
                self.sync_outbox()
                state = self._read_state()
                token = _require_token(state)
                self.store.disable_user(token)
                self.create_local_entry(entry_date="2026-05-02")
                restore_blocked = _raises_permission(lambda: self.store.restore_manifest(token))
                upload_blocked = _raises_permission(lambda: self.sync_outbox())
                steps.append(_step("disabled_account_blocks_restore", restore_blocked))
                steps.append(_step("disabled_account_blocks_upload", upload_blocked))
            elif scenario == "concurrent-restore-two-devices":
                self.reset_state()
                first = self.store.register_user(
                    email=_fixture_email("concurrent-restore"),
                    password=DEFAULT_FIXTURE_PASSWORD,
                    device_label="Device A",
                    platform="backend_test_app",
                )
                second_device = self.store.register_device(
                    first["session_token"],
                    device_label="Device B",
                    platform="backend_test_app",
                )
                second = self.store.login(
                    email=_fixture_email("concurrent-restore"),
                    password=DEFAULT_FIXTURE_PASSWORD,
                    device_id=second_device["device_id"],
                )
                for index in range(3):
                    self.store.create_backup_object(
                        first["session_token"],
                        make_backup_envelope(
                            namespace_id=first["namespace_id"],
                            device_id=first["device_id"],
                            ciphertext=f"fixture_concurrent_restore_{index}",
                            entry_count=index + 1,
                        ),
                    )
                with ThreadPoolExecutor(max_workers=2) as executor:
                    manifests = list(
                        executor.map(
                            lambda token: self.store.restore_manifest(token),
                            (first["session_token"], second["session_token"]),
                        )
                    )
                steps.append(_step("both_devices_restore_same_count", [item["object_count"] for item in manifests] == [3, 3]))
                steps.append(_step("concurrent_restore_omits_ciphertext", "fixture_concurrent_restore" not in json.dumps(manifests, sort_keys=True)))
            elif scenario == "privacy-canary-restore":
                self.reset_state()
                self.register_fixture_user(label="privacy-restore")
                canary = "backend-test-restore-sensitive-canary"
                self.create_local_entry(canary=canary)
                self.sync_outbox()
                self.uninstall()
                restored = self.reinstall_restore()
                scan = self.privacy_scan(canary=canary)
                report_text = json.dumps(restored, sort_keys=True)
                steps.append(_step("privacy_restore_manifest_loaded", restored["manifest"]["object_count"] == 1))
                steps.append(_step("privacy_restore_canary_absent_from_state", canary not in report_text))
                steps.append(_step("privacy_restore_canary_absent_from_reports", scan["ok"]))
            else:
                raise ValueError("unsupported scenario")
        except Exception as exc:
            steps.append({"name": "exception", "ok": False, "error": type(exc).__name__})
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "scenario": scenario,
            "ok": all(step["ok"] for step in steps),
            "steps": steps,
            "view_mode": "redacted_default",
            "state": _redacted_state(self._read_state(), local=self._local_snapshot()),
            "redaction": "redacted",
            "created_at": utc_now_iso(),
            "cli_equivalent": f"python -m developer.backend_test_app run {scenario}",
        }
        path = self._write_report(report)
        report["report_path"] = str(path.relative_to(self.repo_root))
        markdown_path = self._write_markdown_report(report)
        report["markdown_report_path"] = str(markdown_path.relative_to(self.repo_root))
        return report

    def _read_state(self) -> dict[str, Any]:
        self.migrate_local()
        if not self.state_path.exists():
            state = _empty_state()
            self._write_state(state)
            return state
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: Mapping[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(state)
        data["updated_at"] = data.get("updated_at") or utc_now_iso()
        self.state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_report(self, report: Mapping[str, Any]) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{utc_now_iso().replace(':', '').replace('-', '')}_{report['scenario']}.json"
        path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _write_markdown_report(self, report: Mapping[str, Any]) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{utc_now_iso().replace(':', '').replace('-', '')}_{report['scenario']}.md"
        lines = [
            f"# Backend Test Scenario: {report['scenario']}",
            "",
            f"- schema_version: `{REPORT_SCHEMA_VERSION}`",
            f"- ok: `{bool(report.get('ok'))}`",
            f"- redaction: `{report.get('redaction')}`",
            f"- created_at: `{report.get('created_at')}`",
            f"- cli_equivalent: `{report.get('cli_equivalent')}`",
            "",
            "## Steps",
            "",
        ]
        for step in report.get("steps", []):
            lines.append(f"- `{step.get('name')}`: `{bool(step.get('ok'))}` request_id=`{step.get('request_id', '')}`")
        lines.extend(
            [
                "",
                "## Local State Summary",
                "",
                f"- install_id_present: `{bool(report.get('state', {}).get('install_id'))}`",
                f"- auth_session_present: `{bool(report.get('state', {}).get('auth_session_present'))}`",
                f"- network_mode: `{report.get('state', {}).get('network_mode', '')}`",
                f"- local_db_entry_count: `{report.get('state', {}).get('local_db', {}).get('entry_count', 0)}`",
                f"- local_db_outbox_count: `{report.get('state', {}).get('local_db', {}).get('outbox_count', 0)}`",
                f"- local_db_manifest_count: `{report.get('state', {}).get('local_db', {}).get('manifest_count', 0)}`",
                "",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _reset_local_db(self) -> None:
        self.migrate_local()
        with self.connect_local() as conn, conn:
            conn.execute("DELETE FROM local_entries")
            conn.execute("DELETE FROM local_outbox")
            conn.execute("DELETE FROM local_backup_manifest")

    def _local_snapshot(self) -> dict[str, Any]:
        return {
            "db_path": str(self.local_db_path),
            "entry_count": len(self._local_entries()),
            "outbox_count": len(self._local_outbox()),
            "pending_outbox_count": sum(1 for row in self._local_outbox() if row["state"] == "pending"),
            "manifest_count": len(self._local_manifest()),
            "entries": self._local_entries(),
            "outbox": self._local_outbox(),
            "manifest": self._local_manifest(),
        }

    def _local_counts(self) -> dict[str, int]:
        outbox = self._local_outbox()
        return {
            "entries": len(self._local_entries()),
            "outbox": len(outbox),
            "uploaded": sum(1 for row in outbox if row["state"] == "uploaded"),
            "pending": sum(1 for row in outbox if row["state"] == "pending"),
            "manifest": len(self._local_manifest()),
        }

    def _backend_user_count(self) -> int:
        self.store.migrate()
        with self.store.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def _backend_session_count(self) -> int:
        self.store.migrate()
        with self.store.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])

    def _backend_device_count(self) -> int:
        self.store.migrate()
        with self.store.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0])

    def _backend_active_object_count(self, *, label: str | None = None) -> int:
        self.store.migrate()
        with self.store.connect() as conn:
            if label is None:
                return int(conn.execute("SELECT COUNT(*) FROM backup_objects WHERE deleted_at IS NULL").fetchone()[0])
            row = conn.execute("SELECT id FROM users WHERE email_normalized = ?", (_fixture_email(label),)).fetchone()
            if row is None:
                return 0
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM backup_objects WHERE user_id = ? AND deleted_at IS NULL",
                    (str(row["id"]),),
                ).fetchone()[0]
            )

    def _backend_revoked_device_count(self, *, label: str) -> int:
        self.store.migrate()
        with self.store.connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE email_normalized = ?", (_fixture_email(label),)).fetchone()
            if row is None:
                return 0
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM devices WHERE user_id = ? AND revoked_at IS NOT NULL",
                    (str(row["id"]),),
                ).fetchone()[0]
            )

    def _local_entries(self) -> list[dict[str, Any]]:
        self.migrate_local()
        with self.connect_local() as conn:
            rows = conn.execute("SELECT * FROM local_entries ORDER BY created_at ASC").fetchall()
        return [_entry_from_row(row) for row in rows]

    def _local_outbox(self) -> list[dict[str, Any]]:
        self.migrate_local()
        with self.connect_local() as conn:
            rows = conn.execute("SELECT * FROM local_outbox ORDER BY created_at ASC").fetchall()
        return [dict(row) for row in rows]

    def _local_manifest(self) -> list[dict[str, Any]]:
        self.migrate_local()
        with self.connect_local() as conn:
            rows = conn.execute("SELECT * FROM local_backup_manifest ORDER BY server_received_at ASC").fetchall()
        return [dict(row) for row in rows]

    def _replace_manifest(self, objects: list[dict[str, Any]]) -> None:
        self.migrate_local()
        with self.connect_local() as conn, conn:
            conn.execute("DELETE FROM local_backup_manifest")
            for item in objects:
                conn.execute(
                    """
                    INSERT INTO local_backup_manifest(
                        object_id, namespace_id, object_type, object_version,
                        encrypted_blob_sha256, encrypted_size_bytes,
                        client_created_at, server_received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        item["namespace_id"],
                        item["object_type"],
                        int(item["object_version"]),
                        item["encrypted_blob_sha256"],
                        int(item["encrypted_size_bytes"]),
                        item["client_created_at"],
                        item["server_received_at"],
                    ),
                )


def _empty_state() -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "install_id": f"inst_{uuid.uuid4().hex}",
        "active_user_id": "",
        "fixture_label": "fixture",
        "active_device_id": "",
        "auth_session_token": "",
        "auth_session_present": False,
        "auth_session_expiry": "",
        "local_schema_version": 1,
        "sync_cursor": "",
        "network_mode": "online",
        "key_state": {"state": "missing"},
        "namespace_id": "",
        "devices": [],
        "local_entries": [],
        "local_outbox": [],
        "local_backup_manifest": [],
        "last_sync_result": {},
        "last_error": "",
        "created_at": now,
        "updated_at": now,
    }


def _redacted_state(
    state: Mapping[str, Any],
    *,
    local: Mapping[str, Any] | None = None,
    view_mode: str = "redacted_default",
) -> dict[str, Any]:
    mode = _normalize_view_mode(view_mode)
    value = json.loads(json.dumps(dict(state)))
    token = str(value.pop("auth_session_token", "") or "")
    value["view_mode"] = mode
    value["auth_session_present"] = bool(token or value.get("auth_session_present"))
    value["session_hint"] = _token_hint(token)
    if value.get("active_user_id"):
        value["active_user_id_hash"] = _short_hash(str(value["active_user_id"]))
        value.pop("active_user_id", None)
    if mode == "redacted_default":
        _hash_id_field(value, "install_id")
        _hash_id_field(value, "active_device_id")
        _hash_id_field(value, "namespace_id")
        value["devices"] = _redact_nested(value.get("devices", []), view_mode=mode)
    if local is not None:
        value["local_db"] = _redact_nested(dict(local), view_mode=mode)
        value["local_entries"] = value["local_db"]["entries"]
        value["local_outbox"] = value["local_db"]["outbox"]
        value["local_backup_manifest"] = value["local_db"]["manifest"]
    else:
        for key in ("local_entries", "local_outbox", "local_backup_manifest"):
            value[key] = [_redact_nested(item, view_mode=mode) for item in value.get(key, [])]
    return value


def _redact_nested(value: Any, *, view_mode: str = "redacted_default") -> Any:
    mode = _normalize_view_mode(view_mode)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"auth_session_token", "password", "recovery_key", "ciphertext"}:
                result[f"{key}_present"] = bool(item)
            elif mode == "redacted_default" and key in RAW_OPERATIONAL_ID_KEYS:
                result[f"{key}_hash"] = _short_hash(str(item)) if item else ""
            elif key.endswith("_id") and str(item).startswith("usr_"):
                result[f"{key}_hash"] = _short_hash(str(item))
            else:
                result[key] = _redact_nested(item, view_mode=mode)
        return result
    if isinstance(value, list):
        return [_redact_nested(item, view_mode=mode) for item in value]
    return value


def _normalize_view_mode(value: str) -> str:
    mode = str(value or "redacted_default").strip().lower()
    if mode not in VIEW_MODES:
        raise ValueError("unsupported backend test app view mode")
    return mode


def _hash_id_field(value: dict[str, Any], key: str) -> None:
    raw = str(value.get(key) or "")
    if raw:
        value[f"{key}_hash"] = _short_hash(raw)
    value.pop(key, None)


def _entry_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "local_id": row["local_id"],
        "entry_date": row["entry_date"],
        "state": row["state"],
        "encrypted_payload_placeholder": row["encrypted_payload_placeholder"],
        "redacted_summary": json.loads(str(row["redacted_summary_json"] or "{}")),
        "canary_hash": row["canary_hash"] or "",
        "local_version": int(row["local_version"]),
        "server_object_id": row["server_object_id"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _require_token(state: Mapping[str, Any]) -> str:
    token = str(state.get("auth_session_token") or "")
    if not token:
        raise PermissionError("not logged in")
    return token


def _find_entry(state: Mapping[str, Any], local_id: str) -> dict[str, Any]:
    for entry in state.get("local_entries", []):
        if entry.get("local_id") == local_id:
            return entry
    raise ValueError("local entry not found")


def _fixture_email(label: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in str(label or "fixture").lower()).strip("-")
    return f"{safe or 'fixture'}@backend-test.local"


def _namespace_for_user(store: RemoteBackendStore, user_id: str) -> str:
    with store.connect() as conn:
        row = conn.execute("SELECT id FROM backup_namespaces WHERE user_id = ? ORDER BY created_at ASC", (user_id,)).fetchone()
    if row is None:
        raise LookupError("fixture namespace not found")
    return str(row["id"])


def _short_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def _token_hint(token: str) -> str:
    if not token:
        return ""
    return f"sha256:{_short_hash(token)[-4:]}"


def _step(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "request_id": f"local_{uuid.uuid4().hex[:12]}"}


def _raises_permission(action: Any) -> bool:
    try:
        action()
    except PermissionError:
        return True
    return False


def _raises_value_error(action: Any) -> bool:
    try:
        action()
    except ValueError:
        return True
    return False
