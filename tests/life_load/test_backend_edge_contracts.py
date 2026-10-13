import json
import sqlite3
import sys
import datetime as dt
from pathlib import Path
from hashlib import sha256

import pytest

from life_load import auth_policy, backup_crypto, codex_runtime, contracts, core_engine, engine, extraction, fsio, garmin_connect_probe, mobile_web, schema_health, scoring, settings
from life_load.auth_policy import PasswordHashPolicy
from life_load.backend_test_app import BackendTestAppHarness
from life_load.continuity_readiness import (
    ContinuityReadinessConfig,
    build_continuity_readiness_report,
    privacy_scan_report,
    render_continuity_readiness_markdown,
    restore_lost_phone_simulator_contract,
    safe_local_alpha_config,
)
from life_load.codex_runtime import (
    _apply_cwd_to_codex_command,
    _apply_model_to_codex_command,
    _apply_reasoning_effort_to_codex_command,
    codex_turn_command_from_env,
    run_codex_oneshot,
)
from life_load.schema_health import (
    copy_live_import_batches_to_health,
    reconcile_compatibility_tables,
    schema_health_payload,
)
from life_load.object_store import (
    ChecksumMismatchError,
    MemoryObjectStore,
    ObjectDeletedError,
    ObjectNotFoundError,
    ObjectStoreCorruptionError,
    ObjectStoreUnavailableError,
    ProductionObjectStoreNotConfigured,
    S3CompatibleObjectStore,
    S3CompatibleObjectStoreConfig,
    S3ObjectStore,
    SQLiteBlobObjectStore,
    object_store_from_environment,
)
from life_load.remote_backend import RemoteBackendStore
from life_load.sqlite_core import HealthObservabilityStore


def test_codex_runtime_command_normalization_and_process_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFE_LOAD_CODEX_TURN_CMD", "codex exec --model old -c model_reasoning_effort=high")
    assert codex_turn_command_from_env() == ["codex", "exec", "--model", "old", "-c", "model_reasoning_effort=high"]

    modeled = _apply_model_to_codex_command(["codex", "exec", "--model=old", "prompt"], model="gpt-test")
    assert modeled == ["codex", "exec", "--model", "gpt-test", "prompt"]

    effort = _apply_reasoning_effort_to_codex_command(
        ["codex", "exec", "-c", "model_reasoning_effort=high", "prompt"],
        reasoning_effort="low",
    )
    assert effort == ["codex", "exec", "-c", 'model_reasoning_effort="low"', "prompt"]

    cwd_cmd = _apply_cwd_to_codex_command(["codex", "exec", "--cd", "/old", "prompt"], cwd=tmp_path)
    assert cwd_cmd[:4] == ["codex", "exec", "-C", str(tmp_path.resolve())]
    assert _apply_model_to_codex_command(["python", "-m", "tool"], model="ignored") == ["python", "-m", "tool"]

    monkeypatch.delenv("LIFE_LOAD_CODEX_TURN_CMD", raising=False)
    monkeypatch.setattr(codex_runtime.shutil, "which", lambda _name: None)
    missing = run_codex_oneshot(
        worker_id="w",
        binding_type="life_load",
        binding_id="b",
        role="tester",
        message="hello",
        bootstrap_text="bootstrap",
        cwd=tmp_path,
        timeout_s=1,
        command=[],
    )
    assert missing["returncode"] == 127
    assert missing["ok"] is False


def test_codex_runtime_additional_command_branches_and_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _apply_model_to_codex_command(["codex", "--model", "old"], model="gpt-new") == [
        "codex",
        "--model",
        "gpt-new",
    ]
    assert _apply_reasoning_effort_to_codex_command(["codex", "--config", "other=true"], reasoning_effort="HIGH") == [
        "codex",
        "--config",
        "other=true",
        "-c",
        'model_reasoning_effort="high"',
    ]
    assert _apply_cwd_to_codex_command(["codex", "exec", "--cwd=/old", "prompt"], cwd=tmp_path) == [
        "codex",
        "exec",
        "-C",
        str(tmp_path.resolve()),
        "prompt",
    ]
    assert _apply_cwd_to_codex_command(["codex", "run", "--cwd", "/old"], cwd=tmp_path) == ["codex", "run"]

    def _fake_success(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = " answer \n"
            stderr = ""

        assert "bootstrap" in kwargs["input"]
        assert "worker_id=w" in kwargs["input"]
        return Result()

    monkeypatch.setattr(codex_runtime.subprocess, "run", _fake_success)
    success = run_codex_oneshot(
        worker_id="w",
        binding_type="life_load",
        binding_id="b",
        role="tester",
        message="hello",
        bootstrap_text="bootstrap",
        cwd=tmp_path,
        timeout_s=0,
        command=["python", "-c", "print('unused')"],
    )
    assert success == {"ok": True, "content": "answer", "stderr": "", "returncode": 0}

    def _fake_timeout(*args, **kwargs):
        raise codex_runtime.subprocess.TimeoutExpired(cmd=["codex"], timeout=1, output="partial")

    monkeypatch.setattr(codex_runtime.subprocess, "run", _fake_timeout)
    timeout = run_codex_oneshot(
        worker_id="w",
        binding_type="life_load",
        binding_id="b",
        role="tester",
        message="hello",
        bootstrap_text="bootstrap",
        cwd=tmp_path,
        timeout_s=1,
        command=["codex", "exec"],
    )
    assert timeout["returncode"] == 124
    assert timeout["content"] == "partial"


def test_settings_validation_env_override_and_public_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_file = tmp_path / "custom-settings.json"
    monkeypatch.setenv("LIFE_LOAD_SETTINGS_PATH", str(settings_file))

    defaults = settings.normalize_settings({})
    assert defaults["garmin"]["enabled"] is False
    assert defaults["garmin"]["auto_import"] is False

    normalized = settings.save_settings(
        tmp_path,
        {
            "settings": {
                "garmin": {
                    "enabled": "false",
                    "email": "user@example.invalid",
                    "password": "secret-value",
                    "auto_import_days": "999",
                },
                "daily_flow": {"entry_cache_days": "-5", "secondary_cards_collapsed": "true"},
                "reminder": {"enabled": "true", "hour": "99", "minute": "-1"},
                "formula": {"profile": "unknown", "profile_modifiers": ["sleep", "sleep", "bad"]},
            }
        },
    )
    assert settings_file.exists()
    assert normalized["garmin"]["enabled"] is False
    assert normalized["garmin"]["auto_import_days"] <= 31
    assert normalized["daily_flow"]["entry_cache_days"] >= 1
    assert normalized["reminder"] == {"enabled": True, "hour": 23, "minute": 0}
    assert normalized["formula"]["profile"] == settings.DEFAULT_SETTINGS["formula"]["profile"]
    public = settings.settings_payload(tmp_path)["settings"]
    assert public["garmin"]["password_set"] is True
    assert "password" not in public["garmin"]

    with pytest.raises(ValueError, match="settings payload"):
        settings.save_settings(tmp_path, {"settings": []})

    settings_file.write_text("[]", encoding="utf-8")
    assert settings.load_settings(tmp_path) == normalized
    settings_file.write_text("{bad", encoding="utf-8")
    assert settings.load_settings(tmp_path) == normalized


def test_schema_health_missing_configured_copy_and_reconcile_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing_configured = tmp_path / "missing.sqlite"
    monkeypatch.setenv("LIFE_LOAD_DB_PATH", str(missing_configured))
    payload = schema_health_payload(tmp_path)
    assert payload["primary_db"] == "configured"
    assert payload["ok"] is False
    assert "missing_coffee_cups" in payload["correctness_flags"]
    assert payload["databases"][0]["exists"] is False

    assert copy_live_import_batches_to_health(tmp_path) == 0
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "life_load.sqlite"
    target = data_dir / "health.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE other(id INTEGER)")
    target.touch()
    assert copy_live_import_batches_to_health(tmp_path) == 0

    db_path = tmp_path / "compat.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_log(
              date TEXT PRIMARY KEY,
              approved_at TEXT,
              user_approved_at TEXT
            );
            CREATE TABLE daily_log_draft(
              date TEXT PRIMARY KEY,
              draft_payload TEXT,
              created_at TEXT,
              updated_at TEXT
            );
            CREATE TABLE draft_entry(
              date TEXT PRIMARY KEY,
              diary_text TEXT,
              structured_json TEXT,
              summary TEXT,
              updated_at TEXT
            );
            INSERT INTO daily_log(date, approved_at, user_approved_at)
            VALUES ('2026-05-01', '', '2026-05-01T10:00:00Z'),
                   ('2026-05-02', '2026-05-02T10:00:00Z', '');
            INSERT INTO daily_log_draft(date, draft_payload, created_at, updated_at)
            VALUES ('2026-05-03', '{"diary_text":"new","diary_summary":"summary"}', 'a', 'b'),
                   ('2026-05-04', '{bad', 'a', 'b');
            INSERT INTO draft_entry(date, diary_text, structured_json, summary, updated_at)
            VALUES ('2026-05-03', 'old', '{}', '', 'a');
            """
        )
    reconciled = reconcile_compatibility_tables(db_path)
    assert reconciled["drafts_copied_to_core"] == 2
    assert reconciled["approved_at_filled"] == 1
    assert reconciled["user_approved_at_filled"] == 1
    inspected = schema_health._inspect_db(db_path, label="compat")
    assert inspected["schema_flags"]["has_draft_entry"] is True


def test_schema_health_defensive_branches_are_contractual(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing_db = tmp_path / "missing-reconcile.sqlite"
    assert schema_health._columns(sqlite3.connect(":memory:"), "missing_table") == set()
    assert reconcile_compatibility_tables(missing_db) == {
        "drafts_copied_to_core": 0,
        "approved_at_filled": 0,
        "user_approved_at_filled": 0,
    }

    with sqlite3.connect(":memory:") as conn:
        def fail_rows(_conn, _sql, _params=()):
            raise sqlite3.Error("dbstat unavailable")

        monkeypatch.setattr(schema_health, "_rows", fail_rows)
        assert schema_health._dbstat(conn) == {}
    monkeypatch.undo()

    ensure_payload = schema_health.ensure_runtime_schema(tmp_path)
    assert ensure_payload["schema_version"] == "life_load_schema_ensure_v1"
    assert ensure_payload["applied"]
    assert ensure_payload["reconciled"]

    data_dir = tmp_path / "copy-empty"
    (data_dir / "data").mkdir(parents=True)
    source = data_dir / "data" / "life_load.sqlite"
    target = data_dir / "data" / "health.sqlite"
    with sqlite3.connect(source) as conn:
        conn.executescript(
            """
            CREATE TABLE garmin_live_import_batch(
              batch_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, mode TEXT,
              requested_start_date TEXT, requested_end_date TEXT, stale_dates_json TEXT,
              days_requested INTEGER, days_imported INTEGER, passive_created INTEGER,
              passive_updated INTEGER, passive_unchanged INTEGER, activity_created INTEGER,
              activity_updated INTEGER, activity_unchanged INTEGER, skipped INTEGER,
              skipped_reason TEXT, ok INTEGER, error TEXT, source_hashes_json TEXT,
              endpoint_status_json TEXT, result_json TEXT
            );
            """
        )
    target.touch()
    assert copy_live_import_batches_to_health(data_dir) == 0

    data_dir_with_rows = tmp_path / "copy-target-missing"
    (data_dir_with_rows / "data").mkdir(parents=True)
    source_with_rows = data_dir_with_rows / "data" / "life_load.sqlite"
    target_without_table = data_dir_with_rows / "data" / "health.sqlite"
    with sqlite3.connect(source_with_rows) as conn:
        conn.executescript(
            """
            CREATE TABLE garmin_live_import_batch(
              batch_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, mode TEXT,
              requested_start_date TEXT, requested_end_date TEXT, stale_dates_json TEXT,
              days_requested INTEGER, days_imported INTEGER, passive_created INTEGER,
              passive_updated INTEGER, passive_unchanged INTEGER, activity_created INTEGER,
              activity_updated INTEGER, activity_unchanged INTEGER, skipped INTEGER,
              skipped_reason TEXT, ok INTEGER, error TEXT, source_hashes_json TEXT,
              endpoint_status_json TEXT, result_json TEXT
            );
            INSERT INTO garmin_live_import_batch
            VALUES ('batch-missing-target', 's', 'c', 'safe', '2026-05-01', '2026-05-02',
                    '[]', 2, 2, 1, 0, 0, 1, 0, 0, 0, '', 1, '', '{}', '{}', '{}');
            """
        )
    with sqlite3.connect(target_without_table) as conn:
        conn.execute("CREATE TABLE unrelated(id INTEGER)")
    assert copy_live_import_batches_to_health(data_dir_with_rows) == 0

    compat_db = tmp_path / "compat-defensive.sqlite"
    with sqlite3.connect(compat_db) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_log(date TEXT PRIMARY KEY, approved_at TEXT, user_approved_at TEXT);
            CREATE TABLE daily_log_draft(date TEXT PRIMARY KEY, draft_payload TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE draft_entry(date TEXT PRIMARY KEY, diary_text TEXT, structured_json TEXT, summary TEXT, updated_at TEXT);
            INSERT INTO daily_log_draft(date, draft_payload, created_at, updated_at)
            VALUES ('2026-05-01', '{"diary_text":"older"}', 'a', 'b'),
                   ('2026-05-02', '[1, 2]', 'a', 'c');
            INSERT INTO draft_entry(date, diary_text, structured_json, summary, updated_at)
            VALUES ('2026-05-01', 'newer', '{}', '', 'z');
            """
        )
    reconciled = reconcile_compatibility_tables(compat_db)
    assert reconciled["drafts_copied_to_core"] == 1
    with sqlite3.connect(compat_db) as conn:
        row = conn.execute("SELECT diary_text, structured_json FROM draft_entry WHERE date = '2026-05-02'").fetchone()
    assert row == ("", "{}")


