import csv
import json
import sqlite3
from pathlib import Path
from zipfile import ZipFile

import pytest

from life_load import garmin_import
from life_load.garmin_import import CSV_ROOT, import_garmin_export_zip
from life_load.sqlite_core import DB_FILENAME, DEFAULT_ROOT_REL, LEGACY_DB_FILENAME, HealthObservabilityStore
from life_load import fsio


EXPECTED_TABLE_COLUMNS = {
    "daily_log": {
        "date",
        "completed",
        "diary_text",
        "diary_summary",
        "tags",
        "sleep_ok",
        "nutrition_ok",
        "alcohol",
        "binge",
        "mood",
        "stress",
        "energy",
        "coffee_cups",
        "foot_pain",
        "shoulder_pain",
        "migraine_warning",
        "decompression_done",
        "shutdown_done",
        "phone_after_21",
        "project_overrun",
        "primary_activity_type",
        "activity_types",
        "activity_duration_min",
        "rehab_done",
        "other_symptoms",
        "work_intensity",
        "family_stress",
        "after_work_decompression_done",
        "evening_chain_broken",
        "wife_conflict_count",
        "wife_conflict_school",
        "wife_conflict_chores",
        "wife_conflict_other",
        "home_office",
        "alone_home",
        "homework_done",
        "user_approved_at",
        "created_at",
        "updated_at",
    },
    "daily_log_draft": {
        "date",
        "draft_payload",
        "created_at",
        "updated_at",
    },
    "activity_log": {
        "date",
        "activity_type",
        "duration_min",
        "intensity",
        "hard_session",
        "recovery_activity",
        "notes",
        "source",
        "created_at",
    },
    "derived_daily_summary": {
        "date",
        "life_load_score",
        "training_load",
        "recovery_score",
        "strain_score",
        "red_flags",
        "zone",
        "next_action",
        "rules_version",
        "scoring_version",
        "formula_settings_json",
        "formula_settings_hash",
        "calculated_at",
    },
    "derived_weekly_summary": {
        "week_start",
        "week_end",
        "completed_days",
        "sleep_nights",
        "nutrition_clean_days",
        "alcohol_home_count",
        "binge_count",
        "training_load",
        "hard_sessions",
        "rehab_sessions",
        "homework_sessions",
        "net_life_load",
        "zone",
        "success_score",
        "next_action",
        "rules_version",
        "calculated_at",
    },
    "review_snapshot": {
        "date",
        "review_type",
        "period_start",
        "period_end",
        "what_worked",
        "what_failed",
        "highest_risk_day",
        "next_adjustment",
        "notes",
        "created_at",
    },
    "intervention": {
        "start_date",
        "end_date",
        "type",
        "reason",
        "rule",
        "expected_effect",
        "outcome",
        "review_notes",
        "created_at",
    },
    "decision_log": {
        "date",
        "decision",
        "reason",
        "evidence",
        "review_date",
        "status",
        "created_at",
    },
    "episode": {
        "start_date",
        "end_date",
        "title",
        "type",
        "description",
        "tags",
        "created_at",
    },
    "ai_proposal": {
        "proposal_id",
        "date",
        "diary_text_hash",
        "extractor_version",
        "raw_json",
        "created_at",
        "accepted_at",
        "status",
        "error",
    },
    "derived_trend_feature": {
        "date",
        "features_json",
        "rules_version",
        "calculated_at",
    },
    "drift_detection_snapshot": {
        "date",
        "risk_level",
        "mode",
        "contributing_signals",
        "next_action",
        "evidence_note",
        "rules_version",
        "calculated_at",
    },
    "garmin_import_batch": {
        "source_sha256",
        "source_path",
        "imported_at",
        "row_counts_json",
        "date_min",
        "date_max",
    },
    "garmin_daily_passive_summary": {
        "date",
        "has_garmin_data",
        "wellness_steps",
        "wellness_resting_hr",
        "wellness_avg_stress",
        "wellness_active_kcal",
        "activity_count",
        "activity_total_duration_min",
        "activity_total_distance_km",
        "activity_total_time_on_feet_min_est",
        "activity_hard_session_count_est",
        "sleep_total_sleep_min",
        "sleep_time_in_bed_min",
        "sleep_start_gmt",
        "sleep_end_gmt",
        "body_weight_kg_est_from_bmi",
        "body_bmi",
        "source_sha256",
        "raw_json",
        "updated_at",
    },
    "garmin_sleep_session_raw": {
        "source_sha256",
        "source_row_index",
        "date",
        "sleep_start_gmt",
        "sleep_end_gmt",
        "source_file",
        "raw_json",
    },
    "garmin_live_import_batch": {
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
    },
}


