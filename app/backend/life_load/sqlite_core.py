"""Canonical SQLite storage, audit logging, sample seeding, and exports."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from life_load import fsio

DEFAULT_ROOT_REL = Path(".")
DB_FILENAME = "health.sqlite"
LEGACY_DB_FILENAME = "life_load.sqlite"
SCHEMA_VERSION = "life_load_v0.1"

DEFAULT_PROFILE_YAML = """profile_name: default
timezone: Europe/Vienna
daily_log_default_date: yesterday
"""

DEFAULT_RULES_YAML = """rules_version: life_load_v0.1
diary_extraction_mode: manual_only
export_format: csv
"""

DEFAULT_THRESHOLDS_YAML = """mood:
  min: 0
  max: 10
stress:
  min: 0
  max: 10
energy:
  min: 0
  max: 10
"""

SAMPLE_SEED = {
    "daily_log": [
        {
            "date": "2026-05-01",
            "completed": 1,
            "diary_text": "Worked hard, ate well, shut down on time.",
            "diary_summary": "steady day",
            "tags": json.dumps(["baseline", "steady"]),
            "sleep_ok": 1,
            "nutrition_ok": 1,
            "alcohol": 0,
            "binge": 0,
            "mood": 7,
            "stress": 4,
            "energy": 7,
            "foot_pain": 2,
            "shoulder_pain": 1,
            "migraine_warning": 0,
            "decompression_done": 1,
            "shutdown_done": 1,
            "phone_after_21": 0,
            "project_overrun": 0,
            "primary_activity_type": "walk",
            "activity_duration_min": 35,
            "rehab_done": 0,
            "other_symptoms": "",
            "work_intensity": "normal",
            "family_stress": 2,
            "home_office": 1,
            "homework_done": 1,
            "user_approved_at": "2026-05-01T20:00:00Z",
        },
        {
            "date": "2026-05-02",
            "completed": 1,
            "diary_text": "Poor sleep, phone too late, mild migraine signal.",
            "diary_summary": "drift day",
            "tags": json.dumps(["drift", "sleep"]),
            "sleep_ok": 0,
            "nutrition_ok": 0,
            "alcohol": 1,
            "binge": 0,
            "mood": 4,
            "stress": 7,
            "energy": 3,
            "foot_pain": 3,
            "shoulder_pain": 4,
            "migraine_warning": 1,
            "decompression_done": 0,
            "shutdown_done": 0,
            "phone_after_21": 1,
            "project_overrun": 1,
            "primary_activity_type": "run",
            "activity_duration_min": 42,
            "rehab_done": 0,
            "other_symptoms": "mild headache",
            "work_intensity": "heavy",
            "family_stress": 5,
            "home_office": 0,
            "homework_done": 0,
            "user_approved_at": "2026-05-02T20:30:00Z",
        },
    ],
    "activity_log": [
        {
            "date": "2026-05-01",
            "activity_type": "walk",
            "duration_min": 35,
            "intensity": "light",
            "hard_session": 0,
            "recovery_activity": 1,
            "notes": "decompression walk",
            "source": "fake_sample",
        },
        {
            "date": "2026-05-02",
            "activity_type": "strength",
            "duration_min": 45,
            "intensity": "moderate",
            "hard_session": 1,
            "recovery_activity": 0,
            "notes": "compressed training day",
            "source": "fake_sample",
        },
    ],
    "derived_daily_summary": [
        {
            "date": "2026-05-01",
            "life_load_score": 18.0,
            "training_load": 4.0,
            "recovery_score": 8.0,
            "strain_score": 3.0,
            "red_flags": json.dumps([]),
            "zone": "green",
            "next_action": "Keep the boring good habits.",
            "rules_version": SCHEMA_VERSION,
        },
        {
            "date": "2026-05-02",
            "life_load_score": 49.0,
            "training_load": 6.0,
            "recovery_score": 1.0,
            "strain_score": 12.0,
            "red_flags": json.dumps(["migraine_warning", "shutdown_missed"]),
            "zone": "orange",
            "next_action": "Strip the next day down and recover first.",
            "rules_version": SCHEMA_VERSION,
        },
    ],
    "derived_weekly_summary": [
        {
            "week_start": "2026-04-27",
            "week_end": "2026-05-03",
            "completed_days": 2,
            "sleep_nights": 1,
            "nutrition_clean_days": 1,
            "alcohol_home_count": 1,
            "binge_count": 0,
            "training_load": 10.0,
            "hard_sessions": 1,
            "rehab_sessions": 0,
            "homework_sessions": 1,
            "net_life_load": 67.0,
            "zone": "yellow",
            "success_score": 0.5,
            "next_action": "Watch drift signals and protect sleep.",
            "rules_version": SCHEMA_VERSION,
        }
    ],
    "review_snapshot": [
        {
            "date": "2026-05-03",
            "review_type": "weekly",
            "period_start": "2026-04-27",
            "period_end": "2026-05-03",
            "what_worked": "sleep when shutdown happened",
            "what_failed": "late phone use",
            "highest_risk_day": "2026-05-02",
            "next_adjustment": "cut evening project spillover",
            "notes": "sample review",
        }
    ],
    "intervention": [
        {
            "start_date": "2026-05-03",
            "end_date": "2026-05-05",
            "type": "sleep_protection",
            "reason": "migraine warning",
            "rule": "two low-load evenings",
            "expected_effect": "recover energy",
            "outcome": "pending",
            "review_notes": "sample seed",
        }
    ],
    "decision_log": [
        {
            "date": "2026-05-03",
            "decision": "reduce intensity for 48 hours",
            "reason": "orange trend day",
            "evidence": "sleep drift plus migraine warning",
            "review_date": "2026-05-05",
            "status": "active",
        }
    ],
    "episode": [
        {
            "start_date": "2026-05-02",
            "end_date": "2026-05-03",
            "title": "short drift episode",
            "type": "stress",
            "description": "late-night spillover and weak recovery",
            "tags": json.dumps(["drift", "sleep"]),
        }
    ],
}

MIGRATIONS: Sequence[tuple[str, Sequence[str]]] = (
    (
        "0001_canonical_core",
        (
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS daily_log (
                date TEXT PRIMARY KEY,
                completed INTEGER NOT NULL DEFAULT 0,
                diary_text TEXT NOT NULL DEFAULT '',
                diary_summary TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                sleep_ok INTEGER,
                nutrition_ok INTEGER,
                alcohol INTEGER NOT NULL DEFAULT 0,
                binge INTEGER NOT NULL DEFAULT 0,
                mood INTEGER,
                stress INTEGER,
                energy INTEGER,
                foot_pain INTEGER,
                shoulder_pain INTEGER,
                migraine_warning INTEGER NOT NULL DEFAULT 0,
                decompression_done INTEGER,
                shutdown_done INTEGER,
                phone_after_21 INTEGER,
                project_overrun INTEGER,
                work_intensity TEXT NOT NULL DEFAULT '',
                family_stress INTEGER,
                home_office INTEGER,
                homework_done INTEGER,
                user_approved_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                duration_min INTEGER NOT NULL DEFAULT 0,
                intensity TEXT NOT NULL DEFAULT '',
                hard_session INTEGER NOT NULL DEFAULT 0,
                recovery_activity INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS derived_daily_summary (
                date TEXT PRIMARY KEY,
                life_load_score REAL NOT NULL DEFAULT 0,
                training_load REAL NOT NULL DEFAULT 0,
                recovery_score REAL NOT NULL DEFAULT 0,
                strain_score REAL NOT NULL DEFAULT 0,
                red_flags TEXT NOT NULL DEFAULT '[]',
                zone TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                rules_version TEXT NOT NULL DEFAULT '',
                scoring_version TEXT NOT NULL DEFAULT '',
                formula_settings_json TEXT NOT NULL DEFAULT '{}',
                formula_settings_hash TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS derived_weekly_summary (
                week_start TEXT PRIMARY KEY,
                week_end TEXT NOT NULL,
                completed_days INTEGER NOT NULL DEFAULT 0,
                sleep_nights INTEGER NOT NULL DEFAULT 0,
                nutrition_clean_days INTEGER NOT NULL DEFAULT 0,
                alcohol_home_count INTEGER NOT NULL DEFAULT 0,
                binge_count INTEGER NOT NULL DEFAULT 0,
                training_load REAL NOT NULL DEFAULT 0,
                hard_sessions INTEGER NOT NULL DEFAULT 0,
                rehab_sessions INTEGER NOT NULL DEFAULT 0,
                homework_sessions INTEGER NOT NULL DEFAULT 0,
                net_life_load REAL NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT '',
                success_score REAL NOT NULL DEFAULT 0,
                next_action TEXT NOT NULL DEFAULT '',
                rules_version TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                review_type TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                what_worked TEXT NOT NULL DEFAULT '',
                what_failed TEXT NOT NULL DEFAULT '',
                highest_risk_day TEXT NOT NULL DEFAULT '',
                next_adjustment TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS intervention (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL,
                end_date TEXT,
                type TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                rule TEXT NOT NULL DEFAULT '',
                expected_effect TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                review_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '',
                review_date TEXT,
                status TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS episode (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL,
                end_date TEXT,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "0002_daily_log_drafts",
        (
            """
            CREATE TABLE IF NOT EXISTS daily_log_draft (
                date TEXT PRIMARY KEY,
                draft_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "0003_ai_proposals_and_trends",
        (
            """
            CREATE TABLE IF NOT EXISTS ai_proposal (
                proposal_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                diary_text_hash TEXT NOT NULL DEFAULT '',
                extractor_version TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                accepted_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS derived_trend_feature (
                date TEXT PRIMARY KEY,
                features_json TEXT NOT NULL DEFAULT '{}',
                rules_version TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS drift_detection_snapshot (
                date TEXT PRIMARY KEY,
                risk_level TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                contributing_signals TEXT NOT NULL DEFAULT '[]',
                next_action TEXT NOT NULL DEFAULT '',
                evidence_note TEXT NOT NULL DEFAULT '',
                rules_version TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "0004_daily_log_extended_fields",
        (
            "ALTER TABLE daily_log ADD COLUMN primary_activity_type TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN activity_duration_min INTEGER",
            "ALTER TABLE daily_log ADD COLUMN rehab_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN other_symptoms TEXT NOT NULL DEFAULT ''",
        ),
    ),
    (
        "0005_garmin_passive_import",
        (
            """
            CREATE TABLE IF NOT EXISTS garmin_import_batch (
                source_sha256 TEXT PRIMARY KEY,
                source_path TEXT NOT NULL DEFAULT '',
                imported_at TEXT NOT NULL,
                row_counts_json TEXT NOT NULL DEFAULT '{}',
                date_min TEXT NOT NULL DEFAULT '',
                date_max TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_activity (
                activity_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                start_time_local_iso TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                activity_type TEXT NOT NULL DEFAULT '',
                sport_type TEXT NOT NULL DEFAULT '',
                duration_min REAL,
                moving_duration_min REAL,
                distance_km REAL,
                time_on_feet_min_est REAL,
                impact_load_est REAL,
                hard_session_est INTEGER NOT NULL DEFAULT 0,
                calories REAL,
                avg_hr REAL,
                max_hr REAL,
                aerobic_training_effect REAL,
                anaerobic_training_effect REAL,
                source_file TEXT NOT NULL DEFAULT '',
                quality_flag TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_sleep_session (
                date TEXT NOT NULL,
                sleep_start_gmt TEXT NOT NULL DEFAULT '',
                sleep_end_gmt TEXT NOT NULL DEFAULT '',
                total_sleep_min REAL,
                time_in_bed_min REAL,
                deep_sleep_min REAL,
                light_sleep_min REAL,
                rem_sleep_min REAL,
                awake_min REAL,
                confirmation_type TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                quality_flag TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(date, sleep_start_gmt, source_file)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_daily_wellness (
                date TEXT PRIMARY KEY,
                steps INTEGER,
                step_goal INTEGER,
                total_distance_km REAL,
                total_kcal REAL,
                active_kcal REAL,
                moderate_intensity_min INTEGER,
                vigorous_intensity_min INTEGER,
                active_min REAL,
                resting_hr REAL,
                avg_stress REAL,
                max_stress REAL,
                hydration_ml REAL,
                source_file TEXT NOT NULL DEFAULT '',
                quality_flag TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_training_history (
                date TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT '',
                sport TEXT NOT NULL DEFAULT '',
                sub_sport TEXT NOT NULL DEFAULT '',
                weekly_training_load_sum REAL,
                load_tunnel_min REAL,
                load_tunnel_max REAL,
                training_status TEXT NOT NULL DEFAULT '',
                fitness_level_trend TEXT NOT NULL DEFAULT '',
                load_level_trend TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                quality_flag TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(date, timestamp, sport, sub_sport)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_acute_training_load (
                date TEXT NOT NULL,
                timestamp_iso TEXT NOT NULL DEFAULT '',
                acwr_percent REAL,
                acwr_status TEXT NOT NULL DEFAULT '',
                daily_training_load_acute REAL,
                daily_training_load_chronic REAL,
                daily_acwr REAL,
                source_file TEXT NOT NULL DEFAULT '',
                quality_flag TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(date, timestamp_iso)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_body_measurement (
                date TEXT NOT NULL DEFAULT '',
                weight_kg_est_from_bmi REAL,
                body_fat_pct REAL,
                bmi REAL,
                rhr REAL,
                chronological_age REAL,
                current_fitness_age REAL,
                weight_data_last_entry_date TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                quality_flag TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(date, source_file, quality_flag)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_daily_passive_summary (
                date TEXT PRIMARY KEY,
                has_garmin_data INTEGER NOT NULL DEFAULT 1,
                wellness_steps INTEGER,
                wellness_resting_hr REAL,
                wellness_avg_stress REAL,
                wellness_active_kcal REAL,
                activity_count INTEGER,
                activity_total_duration_min REAL,
                activity_total_distance_km REAL,
                activity_total_time_on_feet_min_est REAL,
                activity_hard_session_count_est INTEGER,
                sleep_total_sleep_min REAL,
                sleep_time_in_bed_min REAL,
                sleep_start_gmt TEXT NOT NULL DEFAULT '',
                sleep_end_gmt TEXT NOT NULL DEFAULT '',
                body_weight_kg_est_from_bmi REAL,
                body_bmi REAL,
                source_sha256 TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_source_manifest (
                source_sha256 TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER,
                compressed_size_bytes INTEGER,
                modified TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(source_sha256, path)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS garmin_uploaded_files_manifest (
                source_sha256 TEXT NOT NULL,
                outer_zip TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER,
                kind TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(source_sha256, outer_zip, path)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_garmin_activity_date ON garmin_activity(date)",
            "CREATE INDEX IF NOT EXISTS idx_garmin_sleep_date ON garmin_sleep_session(date)",
            "CREATE INDEX IF NOT EXISTS idx_garmin_training_date ON garmin_training_history(date)",
            "CREATE INDEX IF NOT EXISTS idx_garmin_acute_load_date ON garmin_acute_training_load(date)",
        ),
    ),
    (
        "0006_garmin_raw_sleep_rows",
        (
            """
            CREATE TABLE IF NOT EXISTS garmin_sleep_session_raw (
                source_sha256 TEXT NOT NULL,
                source_row_index INTEGER NOT NULL,
                date TEXT NOT NULL,
                sleep_start_gmt TEXT NOT NULL DEFAULT '',
                sleep_end_gmt TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(source_sha256, source_row_index)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_garmin_sleep_raw_date ON garmin_sleep_session_raw(date)",
        ),
    ),
    (
        "0007_daily_log_evening_conflict_fields",
        (
            "ALTER TABLE daily_log ADD COLUMN after_work_decompression_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN evening_chain_broken INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_count INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_school INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_chores INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_other INTEGER",
        ),
    ),
    (
        "0008_daily_log_alone_home_field",
        (
            "ALTER TABLE daily_log ADD COLUMN alone_home INTEGER",
        ),
    ),
    (
        "0009_garmin_live_import_audit",
        (
            """
            CREATE TABLE IF NOT EXISTS garmin_live_import_batch (
                batch_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT '',
                requested_start_date TEXT NOT NULL DEFAULT '',
                requested_end_date TEXT NOT NULL DEFAULT '',
                stale_dates_json TEXT NOT NULL DEFAULT '[]',
                days_requested INTEGER NOT NULL DEFAULT 0,
                days_imported INTEGER NOT NULL DEFAULT 0,
                passive_created INTEGER NOT NULL DEFAULT 0,
                passive_updated INTEGER NOT NULL DEFAULT 0,
                passive_unchanged INTEGER NOT NULL DEFAULT 0,
                activity_created INTEGER NOT NULL DEFAULT 0,
                activity_updated INTEGER NOT NULL DEFAULT 0,
                activity_unchanged INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                skipped_reason TEXT NOT NULL DEFAULT '',
                ok INTEGER NOT NULL DEFAULT 1,
                error TEXT NOT NULL DEFAULT '',
                source_hashes_json TEXT NOT NULL DEFAULT '[]',
                endpoint_status_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}'
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_garmin_live_import_completed ON garmin_live_import_batch(completed_at)",
            "CREATE INDEX IF NOT EXISTS idx_garmin_live_import_requested ON garmin_live_import_batch(requested_start_date, requested_end_date)",
        ),
    ),
    (
        "0010_daily_log_coffee_cups",
        (
            "ALTER TABLE daily_log ADD COLUMN coffee_cups INTEGER",
        ),
    ),
    (
        "0011_derived_daily_formula_version",
        (
            "ALTER TABLE derived_daily_summary ADD COLUMN scoring_version TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE derived_daily_summary ADD COLUMN formula_settings_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE derived_daily_summary ADD COLUMN formula_settings_hash TEXT NOT NULL DEFAULT ''",
        ),
    ),
    (
        "0012_daily_log_activity_types",
        (
            "ALTER TABLE daily_log ADD COLUMN activity_types TEXT NOT NULL DEFAULT '[]'",
        ),
    ),
    (
        "0013_legacy_daily_log_compatibility",
        (
            "ALTER TABLE daily_log ADD COLUMN completed INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE daily_log ADD COLUMN diary_text TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN diary_summary TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE daily_log ADD COLUMN sleep_ok INTEGER",
            "ALTER TABLE daily_log ADD COLUMN nutrition_ok INTEGER",
            "ALTER TABLE daily_log ADD COLUMN alcohol INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE daily_log ADD COLUMN binge INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE daily_log ADD COLUMN mood INTEGER",
            "ALTER TABLE daily_log ADD COLUMN stress INTEGER",
            "ALTER TABLE daily_log ADD COLUMN energy INTEGER",
            "ALTER TABLE daily_log ADD COLUMN coffee_cups INTEGER",
            "ALTER TABLE daily_log ADD COLUMN foot_pain INTEGER",
            "ALTER TABLE daily_log ADD COLUMN shoulder_pain INTEGER",
            "ALTER TABLE daily_log ADD COLUMN migraine_warning INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE daily_log ADD COLUMN decompression_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN shutdown_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN phone_after_21 INTEGER",
            "ALTER TABLE daily_log ADD COLUMN project_overrun INTEGER",
            "ALTER TABLE daily_log ADD COLUMN primary_activity_type TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN activity_duration_min INTEGER",
            "ALTER TABLE daily_log ADD COLUMN rehab_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN other_symptoms TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN work_intensity TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN family_stress INTEGER",
            "ALTER TABLE daily_log ADD COLUMN home_office INTEGER",
            "ALTER TABLE daily_log ADD COLUMN alone_home INTEGER",
            "ALTER TABLE daily_log ADD COLUMN homework_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN after_work_decompression_done INTEGER",
            "ALTER TABLE daily_log ADD COLUMN evening_chain_broken INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_count INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_school INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_chores INTEGER",
            "ALTER TABLE daily_log ADD COLUMN wife_conflict_other INTEGER",
            "ALTER TABLE daily_log ADD COLUMN user_approved_at TEXT",
            "ALTER TABLE daily_log ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE daily_log ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
        ),
    ),
)


def utc_now_iso() -> str:
    return fsio.utc_now_iso()


def _dump_json(value: Any, default: Any) -> str:
    payload = default if value is None else value
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith(("[", "{")):
            try:
                parsed = json.loads(text)
            except Exception:
                pass
            else:
                payload = parsed
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass
class HealthObservabilityStore:
    repo_root: Path
    root_rel: Path = DEFAULT_ROOT_REL
    db_path_override: Path | None = None
    _layout_ready: bool = field(default=False, init=False, repr=False)
    _migrations_checked: bool = field(default=False, init=False, repr=False)

    @property
    def root(self) -> Path:
        return (self.repo_root / self.root_rel).resolve()

    @property
    def config_root(self) -> Path:
        return self.repo_root / "runtime" / "config" / "life_load"

    @property
    def db_root(self) -> Path:
        return self.repo_root / "data"

    @property
    def generated_root(self) -> Path:
        return self.repo_root / "runtime" / "generated" / "life_load"

    @property
    def audit_root(self) -> Path:
        return self.repo_root / "runtime" / "audit" / "life_load"

    @property
    def samples_root(self) -> Path:
        return self.repo_root / "runtime" / "samples" / "life_load" / "fake_sample_data"

    @property
    def db_path(self) -> Path:
        if self.db_path_override is not None:
            return Path(self.db_path_override).expanduser().resolve()
        override = str(os.environ.get("LIFE_LOAD_DB_PATH") or "").strip()
        if override:
            return Path(override).expanduser().resolve()
        return self.db_root / DB_FILENAME

    @property
    def audit_path(self) -> Path:
        return self.audit_root / "events.jsonl"

    @property
    def sample_seed_path(self) -> Path:
        return self.samples_root / "sample_seed.json"

    def ensure_layout(self) -> None:
        if self._layout_ready:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.config_root,
            self.db_root,
            self.generated_root / "dashboards",
            self.generated_root / "charts",
            self.generated_root / "exports",
            self.generated_root / "reports",
            self.audit_root,
            self.samples_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self._remove_copied_legacy_file_if_matching(
            self.generated_root / "validation" / "health_observability_intent_validation.json",
            ("health_observability_intent_validation",),
        )
        self._remove_copied_legacy_file_if_matching(
            self.generated_root / "reports" / "health_observability_family_closeout.md",
            ("Health Observability Family Closeout",),
        )
        self._write_default_text(self.config_root / "profile.yaml", DEFAULT_PROFILE_YAML)
        self._write_or_migrate_rules(self.config_root / "rules.yaml")
        self._write_default_text(self.config_root / "thresholds.yaml", DEFAULT_THRESHOLDS_YAML)
        self._write_default_text(self.generated_root / "dashboards" / ".gitkeep", "")
        self._write_default_text(self.generated_root / "charts" / ".gitkeep", "")
        self._write_default_text(self.generated_root / "exports" / ".gitkeep", "")
        self._write_default_text(self.generated_root / "reports" / ".gitkeep", "")
        self._write_default_text(self.db_root / ".gitkeep", "")
        self._write_default_text(self.audit_root / ".gitkeep", "")
        self._write_or_migrate_sample_seed()
        self._migrate_legacy_db_filename_if_needed()
        self._layout_ready = True

    def _migrate_legacy_db_filename_if_needed(self) -> None:
        if self.root_rel != DEFAULT_ROOT_REL:
            return
        current_db = self.db_path
        legacy_db = self.db_root / LEGACY_DB_FILENAME
        if current_db == legacy_db:
            return
        with fsio.file_lock(current_db):
            current_exists = current_db.exists()
            legacy_exists = legacy_db.exists()
            if current_exists and not legacy_exists:
                return
            if current_exists and legacy_exists:
                current_ok = self._database_integrity_ok(current_db)
                legacy_ok = self._database_integrity_ok(legacy_db)
                if current_ok:
                    # Both names are retained when the canonical database is
                    # already usable. Deleting the legacy source can destroy
                    # the only recoverable copy after an interrupted startup.
                    self.append_audit_event(
                        "legacy_db_retained_canonical_exists",
                        {"canonical": str(current_db), "legacy": str(legacy_db), "canonical_integrity": "ok", "legacy_integrity": legacy_ok},
                    )
                    return
                if not legacy_ok:
                    self.append_audit_event(
                        "legacy_db_migration_blocked_both_invalid",
                        {"canonical": str(current_db), "legacy": str(legacy_db)},
                    )
                    raise RuntimeError(f"Cannot migrate Life Load database: both {current_db} and {legacy_db} failed integrity checks")
                recovery = current_db.with_name(f"{current_db.name}.corrupt.{uuid.uuid4().hex}")
                os.replace(current_db, recovery)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(f"{current_db}{suffix}")
                    if sidecar.exists():
                        os.replace(sidecar, Path(f"{recovery}{suffix}"))
                self.append_audit_event(
                    "canonical_db_quarantined_before_legacy_migration",
                    {"canonical": str(current_db), "recovery": str(recovery), "legacy": str(legacy_db)},
                )
            elif not legacy_exists:
                return

            current_db.parent.mkdir(parents=True, exist_ok=True)
            temp_db = current_db.with_name(f".{current_db.name}.migration.{os.getpid()}.{uuid.uuid4().hex}.tmp")
            source = target = None
            try:
                # sqlite backup is WAL-aware and copies the committed view;
                # copying the main file directly can omit committed WAL rows.
                source = sqlite3.connect(str(legacy_db))
                target = sqlite3.connect(str(temp_db))
                source.backup(target)
                target.commit()
                target.close()
                target = None
                source.close()
                source = None
                if not self._database_integrity_ok(temp_db):
                    raise RuntimeError(f"migrated database failed integrity check: {temp_db}")
                with temp_db.open("rb") as fh:
                    os.fsync(fh.fileno())
                os.replace(temp_db, current_db)
                self.append_audit_event(
                    "legacy_db_migrated",
                    {"legacy": str(legacy_db), "canonical": str(current_db), "source_retained": True},
                )
            except Exception as exc:
                if target is not None:
                    target.close()
                if source is not None:
                    source.close()
                try:
                    temp_db.unlink()
                except FileNotFoundError:
                    pass
                self.append_audit_event(
                    "legacy_db_migration_failed",
                    {"legacy": str(legacy_db), "canonical": str(current_db), "source_retained": True, "error": str(exc)},
                )
                raise RuntimeError(f"Life Load database migration failed; legacy source retained: {legacy_db}") from exc

    @staticmethod
    def _database_integrity_ok(path: Path) -> bool:
        if not path.exists() or path.stat().st_size == 0:
            return False
        try:
            with sqlite3.connect(str(path)) as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok")
        except (OSError, sqlite3.DatabaseError):
            return False

    def _write_default_text(self, path: Path, content: str) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_or_migrate_readme(self, path: Path) -> None:
        if not path.exists():
            self._write_default_text(path, self._readme_text())
            return
        text = path.read_text(encoding="utf-8")
        if "Health Observability" in text or "db/health.sqlite" in text:
            path.write_text(self._readme_text(), encoding="utf-8")

    def _write_or_merge_gitignore(self, path: Path) -> None:
        desired_lines = [line for line in self._gitignore_text().splitlines() if line.strip()]
        if not path.exists():
            self._write_default_text(path, self._gitignore_text())
            return
        existing_lines = path.read_text(encoding="utf-8").splitlines()
        existing = {line.strip() for line in existing_lines if line.strip()}
        missing = [line for line in desired_lines if line.strip() not in existing]
        if not missing:
            return
        merged = existing_lines[:]
        if merged and merged[-1].strip():
            merged.append("")
        merged.extend(missing)
        path.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")

    def _remove_copied_legacy_file_if_matching(self, path: Path, markers: Iterable[str]) -> None:
        if not path.exists() or not path.is_file():
            return
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in markers):
            path.unlink()

    def _write_or_migrate_rules(self, path: Path) -> None:
        if not path.exists():
            self._write_default_text(path, DEFAULT_RULES_YAML)
            return
        text = path.read_text(encoding="utf-8")
        if "health_observability_v0.1" in text:
            path.write_text(text.replace("health_observability_v0.1", SCHEMA_VERSION), encoding="utf-8")

    def _write_or_migrate_sample_seed(self) -> None:
        if not self.sample_seed_path.exists():
            fsio.write_json_atomic(self.sample_seed_path, SAMPLE_SEED)
            return
        text = self.sample_seed_path.read_text(encoding="utf-8")
        if "health_observability_v0.1" in text:
            fsio.write_json_atomic(self.sample_seed_path, SAMPLE_SEED)

    def _export_script_text(self) -> str:
        return (
            "from __future__ import annotations\n\n"
            "import sys\n\n"
            "from life_load.sqlite_core import main\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    raise SystemExit(main(sys.argv[1:]))\n"
        )

    def _readme_text(self) -> str:
        return (
            "# Life Load\n\n"
            "SQLite in `db/life_load.sqlite` is canonical truth.\n"
            "`generated/` holds reproducible read models only.\n"
            "`audit/events.jsonl` is append-only audit evidence.\n"
            "Runtime data is intentionally separate from backend package code.\n"
        )

    def _gitignore_text(self) -> str:
        return (
            "db/life_load.sqlite\n"
            "db/health.sqlite\n"
            "db/*.sqlite-shm\n"
            "db/*.sqlite-wal\n"
            "audit/events.jsonl\n"
            "generated/dashboards/*\n"
            "!generated/dashboards/.gitkeep\n"
            "generated/charts/*\n"
            "!generated/charts/.gitkeep\n"
            "generated/exports/*\n"
            "!generated/exports/.gitkeep\n"
            "generated/reports/*\n"
            "!generated/reports/.gitkeep\n"
        )

    def connect(self) -> sqlite3.Connection:
        self.ensure_layout()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> List[str]:
        if self._migrations_checked:
            return []
        self.ensure_layout()
        applied: List[str] = []
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            existing = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
            for version, statements in MIGRATIONS:
                if version in existing:
                    continue
                with conn:
                    for statement in statements:
                        self._execute_migration_statement(conn, statement)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, utc_now_iso()),
                    )
                applied.append(version)
        if applied:
            self.append_audit_event("schema_migrated", {"versions": applied})
        self._migrations_checked = True
        return applied

    def _execute_migration_statement(self, conn: sqlite3.Connection, statement: str) -> None:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "duplicate column name" in message:
                return
            if "already exists" in message and statement.strip().upper().startswith("CREATE INDEX"):
                return
            raise

    def append_audit_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        record = {
            "schema_version": SCHEMA_VERSION,
            "event_type": event_type,
            "utc": utc_now_iso(),
            "payload": dict(payload),
        }
        with fsio.file_lock(self.audit_path):
            fsio.append_jsonl(self.audit_path, record)

    def upsert_daily_log(self, row: Mapping[str, Any]) -> None:
        self.migrate()
        date_value = str(row["date"])
        now = utc_now_iso()
        existing = self.fetch_one("SELECT created_at FROM daily_log WHERE date = ?", (date_value,))
        created_at = str(existing["created_at"]) if existing else now
        payload = (
            date_value,
            int(bool(row.get("completed", 0))),
            str(row.get("diary_text", "")),
            str(row.get("diary_summary", "")),
            _dump_json(row.get("tags", []), []),
            row.get("sleep_ok"),
            row.get("nutrition_ok"),
            int(row.get("alcohol", 0) or 0),
            int(bool(row.get("binge", 0))),
            row.get("mood"),
            row.get("stress"),
            row.get("energy"),
            row.get("coffee_cups"),
            row.get("foot_pain"),
            row.get("shoulder_pain"),
            int(bool(row.get("migraine_warning", 0))),
            row.get("decompression_done"),
            row.get("shutdown_done"),
            row.get("phone_after_21"),
            row.get("project_overrun"),
            str(row.get("primary_activity_type", "")),
            _dump_json(row.get("activity_types", []), []),
            row.get("activity_duration_min"),
            row.get("rehab_done"),
            str(row.get("other_symptoms", "")),
            str(row.get("work_intensity", "")),
            row.get("family_stress"),
            row.get("home_office"),
            row.get("alone_home"),
            row.get("homework_done"),
            row.get("after_work_decompression_done"),
            row.get("evening_chain_broken"),
            row.get("wife_conflict_count"),
            row.get("wife_conflict_school"),
            row.get("wife_conflict_chores"),
            row.get("wife_conflict_other"),
            row.get("user_approved_at"),
            created_at,
            now,
        )
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO daily_log(
                    date, completed, diary_text, diary_summary, tags, sleep_ok, nutrition_ok, alcohol, binge,
                    mood, stress, energy, coffee_cups, foot_pain, shoulder_pain, migraine_warning, decompression_done,
                    shutdown_done, phone_after_21, project_overrun, primary_activity_type, activity_types, activity_duration_min,
                    rehab_done, other_symptoms, work_intensity, family_stress, home_office, alone_home, homework_done,
                    after_work_decompression_done, evening_chain_broken, wife_conflict_count,
                    wife_conflict_school, wife_conflict_chores, wife_conflict_other,
                    user_approved_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    completed=excluded.completed,
                    diary_text=excluded.diary_text,
                    diary_summary=excluded.diary_summary,
                    tags=excluded.tags,
                    sleep_ok=excluded.sleep_ok,
                    nutrition_ok=excluded.nutrition_ok,
                    alcohol=excluded.alcohol,
                    binge=excluded.binge,
                    mood=excluded.mood,
                    stress=excluded.stress,
                    energy=excluded.energy,
                    coffee_cups=excluded.coffee_cups,
                    foot_pain=excluded.foot_pain,
                    shoulder_pain=excluded.shoulder_pain,
                    migraine_warning=excluded.migraine_warning,
                    decompression_done=excluded.decompression_done,
                    shutdown_done=excluded.shutdown_done,
                    phone_after_21=excluded.phone_after_21,
                    project_overrun=excluded.project_overrun,
                    primary_activity_type=excluded.primary_activity_type,
                    activity_types=excluded.activity_types,
                    activity_duration_min=excluded.activity_duration_min,
                    rehab_done=excluded.rehab_done,
                    other_symptoms=excluded.other_symptoms,
                    work_intensity=excluded.work_intensity,
                    family_stress=excluded.family_stress,
                    home_office=excluded.home_office,
                    alone_home=excluded.alone_home,
                    homework_done=excluded.homework_done,
                    after_work_decompression_done=excluded.after_work_decompression_done,
                    evening_chain_broken=excluded.evening_chain_broken,
                    wife_conflict_count=excluded.wife_conflict_count,
                    wife_conflict_school=excluded.wife_conflict_school,
                    wife_conflict_chores=excluded.wife_conflict_chores,
                    wife_conflict_other=excluded.wife_conflict_other,
                    user_approved_at=excluded.user_approved_at,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
        self.append_audit_event(
            "daily_log_upserted",
            {"date": date_value, "completed": int(bool(row.get("completed", 0))), "source": "explicit_write"},
        )

    def approve_daily_log_with_derived(
        self,
        row: Mapping[str, Any],
        *,
        daily_summary: Mapping[str, Any],
        weekly_summary: Mapping[str, Any],
    ) -> None:
        """Commit canonical approval, draft deletion, and derived rows together."""
        self.migrate()
        date_value = str(row["date"])
        now = utc_now_iso()
        with self.connect() as conn, conn:
            existing = conn.execute("SELECT created_at FROM daily_log WHERE date = ?", (date_value,)).fetchone()
            created_at = str(existing["created_at"]) if existing else now
            canonical = {
                "date": date_value,
                "completed": int(bool(row.get("completed", 0))),
                "diary_text": str(row.get("diary_text", "")),
                "diary_summary": str(row.get("diary_summary", "")),
                "tags": _dump_json(row.get("tags", []), []),
                "sleep_ok": row.get("sleep_ok"),
                "nutrition_ok": row.get("nutrition_ok"),
                "alcohol": int(row.get("alcohol", 0) or 0),
                "binge": int(bool(row.get("binge", 0))),
                "mood": row.get("mood"),
                "stress": row.get("stress"),
                "energy": row.get("energy"),
                "coffee_cups": row.get("coffee_cups"),
                "foot_pain": row.get("foot_pain"),
                "shoulder_pain": row.get("shoulder_pain"),
                "migraine_warning": int(bool(row.get("migraine_warning", 0))),
                "decompression_done": row.get("decompression_done"),
                "shutdown_done": row.get("shutdown_done"),
                "phone_after_21": row.get("phone_after_21"),
                "project_overrun": row.get("project_overrun"),
                "primary_activity_type": str(row.get("primary_activity_type", "")),
                "activity_types": _dump_json(row.get("activity_types", []), []),
                "activity_duration_min": row.get("activity_duration_min"),
                "rehab_done": row.get("rehab_done"),
                "other_symptoms": str(row.get("other_symptoms", "")),
                "work_intensity": str(row.get("work_intensity", "")),
                "family_stress": row.get("family_stress"),
                "home_office": row.get("home_office"),
                "alone_home": row.get("alone_home"),
                "homework_done": row.get("homework_done"),
                "after_work_decompression_done": row.get("after_work_decompression_done"),
                "evening_chain_broken": row.get("evening_chain_broken"),
                "wife_conflict_count": row.get("wife_conflict_count"),
                "wife_conflict_school": row.get("wife_conflict_school"),
                "wife_conflict_chores": row.get("wife_conflict_chores"),
                "wife_conflict_other": row.get("wife_conflict_other"),
                "user_approved_at": row.get("user_approved_at"),
                "created_at": created_at,
                "updated_at": now,
            }
            self._upsert_mapping_conn(conn, "daily_log", ("date",), canonical)
            conn.execute("DELETE FROM daily_log_draft WHERE date = ?", (date_value,))
            self._upsert_mapping_conn(
                conn,
                "derived_daily_summary",
                ("date",),
                {
                    "date": daily_summary["date"],
                    "life_load_score": daily_summary.get("life_load_score", 0.0),
                    "training_load": daily_summary.get("training_load", 0.0),
                    "recovery_score": daily_summary.get("recovery_score", 0.0),
                    "strain_score": daily_summary.get("strain_score", 0.0),
                    "red_flags": _dump_json(daily_summary.get("red_flags", []), []),
                    "zone": daily_summary.get("zone", ""),
                    "next_action": daily_summary.get("next_action", ""),
                    "rules_version": daily_summary.get("rules_version", SCHEMA_VERSION),
                    "scoring_version": daily_summary.get("scoring_version", ""),
                    "formula_settings_json": _dump_json(daily_summary.get("formula_settings_json", {}), {}),
                    "formula_settings_hash": daily_summary.get("formula_settings_hash", ""),
                    "calculated_at": now,
                },
            )
            self._upsert_mapping_conn(
                conn,
                "derived_weekly_summary",
                ("week_start",),
                {
                    "week_start": weekly_summary["week_start"],
                    "week_end": weekly_summary["week_end"],
                    "completed_days": weekly_summary.get("completed_days", 0),
                    "sleep_nights": weekly_summary.get("sleep_nights", 0),
                    "nutrition_clean_days": weekly_summary.get("nutrition_clean_days", 0),
                    "alcohol_home_count": weekly_summary.get("alcohol_home_count", 0),
                    "binge_count": weekly_summary.get("binge_count", 0),
                    "training_load": weekly_summary.get("training_load", 0.0),
                    "hard_sessions": weekly_summary.get("hard_sessions", 0),
                    "rehab_sessions": weekly_summary.get("rehab_sessions", 0),
                    "homework_sessions": weekly_summary.get("homework_sessions", 0),
                    "net_life_load": weekly_summary.get("net_life_load", 0.0),
                    "zone": weekly_summary.get("zone", ""),
                    "success_score": weekly_summary.get("success_score", 0.0),
                    "next_action": weekly_summary.get("next_action", ""),
                    "rules_version": weekly_summary.get("rules_version", SCHEMA_VERSION),
                    "calculated_at": now,
                },
            )
        self.append_audit_event("daily_log_approved_atomically", {"date": date_value})

    @staticmethod
    def _upsert_mapping_conn(
        conn: sqlite3.Connection,
        table: str,
        key_columns: Sequence[str],
        row: Mapping[str, Any],
    ) -> None:
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in key_columns)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(key_columns)}) DO UPDATE SET {updates}"
        )
        conn.execute(sql, tuple(row[column] for column in columns))

    def upsert_daily_log_draft(self, *, date: str, draft_payload: Mapping[str, Any]) -> None:
        self.migrate()
        now = utc_now_iso()
        existing = self.fetch_one("SELECT created_at FROM daily_log_draft WHERE date = ?", (date,))
        created_at = str(existing["created_at"]) if existing else now
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO daily_log_draft(date, draft_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    draft_payload=excluded.draft_payload,
                    updated_at=excluded.updated_at
                """,
                (date, _dump_json(draft_payload, {}), created_at, now),
            )
        self.append_audit_event("daily_log_draft_upserted", {"date": date})

    def fetch_daily_log_draft(self, date: str) -> Dict[str, Any] | None:
        row = self.fetch_one("SELECT date, draft_payload, created_at, updated_at FROM daily_log_draft WHERE date = ?", (date,))
        if not row:
            return None
        payload = row.get("draft_payload")
        parsed: Dict[str, Any] = {}
        if isinstance(payload, str) and payload.strip():
            try:
                loaded = json.loads(payload)
            except Exception:
                loaded = {}
            if isinstance(loaded, dict):
                parsed = loaded
        return {
            "date": str(row.get("date") or date),
            "draft_payload": parsed,
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def delete_daily_log_draft(self, date: str) -> bool:
        self.migrate()
        with self.connect() as conn, conn:
            cursor = conn.execute("DELETE FROM daily_log_draft WHERE date = ?", (date,))
            changed = int(cursor.rowcount or 0) > 0
        if changed:
            self.append_audit_event("daily_log_draft_deleted", {"date": date})
        return changed

    def list_daily_log_drafts(self, *, limit: int = 90) -> List[Dict[str, Any]]:
        capped = max(1, min(int(limit), 366))
        rows = self.fetch_all(
            "SELECT date, draft_payload, created_at, updated_at FROM daily_log_draft ORDER BY date DESC LIMIT ?",
            (capped,),
        )
        drafts: List[Dict[str, Any]] = []
        for row in rows:
            payload = row.get("draft_payload")
            parsed: Dict[str, Any] = {}
            if isinstance(payload, str) and payload.strip():
                try:
                    loaded = json.loads(payload)
                except Exception:
                    loaded = {}
                if isinstance(loaded, dict):
                    parsed = loaded
            drafts.append(
                {
                    "date": str(row.get("date") or ""),
                    "draft_payload": parsed,
                    "created_at": str(row.get("created_at") or ""),
                    "updated_at": str(row.get("updated_at") or ""),
                }
            )
        return drafts

    def insert_activity(self, row: Mapping[str, Any]) -> None:
        self.migrate()
        payload = (
            str(row["date"]),
            str(row["activity_type"]),
            int(row.get("duration_min", 0) or 0),
            str(row.get("intensity", "")),
            int(bool(row.get("hard_session", 0))),
            int(bool(row.get("recovery_activity", 0))),
            str(row.get("notes", "")),
            str(row.get("source", "")),
            utc_now_iso(),
        )
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO activity_log(
                    date, activity_type, duration_min, intensity, hard_session,
                    recovery_activity, notes, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
        self.append_audit_event(
            "activity_logged",
            {"date": row["date"], "activity_type": row["activity_type"], "source": row.get("source", "")},
        )

    def upsert_derived_daily_summary(self, row: Mapping[str, Any]) -> None:
        self._upsert_generic(
            table="derived_daily_summary",
            key_columns=("date",),
            row={
                "date": row["date"],
                "life_load_score": row.get("life_load_score", 0.0),
                "training_load": row.get("training_load", 0.0),
                "recovery_score": row.get("recovery_score", 0.0),
                "strain_score": row.get("strain_score", 0.0),
                "red_flags": _dump_json(row.get("red_flags", []), []),
                "zone": row.get("zone", ""),
                "next_action": row.get("next_action", ""),
                "rules_version": row.get("rules_version", SCHEMA_VERSION),
                "scoring_version": row.get("scoring_version", ""),
                "formula_settings_json": _dump_json(row.get("formula_settings_json", {}), {}),
                "formula_settings_hash": row.get("formula_settings_hash", ""),
                "calculated_at": utc_now_iso(),
            },
        )

    def upsert_derived_weekly_summary(self, row: Mapping[str, Any]) -> None:
        self._upsert_generic(
            table="derived_weekly_summary",
            key_columns=("week_start",),
            row={
                "week_start": row["week_start"],
                "week_end": row["week_end"],
                "completed_days": row.get("completed_days", 0),
                "sleep_nights": row.get("sleep_nights", 0),
                "nutrition_clean_days": row.get("nutrition_clean_days", 0),
                "alcohol_home_count": row.get("alcohol_home_count", 0),
                "binge_count": row.get("binge_count", 0),
                "training_load": row.get("training_load", 0.0),
                "hard_sessions": row.get("hard_sessions", 0),
                "rehab_sessions": row.get("rehab_sessions", 0),
                "homework_sessions": row.get("homework_sessions", 0),
                "net_life_load": row.get("net_life_load", 0.0),
                "zone": row.get("zone", ""),
                "success_score": row.get("success_score", 0.0),
                "next_action": row.get("next_action", ""),
                "rules_version": row.get("rules_version", SCHEMA_VERSION),
                "calculated_at": utc_now_iso(),
            },
        )

    def insert_review_snapshot(self, row: Mapping[str, Any]) -> None:
        self._insert_generic(
            "review_snapshot",
            {
                "date": row["date"],
                "review_type": row["review_type"],
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "what_worked": row.get("what_worked", ""),
                "what_failed": row.get("what_failed", ""),
                "highest_risk_day": row.get("highest_risk_day", ""),
                "next_adjustment": row.get("next_adjustment", ""),
                "notes": row.get("notes", ""),
                "created_at": utc_now_iso(),
            },
        )

    def upsert_ai_proposal(self, row: Mapping[str, Any]) -> None:
        self._upsert_generic(
            table="ai_proposal",
            key_columns=("proposal_id",),
            row={
                "proposal_id": row["proposal_id"],
                "date": row["date"],
                "diary_text_hash": row.get("diary_text_hash", ""),
                "extractor_version": row.get("extractor_version", ""),
                "raw_json": _dump_json(row.get("raw_json", {}), {}),
                "created_at": row.get("created_at", utc_now_iso()),
                "accepted_at": row.get("accepted_at"),
                "status": row.get("status", "pending"),
                "error": row.get("error", ""),
            },
        )

    def fetch_ai_proposal(self, proposal_id: str) -> Dict[str, Any] | None:
        row = self.fetch_one("SELECT * FROM ai_proposal WHERE proposal_id = ?", (proposal_id,))
        if not row:
            return None
        payload = dict(row)
        raw_json = payload.get("raw_json")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                payload["raw_json"] = json.loads(raw_json)
            except Exception:
                payload["raw_json"] = {}
        return payload

    def fetch_latest_ai_proposal_for_date(self, date: str, *, statuses: Sequence[str] | None = None) -> Dict[str, Any] | None:
        params: List[Any] = [date]
        sql = "SELECT * FROM ai_proposal WHERE date = ?"
        status_values = [str(item or "").strip() for item in list(statuses or []) if str(item or "").strip()]
        if status_values:
            sql += f" AND status IN ({', '.join('?' for _ in status_values)})"
            params.extend(status_values)
        sql += " ORDER BY created_at DESC, proposal_id DESC LIMIT 1"
        row = self.fetch_one(sql, tuple(params))
        if not row:
            return None
        return self.fetch_ai_proposal(str(row["proposal_id"]))

    def update_ai_proposal_status(self, proposal_id: str, *, status: str, accepted_at: str | None = None, error: str = "") -> None:
        self.migrate()
        with self.connect() as conn, conn:
            conn.execute(
                """
                UPDATE ai_proposal
                SET status = ?, accepted_at = ?, error = ?
                WHERE proposal_id = ?
                """,
                (status, accepted_at, error, proposal_id),
            )
        self.append_audit_event("ai_proposal_status_updated", {"proposal_id": proposal_id, "status": status})

    def upsert_derived_trend_feature(self, row: Mapping[str, Any]) -> None:
        self._upsert_generic(
            table="derived_trend_feature",
            key_columns=("date",),
            row={
                "date": row["date"],
                "features_json": _dump_json(row.get("features_json", {}), {}),
                "rules_version": row.get("rules_version", SCHEMA_VERSION),
                "calculated_at": row.get("calculated_at", utc_now_iso()),
            },
        )

    def fetch_derived_trend_feature(self, date: str) -> Dict[str, Any] | None:
        row = self.fetch_one("SELECT * FROM derived_trend_feature WHERE date = ?", (date,))
        if not row:
            return None
        payload = dict(row)
        raw_json = payload.get("features_json")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                payload["features_json"] = json.loads(raw_json)
            except Exception:
                payload["features_json"] = {}
        return payload

    def upsert_drift_detection_snapshot(self, row: Mapping[str, Any]) -> None:
        self._upsert_generic(
            table="drift_detection_snapshot",
            key_columns=("date",),
            row={
                "date": row["date"],
                "risk_level": row.get("risk_level", ""),
                "mode": row.get("mode", ""),
                "contributing_signals": _dump_json(row.get("contributing_signals", []), []),
                "next_action": row.get("next_action", ""),
                "evidence_note": row.get("evidence_note", ""),
                "rules_version": row.get("rules_version", SCHEMA_VERSION),
                "calculated_at": row.get("calculated_at", utc_now_iso()),
            },
        )

    def fetch_drift_detection_snapshot(self, date: str) -> Dict[str, Any] | None:
        row = self.fetch_one("SELECT * FROM drift_detection_snapshot WHERE date = ?", (date,))
        if not row:
            return None
        payload = dict(row)
        raw_json = payload.get("contributing_signals")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                payload["contributing_signals"] = json.loads(raw_json)
            except Exception:
                payload["contributing_signals"] = []
        return payload

    def fetch_garmin_passive_summary(self, date: str) -> Dict[str, Any] | None:
        row = self.fetch_one("SELECT * FROM garmin_daily_passive_summary WHERE date = ?", (date,))
        if not row:
            return None
        payload = dict(row)
        raw_json = payload.get("raw_json")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                payload["raw_json"] = json.loads(raw_json)
            except Exception:
                payload["raw_json"] = {}
        return payload

    def insert_garmin_live_import_batch(self, row: Mapping[str, Any]) -> None:
        self._insert_generic(
            "garmin_live_import_batch",
            {
                "batch_id": row["batch_id"],
                "started_at": row.get("started_at", utc_now_iso()),
                "completed_at": row.get("completed_at", utc_now_iso()),
                "mode": row.get("mode", ""),
                "requested_start_date": row.get("requested_start_date", ""),
                "requested_end_date": row.get("requested_end_date", ""),
                "stale_dates_json": _dump_json(row.get("stale_dates", []), []),
                "days_requested": int(row.get("days_requested", 0) or 0),
                "days_imported": int(row.get("days_imported", 0) or 0),
                "passive_created": int(row.get("passive_created", 0) or 0),
                "passive_updated": int(row.get("passive_updated", 0) or 0),
                "passive_unchanged": int(row.get("passive_unchanged", 0) or 0),
                "activity_created": int(row.get("activity_created", 0) or 0),
                "activity_updated": int(row.get("activity_updated", 0) or 0),
                "activity_unchanged": int(row.get("activity_unchanged", 0) or 0),
                "skipped": int(bool(row.get("skipped", False))),
                "skipped_reason": row.get("skipped_reason", ""),
                "ok": int(bool(row.get("ok", True))),
                "error": row.get("error", ""),
                "source_hashes_json": _dump_json(row.get("source_hashes", []), []),
                "endpoint_status_json": _dump_json(row.get("endpoint_status", {}), {}),
                "result_json": _dump_json(row.get("result", {}), {}),
            },
        )

    def fetch_latest_garmin_live_import_batch(self) -> Dict[str, Any] | None:
        row = self.fetch_one(
            "SELECT * FROM garmin_live_import_batch ORDER BY completed_at DESC, batch_id DESC LIMIT 1"
        )
        if not row:
            return None
        payload = dict(row)
        for key in ("stale_dates_json", "source_hashes_json", "endpoint_status_json", "result_json"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    payload[key] = json.loads(value)
                except Exception:
                    payload[key] = [] if key in {"stale_dates_json", "source_hashes_json"} else {}
        return payload

    def insert_intervention(self, row: Mapping[str, Any]) -> None:
        self._insert_generic(
            "intervention",
            {
                "start_date": row["start_date"],
                "end_date": row.get("end_date"),
                "type": row["type"],
                "reason": row.get("reason", ""),
                "rule": row.get("rule", ""),
                "expected_effect": row.get("expected_effect", ""),
                "outcome": row.get("outcome", ""),
                "review_notes": row.get("review_notes", ""),
                "created_at": utc_now_iso(),
            },
        )

    def insert_decision_log(self, row: Mapping[str, Any]) -> None:
        self._insert_generic(
            "decision_log",
            {
                "date": row["date"],
                "decision": row["decision"],
                "reason": row.get("reason", ""),
                "evidence": row.get("evidence", ""),
                "review_date": row.get("review_date"),
                "status": row.get("status", ""),
                "created_at": utc_now_iso(),
            },
        )

    def insert_episode(self, row: Mapping[str, Any]) -> None:
        self._insert_generic(
            "episode",
            {
                "start_date": row["start_date"],
                "end_date": row.get("end_date"),
                "title": row["title"],
                "type": row["type"],
                "description": row.get("description", ""),
                "tags": _dump_json(row.get("tags", []), []),
                "created_at": utc_now_iso(),
            },
        )

    def _insert_generic(self, table: str, row: Mapping[str, Any]) -> None:
        self.migrate()
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        with self.connect() as conn, conn:
            conn.execute(sql, tuple(row[column] for column in columns))
        self.append_audit_event(f"{table}_inserted", {"table": table})

    def _upsert_generic(self, *, table: str, key_columns: Sequence[str], row: Mapping[str, Any]) -> None:
        self.migrate()
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in key_columns)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(key_columns)}) DO UPDATE SET {updates}"
        )
        with self.connect() as conn, conn:
            conn.execute(sql, tuple(row[column] for column in columns))
        self.append_audit_event(f"{table}_upserted", {"table": table, "keys": {key: row[key] for key in key_columns}})

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Dict[str, Any] | None:
        self.migrate()
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        self.migrate()
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_table_columns(self, table: str) -> List[str]:
        self.migrate()
        with self.connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [str(row["name"]) for row in rows]

    def seed_fake_sample_data(self) -> Dict[str, int]:
        self.migrate()
        sample = fsio.read_json_dict_strict(self.sample_seed_path)
        if not sample:
            raise ValueError(f"sample seed is empty: {self.sample_seed_path}")
        counts: Dict[str, int] = {}
        for row in sample.get("daily_log", []):
            self.upsert_daily_log(row)
        counts["daily_log"] = len(sample.get("daily_log", []))
        for row in sample.get("activity_log", []):
            self.insert_activity(row)
        counts["activity_log"] = len(sample.get("activity_log", []))
        for row in sample.get("derived_daily_summary", []):
            self.upsert_derived_daily_summary(row)
        counts["derived_daily_summary"] = len(sample.get("derived_daily_summary", []))
        for row in sample.get("derived_weekly_summary", []):
            self.upsert_derived_weekly_summary(row)
        counts["derived_weekly_summary"] = len(sample.get("derived_weekly_summary", []))
        for row in sample.get("review_snapshot", []):
            self.insert_review_snapshot(row)
        counts["review_snapshot"] = len(sample.get("review_snapshot", []))
        for row in sample.get("intervention", []):
            self.insert_intervention(row)
        counts["intervention"] = len(sample.get("intervention", []))
        for row in sample.get("decision_log", []):
            self.insert_decision_log(row)
        counts["decision_log"] = len(sample.get("decision_log", []))
        for row in sample.get("episode", []):
            self.insert_episode(row)
        counts["episode"] = len(sample.get("episode", []))
        self.append_audit_event("fake_sample_seeded", counts)
        return counts

    def export_canonical_state(self) -> Dict[str, str]:
        self.migrate()
        exports = {
            "daily_log": self.generated_root / "exports" / "daily_log.csv",
            "activity_log": self.generated_root / "exports" / "activity_log.csv",
            "derived_daily_summary": self.generated_root / "exports" / "derived_daily_summary.csv",
            "derived_weekly_summary": self.generated_root / "exports" / "derived_weekly_summary.csv",
            "ai_proposal": self.generated_root / "exports" / "ai_proposal.csv",
            "derived_trend_feature": self.generated_root / "exports" / "derived_trend_feature.csv",
            "drift_detection_snapshot": self.generated_root / "exports" / "drift_detection_snapshot.csv",
            "garmin_daily_passive_summary": self.generated_root / "exports" / "garmin_daily_passive_summary.csv",
        }
        for table, path in exports.items():
            rows = self.fetch_all(f"SELECT * FROM {table} ORDER BY 1")
            self._write_csv(path, rows)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now_iso(),
            "exports": {table: str(path.relative_to(self.root)) for table, path in exports.items()},
        }
        fsio.write_json_atomic(self.generated_root / "exports" / "manifest.json", manifest)
        self.append_audit_event("canonical_state_exported", {"tables": sorted(exports.keys())})
        return {table: str(path) for table, path in exports.items()}

    def _write_csv(self, path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
        row_list = list(rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(row_list[0].keys()) if row_list else []
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                for row in row_list:
                    writer.writerow(dict(row))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv or [])
    command = args[0] if args else "export"
    store = HealthObservabilityStore(repo_root=Path.cwd())
    if command == "init":
        store.ensure_layout()
        store.migrate()
        return 0
    if command == "seed":
        store.seed_fake_sample_data()
        return 0
    if command == "export":
        store.export_canonical_state()
        return 0
    raise SystemExit(f"unsupported command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