def test_schema_health_reports_duplicate_and_stale_garmin_risk(tmp_path: Path) -> None:
    db_path = tmp_path / "garmin-risk.sqlite"
    stale_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    fresh_updated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    old_updated_at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations(version TEXT PRIMARY KEY);
            CREATE TABLE daily_log(date TEXT PRIMARY KEY, coffee_cups INTEGER, approved_at TEXT, user_approved_at TEXT);
            CREATE TABLE garmin_live_import_batch(
              batch_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, mode TEXT,
              requested_start_date TEXT, requested_end_date TEXT, stale_dates_json TEXT,
              days_requested INTEGER, days_imported INTEGER, passive_created INTEGER,
              passive_updated INTEGER, passive_unchanged INTEGER, activity_created INTEGER,
              activity_updated INTEGER, activity_unchanged INTEGER, skipped INTEGER,
              skipped_reason TEXT, ok INTEGER, error TEXT, source_hashes_json TEXT,
              endpoint_status_json TEXT, result_json TEXT
            );
            CREATE TABLE garmin_daily_passive_summary(date TEXT, updated_at TEXT);
            CREATE TABLE garmin_daily_wellness(date TEXT);
            CREATE TABLE garmin_sleep_session(date TEXT, sleep_start_gmt TEXT, sleep_end_gmt TEXT);
            CREATE TABLE garmin_activity(
              date TEXT, activity_type TEXT, start_time_local_iso TEXT,
              duration_min INTEGER, distance_km REAL
            );
            """
        )
        conn.execute(
            "INSERT INTO garmin_live_import_batch VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("batch-latest", "s", "z", "safe", stale_date, stale_date, "[]", 1, 1, 1, 0, 0, 1, 0, 0, 0, "", 1, "", "{}", "{}", "{}"),
        )
        conn.executemany(
            "INSERT INTO garmin_daily_passive_summary(date, updated_at) VALUES (?, ?)",
            [(stale_date, old_updated_at), (stale_date, fresh_updated_at)],
        )
        conn.executemany("INSERT INTO garmin_daily_wellness(date) VALUES (?)", [(stale_date,), (stale_date,)])
        conn.executemany(
            "INSERT INTO garmin_sleep_session(date, sleep_start_gmt, sleep_end_gmt) VALUES (?, ?, ?)",
            [(stale_date, "a", "b"), (stale_date, "a", "b")],
        )
        conn.executemany(
            "INSERT INTO garmin_activity(date, activity_type, start_time_local_iso, duration_min, distance_km) VALUES (?, ?, ?, ?, ?)",
            [(stale_date, "run", "start", 30, 5.0), (stale_date, "run", "start", 30, 5.0)],
        )

    inspected = schema_health._inspect_db(db_path, label="garmin-risk")
    assert inspected["latest_garmin_live_import_batch"]["batch_id"] == "batch-latest"
    assert stale_date in inspected["recent_stale_garmin_dates"]
    assert inspected["duplicate_risk"] == {
        "garmin_passive_duplicate_dates": 1,
        "garmin_wellness_duplicate_dates": 1,
        "garmin_sleep_duplicate_sessions": 1,
        "garmin_activity_duplicate_shape": 1,
    }


def test_backend_test_app_session_device_redaction_and_error_edges(tmp_path: Path) -> None:
    harness = BackendTestAppHarness(repo_root=tmp_path, store=RemoteBackendStore(repo_root=tmp_path))
    harness.reset_state()
    first = harness.register_fixture_user(label="coverage-user")
    assert first["ok"] is True
    second = harness.register_fixture_user(label="coverage-user")
    assert second["ok"] is True

    logged_in = harness.login()
    assert logged_in["state"]["auth_session_present"] is True
    added_device = harness.register_device(label="Coverage second device")
    assert added_device["state"]["active_device_id_hash"]
    revoked = harness.revoke_active_device()
    assert revoked["state"]["auth_session_present"] is False
    assert harness._backend_revoked_device_count(label="coverage-user") >= 1
    assert harness._backend_revoked_device_count(label="missing-user") == 0
    assert harness._backend_active_object_count(label="missing-user") == 0

    assert harness.logout()["ok"] is True
    harness.register_fixture_user(label="coverage-user")
    logged_out = harness.logout()
    assert logged_out["state"]["auth_session_present"] is False

    with pytest.raises(ValueError, match="unsupported network mode"):
        harness.set_network_mode("production")
    with pytest.raises(ValueError, match="unsupported backend test app view mode"):
        harness.state(view_mode="raw")

    harness.login()
    harness.set_network_mode("online")
    created = harness.create_local_entry(canary="coverage-canary")
    with harness.connect_local() as conn, conn:
        local_id = conn.execute("SELECT local_id FROM local_entries LIMIT 1").fetchone()["local_id"]
        conn.execute("DELETE FROM local_entries WHERE local_id = ?", (local_id,))
    assert harness.sync_outbox()["uploaded"] == 0

    exported = harness.export_local_state()
    assert exported["checksum"]
    with pytest.raises(ValueError, match="unsupported backend test local export"):
        harness.import_local_state({"schema_version": "wrong"})
    assert harness.import_local_state(exported)["ok"] is True

    harness.reports_dir.mkdir(parents=True, exist_ok=True)
    (harness.reports_dir / "leak.json").write_text('{"value":"coverage-canary"}', encoding="utf-8")
    scan = harness.privacy_scan(canary="coverage-canary")
    assert scan["ok"] is False
    assert "canary" in scan["found"]

    unsupported = harness.run_scenario("not-a-scenario")
    assert unsupported["ok"] is False
    assert unsupported["steps"][-1]["error"] == "ValueError"

    success = run_codex_oneshot(
        worker_id="w",
        binding_type="life_load",
        binding_id="b",
        role="tester",
        message="hello",
        bootstrap_text="bootstrap",
        cwd=tmp_path,
        timeout_s=2,
        command=[sys.executable, "-c", "import sys; print(sys.stdin.read().splitlines()[0])"],
    )
    assert success["ok"] is True
    assert success["content"] == "bootstrap"

    timeout = run_codex_oneshot(
        worker_id="w",
        binding_type="life_load",
        binding_id="b",
        role="tester",
        message="hello",
        bootstrap_text="bootstrap",
        cwd=tmp_path,
        timeout_s=1,
        command=[sys.executable, "-c", "import time; time.sleep(2)"],
    )
    assert timeout["returncode"] == 124
    assert "timed out" in timeout["stderr"]


def test_fsio_json_helpers_cover_invalid_atomic_and_strict_paths(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert fsio.read_json_dict(missing) == {}

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    assert fsio.read_json_dict(invalid) == {}

    array_json = tmp_path / "array.json"
    array_json.write_text("[]", encoding="utf-8")
    assert fsio.read_json_dict(array_json) == {}
    with pytest.raises(ValueError):
        fsio.read_json_dict_strict(array_json)

    target = tmp_path / "nested" / "state.json"
    fsio.write_json_atomic(target, {"b": 2, "a": 1})
    assert fsio.read_json_dict_strict(target) == {"a": 1, "b": 2}

    jsonl = tmp_path / "rows.jsonl"
    fsio.append_jsonl(jsonl, {"ok": True})
    jsonl.write_text(jsonl.read_text(encoding="utf-8") + "\nnot-json\n[]\n", encoding="utf-8")
    assert fsio.read_jsonl(jsonl) == [{"ok": True}]
    with pytest.raises(json.JSONDecodeError):
        fsio.read_jsonl_strict(jsonl)

    object_error = tmp_path / "object_error.jsonl"
    object_error.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        fsio.read_jsonl_strict(object_error)

    assert fsio.file_lock(target) is fsio.file_lock(target)
    assert fsio.utc_now_iso().endswith("Z")


def test_schema_health_reconciles_compatibility_tables_and_copies_live_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "health.sqlite"
    default_path = data_dir / "life_load.sqlite"

    with sqlite3.connect(db_path) as conn, conn:
      conn.executescript(
          """
          CREATE TABLE daily_log(date TEXT PRIMARY KEY, approved_at TEXT, user_approved_at TEXT, coffee_cups INTEGER);
          CREATE TABLE daily_log_draft(date TEXT PRIMARY KEY, draft_payload TEXT, created_at TEXT, updated_at TEXT);
          CREATE TABLE draft_entry(date TEXT PRIMARY KEY, diary_text TEXT, structured_json TEXT, summary TEXT, updated_at TEXT);
          CREATE TABLE garmin_live_import_batch(
            batch_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, mode TEXT,
            requested_start_date TEXT, requested_end_date TEXT, stale_dates_json TEXT,
            days_requested INTEGER, days_imported INTEGER, passive_created INTEGER,
            passive_updated INTEGER, passive_unchanged INTEGER, activity_created INTEGER,
            activity_updated INTEGER, activity_unchanged INTEGER, skipped INTEGER,
            skipped_reason TEXT, ok INTEGER, error TEXT, source_hashes_json TEXT,
            endpoint_status_json TEXT, result_json TEXT
          );
          """
      )
      conn.execute(
          "INSERT INTO daily_log(date, approved_at, user_approved_at, coffee_cups) VALUES (?, ?, ?, ?)",
          ("2026-05-01", "", "2026-05-01T10:00:00Z", 2),
      )
      conn.execute(
          "INSERT INTO daily_log(date, approved_at, user_approved_at, coffee_cups) VALUES (?, ?, ?, ?)",
          ("2026-05-02", "2026-05-02T10:00:00Z", "", 1),
      )
      conn.execute(
          "INSERT INTO daily_log_draft(date, draft_payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
          ("2026-05-03", json.dumps({"diary_text": "draft", "diary_summary": "summary"}), "a", "b"),
      )

    with sqlite3.connect(default_path) as conn, conn:
      conn.executescript(
          """
          CREATE TABLE garmin_live_import_batch(
            batch_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, mode TEXT,
            requested_start_date TEXT, requested_end_date TEXT, stale_dates_json TEXT,
            days_requested INTEGER, days_imported INTEGER, passive_created INTEGER,
            passive_updated INTEGER, passive_unchanged INTEGER, activity_created INTEGER,
            activity_updated INTEGER, activity_unchanged INTEGER, skipped INTEGER,
            skipped_reason TEXT, ok INTEGER, error TEXT, source_hashes_json TEXT,
            endpoint_status_json TEXT, result_json TEXT
          );
          """
      )
      conn.execute(
          """
          INSERT INTO garmin_live_import_batch
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          """,
          ("batch-1", "s", "c", "safe", "2026-05-01", "2026-05-02", "[]", 2, 2, 1, 0, 0, 1, 0, 0, 0, "", 1, "", "{}", "{}", "{}"),
      )

    reconciled = reconcile_compatibility_tables(db_path)
    assert reconciled == {"drafts_copied_to_core": 1, "approved_at_filled": 1, "user_approved_at_filled": 1}
    assert copy_live_import_batches_to_health(tmp_path) == 1
    assert copy_live_import_batches_to_health(tmp_path) == 0

    monkeypatch.setenv("LIFE_LOAD_DB_PATH", str(db_path))
    payload = schema_health_payload(tmp_path)
    assert payload["primary_db"] == "configured"
    assert "dual_draft_tables" in payload["compatibility_flags"]
    assert "dual_approval_timestamps" in payload["compatibility_flags"]
    assert "missing_garmin_live_import_batch" not in payload["correctness_flags"]

    monkeypatch.delenv("LIFE_LOAD_DB_PATH", raising=False)
    missing_payload = schema_health_payload(tmp_path / "missing-root")
    assert missing_payload["ok"] is False
    assert missing_payload["databases"][0]["exists"] is False


def test_extraction_validation_json_and_heuristic_edge_paths() -> None:
    parsed = extraction._extract_json_object('prefix```json\n{"date":"2026-05-04","fields":{}}\n```suffix')
    assert parsed["date"] == "2026-05-04"
    with pytest.raises(ValueError):
        extraction._extract_json_object("")

    proposal = extraction.validate_proposal(
        request_date="2026-05-04",
        proposal={
            "date": "2026-05-04",
            "fields": {
                "sleep_ok": "done",
                "nutrition_ok": "not done",
                "mood": "12/10",
                "stress": "bad",
                "coffee_cups": "11 coffees",
                "wife_conflict_count": "many",
                "activity_duration_min": "2000 min",
                "primary_activity_type": "jogging",
                "work_intensity": "very heavy",
                "homework_done": "unknown",
                "tags": ["Work Heavy", "work_heavy", "bad!!!tag"],
                "other_symptoms": "x" * 300,
                "unknown": True,
            },
            "red_flags": [
                {"type": "late_phone", "severity": "purple", "evidence": "late video"},
                {"type": "unknown_flag", "severity": "red"},
                "bad",
            ],
            "summary": "summary",
            "next_action": "next",
        },
    )
    assert proposal["fields"]["sleep_ok"] is True
    assert proposal["fields"]["nutrition_ok"] is False
    assert proposal["fields"]["mood"] == 10
    assert proposal["fields"]["coffee_cups"] == 8
    assert proposal["fields"]["wife_conflict_count"] == 4
    assert proposal["fields"]["activity_duration_min"] == 1440
    assert proposal["fields"]["primary_activity_type"] == "run"
    assert proposal["fields"]["work_intensity"] == "heavy"
    assert proposal["fields"]["homework_done"] is None
    assert proposal["fields"]["tags"] == ["work-heavy", "badtag"]
    assert len(proposal["fields"]["other_symptoms"]) == 240
    assert proposal["red_flags"][0]["severity"] == "yellow"
    assert "invalid_score:stress" in proposal["validation_issues"]
    assert "unknown_field:unknown" in proposal["validation_issues"]
    assert "unknown_red_flag:unknown_flag" in proposal["validation_issues"]
    assert "invalid_red_flag:not_object" in proposal["validation_issues"]

    heuristic = extraction._heuristic_analyze_diary_entry(
        date="2026-05-04",
        diary_text=(
            "Bad sleep, junk food, beer, binge, watched videos after 21, project overrun. "
            "No shutdown, no decompression after work and the evening chain broke. "
            "Two fights with my wife about son's school and chores. Bike commute 45 min, "
            "rehab, migraine warning, heavy work, home office, alone at home, mood 4, "
            "stress 8, energy 3, coffee 9, foot pain 6/10, shoulder pain 7/10."
        ),
    )
    fields = heuristic["fields"]
    assert fields["sleep_ok"] is False
    assert fields["nutrition_ok"] is False
    assert fields["alcohol"] is True
    assert fields["binge"] is True
    assert fields["phone_after_21"] is True
    assert fields["project_overrun"] is True
    assert fields["after_work_decompression_done"] is False
    assert fields["evening_chain_broken"] is True
    assert fields["wife_conflict_count"] == 2
    assert fields["wife_conflict_school"] is True
    assert fields["wife_conflict_chores"] is True
    assert fields["primary_activity_type"] == "bike_commute"
    assert fields["coffee_cups"] == 8
    assert "Protect recovery first" in heuristic["next_action"]


def test_extraction_invalid_proposal_and_positive_heuristic_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert extraction._read_text(tmp_path / "missing.txt") == ""
    assert extraction._score_from_pattern("mood broken", "mood") is None
    assert extraction._minutes_or_none("none") is None
    assert extraction._count_or_none("none") is None
    assert extraction._normalize_activity_type("unknown sport") is None

    with pytest.raises(ValueError, match="JSON object"):
        extraction._extract_json_object("[]")
    with pytest.raises(ValueError, match="date"):
        extraction.validate_proposal(request_date="2026-05-04", proposal={"date": "2026-05-05", "fields": {}})
    with pytest.raises(ValueError, match="fields"):
        extraction.validate_proposal(request_date="2026-05-04", proposal={"date": "2026-05-04", "fields": [1]})

    invalid = extraction.validate_proposal(
        request_date="2026-05-04",
        proposal={
            "date": "2026-05-04",
            "fields": {
                "sleep_ok": "maybe",
                "wife_conflict_count": "none",
                "coffee_cups": "none",
                "activity_duration_min": "none",
                "primary_activity_type": "hoverboard",
                "work_intensity": "impossible",
            },
            "red_flags": {"bad": "shape"},
        },
    )
    assert "invalid_boolean:sleep_ok" in invalid["validation_issues"]
    assert "invalid_count:wife_conflict_count" in invalid["validation_issues"]
    assert "invalid_range:coffee_cups" in invalid["validation_issues"]
    assert "invalid_minutes:activity_duration_min" in invalid["validation_issues"]
    assert "invalid_activity_type:primary_activity_type" in invalid["validation_issues"]
    assert "invalid_work_intensity:work_intensity" in invalid["validation_issues"]
    assert "invalid_red_flags:not_list" in invalid["validation_issues"]

    positive = extraction._heuristic_analyze_diary_entry(
        date="2026-05-05",
        diary_text=(
            "Good sleep and clean food. No alcohol. Shutdown done and walk after work. "
            "I ran, did crossfit, and then bike to work. Mood 7, stress 2, energy 8."
        ),
    )
    positive_fields = positive["fields"]
    assert positive_fields["sleep_ok"] is True
    assert positive_fields["nutrition_ok"] is True
    assert positive_fields["alcohol"] is False
    assert positive_fields["shutdown_done"] is True
    assert positive_fields["after_work_decompression_done"] is True
    assert positive_fields["primary_activity_type"] == "bike_commute"
    assert "Clean food" in positive["summary"]
    assert positive["next_action"] == "Review the proposed fields and fill any unknowns before approval."

    monkeypatch.setattr(extraction, "run_codex_oneshot", lambda **_kwargs: {"ok": False, "stderr": "worker failed"})
    with pytest.raises(ValueError, match="worker failed"):
        extraction._codex_analyze_diary_entry(
            date="2026-05-05",
            diary_text="hello",
            existing_entry={},
            week_context={},
            repo_root=tmp_path,
        )


class _Body:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.buckets: set[str] = set()

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise RuntimeError("missing bucket")

    def create_bucket(self, *, Bucket: str) -> None:
        self.buckets.add(Bucket)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, Metadata: dict[str, str]) -> None:
        self.objects[(Bucket, Key)] = {"body": bytes(Body), "metadata": dict(Metadata)}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if (Bucket, Key) not in self.objects:
            raise RuntimeError("missing object")
        item = self.objects[(Bucket, Key)]
        return {
            "Body": _Body(item["body"]),  # type: ignore[arg-type]
            "Metadata": dict(item["metadata"]),  # type: ignore[arg-type]
            "ContentLength": len(item["body"]),  # type: ignore[arg-type]
        }

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if (Bucket, Key) not in self.objects:
            raise RuntimeError("missing object")
        item = self.objects[(Bucket, Key)]
        return {
            "Metadata": dict(item["metadata"]),  # type: ignore[arg-type]
            "ContentLength": len(item["body"]),  # type: ignore[arg-type]
        }

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict[str, object]:
        return {
            "Contents": [
                {"Key": key}
                for bucket, key in sorted(self.objects)
                if bucket == Bucket and key.startswith(Prefix)
            ]
        }

    def copy_object(
        self,
        *,
        Bucket: str,
        Key: str,
        CopySource: dict[str, str],
        Metadata: dict[str, str],
        MetadataDirective: str,
    ) -> None:
        source_key = CopySource["Key"]
        item = self.objects[(Bucket, source_key)]
        self.objects[(Bucket, Key)] = {"body": item["body"], "metadata": dict(Metadata)}


def test_object_store_sqlite_and_s3_compatible_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"opaque backup payload"
    checksum = sha256(payload).hexdigest()

    sqlite_store = SQLiteBlobObjectStore(tmp_path / "objects.sqlite")
    with pytest.raises(ChecksumMismatchError):
        sqlite_store.put_object(user_id="u", namespace_id="n", object_id="bad", payload=payload, sha256="wrong")
    metadata = sqlite_store.put_object(
        user_id="u",
        namespace_id="n",
        object_id="o1",
        payload=payload,
        sha256=checksum,
        idempotency_key="idem",
    )
    assert metadata.as_dict()["purge_implemented"] is False
    assert sqlite_store.get_object(user_id="u", object_id="o1") == payload
    assert sqlite_store.object_exists(user_id="u", object_id="o1") is True
    assert sqlite_store.verify_checksum(user_id="u", object_id="o1") is True
    assert [item.object_id for item in sqlite_store.list_objects(user_id="u", namespace_id="n")] == ["o1"]
    assert sqlite_store.purge_object(user_id="u", object_id="o1")["purged"] is False
    sqlite_store.mark_deleted(user_id="u", object_id="o1")
    assert sqlite_store.list_objects(user_id="u", namespace_id="n") == []
    with pytest.raises(ObjectDeletedError):
        sqlite_store.get_object(user_id="u", object_id="o1")
    with pytest.raises(ObjectNotFoundError):
        sqlite_store.get_object(user_id="u", object_id="missing")
    assert sqlite_store.delete_all_for_user(user_id="u") == 0

    monkeypatch.setenv("LIFE_LOAD_OBJECT_STORE_MODE", "memory")
    assert object_store_from_environment(sqlite_path=tmp_path / "ignored.sqlite").__class__.__name__ == "MemoryObjectStore"
    monkeypatch.setenv("LIFE_LOAD_OBJECT_STORE_MODE", "unknown")
    with pytest.raises(ValueError):
        object_store_from_environment(sqlite_path=tmp_path / "ignored.sqlite")
    monkeypatch.setenv("LIFE_LOAD_OBJECT_STORE_MODE", "minio")
    monkeypatch.delenv("MINIO_TEST_ENDPOINT", raising=False)
    with pytest.raises(ProductionObjectStoreNotConfigured):
        object_store_from_environment(sqlite_path=tmp_path / "ignored.sqlite")

    config = S3CompatibleObjectStoreConfig(
        endpoint_url="http://minio.local",
        access_key="access",
        secret_key="secret",
        bucket="bucket",
        prefix="prefix/with unsafe chars",
        initialize_bucket=True,
    )
    assert config.redacted_summary()["secret_key_configured"] is True
    client = _FakeS3Client()
    s3_store = S3CompatibleObjectStore(config, client=client)
    assert s3_store.initialize_bucket_for_test()["created"] is False
    assert s3_store.readiness()["production_ready"] is False
    assert s3_store.inject_failure_for_test("put", count=1)["remaining"] == 1
    with pytest.raises(ObjectStoreUnavailableError):
        s3_store.put_object(user_id="user/unsafe", namespace_id="ns", object_id="o/1", payload=payload, sha256=checksum)
    s3_store.put_object(user_id="user/unsafe", namespace_id="ns", object_id="o/1", payload=payload, sha256=checksum)
    assert s3_store.object_exists(user_id="user/unsafe", object_id="o/1") is True
    assert s3_store.get_object(user_id="user/unsafe", object_id="o/1") == payload
    assert s3_store.verify_checksum(user_id="user/unsafe", object_id="o/1") is True
    assert [item.object_id for item in s3_store.list_objects(user_id="user/unsafe", namespace_id="ns")] == ["o/1"]
    assert s3_store.delete_all_for_user(user_id="other") == 0
    s3_store.mark_deleted(user_id="user/unsafe", object_id="o/1")
    with pytest.raises(ObjectDeletedError):
        s3_store.get_object(user_id="user/unsafe", object_id="o/1")
    assert s3_store.verify_checksum(user_id="user/unsafe", object_id="o/1") is False

    corrupt_key = next(iter(client.objects))
    metadata = dict(client.objects[corrupt_key]["metadata"])  # type: ignore[arg-type]
    metadata["life-load-deleted-at"] = ""
    client.objects[corrupt_key] = {"body": b"corrupt", "metadata": metadata}
    with pytest.raises(ObjectStoreCorruptionError):
        s3_store.get_object(user_id="user/unsafe", object_id="o/1")


def test_continuity_readiness_reports_markdown_and_privacy_scan(tmp_path: Path) -> None:
    unsafe_report = build_continuity_readiness_report(
        repo_root=tmp_path,
        config=ContinuityReadinessConfig(
            non_local_access=True,
            public_http_enabled=True,
            router_port_forwarding_enabled=True,
        ),
        migration_report={"ok": True},
    )
    assert unsafe_report["ok"] is False
    assert "plain_http_public_internet_blocked" in unsafe_report["local_alpha_preflight"]["fatal"]
    assert "router_port_forwarding_blocked" in unsafe_report["local_alpha_preflight"]["fatal"]

    safe_report = build_continuity_readiness_report(
        repo_root=tmp_path,
        config=safe_local_alpha_config(non_local_access=True),
        migration_report={"ok": True, "active_manifest_count": 2, "purge_job_count": 0},
        observability_events=[
            {
                "event_type": "auth_failure",
                "category": "auth",
                "request_id": "req-1",
                "status_code": 401,
                "user_id_hash": "hash-1",
                "redacted_error_category": "invalid_credentials",
            }
        ],
    )
    assert safe_report["ok"] is True
    assert safe_report["acceptance"]["restore_simulator_backend_test_app_only"] is True
    assert safe_report["support_monitoring"]["observability"]["event_count"] == 1
    assert restore_lost_phone_simulator_contract()["support_or_admin_recovery"] is False

    markdown = render_continuity_readiness_markdown(safe_report)
    assert "product_cloud_backup_claim_introduced: `false`" in markdown
    assert "production_ready: `false`" in markdown
    assert privacy_scan_report({"nested": {"bad": "session_token leaked"}})["ok"] is False


def test_settings_normalization_public_payload_and_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "settings.json"
    monkeypatch.setenv("LIFE_LOAD_SETTINGS_PATH", str(override))
    monkeypatch.setattr(settings.os, "chmod", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("chmod blocked")))

    saved = settings.save_settings(
        tmp_path,
        {
            "settings": {
                "garmin": {
                    "enabled": "false",
                    "email": "operator@example.test",
                    "password": "fixture-secret",
                    "auto_import_days": 99,
                },
                "daily_flow": {
                    "default_date": "tomorrow",
                    "entry_cache_days": "bad",
                    "secondary_cards_collapsed": "TRUE",
                },
                "reminder": {
                    "enabled": "true",
                    "hour": 25,
                    "minute": -4,
                },
                "formula": {
                    "profile": "unsupported",
                    "profile_modifiers": ["balanced", "balanced", "unknown", "protective"],
                    "include_late_phone": "false",
                },
            }
        },
    )
    assert saved["garmin"]["enabled"] is False
    assert saved["garmin"]["auto_import_days"] == 14
    assert saved["daily_flow"]["default_date"] == "yesterday"
    assert saved["daily_flow"]["entry_cache_days"] == 5
    assert saved["daily_flow"]["secondary_cards_collapsed"] is True
    assert saved["reminder"] == {"enabled": True, "hour": 23, "minute": 0}
    assert saved["formula"]["profile"] == "balanced"
    assert saved["formula"]["profile_modifiers"] == ["balanced", "protective"]
    assert saved["formula"]["include_late_phone"] is False

    public = settings.settings_payload(tmp_path)
    assert public["settings"]["garmin"]["password_set"] is True
    assert "password" not in public["settings"]["garmin"]

    override.write_text("[1, 2, 3]\n", encoding="utf-8")
    assert settings.load_settings(tmp_path)["reminder"]["enabled"] is True

    override.write_text("{bad json", encoding="utf-8")
    assert settings.load_settings(tmp_path)["formula"]["include_late_phone"] is False

    override.unlink()
    with pytest.raises(ValueError, match="settings payload must be an object"):
        settings.save_settings(tmp_path, {"settings": []})


def test_contract_validation_and_load_failure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contracts, "CONTRACT_JSON_PATH", tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="is missing"):
        contracts._load_contract_definition()

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(contracts, "CONTRACT_JSON_PATH", invalid_json)
    with pytest.raises(RuntimeError, match="is invalid"):
        contracts._load_contract_definition()

    array_json = tmp_path / "array.json"
    array_json.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(contracts, "CONTRACT_JSON_PATH", array_json)
    with pytest.raises(RuntimeError, match="root must be an object"):
        contracts._load_contract_definition()

    valid = contracts.contract_payload()
    assert valid["schema_version"] == contracts.CONTRACT_SCHEMA_VERSION
    assert valid["score"]["output_keys"]

    bad_payloads = [
        {"schema_version": "wrong"},
        {**valid, "trend": {"feature_fields": ["x"], "chart": {"load_field": "x"}}},
        {
            **valid,
            "trend": {
                "feature_fields": ["load", "capacity"],
                "chart": {"load_field": "load", "load_fallback_field": "missing", "capacity_field": "capacity"},
            },
        },
        {**valid, "formula": {"sections": []}},
        {**valid, "formula": {"sections": [{"title": "", "items": []}]}},
        {**valid, "garmin_import": []},
    ]
    for payload in bad_payloads:
        with pytest.raises(RuntimeError):
            contracts._validate_contract_definition(payload)


def test_auth_policy_hashing_rate_limit_and_redaction_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    assert auth_policy.hash_session_token("token", secret="secret").startswith("hmac_sha256$")
    monkeypatch.setenv("LIFE_LOAD_SESSION_TOKEN_HMAC_SECRET", "env-secret")
    assert auth_policy.hash_session_token("token").startswith("hmac_sha256$")
    monkeypatch.delenv("LIFE_LOAD_SESSION_TOKEN_HMAC_SECRET", raising=False)
    assert "$" not in auth_policy.hash_session_token("token")

    with pytest.raises(ValueError, match="at least 8"):
        auth_policy.hash_password_for_storage("short")

    stored = auth_policy.hash_password_for_storage(
        "correct horse battery",
        policy=PasswordHashPolicy(iterations=1_000, pepper="pepper"),
    )
    assert stored.startswith("pbkdf2_sha256_peppered$")
    assert auth_policy.verify_password("correct horse battery", stored, pepper="pepper") is True
    assert auth_policy.verify_password("correct horse battery", stored, pepper="wrong") is False
    assert auth_policy.verify_password("correct horse battery", "not-a-hash") is False
    assert auth_policy.verify_password("correct horse battery", "unknown$1$salt$digest") is False

    allowed = auth_policy.login_rate_limit_decision(recent_failure_count=-5)
    blocked = auth_policy.login_rate_limit_decision(recent_failure_count=5, limit=5, window_seconds=30)
    assert allowed.as_dict()["allowed"] is True
    assert blocked.as_dict()["retry_after_seconds"] == 30
    event = auth_policy.redacted_auth_event(
        event_type="login_failed",
        user_id_hash="hash-user",
        result="denied",
        category="password",
    )
    assert event == {
        "schema_version": "life_load_auth_event_v1",
        "event_type": "login_failed",
        "user_id_hash": "hash-user",
        "result": "denied",
        "redacted_category": "password",
    }


def test_backup_crypto_v1_validation_tamper_and_recovery_edges() -> None:
    data_key = b"k" * backup_crypto.KEY_BYTES
    aad_fields = {
        "user_id_hash": "user-hash",
        "object_type": "fake_record",
        "object_id": "obj-1",
        "object_version": 1,
        "schema_version": "fixture_v1",
    }
    envelope = backup_crypto.encrypt_payload_v1(
        {"private": "fixture only"},
        data_key=data_key,
        aad_fields=aad_fields,
        key_wrapping_mode="future_device_key_placeholder",
    )
    assert backup_crypto.decrypt_payload_v1(envelope, data_key=data_key, aad_fields=aad_fields)["private"] == "fixture only"

    seen: set[tuple[str, str]] = set()
    backup_crypto.validate_crypto_envelope_v1(envelope, production_like=False, seen_nonces=seen)
    with pytest.raises(ValueError, match="nonce reuse"):
        backup_crypto.validate_crypto_envelope_v1(envelope, production_like=False, seen_nonces=seen)
    with pytest.raises(ValueError, match="production-like"):
        backup_crypto.validate_crypto_envelope_v1(envelope, production_like=True)
    with pytest.raises(ValueError, match="aad mismatch"):
        backup_crypto.decrypt_payload_v1(envelope, data_key=data_key, aad_fields={**aad_fields, "object_id": "other"})
    with pytest.raises(ValueError, match="ciphertext checksum"):
        backup_crypto.decrypt_payload_v1({**envelope, "ciphertext_sha256": "bad"}, data_key=data_key, aad_fields=aad_fields)
    with pytest.raises(ValueError, match="unsupported key_wrapping_mode"):
        backup_crypto.encrypt_payload_v1(
            {"private": "fixture only"},
            data_key=data_key,
            aad_fields=aad_fields,
            key_wrapping_mode="unsupported",
        )

    recovery_key = backup_crypto.generate_recovery_key()
    wrapped = backup_crypto.wrap_key_with_recovery_key_v1(
        data_key,
        recovery_key=recovery_key,
        aad_fields=aad_fields,
        iterations=1_000,
    )
    assert backup_crypto.unwrap_key_with_recovery_key_v1(wrapped, recovery_key=recovery_key, aad_fields=aad_fields) == data_key
    with pytest.raises(ValueError, match="aad mismatch"):
        backup_crypto.unwrap_key_with_recovery_key_v1(
            wrapped,
            recovery_key=recovery_key,
            aad_fields={**aad_fields, "object_version": 2},
        )
    with pytest.raises(ValueError, match="unsupported wrap_version"):
        backup_crypto.unwrap_key_with_recovery_key_v1(
            {**wrapped, "wrap_version": "old"},
            recovery_key=recovery_key,
            aad_fields=aad_fields,
        )
    with pytest.raises(ValueError, match="authentication failed"):
        backup_crypto.unwrap_key_with_recovery_key_v1(
            wrapped,
            recovery_key=backup_crypto.generate_recovery_key(),
            aad_fields=aad_fields,
        )

    prototype = backup_crypto.encrypt_payload_for_test({"value": 1}, backup_key=data_key, aad="aad")
    assert backup_crypto.decrypt_payload_for_test(prototype, backup_key=data_key, aad="aad") == {"value": 1}
    with pytest.raises(ValueError, match="authentication tag mismatch"):
        backup_crypto.decrypt_payload_for_test({**prototype, "tag": "AAAA"}, backup_key=data_key, aad="aad")
    recovery_wrap = backup_crypto.wrap_backup_key_with_recovery_key(
        data_key,
        recovery_key=recovery_key,
        aad="aad",
        iterations=100_000,
    )
    assert backup_crypto.unwrap_backup_key_with_recovery_key(
        recovery_wrap,
        recovery_key=recovery_key,
        aad="aad",
    ) == data_key
    with pytest.raises(ValueError, match="kdf iterations too low"):
        backup_crypto.unwrap_backup_key_with_recovery_key(
            {**recovery_wrap, "iterations": 1},
            recovery_key=recovery_key,
            aad="aad",
        )


class _ProbeLoginClient:
    def __init__(self, email: str | None, password: str | None, prompt_mfa: object) -> None:
        self.email = email
        self.password = password
        self.prompt_mfa = prompt_mfa
        self.logged_in_tokenstore = ""

    def login(self, tokenstore: str) -> None:
        self.logged_in_tokenstore = tokenstore

    def get_stats(self, date_text: str) -> dict[str, object]:
        return {"steps": "1000"}


class _ProbeActivityClient:
    def __init__(self, activity_id: str = "a1", steps: int = 1000) -> None:
        self.activity_id = activity_id
        self.steps = steps

    def get_stats(self, date_text: str) -> dict[str, object]:
        return {"totalSteps": self.steps, "activeKilocalories": 100}

    def get_user_summary(self, date_text: str) -> dict[str, object]:
        return {"totalSteps": self.steps}

    def get_heart_rates(self, date_text: str) -> dict[str, object]:
        return {"restingHeartRate": 58}

    def get_resting_heart_rate(self, date_text: str) -> int:
        return 59

    def get_sleep_data(self, date_text: str) -> dict[str, object]:
        return {"sleepData": {"sleepTimeMillis": 6 * 60 * 60 * 1000}}

    def get_all_day_stress(self, date_text: str) -> dict[str, object]:
        return {"avgStressLevel": "57"}

    def get_stress_data(self, date_text: str) -> dict[str, object]:
        return {"averageStressLevel": 54}

    def get_body_battery(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        return []

    def get_activities_by_date(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        return [
            {
                "activity_id": self.activity_id,
                "name": "Fallback Activity",
                "activityType": {"sportTypeKey": "running"},
                "sportType": {"name": "road"},
                "date": start_date,
                "duration_min": 50,
                "movingDurationInSeconds": 2400,
                "distance_km": 8.5,
                "aerobic_training_effect": 3.5,
                "calories": 500,
            },
            "ignored-row",
        ]

    def get_activities_fordate(self, date_text: str) -> dict[str, object]:
        return {"ActivitiesForDay": {"payload": [{"activityId": self.activity_id}]}}

    def get_steps_data(self, date_text: str) -> list[dict[str, object]]:
        return [{"steps": True}, {"steps": "bad"}, {"steps": self.steps}]

    def get_intensity_minutes_data(self, date_text: str) -> dict[str, object]:
        return {"weeklyModerate": "12", "weeklyVigorous": 3, "weeklyTotal": 15}


def test_garmin_probe_login_prompt_import_and_date_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert garmin_connect_probe.parse_date_text(None)
    with pytest.raises(garmin_connect_probe.GarminConnectProbeError, match="days must be"):
        garmin_connect_probe.date_range_texts(end_date="2026-05-04", days=0)
    with pytest.raises(garmin_connect_probe.GarminConnectProbeError, match="days must be"):
        garmin_connect_probe.fetch_days_bundle(_ProbeActivityClient(), end_date="2026-05-04", days=32)

    class NonTty:
        def isatty(self) -> bool:
            return False

    class Tty:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(garmin_connect_probe.sys, "stdin", NonTty())
    with pytest.raises(garmin_connect_probe.GarminConnectProbeError, match="MFA"):
        garmin_connect_probe.prompt_mfa()
    monkeypatch.setattr(garmin_connect_probe.sys, "stdin", Tty())
    monkeypatch.setattr("builtins.input", lambda _prompt: "123456")
    assert garmin_connect_probe.prompt_mfa() == "123456"

    original_import = __import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "garminconnect":
            raise ImportError("blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    with pytest.raises(garmin_connect_probe.GarminConnectProbeError, match="Optional dependency missing"):
        garmin_connect_probe.import_garmin_class()

    tokenstore = tmp_path / "tokens"
    tokenstore.mkdir()
    monkeypatch.setattr(garmin_connect_probe, "import_garmin_class", lambda: _ProbeLoginClient)
    client = garmin_connect_probe.login_client(
        garmin_connect_probe.ProbeConfig(
            date="2026-05-04",
            email=None,
            password=None,
            tokenstore=str(tokenstore),
            output_dir=tmp_path,
            write_raw=False,
        )
    )
    assert isinstance(client, _ProbeLoginClient)
    assert client.logged_in_tokenstore == str(tokenstore)

    with pytest.raises(garmin_connect_probe.GarminConnectProbeError, match="No Garmin token store"):
        garmin_connect_probe.login_client(
            garmin_connect_probe.ProbeConfig(
                date="2026-05-04",
                email=None,
                password=None,
                tokenstore=str(tmp_path / "missing"),
                output_dir=tmp_path,
                write_raw=False,
            )
        )


def test_garmin_probe_summary_import_auto_and_cli_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = garmin_connect_probe.fetch_day_bundle(_ProbeActivityClient(activity_id="", steps=2222), "2026-05-04")
    summary = garmin_connect_probe.summarize_day_bundle(bundle)
    assert summary["steps"] == 2222
    assert summary["sleep_total_min"] == 360
    assert summary["avg_stress"] == 57
    assert summary["activities_for_day_count"] == 1
    assert summary["moderate_minutes"] == 12

    assert garmin_connect_probe.summarize_day_bundle({"date": "x", "calls": {"resting_heart_rate": {"ok": True, "data": 51}}})["resting_hr"] == 51
    assert garmin_connect_probe.summarize_day_bundle(
        {"date": "x", "calls": {"steps_data": {"ok": True, "data": [{"steps": False}, {"steps": "nope"}]}}}
    )["steps"] is None

    store = HealthObservabilityStore(repo_root=tmp_path)
    store.migrate()
    tokenstore = tmp_path / "tokens"
    tokenstore.mkdir()
    monkeypatch.setattr(garmin_connect_probe, "login_client", lambda _config: _ProbeActivityClient(activity_id="auto1", steps=3333))
    auto = garmin_connect_probe.import_recent_days_if_stale(
        store,
        end_date="2026-05-04",
        days=1,
        tokenstore=str(tokenstore),
        max_age_minutes=0,
    )
    assert auto["skipped"] is False
    assert auto["days_imported"] == 1
    assert store.fetch_latest_garmin_live_import_batch()["mode"] == "auto"  # type: ignore[index]

    fresh = garmin_connect_probe.import_recent_days_if_stale(
        store,
        end_date="2026-05-04",
        days=1,
        tokenstore=str(tokenstore),
        max_age_minutes=10_000,
    )
    assert fresh["skipped"] is True
    assert fresh["skipped_reason"] == "fresh"

    manual = garmin_connect_probe.import_recent_days(store, end_date="2026-05-04", days=1, tokenstore=str(tokenstore))
    assert manual["days_imported"] == 1

    run = garmin_connect_probe.run_probe(
        garmin_connect_probe.ProbeConfig(
            date="2026-05-04",
            email=None,
            password=None,
            tokenstore=str(tokenstore),
            output_dir=tmp_path / "probe",
            write_raw=True,
        ),
        client_factory=lambda _config: _ProbeActivityClient(),
    )
    assert Path(str(run["output_path"])).exists()

    monkeypatch.setattr(
        garmin_connect_probe,
        "run_probe",
        lambda config: {"summary": {"date": config.date}, "output_path": None},
    )
    assert garmin_connect_probe.main(["--date", "2026-05-04", "--summary-only"]) == 0
    assert '"date": "2026-05-04"' in capsys.readouterr().out


def test_scoring_low_level_edges_and_decision_branches() -> None:
    assert scoring.as_bool(2) is True
    assert scoring.as_bool("off") is False
    assert scoring.as_optional_int("bad") is None
    assert scoring.clamp_int("20", minimum=1, maximum=10) == 10
    assert scoring.duration_minutes({"duration_min": "bad", "moving_duration_min": 500}) == 360.0
    assert scoring.activity_training_points({"activity_type": "unknown", "intensity": "hard", "duration_min": 0}) == 2.0
    assert scoring.activity_training_points({"activity_type": "unknown", "intensity": "moderate", "duration_min": 30}) == 1.0
    assert scoring.activity_training_points({"activity_type": "unknown", "intensity": "light", "duration_min": 30}) == 0.32
    assert scoring.activity_training_points({"activity_type": "unknown", "intensity": "", "duration_min": 30}) == 0.0
    assert scoring.profile_modifiers({"profile": "protective"}) == {"protective"}
    assert scoring.formula_settings_hash({"profile_modifiers": ["sports_light"]})

    json_activity = scoring.entry_activity_rows(
        {"date": "2026-05-04", "activity_types": '["running","physio"]', "activity_duration_min": 60}
    )
    assert [row["activity_type"] for row in json_activity] == ["run", "rehab"]
    assert scoring.entry_activity_rows({"date": "2026-05-04", "activity_types": "[bad", "primary_activity_type": "cycling"})[0][
        "activity_type"
    ] == "bike"
    assert [row["activity_type"] for row in scoring.entry_activity_rows({"date": "d", "activity_types": "run,bike"})] == [
        "run",
        "bike",
    ]
    assert scoring.entry_activity_row({"date": "d"}) is None
    assert scoring.activity_already_represented(
        {"activity_type": "crossfit", "duration_min": 40},
        [{"activity_type": "strength", "duration_min": 45, "source": "garmin_activity"}],
    )
    combined = scoring.combine_activity_rows(
        [{"activity_type": "bike", "duration_min": 30, "source": "garmin_activity"}],
        {"activity_type": "bike_commute", "duration_min": 30},
    )
    assert combined[-1]["activity_type"] == "bike_commute"
    assert scoring.load_context_from_history([1.0] * 42, today_training_load=12.0)["warnings"] == ["acute training spike"]
    assert scoring.garmin_sleep_risk("bad")["level"] == "unknown"

    red = scoring.score_entry(
        {
            "date": "2026-05-04",
            "sleep_ok": None,
            "nutrition_ok": True,
            "stress": 0,
            "energy": 8,
        },
        garmin_passive={"sleep_total_sleep_min": 180},
    )
    assert red["zone"] == "red"
    assert "impaired by short sleep" in red["next_action"]

    orange = scoring.score_entry(
        {"date": "2026-05-04", "sleep_ok": None, "nutrition_ok": True, "stress": 0, "energy": 8},
        garmin_passive={"sleep_total_sleep_min": 270},
    )
    assert orange["zone"] == "orange"
    assert "Hold progression" in orange["next_action"]

    yellow_missing = scoring.score_entry({"date": "2026-05-04"})
    assert yellow_missing["zone"] == "yellow"
    assert "fields are missing" in yellow_missing["next_action"]

    emotional = scoring.score_entry(
        {
            "date": "2026-05-04",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 7,
            "energy": 3,
            "mood": 3,
            "family_stress": 8,
            "wife_conflict_count": 2,
            "shutdown_done": False,
            "decompression_done": False,
            "after_work_decompression_done": False,
            "evening_chain_broken": True,
            "project_overrun": True,
            "phone_after_21": True,
            "work_intensity": "heavy",
            "alone_home": True,
        },
        formula_settings={"formula": {"profile_modifiers": ["protective"]}},
    )
    assert emotional["zone"] in {"orange", "red"}
    assert any("emotional" in warning for warning in emotional["warnings"])

    green = scoring.score_entry(
        {
            "date": "2026-05-04",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 0,
            "energy": 8,
            "shutdown_done": True,
            "decompression_done": True,
            "homework_done": True,
        }
    )
    assert green["zone"] == "green"
    assert green["next_action"] == "Keep the steady baseline."


def test_legacy_engine_normalization_store_errors_and_payload_boundaries(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="date is required"):
        engine.parse_date("")
    with pytest.raises(ValueError, match="invalid date"):
        engine.parse_date("05-04-2026")
    assert engine.boolish(None, default=True) is True
    assert engine.boolish("maybe", default=False) is False
    assert engine.nullable_bool("") is None
    assert engine.number("bad", default=4.5) == 4.5
    assert engine.int_0_10("bad", default=6) == 6
    assert engine.normalize_tags(" Work Heavy ;work heavy,Long Tag " * 3)[0] == "work-heavy"

    weekend = engine.normalize_entry(
        {
            "date": "2026-05-02",
            "homework_done": "No",
            "run": "yes",
            "run_distance_km": "7.25",
            "mood": "bad",
            "stress": 11,
            "tags": ["A", "A", "long tag"],
        }
    )
    assert weekend["homework_done"] == "N/A"
    assert weekend["run_distance_km"] == 7.25
    assert weekend["mood"] == 5
    assert weekend["stress"] == 10
    assert weekend["tags"] == ["a", "long-tag"]

    store = engine.LifeLoadStore(repo_root=tmp_path)
    store.ensure()
    store.rules_path.write_text("{bad json", encoding="utf-8")
    assert store.load_rules() == engine.DEFAULT_RULES

    bad_entry_path = store.entry_path(engine.parse_date("2026-05-04"))
    bad_entry_path.parent.mkdir(parents=True, exist_ok=True)
    bad_entry_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="entry is not an object"):
        store.get_entry(engine.parse_date("2026-05-04"))
    bad_entry_path.unlink()

    saved = engine.save_entry_payload(
        store,
        {
            "entry": {
                "date": "2026-05-04",
                "completed": True,
                "sleep_on_time": False,
                "nutrition_clean": False,
                "alcohol": "Social",
                "binge": True,
                "bike_commute": True,
                "crossfit": True,
                "run": True,
                "run_distance_km": 6,
                "rehab": True,
                "home_strength_mobility": True,
                "work_intensity": "Very heavy",
                "home_office": True,
                "decompression": "Other",
                "shutdown_done": False,
                "phone_after_21": True,
                "project_after_2045": True,
                "morning_reset": True,
                "injury_pain": 5,
                "foot_pain_next_day": 4,
                "migraine_warning": True,
                "on_fire": "Dangerous",
                "weekend_prep_adventure": True,
            }
        },
    )
    assert saved["save_action"] == "created"
    assert saved["score"]["zone"] == "Red"
    assert "Run distance cap violated" in " ".join(saved["score"]["red_flags"])

    entry_payload = engine.get_entry_payload(store, date_value="2026-05-04")
    assert entry_payload["entry_state"] == "saved"
    assert entry_payload["previous_date"] == "2026-05-03"
    assert entry_payload["next_date"] == "2026-05-05"

    with pytest.raises(ValueError, match="entry body"):
        engine.save_entry_payload(store, [])
    with pytest.raises(ValueError, match="end must"):
        engine.range_payload(store, start_value="2026-05-05", end_value="2026-05-04")
    with pytest.raises(ValueError, match="range too large"):
        engine.range_payload(store, start_value="2025-01-01", end_value="2026-02-01")
    assert len(engine.range_payload(store, start_value="2026-05-04", end_value="2026-05-04")["entries"]) == 1

    weekly = engine.calculate_weekly_summary(
        [
            engine.normalize_entry({"date": "2026-05-04", "completed": True, "run": True, "run_distance_km": 4}),
            engine.normalize_entry({"date": "2026-05-05", "completed": True, "crossfit": True}),
            engine.normalize_entry({"date": "2026-05-06", "completed": True, "crossfit": True}),
            engine.normalize_entry({"date": "2026-05-07", "completed": True, "crossfit": True}),
        ],
        engine.DEFAULT_RULES,
        start=engine.parse_date("2026-05-04"),
    )
    assert "Hard session cap violated" in weekly["red_flags"]
    assert weekly["next_action"] == "Stabilization week. Reduce hard sessions and protect deload."

    assert engine.weekly_zone(15, [], engine.DEFAULT_RULES["zones"]) == "Yellow"
    assert engine.weekly_zone(30, [], engine.DEFAULT_RULES["zones"]) == "Orange"
    assert engine.weekly_zone(50, [], engine.DEFAULT_RULES["zones"]) == "Red"
    assert engine.next_action_for("Red", ["Alcohol at home"], []) == "Stabilization week. Remove alcohol exposure and protect sleep."
    assert engine.next_action_for("Red", ["Running session cap violated"], []) == "Stabilization week. Freeze running progression and keep rehab."
    assert engine.next_action_for("Red", [], []) == "Stabilization week. Do minimum plan, no punishment workout."
    assert engine.next_action_for("Orange", [], []) == "Reduce ambition. Hold progression, add decompression, protect shutdown."
    assert engine.next_action_for("Yellow", [], []) == "Load building. Keep plan flat, protect sleep and decompression."
    assert engine.next_action_for("Green", [], []) == "Continue. No heroic expansion."

    engine.write_exports(store, [])
    engine.export_weekly_summaries_csv(store, [weekly])
    assert (store.generated_root / "exports" / "weekly_summaries.csv").exists()
    assert engine.load_daily_entry(store, "2026-05-04")["date"] == "2026-05-04"
    assert engine.save_daily_entry(store, {"date": "2026-05-05"})["date"] == "2026-05-05"
    assert engine.calculate_daily_score(engine.normalize_entry({"date": "2026-05-05"}), engine.DEFAULT_RULES)["date"] == "2026-05-05"
    assert engine.calculate_dashboard_state(store, date_value="2026-05-05", weeks=0)["date"] == "2026-05-05"
    assert engine.api_store(tmp_path).rules_path.exists()


def test_sqlite_core_json_fallbacks_generic_tables_exports_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.ensure_layout()
    store.migrate()

    assert store.fetch_daily_log_draft("2026-05-04") is None
    store.upsert_daily_log_draft(date="2026-05-04", draft_payload={"diary_text": "draft"})
    store.upsert_daily_log_draft(date="2026-05-04", draft_payload={"diary_text": "updated"})
    assert store.fetch_daily_log_draft("2026-05-04")["draft_payload"]["diary_text"] == "updated"  # type: ignore[index]
    with store.connect() as conn, conn:
        conn.execute("UPDATE daily_log_draft SET draft_payload = 'not-json' WHERE date = '2026-05-04'")
    assert store.fetch_daily_log_draft("2026-05-04")["draft_payload"] == {}  # type: ignore[index]
    assert store.list_daily_log_drafts(limit=999)[0]["draft_payload"] == {}
    assert store.delete_daily_log_draft("missing") is False
    assert store.delete_daily_log_draft("2026-05-04") is True

    store.upsert_daily_log(
        {
            "date": "2026-05-04",
            "completed": 1,
            "diary_text": "fixture",
            "tags": '["tag"]',
            "activity_types": '["run"]',
            "user_approved_at": "2026-05-04T10:00:00Z",
        }
    )
    store.insert_activity({"date": "2026-05-04", "activity_type": "run", "duration_min": 30, "source": "fixture"})
    store.upsert_derived_daily_summary(
        {
            "date": "2026-05-04",
            "life_load_score": 10,
            "red_flags": '["flag"]',
            "formula_settings_json": '{"formula": true}',
            "zone": "yellow",
        }
    )
    store.upsert_derived_weekly_summary(
        {
            "week_start": "2026-05-04",
            "week_end": "2026-05-10",
            "completed_days": 1,
            "zone": "yellow",
        }
    )
    store.insert_review_snapshot(
        {
            "date": "2026-05-04",
            "review_type": "weekly",
            "period_start": "2026-05-04",
            "period_end": "2026-05-10",
        }
    )
    store.insert_intervention({"start_date": "2026-05-04", "type": "deload"})
    store.insert_decision_log({"date": "2026-05-04", "decision": "hold progression"})
    store.insert_episode({"start_date": "2026-05-04", "title": "fixture", "type": "test", "tags": ["a"]})

    store.upsert_ai_proposal(
        {
            "proposal_id": "p1",
            "date": "2026-05-04",
            "raw_json": {"ok": True},
            "created_at": "2026-05-04T09:00:00Z",
            "status": "pending",
        }
    )
    assert store.fetch_latest_ai_proposal_for_date("2026-05-04", statuses=["", "pending"])["proposal_id"] == "p1"  # type: ignore[index]
    store.update_ai_proposal_status("p1", status="accepted", accepted_at="2026-05-04T10:00:00Z")
    with store.connect() as conn, conn:
        conn.execute("UPDATE ai_proposal SET raw_json = 'not-json' WHERE proposal_id = 'p1'")
    assert store.fetch_ai_proposal("p1")["raw_json"] == {}  # type: ignore[index]
    assert store.fetch_latest_ai_proposal_for_date("2026-05-04", statuses=["missing"]) is None

    store.upsert_derived_trend_feature({"date": "2026-05-04", "features_json": {"risk": "low"}})
    store.upsert_drift_detection_snapshot({"date": "2026-05-04", "contributing_signals": ["sleep"]})
    with store.connect() as conn, conn:
        conn.execute("UPDATE derived_trend_feature SET features_json = 'bad' WHERE date = '2026-05-04'")
        conn.execute("UPDATE drift_detection_snapshot SET contributing_signals = 'bad' WHERE date = '2026-05-04'")
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, source_sha256, raw_json, updated_at
            ) VALUES ('2026-05-04', 1, 'sha', 'bad', '2026-05-04T00:00:00Z')
            ON CONFLICT(date) DO UPDATE SET raw_json='bad'
            """
        )
    assert store.fetch_derived_trend_feature("2026-05-04")["features_json"] == {}  # type: ignore[index]
    assert store.fetch_drift_detection_snapshot("2026-05-04")["contributing_signals"] == []  # type: ignore[index]
    assert store.fetch_garmin_passive_summary("2026-05-04")["raw_json"] == {}  # type: ignore[index]

    store.insert_garmin_live_import_batch(
        {
            "batch_id": "b1",
            "started_at": "2026-05-04T00:00:00Z",
            "completed_at": "2026-05-04T00:01:00Z",
            "mode": "fixture",
            "stale_dates": ["2026-05-04"],
            "source_hashes": ["sha"],
            "endpoint_status": {"ok": True},
            "result": {"ok": True},
        }
    )
    with store.connect() as conn, conn:
        conn.execute(
            """
            UPDATE garmin_live_import_batch
            SET stale_dates_json='bad', source_hashes_json='bad',
                endpoint_status_json='bad', result_json='bad'
            WHERE batch_id='b1'
            """
        )
    latest = store.fetch_latest_garmin_live_import_batch()
    assert latest is not None
    assert latest["stale_dates_json"] == []
    assert latest["endpoint_status_json"] == {}

    assert "daily_log" in store.export_canonical_state()
    manifest = fsio.read_json_dict_strict(store.generated_root / "exports" / "manifest.json")
    assert "daily_log" in manifest["exports"]
    empty_csv = tmp_path / "empty.csv"
    store._write_csv(empty_csv, [])
    assert empty_csv.read_text(encoding="utf-8") == ""
    assert "date" in store.list_table_columns("daily_log")

    monkeypatch.chdir(tmp_path)
    assert __import__("life_load.sqlite_core").sqlite_core.main(["init"]) == 0
    assert __import__("life_load.sqlite_core").sqlite_core.main(["export"]) == 0
    with pytest.raises(SystemExit, match="unsupported command"):
        __import__("life_load.sqlite_core").sqlite_core.main(["unknown"])