def test_migrations_create_canonical_tables_and_are_idempotent(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    first = store.migrate()
    second = store.migrate()

    assert store.root == (tmp_path / DEFAULT_ROOT_REL).resolve()
    assert store.db_path == (tmp_path / "data" / DB_FILENAME).resolve()
    assert first == [
        "0001_canonical_core",
        "0002_daily_log_drafts",
        "0003_ai_proposals_and_trends",
        "0004_daily_log_extended_fields",
        "0005_garmin_passive_import",
        "0006_garmin_raw_sleep_rows",
        "0007_daily_log_evening_conflict_fields",
        "0008_daily_log_alone_home_field",
        "0009_garmin_live_import_audit",
        "0010_daily_log_coffee_cups",
        "0011_derived_daily_formula_version",
        "0012_daily_log_activity_types",
        "0013_legacy_daily_log_compatibility",
    ]
    assert second == []
    for table, expected in EXPECTED_TABLE_COLUMNS.items():
        columns = set(store.list_table_columns(table))
        assert expected.issubset(columns)

    audit_rows = fsio.read_jsonl(store.audit_path)
    assert audit_rows[-1]["event_type"] == "schema_migrated"


def test_default_store_migrates_old_data_db_filename_without_mutating_source(tmp_path: Path) -> None:
    old_store = HealthObservabilityStore(repo_root=tmp_path)
    old_store.db_root.mkdir(parents=True, exist_ok=True)
    old_db = old_store.db_root / LEGACY_DB_FILENAME
    with sqlite3.connect(old_db) as conn, conn:
        conn.execute("CREATE TABLE daily_log (date TEXT PRIMARY KEY, completed INTEGER NOT NULL DEFAULT 0, diary_text TEXT NOT NULL DEFAULT '')")
        conn.execute("INSERT INTO daily_log(date, completed, diary_text) VALUES ('2026-05-20', 1, 'legacy canonical row')")

    migrated_store = HealthObservabilityStore(repo_root=tmp_path)
    migrated_store.migrate()

    assert migrated_store.root == (tmp_path / DEFAULT_ROOT_REL).resolve()
    assert migrated_store.db_path == (tmp_path / "data" / DB_FILENAME).resolve()
    assert migrated_store.db_path.exists()
    # The legacy source remains available as a recovery copy after an atomic
    # migration; startup must never delete the only known-good database.
    assert old_db.exists()
    assert "rules_version: life_load_v0.1" in (migrated_store.config_root / "rules.yaml").read_text(encoding="utf-8")
    row = migrated_store.fetch_one("SELECT diary_text, completed FROM daily_log WHERE date = ?", ("2026-05-20",))
    assert row == {"diary_text": "legacy canonical row", "completed": 1}


def test_default_store_uses_product_data_config_and_runtime_roots(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.migrate()

    assert store.db_root == tmp_path / "data"
    assert store.config_root == tmp_path / "runtime" / "config" / "life_load"
    assert store.generated_root == tmp_path / "runtime" / "generated" / "life_load"
    assert store.audit_root == tmp_path / "runtime" / "audit" / "life_load"
    assert store.audit_path.exists()
    assert store.sample_seed_path.exists()
    assert (store.config_root / "rules.yaml").exists()


def test_upsert_daily_log_works_after_layout_cleanup(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.upsert_daily_log(
        {
            "date": "2026-05-20",
            "completed": 1,
            "diary_text": "canonical row",
        }
    )
    row = store.fetch_one("SELECT diary_text, completed FROM daily_log WHERE date = ?", ("2026-05-20",))
    assert row == {"diary_text": "canonical row", "completed": 1}


def test_create_update_query_and_export_use_sqlite_as_canonical_truth(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.upsert_daily_log(
        {
            "date": "2026-05-10",
            "completed": 1,
            "diary_text": "initial",
            "diary_summary": "day",
            "tags": ["stable"],
            "sleep_ok": 1,
            "nutrition_ok": 1,
            "alcohol": 0,
            "binge": 0,
            "mood": 7,
            "stress": 3,
            "energy": 8,
            "coffee_cups": 2,
            "foot_pain": 1,
            "shoulder_pain": 0,
            "migraine_warning": 0,
            "decompression_done": 1,
            "shutdown_done": 1,
            "phone_after_21": 0,
            "project_overrun": 0,
            "primary_activity_type": "walk",
            "activity_types": ["walk", "rehab"],
            "activity_duration_min": 30,
            "rehab_done": 1,
            "other_symptoms": "none",
            "work_intensity": "normal",
            "family_stress": 2,
            "home_office": 1,
            "homework_done": 1,
            "user_approved_at": "2026-05-10T19:00:00Z",
        }
    )
    store.upsert_daily_log(
        {
            "date": "2026-05-10",
            "completed": 1,
            "diary_text": "updated canonical text",
            "diary_summary": "updated",
            "tags": ["stable", "updated"],
            "sleep_ok": 1,
            "nutrition_ok": 0,
            "alcohol": 0,
            "binge": 0,
            "mood": 6,
            "stress": 4,
            "energy": 6,
            "coffee_cups": 4,
            "foot_pain": 2,
            "shoulder_pain": 0,
            "migraine_warning": 0,
            "decompression_done": 1,
            "shutdown_done": 1,
            "phone_after_21": 0,
            "project_overrun": 0,
            "primary_activity_type": "walk",
            "activity_types": ["walk"],
            "activity_duration_min": 25,
            "rehab_done": 0,
            "other_symptoms": "",
            "work_intensity": "normal",
            "family_stress": 3,
            "home_office": 0,
            "homework_done": 1,
            "user_approved_at": "2026-05-10T19:15:00Z",
        }
    )
    store.upsert_derived_daily_summary(
        {
            "date": "2026-05-10",
            "life_load_score": 21,
            "training_load": 3,
            "recovery_score": 7,
            "strain_score": 4,
            "red_flags": ["none"],
            "zone": "green",
            "next_action": "repeat the boring good day",
        }
    )
    store.upsert_derived_weekly_summary(
        {
            "week_start": "2026-05-04",
            "week_end": "2026-05-10",
            "completed_days": 1,
            "sleep_nights": 1,
            "nutrition_clean_days": 0,
            "alcohol_home_count": 0,
            "binge_count": 0,
            "training_load": 3,
            "hard_sessions": 0,
            "rehab_sessions": 0,
            "homework_sessions": 1,
            "net_life_load": 21,
            "zone": "green",
            "success_score": 0.2,
            "next_action": "stay consistent",
        }
    )

    row = store.fetch_one("SELECT diary_text, nutrition_ok, activity_types FROM daily_log WHERE date = ?", ("2026-05-10",))
    assert row["diary_text"] == "updated canonical text"
    assert row["nutrition_ok"] == 0
    assert json.loads(row["activity_types"]) == ["walk"]

    export_paths = store.export_canonical_state()
    daily_export = Path(export_paths["daily_log"])
    with daily_export.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-10"
    assert rows[0]["diary_text"] == "updated canonical text"

    audit_rows = fsio.read_jsonl(store.audit_path)
    event_types = [row["event_type"] for row in audit_rows]
    assert event_types.count("daily_log_upserted") == 2
    assert "canonical_state_exported" in event_types


def test_fake_sample_seed_populates_canonical_sqlite_and_export_surface(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)

    counts = store.seed_fake_sample_data()
    daily_rows = store.fetch_all("SELECT date, diary_summary FROM daily_log ORDER BY date")
    weekly_rows = store.fetch_all("SELECT week_start, zone FROM derived_weekly_summary ORDER BY week_start")
    export_paths = store.export_canonical_state()

    assert counts["daily_log"] >= 2
    assert len(daily_rows) == counts["daily_log"]
    assert weekly_rows == [{"week_start": "2026-04-27", "zone": "yellow"}]
    assert Path(export_paths["derived_daily_summary"]).exists()
    assert Path(export_paths["derived_weekly_summary"]).exists()


def test_new_ai_trend_and_drift_tables_round_trip_and_export(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.upsert_ai_proposal(
        {
            "proposal_id": "prop_20260503_demo",
            "date": "2026-05-03",
            "diary_text_hash": "abc123",
            "extractor_version": "heuristic_diary_v0_1",
            "raw_json": {"summary": "demo"},
            "status": "applied_to_draft",
        }
    )
    store.upsert_derived_trend_feature(
        {
            "date": "2026-05-03",
            "features_json": {"sleep_compliance_7d": 0.57, "project_overrun_count_7d": 2},
            "rules_version": "trend_features_v0_1",
        }
    )
    store.upsert_drift_detection_snapshot(
        {
            "date": "2026-05-03",
            "risk_level": "orange",
            "mode": "hold",
            "contributing_signals": ["project overruns rising"],
            "next_action": "Cut evening spillover.",
            "evidence_note": "Triggered by: project overruns rising.",
            "rules_version": "drift_detector_v0_1",
        }
    )

    proposal = store.fetch_latest_ai_proposal_for_date("2026-05-03")
    trend = store.fetch_derived_trend_feature("2026-05-03")
    drift = store.fetch_drift_detection_snapshot("2026-05-03")
    export_paths = store.export_canonical_state()

    assert proposal is not None
    assert proposal["raw_json"]["summary"] == "demo"
    assert trend is not None
    assert trend["features_json"]["project_overrun_count_7d"] == 2
    assert drift is not None
    assert drift["risk_level"] == "orange"
    assert Path(export_paths["ai_proposal"]).exists()
    assert Path(export_paths["derived_trend_feature"]).exists()
    assert Path(export_paths["drift_detection_snapshot"]).exists()


def test_generated_and_sample_files_cannot_silently_replace_canonical_sqlite_truth(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.upsert_daily_log(
        {
            "date": "2026-05-12",
            "completed": 1,
            "diary_text": "canonical sqlite row",
            "diary_summary": "real",
            "tags": ["real"],
            "sleep_ok": 1,
            "nutrition_ok": 1,
            "alcohol": 0,
            "binge": 0,
        }
    )
    rogue_export = store.generated_root / "exports" / "daily_log.csv"
    rogue_export.parent.mkdir(parents=True, exist_ok=True)
    rogue_export.write_text("date,diary_text\n2026-05-12,forged export row\n", encoding="utf-8")
    rogue_sample = store.samples_root / "rogue_daily_log.json"
    fsio.write_json_atomic(rogue_sample, {"date": "2026-05-12", "diary_text": "sample override"})

    row = store.fetch_one("SELECT diary_text FROM daily_log WHERE date = ?", ("2026-05-12",))
    assert row == {"diary_text": "canonical sqlite row"}

    store.export_canonical_state()
    with rogue_export.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-12"
    assert rows[0]["diary_text"] == "canonical sqlite row"
    assert rows[0]["diary_text"] != "forged export row"
    assert rows[0]["tags"] == '["real"]'
    assert rows[0]["coffee_cups"] == ""
    assert rows[0]["created_at"]
    assert rows[0]["updated_at"]

    audit_rows = fsio.read_jsonl(store.audit_path)
    assert audit_rows[-1]["event_type"] == "canonical_state_exported"


def _write_garmin_csv(zip_file: ZipFile, name: str, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(value) for value in row))
    zip_file.writestr(CSV_ROOT + name, "\n".join(lines) + "\n")


def _tiny_garmin_zip(path: Path) -> None:
    with ZipFile(path, "w") as zip_file:
        _write_garmin_csv(
            zip_file,
            "activities.csv",
            [
                "activity_id",
                "date",
                "start_time_local_iso",
                "name",
                "activity_type",
                "sport_type",
                "duration_min",
                "moving_duration_min",
                "distance_km",
                "time_on_feet_min_est",
                "impact_load_est",
                "hard_session_est",
                "calories",
                "avg_hr",
                "max_hr",
                "aerobic_training_effect",
                "anaerobic_training_effect",
                "source_file",
                "quality_flag",
            ],
            [["a1", "2024-06-12", "2024-06-12T07:00:00+02:00", "Morning Run", "running", "RUNNING", 35, 34, 5.2, 34, 1, "True", 420, 145, 171, 3.1, 0.2, "activities.json", "normalized"]],
        )
        _write_garmin_csv(
            zip_file,
            "sleep_sessions.csv",
            [
                "date",
                "sleep_start_gmt",
                "sleep_end_gmt",
                "total_sleep_min",
                "time_in_bed_min",
                "deep_sleep_min",
                "light_sleep_min",
                "rem_sleep_min",
                "awake_min",
                "confirmation_type",
                "source_file",
                "quality_flag",
            ],
            [["2024-06-12", "2024-06-11T20:30:00Z", "2024-06-12T04:30:00Z", 430, 480, 80, 250, 100, 50, "AUTO", "sleep.json", "device"]],
        )
        _write_garmin_csv(
            zip_file,
            "daily_wellness.csv",
            [
                "date",
                "steps",
                "step_goal",
                "total_distance_km",
                "total_kcal",
                "active_kcal",
                "moderate_intensity_min",
                "vigorous_intensity_min",
                "active_min",
                "resting_hr",
                "avg_stress",
                "max_stress",
                "hydration_ml",
                "source_file",
                "quality_flag",
            ],
            [["2024-06-12", 12345, 10000, 8.2, 2700, 650, 20, 18, 72, 52, 34, 77, "", "wellness.json", "device"]],
        )
        _write_garmin_csv(
            zip_file,
            "training_history.csv",
            [
                "date",
                "timestamp",
                "sport",
                "sub_sport",
                "weekly_training_load_sum",
                "load_tunnel_min",
                "load_tunnel_max",
                "training_status",
                "fitness_level_trend",
                "load_level_trend",
                "source_file",
                "quality_flag",
            ],
            [["2024-06-12", "2024-06-12T05:00:00Z", "RUNNING", "GENERIC", 330, 145, 420, "PRODUCTIVE", "UP", "OPTIMAL", "training.json", "device"]],
        )
        _write_garmin_csv(
            zip_file,
            "acute_training_load.csv",
            [
                "date",
                "timestamp_iso",
                "acwr_percent",
                "acwr_status",
                "daily_training_load_acute",
                "daily_training_load_chronic",
                "daily_acwr",
                "source_file",
                "quality_flag",
            ],
            [["2024-06-12", "2024-06-12T23:59:59Z", 80, "OPTIMAL", 130, 160, 0.81, "acute.json", "device"]],
        )
        _write_garmin_csv(
            zip_file,
            "body_measurements.csv",
            [
                "date",
                "weight_kg_est_from_bmi",
                "body_fat_pct",
                "bmi",
                "rhr",
                "chronological_age",
                "current_fitness_age",
                "weight_data_last_entry_date",
                "source_file",
                "quality_flag",
            ],
            [["2024-06-12", 98.5, "", 27.4, 52, 44, 42, "2024-06-12", "body.json", "estimate"]],
        )
        _write_garmin_csv(
            zip_file,
            "daily_joined_summary.csv",
            [
                "date",
                "wellness_steps",
                "wellness_resting_hr",
                "wellness_avg_stress",
                "wellness_active_kcal",
                "activity_activity_count",
                "activity_total_duration_min",
                "activity_total_distance_km",
                "activity_total_time_on_feet_min_est",
                "activity_hard_session_count_est",
                "sleep_total_sleep_min",
                "sleep_time_in_bed_min",
                "sleep_sleep_start_gmt",
                "sleep_sleep_end_gmt",
                "body_weight_kg_est_from_bmi",
                "body_bmi",
            ],
            [["2024-06-12", 12345, 52, 34, 650, 1, 35, 5.2, 34, 1, 430, 480, "2024-06-11T20:30:00Z", "2024-06-12T04:30:00Z", 98.5, 27.4]],
        )
        _write_garmin_csv(
            zip_file,
            "source_manifest.csv",
            ["path", "size_bytes", "compressed_size_bytes", "modified", "kind"],
            [["DI_CONNECT/example.json", 100, 80, "2026-05-03T00:00:00", "json"]],
        )
        _write_garmin_csv(
            zip_file,
            "uploaded_files_inner_manifest.csv",
            ["outer_zip", "path", "size_bytes", "kind"],
            [["outer.zip", "DI_CONNECT/uploaded.json", 44, "json"]],
        )


def test_garmin_import_populates_passive_tables_without_overwriting_daily_truth(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.upsert_daily_log(
        {
            "date": "2024-06-12",
            "completed": 1,
            "diary_text": "manual truth stays",
            "diary_summary": "manual",
            "tags": ["manual"],
            "sleep_ok": 0,
            "nutrition_ok": 1,
            "alcohol": 0,
            "binge": 0,
        }
    )
    zip_path = tmp_path / "garmin.zip"
    _tiny_garmin_zip(zip_path)

    first = import_garmin_export_zip(store, zip_path)
    second = import_garmin_export_zip(store, zip_path)

    assert first["row_counts"]["daily_joined_summary"] == 1
    assert first["source_sha256"] == second["source_sha256"]
    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_activity") == {"c": 1}
    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_sleep_session") == {"c": 1}
    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_sleep_session_raw") == {"c": 1}
    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_uploaded_files_manifest") == {"c": 1}
    passive = store.fetch_garmin_passive_summary("2024-06-12")
    assert passive is not None
    assert passive["wellness_steps"] == 12345
    assert passive["activity_hard_session_count_est"] == 1
    assert passive["raw_json"]["activity_total_distance_km"] == "5.2"
    manual = store.fetch_one("SELECT diary_text, completed FROM daily_log WHERE date = ?", ("2024-06-12",))
    assert manual == {"diary_text": "manual truth stays", "completed": 1}


def test_garmin_import_rejects_missing_required_csv_without_partial_tables(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    zip_path = tmp_path / "bad_garmin.zip"
    with ZipFile(zip_path, "w") as zip_file:
        _write_garmin_csv(zip_file, "activities.csv", ["activity_id", "date"], [["a1", "2024-06-12"]])

    try:
        import_garmin_export_zip(store, zip_path)
    except ValueError as exc:
        assert "missing required CSVs" in str(exc)
    else:
        raise AssertionError("bad Garmin export should fail")

    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_activity") == {"c": 0}


def test_garmin_import_cli_and_numeric_error_edges(tmp_path: Path, capsys) -> None:
    assert garmin_import._float_or_none("not-a-number") is None
    assert garmin_import._int_or_none("") is None

    store = HealthObservabilityStore(repo_root=tmp_path / "missing")
    with pytest.raises(FileNotFoundError):
        import_garmin_export_zip(store, tmp_path / "missing.zip")

    with pytest.raises(SystemExit, match="usage:"):
        garmin_import.main([])

    zip_path = tmp_path / "garmin-cli.zip"
    repo_root = tmp_path / "repo"
    _tiny_garmin_zip(zip_path)
    exit_code = garmin_import.main([str(zip_path), str(repo_root)])
    stdout = capsys.readouterr().out
    report = json.loads(stdout)

    assert exit_code == 0
    assert report["schema_version"] == "garmin_import_result_v1"
    assert report["row_counts"]["uploaded_files_manifest"] == 1
    imported = HealthObservabilityStore(repo_root=repo_root).fetch_one(
        "SELECT COUNT(*) AS c FROM garmin_uploaded_files_manifest"
    )
    assert imported == {"c": 1}
