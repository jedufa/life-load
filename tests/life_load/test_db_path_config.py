from pathlib import Path

from life_load.schema_health import schema_health_payload
from life_load.sqlite_core import HealthObservabilityStore


def test_life_load_db_path_env_override_selects_existing_db(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "external" / "health.sqlite"
    monkeypatch.setenv("LIFE_LOAD_DB_PATH", str(db_path))

    store = HealthObservabilityStore(repo_root=tmp_path)
    store.ensure_layout()
    store.migrate()

    assert store.db_path == db_path.resolve()
    assert db_path.exists()


def test_schema_health_reports_life_load_db_path_override(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "copied" / "health.sqlite"
    monkeypatch.setenv("LIFE_LOAD_DB_PATH", str(db_path))
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.migrate()

    payload = schema_health_payload(tmp_path)

    assert payload["ok"] is True
    assert payload["primary_db"] == "configured"
    assert payload["configured_db_path"] == str(db_path.resolve())
    configured = next(db for db in payload["databases"] if db["label"] == "configured")
    assert configured["exists"] is True
    assert configured["pending_migrations"] == []