def test_core_engine_helper_branches_and_recent_context_edges() -> None:
    with pytest.raises(ValueError, match="date is required"):
        core_engine.parse_date(None)
    with pytest.raises(ValueError, match="invalid date"):
        core_engine.parse_date("2026/05/04")

    assert core_engine._json_dump({object()}, default={"fallback": True}) == '{"fallback": true}'
    assert core_engine._json_load({"ok": True}, {}) == {"ok": True}
    assert core_engine._json_load("bad", {"fallback": True}) == {"fallback": True}
    assert core_engine._bool(1) is True
    assert core_engine._bool("off") is False
    assert core_engine._bool("maybe") is None
    assert core_engine._int_0_10("7/10") == 7
    assert core_engine._int_0_10("bad") is None
    assert core_engine._alcohol("no beer") is None
    assert core_engine._alcohol("outside") == "social"
    assert core_engine._alcohol("at-home") == "home"
    assert core_engine._family_stress("5") == "normal"
    assert core_engine._family_stress("overloaded") == "heavy"
    assert core_engine._family_stress("unexpected") == "heavy"
    assert core_engine._activity_type("cross-fit") == "crossfit"
    assert core_engine._activity_type("unknown") is None
    assert core_engine._minutes("bad") is None
    assert core_engine._minutes("2000") == 1440
    assert core_engine._count_0_12("99") == 12
    assert core_engine._count_0_12("bad") is None
    assert core_engine._diary_says_no_alcohol("No alcohol, but not no beer.") is True
    assert core_engine._diary_says_no_alcohol("No alcohol, then had alcohol.") is False
    assert core_engine._homework("maybe", date_text="2026-05-05") is None

    with pytest.raises(ValueError, match="unknown fields"):
        core_engine.normalize_structured_fields({"unknown": True}, date_text="2026-05-04", reject_unknown=True)
    normalized = core_engine.normalize_structured_fields(
        {
            "sleep_ok": "yes",
            "work_intensity": "impossible",
            "family_stress": "extreme",
            "homework_done": "n/a",
            "primary_activity_type": "jogging",
            "activity_duration_min": "75",
            "wife_conflict_count": "20",
            "tags": "Work Heavy;work_heavy",
            "other_symptoms": "x" * 300,
            "summary": "summary",
            "diary_text": " diary ",
        },
        date_text="2026-05-04",
    )
    assert normalized["sleep_ok"] is True
    assert "work_intensity" not in normalized
    assert normalized["family_stress"] == "heavy"
    assert normalized["homework_done"] == "na"
    assert normalized["primary_activity_type"] == "run"
    assert normalized["activity_duration_min"] == 75
    assert normalized["wife_conflict_count"] == 12
    assert normalized["tags"] == ["work-heavy"]
    assert len(normalized["other_symptoms"]) == 240
    assert normalized["diary_summary"] == "summary"
    assert normalized["diary_text"] == "diary"

    rows = [
        {
            "date": "2026-05-01",
            "phone_after_21": 1,
            "project_overrun": 1,
            "sleep_ok": 0,
            "nutrition_ok": 0,
            "binge": 1,
            "alcohol": "home",
            "foot_pain": 6,
            "shoulder_pain": 0,
            "wife_conflict_count": 2,
            "alone_home": 1,
            "after_work_decompression_done": 0,
            "decompression_done": 0,
            "summary_zone": "orange",
            "training_load": 5,
        },
        {
            "date": "2026-05-02",
            "phone_after_21": 1,
            "project_overrun": 1,
            "sleep_ok": 0,
            "nutrition_ok": 0,
            "binge": 0,
            "alcohol": "none",
            "foot_pain": 0,
            "shoulder_pain": 5,
            "wife_conflict_count": 1,
            "alone_home": 1,
            "after_work_decompression_done": 0,
            "decompression_done": 1,
            "summary_zone": "yellow",
            "training_load": 4,
        },
        {
            "date": "2026-05-03",
            "phone_after_21": 0,
            "project_overrun": 0,
            "sleep_ok": 1,
            "nutrition_ok": 1,
            "binge": 0,
            "alcohol": "none",
            "foot_pain": 0,
            "shoulder_pain": 0,
            "wife_conflict_count": 0,
            "alone_home": 0,
            "after_work_decompression_done": 1,
            "decompression_done": 1,
            "summary_zone": "orange",
            "training_load": 0,
        },
    ]
    context = core_engine._recent_context_from_rows(rows, lookback_days=6)
    assert context["risk_zone"] == "red"
    assert "repeated late phone" in context["signals"]
    assert context["counts"]["orange_red_days"] == 2
    assert core_engine._recent_context_from_rows([], lookback_days=6)["risk_zone"] == "green"


def test_core_engine_scoring_profile_branches_and_dashboard_fallbacks(tmp_path: Path) -> None:
    fragmented = core_engine.score_entry(
        {
            "date": "2026-05-04",
            "diary_text": "I could not sleep again after midnight.",
            "sleep_ok": True,
            "nutrition_ok": True,
        }
    )
    assert "Sleep fragmentation" in fragmented["why"]

    social = core_engine.score_entry(
        {
            "date": "2026-05-04",
            "sleep_ok": True,
            "nutrition_ok": True,
            "alcohol": "social",
            "binge": True,
            "shutdown_done": False,
            "phone_after_21": True,
            "migraine_warning": True,
            "decompression_done": False,
            "foot_pain": 0,
            "shoulder_pain": 0,
            "mood": 4,
            "energy": 4,
            "stress": 8,
            "family_stress": "heavy",
            "work_intensity": "heavy",
            "home_office": True,
            "alone_home": True,
            "after_work_decompression_done": False,
            "evening_chain_broken": True,
            "wife_conflict_count": 2,
            "wife_conflict_school": True,
            "wife_conflict_chores": True,
            "primary_activity_type": "meditation",
            "activity_duration_min": 30,
            "rehab_done": True,
        },
        formula_settings={"formula": {"profile_modifiers": ["protective"]}},
    )
    assert "Alcohol exposure" in social["why"]
    assert "binge plus evening drift" in social["red_flags"]
    assert "protective increased after-work decompression strain" in social["profile_effects"]

    sports_light_cases = [
        ({"foot_pain": 5, "energy": 8, "sleep_ok": True, "migraine_warning": False}, "pain >= 5"),
        ({"foot_pain": 0, "energy": 3, "sleep_ok": True, "migraine_warning": False}, "energy <= 3"),
        ({"foot_pain": 0, "energy": 8, "sleep_ok": True, "migraine_warning": True}, "migraine signal"),
        ({"foot_pain": 0, "energy": 8, "sleep_ok": False, "migraine_warning": False}, "sleep was disrupted"),
        (
            {"foot_pain": 0, "energy": 8, "sleep_ok": True, "migraine_warning": False, "alcohol": "home"},
            "non-training risk",
        ),
    ]
    for extra, expected in sports_light_cases:
        score = core_engine.score_entry(
            {
                "date": "2026-05-04",
                "nutrition_ok": True,
                "primary_activity_type": "run",
                "activity_duration_min": 30,
                **extra,
            },
            formula_settings={"formula": {"profile_modifiers": ["sports_light"]}},
        )
        assert any(expected in effect for effect in score["profile_effects"])

    context_adjusted = core_engine.score_entry_with_context(
        {
            "date": "2026-05-04",
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 0,
            "energy": 8,
            "mood": 8,
        },
        {"risk_zone": "orange", "signals": ["repeated protect days"]},
    )
    assert context_adjusted["zone"] == "yellow"
    assert "repeated protect days" in context_adjusted["why"]

    assert core_engine.next_action_card(mode="stabilize", why=["risk"], entry={})["primary_action"].startswith("No hard")
    assert core_engine.next_action_card(mode="hold", why=["risk"], entry={})["avoid"] == "No catch-up workout."
    assert core_engine.next_action_card(mode="protect", why=["risk"], entry={})["primary_action"].startswith("Phone")
    assert core_engine.next_action_card(mode="continue", why=["risk"], entry={})["avoid"] == "No heroic add-ons."

    store = core_engine.core_store(tmp_path)
    assert core_engine.legacy_entry_payload({"date": "2026-05-04", "draftEntry": {"structured": {"sleep_ok": True}}})[
        "entry_state"
    ] == "draft"
    assert core_engine.approve_payload
    with pytest.raises(ValueError, match="no draftEntry"):
        core_engine.approve_payload(store, {"date": "2026-05-04"})
    dashboard = core_engine.dashboard_payload(store, date_value="2026-05-04")
    assert dashboard["daily_zone"] == "green"
    assert dashboard["next_action"] is None


class _BrokenS3Client(_FakeS3Client):
    def put_object(self, **_kwargs: object) -> None:
        raise RuntimeError("put failed")


class _BrokenListS3Client(_FakeS3Client):
    def list_objects_v2(self, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("list failed")


class _BrokenDeleteS3Client(_FakeS3Client):
    def copy_object(self, **_kwargs: object) -> None:
        raise RuntimeError("copy failed")


def test_object_store_memory_s3_errors_and_environment_config_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"payload"
    checksum = sha256(payload).hexdigest()

    memory = MemoryObjectStore()
    with pytest.raises(ObjectNotFoundError):
        memory.get_object(user_id="u", object_id="missing")
    memory.put_object(user_id="u", namespace_id="n", object_id="o1", payload=payload, sha256=checksum)
    memory.put_object(user_id="u", namespace_id="n", object_id="o2", payload=payload, sha256=checksum)
    assert memory.object_exists(user_id="u", object_id="o1") is True
    assert memory.verify_checksum(user_id="u", object_id="o1") is True
    assert memory.get_object_metadata(user_id="u", object_id="o1").object_id == "o1"
    deleted = memory.mark_deleted(user_id="u", object_id="o1")
    assert memory.mark_deleted(user_id="u", object_id="o1") == deleted
    assert memory.delete_all_for_user(user_id="u") == 1
    assert memory.purge_object(user_id="u", object_id="o1")["purged"] is False

    placeholder = S3ObjectStore(configured=True)
    assert placeholder.readiness()["configured"] is True
    with pytest.raises(ProductionObjectStoreNotConfigured):
        placeholder.any_operation()

    for key, value in {
        "MINIO_TEST_ENDPOINT": "http://minio.local",
        "MINIO_TEST_ACCESS_KEY": "access",
        "MINIO_TEST_SECRET_KEY": "secret",
        "MINIO_TEST_BUCKET": "bucket",
        "MINIO_TEST_PREFIX": "prefix",
        "MINIO_TEST_INIT_BUCKET": "yes",
    }.items():
        monkeypatch.setenv(key, value)
    config = S3CompatibleObjectStoreConfig.from_env()
    assert config is not None
    assert config.initialize_bucket is True
    monkeypatch.setenv("LIFE_LOAD_OBJECT_STORE_MODE", "minio")
    with pytest.raises(ProductionObjectStoreNotConfigured):
        object_store_from_environment(sqlite_path=tmp_path / "ignored.sqlite")

    with pytest.raises(ValueError, match="unsupported"):
        S3CompatibleObjectStore(config, client=_FakeS3Client()).inject_failure_for_test("bad/op")
    with pytest.raises(ProductionObjectStoreNotConfigured):
        S3CompatibleObjectStore(config, client=None)

    with pytest.raises(ObjectStoreUnavailableError):
        S3CompatibleObjectStore(config, client=_BrokenS3Client()).put_object(
            user_id="u", namespace_id="n", object_id="o", payload=payload, sha256=checksum
        )
    with pytest.raises(ObjectStoreUnavailableError):
        S3CompatibleObjectStore(config, client=_BrokenListS3Client()).list_objects(user_id="u", namespace_id="n")

    delete_client = _BrokenDeleteS3Client()
    delete_client.buckets.add("bucket")
    delete_client.put_object(Bucket="bucket", Key="prefix/u/o", Body=payload, Metadata={
        "life-load-user-id": "u",
        "life-load-namespace-id": "n",
        "life-load-object-id": "o",
        "life-load-sha256": checksum,
        "life-load-size-bytes": str(len(payload)),
        "life-load-created-at": "now",
        "life-load-deleted-at": "",
        "life-load-idempotency-key": "",
    })
    with pytest.raises(ObjectStoreUnavailableError):
        S3CompatibleObjectStore(config, client=delete_client).mark_deleted(user_id="u", object_id="o")

    mismatch_client = _FakeS3Client()
    mismatch_client.objects[("bucket", "prefix/u/o")] = {
        "body": payload,
        "metadata": {
            "life-load-user-id": "other",
            "life-load-namespace-id": "n",
            "life-load-object-id": "o",
            "life-load-sha256": checksum,
            "life-load-size-bytes": str(len(payload)),
        },
    }
    store = S3CompatibleObjectStore(config, client=mismatch_client)
    with pytest.raises(PermissionError):
        store.get_object_metadata(user_id="u", object_id="o")
    assert store.object_exists(user_id="u", object_id="missing") is False
    with pytest.raises(ObjectNotFoundError):
        store.get_object(user_id="u", object_id="missing")
    assert store.delete_all_for_user(user_id="missing") == 0


def test_mobile_web_helper_review_range_and_analysis_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="invalid date"):
        mobile_web._parse_date("2026/05/04")
    assert mobile_web._normalize_alcohol(2) == "social"
    assert mobile_web._normalize_alcohol(True) == "home"
    assert mobile_web._alcohol_storage_value("outside") == 2
    assert mobile_web._as_optional_int("bad") is None
    assert mobile_web._normalize_tags(['["a", ["b", "a"]]', None, "c; d"]) == ["a", "b", "c", "d"]
    assert mobile_web._parse_json_list('{"not":"list"}') == []
    assert mobile_web._parse_json_list("plain") == ["plain"]
    assert mobile_web._normalize_activity_types("[bad", fallback="running") == []
    assert mobile_web._normalize_activity_types("", fallback="running") == ["run"]
    assert mobile_web._entry_fields_equal({"a": 1}, {"a": 1}) is True

    merged = mobile_web._merge_entry(
        mobile_web._default_entry(dt.date(2026, 5, 4)),
        {
            "tags": "A;B",
            "sleep_ok": "yes",
            "alcohol": "social",
            "binge": "yes",
            "coffee_cups": "99",
            "wife_conflict_count": "99",
            "activity_types": "running,cycling",
            "primary_activity_type": "Ignored Later",
            "work_intensity": "impossible",
            "other_symptoms": "x" * 300,
            "unknown": "kept",
        },
    )
    assert merged["tags"] == ["a", "b"]
    assert merged["alcohol"] == "social"
    assert merged["coffee_cups"] == 8
    assert merged["wife_conflict_count"] == 12
    assert merged["activity_types"] == ["run", "bike"]
    assert merged["work_intensity"] == "normal"
    assert len(merged["other_symptoms"]) == 240
    assert "unknown" not in merged

    assert mobile_web._activity_raw_json({"raw_json": {"ok": True}}) == {"ok": True}
    assert mobile_web._activity_raw_json({"raw_json": "bad"}) == {}
    assert mobile_web._activity_start_hour({"start_time_local_iso": ""}) is None
    assert mobile_web._activity_start_hour({"start_time_local_iso": "bad"}) is None
    assert mobile_web._elapsed_minutes({}, {"elapsedDuration": "7200"}) == 120
    commute = {
        "date": "2026-05-04",
        "activity_type": "bike",
        "sport_type": "",
        "name": "Bike to work",
        "duration_min": 30,
        "moving_duration_min": 30,
        "distance_km": 9,
        "aerobic_training_effect": 1.0,
        "start_time_local_iso": "2026-05-04T07:30:00",
        "raw_json": "{}",
    }
    assert mobile_web._infer_garmin_activity_type(commute) == "bike_commute"
    assert mobile_web._garmin_intensity({"aerobic_training_effect": 3.5}, activity_type="run") == "hard"
    assert mobile_web._garmin_intensity({"aerobic_training_effect": 2.0}, activity_type="bike_commute") == "moderate"
    assert mobile_web._garmin_hard_session({"hard_session_est": 1}, activity_type="bike_commute", intensity="hard") is False
    assert mobile_web._garmin_hard_session(
        {"hard_session_est": 1, "moving_duration_min": 30, "aerobic_training_effect": 2.0},
        activity_type="strength",
        intensity="moderate",
    ) is True

    store = mobile_web.api_store(tmp_path)
    with pytest.raises(ValueError, match="entry body"):
        mobile_web.save_entry_payload(store, [])
    with pytest.raises(ValueError, match="action"):
        mobile_web.save_entry_payload(store, {"action": "delete", "date": "2026-05-04"})
    with pytest.raises(ValueError, match="entry body"):
        mobile_web.analyze_diary_payload(store, [])
    with pytest.raises(ValueError, match="diary_text"):
        mobile_web.analyze_diary_payload(store, {"date": "2026-05-04", "diary_text": ""})
    with pytest.raises(ValueError, match="end must"):
        mobile_web.range_payload(store, start_value="2026-05-05", end_value="2026-05-04")
    with pytest.raises(ValueError, match="range too large"):
        mobile_web.range_payload(store, start_value="2025-01-01", end_value="2026-02-01")
    with pytest.raises(ValueError, match="review body"):
        mobile_web.save_review_payload(store, [])
    with pytest.raises(ValueError, match="review_type"):
        mobile_web.save_review_payload(store, {"review_type": "yearly", "date": "2026-05-04"})

    mobile_web.save_review_payload(store, {"review_type": "monthly", "date": "2026-12-15"})
    reviews = mobile_web.reviews_payload(store, date_value="2026-12-15")
    assert reviews["monthly_review_placeholder"]["period_end"] == "2026-12-31"
    assert reviews["recent_reviews"][0]["review_type"] == "monthly"

    monkeypatch.setattr(
        mobile_web,
        "analyze_diary_entry",
        lambda **_kwargs: {
            "date": "2026-05-04",
            "fields": {"sleep_ok": True, "tags": ["clear"]},
            "summary": "Clear day",
            "red_flags": [],
            "next_action": "Repeat baseline",
            "extractor_model": "fixture",
            "extractor_timeout_s": 3,
            "fallback_error": "used_fixture",
        },
    )
    analyzed = mobile_web.analyze_diary_payload(store, {"date": "2026-05-04", "diary_text": "Clean day"})
    assert analyzed["proposal"]["fallback_error"] == "used_fixture"
    assert analyzed["extractor_model"] == "fixture"

    approved = mobile_web.save_entry_payload(store, {"action": "approve", "entry": analyzed["entry"]})
    assert approved["entry_state"] == "approved"
    same = mobile_web.analyze_diary_payload(store, {"date": "2026-05-04", "diary_text": "Clean day"})
    assert same["has_draft"] is False

    replay = mobile_web.weekly_replay_payload(store, date_value="2026-05-04", weeks=99)
    assert replay["weeks_requested"] == 16
    assert replay["privacy"]["contains_diary_text"] is False
    assert mobile_web._concrete_weekly_correction(["take it easy"], ["project overrun"]) == "No project work after 20:45 for the next two evenings."
    assert mobile_web._concrete_weekly_correction(["protect sleep"], ["late phone"]) == "Put the phone away by 21:00 tonight."
    assert mobile_web._concrete_weekly_correction(["be careful"], ["nutrition drift"]) == "Plan the next normal dinner before 17:00."
    assert mobile_web._concrete_weekly_correction(["Concrete action today"], []) == "Concrete action today"
