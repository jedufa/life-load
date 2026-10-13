from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from life_load.core_engine import (
    CORE_SCORING_VERSION,
    analyze_diary_payload,
    approve_payload,
    core_store,
    dashboard_payload,
    get_entry_payload,
    replay_approved_days,
    update_draft_payload,
)
from life_load import extraction
from life_load.settings import save_settings


def _extractor(payload: dict) -> str:
    return json.dumps(payload)


def test_analyze_diary_valid_json_updates_draft_not_canonical_entry(tmp_path: Path) -> None:
    store = core_store(tmp_path)

    payload = analyze_diary_payload(
        store,
        {"date": "2026-05-04", "diary_text": "Watched videos late after heavy work."},
        extractor=lambda **_: _extractor(
            {
                "date": "2026-05-04",
                "fields": {"phone_after_21": True, "work_intensity": "heavy", "stress": 7},
                "summary": "Heavy work and late phone.",
                "red_flags": [{"type": "late_phone", "severity": "yellow", "evidence": "Videos after 21:00."}],
                "next_action": "Phone outside bedroom by 21:00 tonight.",
            }
        ),
    )

    assert payload["entry"] is None
    assert payload["draftEntry"]["structured"]["phone_after_21"] is True
    assert payload["draftEntry"]["structured"]["work_intensity"] == "heavy"
    assert store.fetch_one("SELECT * FROM daily_log WHERE date = ?", ("2026-05-04",)) is None


def test_approve_copies_draft_into_canonical_daily_log(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    analyze_diary_payload(
        store,
        {"date": "2026-05-04", "diary_text": "Clean food, phone outside bedroom."},
        extractor=lambda **_: {
            "date": "2026-05-04",
            "fields": {"sleep_ok": True, "nutrition_ok": True, "phone_after_21": False},
            "summary": "Clean stable day.",
            "red_flags": [],
            "next_action": "Repeat the baseline.",
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    row = store.fetch_one("SELECT completed, diary_text, approved_at FROM daily_log WHERE date = ?", ("2026-05-04",))
    assert row is not None
    assert row["completed"] == 1
    assert row["diary_text"] == "Clean food, phone outside bedroom."
    assert row["approved_at"]
    assert approved["entry"]["sleep_ok"] is True
    assert approved["summary"]["zone"] in {"green", "yellow", "orange", "red"}


def test_approval_summary_failure_keeps_core_draft_and_canonical_unchanged(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {"date": "2026-05-04", "diary_text": "Retryable core approval", "fields": {"stress": 8}},
    )
    with store.connect() as conn, conn:
        conn.execute(
            """
            CREATE TRIGGER fail_core_daily_summary
            BEFORE INSERT ON derived_daily_summary
            BEGIN
              SELECT RAISE(ABORT, 'synthetic derived failure');
            END
            """,
        )

    with pytest.raises(sqlite3.IntegrityError, match="synthetic derived failure"):
        approve_payload(store, {"date": "2026-05-04"})

    assert store.fetch_one("SELECT date FROM daily_log WHERE date = ?", ("2026-05-04",)) is None
    draft = store.fetch_one("SELECT diary_text FROM draft_entry WHERE date = ?", ("2026-05-04",))
    assert draft == {"diary_text": "Retryable core approval"}


def test_approve_allows_structured_only_draft_without_diary_text(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "", "fields": {"sleep_ok": True}})

    approved = approve_payload(store, {"date": "2026-05-04"})

    row = store.fetch_one("SELECT completed, diary_text, sleep_ok FROM daily_log WHERE date = ?", ("2026-05-04",))
    assert row is not None
    assert row["completed"] == 1
    assert row["diary_text"] == ""
    assert row["sleep_ok"] == 1
    assert approved["entry"]["sleep_ok"] is True


def test_invalid_extraction_json_does_not_overwrite_draft(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Initial", "fields": {"stress": 4}})

    payload = analyze_diary_payload(
        store,
        {"date": "2026-05-04", "diary_text": "New text"},
        extractor=lambda **_: "not json",
    )

    assert payload["warnings"]
    loaded = get_entry_payload(store, date_value="2026-05-04")
    assert loaded["draftEntry"]["structured"]["stress"] == 4
    assert loaded["draftEntry"]["diary_text"] == "New text"
    assert store.fetch_one("SELECT status FROM ai_proposal WHERE date = ?", ("2026-05-04",)) == {"status": "error"}


def test_alcohol_at_home_forces_red(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {"date": "2026-05-04", "diary_text": "Alcohol at home.", "fields": {"alcohol": "home", "sleep_ok": True}},
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["summary"]["zone"] == "red"
    assert approved["summary"]["mode"] == "stabilize"
    assert "Alcohol at home" in approved["summary"]["why"]


def test_weekend_homework_na_is_neutral(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {"date": "2026-05-02", "diary_text": "Weekend.", "fields": {"homework_done": False, "sleep_ok": True}},
    )
    approved = approve_payload(store, {"date": "2026-05-02"})

    assert approved["entry"]["homework_done"] == "na"
    assert "homework" not in " ".join(approved["summary"]["why"]).lower()


def test_unknown_fields_are_not_scored_as_false(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Sparse day.", "fields": {"sleep_ok": True}})
    approved = approve_payload(store, {"date": "2026-05-04"})

    assert "Nutrition drift" not in approved["summary"]["why"]
    assert "Shutdown missed" not in approved["summary"]["why"]
    assert approved["summary"]["confidence"] < 1.0


def test_phone_after_21_adds_strain(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Phone late.", "fields": {"phone_after_21": True}})
    approved = approve_payload(store, {"date": "2026-05-04"})

    assert "Late phone" in approved["summary"]["why"]
    assert approved["summary"]["strain_score"] >= 2.0


def test_project_overrun_adds_strain(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Project ran late.", "fields": {"project_overrun": True}})
    approved = approve_payload(store, {"date": "2026-05-04"})

    assert "Project overrun" in approved["summary"]["why"]
    assert approved["summary"]["strain_score"] >= 2.5


def test_pain_gte_5_creates_warning(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Foot pain.", "fields": {"foot_pain": 6}})
    approved = approve_payload(store, {"date": "2026-05-04"})

    assert "Foot pain 6" in approved["summary"]["why"]
    assert approved["summary"]["zone"] in {"orange", "red"}


def test_dashboard_contains_zone_mode_why_next_action(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Late phone.", "fields": {"phone_after_21": True}})
    approve_payload(store, {"date": "2026-05-04"})

    payload = dashboard_payload(store, date_value="2026-05-04")

    assert payload["daily_zone"]
    assert payload["mode"]
    assert payload["why"]
    assert payload["next_action"]["primary_action"]


def test_weekly_summary_recomputes_after_approval(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Late phone.", "fields": {"phone_after_21": True}})
    first = approve_payload(store, {"date": "2026-05-04"})
    update_draft_payload(store, {"date": "2026-05-05", "diary_text": "Project overrun.", "fields": {"project_overrun": True}})
    second = approve_payload(store, {"date": "2026-05-05"})

    assert first["weekly_summary"]["approved_days"] == 1
    assert second["weekly_summary"]["approved_days"] == 2
    assert second["weekly_summary"]["late_phone_count"] == 1
    assert second["weekly_summary"]["project_overrun_count"] == 1


def test_approved_day_edit_recomputes_canonical_summary_and_clears_draft(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Phone late.", "fields": {"phone_after_21": True}})
    first = approve_payload(store, {"date": "2026-05-04"})

    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Clean recovery day.",
            "fields": {
                "sleep_ok": True,
                "nutrition_ok": True,
                "binge": False,
                "shutdown_done": True,
                "phone_after_21": False,
                "project_overrun": False,
                "migraine_warning": False,
                "decompression_done": True,
                "stress": 2,
                "energy": 6,
                "mood": 6,
            },
        },
    )
    edited = approve_payload(store, {"date": "2026-05-04"})
    loaded = get_entry_payload(store, date_value="2026-05-04")
    summary = store.fetch_one("SELECT zone, why_json FROM derived_daily_summary WHERE date = ?", ("2026-05-04",))

    assert first["summary"]["zone"] == "yellow"
    assert edited["entry"]["diary_text"] == "Clean recovery day."
    assert edited["summary"]["zone"] == "green"
    assert "Late phone" not in edited["summary"]["why"]
    assert loaded["draftEntry"] is None
    assert loaded["entry"]["phone_after_21"] is False
    assert summary is not None
    assert summary["zone"] == "green"
    assert "Late phone" not in summary["why_json"]


def test_completed_days_are_not_hard_sessions(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Completed day.", "fields": {"sleep_ok": True}})
    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["summary"]["training_load"] == 0.0
    assert "hard session" not in " ".join(approved["summary"]["why"]).lower()


def test_core_store_migrates_existing_data_tables_without_dropping_data(tmp_path: Path) -> None:
    db_path = tmp_path / "data/health.sqlite"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn, conn:
        conn.execute(
            """
            CREATE TABLE daily_log (
                date TEXT PRIMARY KEY,
                completed INTEGER NOT NULL DEFAULT 0,
                diary_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_daily_summary (
                date TEXT PRIMARY KEY,
                life_load_score REAL NOT NULL DEFAULT 0,
                training_load REAL NOT NULL DEFAULT 0,
                recovery_score REAL NOT NULL DEFAULT 0,
                strain_score REAL NOT NULL DEFAULT 0,
                red_flags TEXT NOT NULL DEFAULT '[]',
                zone TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_weekly_summary (
                week_start TEXT PRIMARY KEY,
                week_end TEXT NOT NULL,
                completed_days INTEGER NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO daily_log(date, diary_text, created_at, updated_at) VALUES ('2026-05-04', 'legacy', 'x', 'x')")

    store = core_store(tmp_path)

    assert store.fetch_one("SELECT diary_text, approved_at FROM daily_log WHERE date = ?", ("2026-05-04",)) == {
        "diary_text": "legacy",
        "approved_at": "",
    }
    update_draft_payload(store, {"date": "2026-05-05", "diary_text": "Late phone.", "fields": {"phone_after_21": True}})
    approved = approve_payload(store, {"date": "2026-05-05"})
    assert approved["summary"]["zone"] == "yellow"


def test_migrated_approved_entry_can_be_edited_and_recomputed(tmp_path: Path) -> None:
    db_path = tmp_path / "data/health.sqlite"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn, conn:
        conn.execute(
            """
            CREATE TABLE daily_log (
                date TEXT PRIMARY KEY,
                completed INTEGER NOT NULL DEFAULT 0,
                diary_text TEXT NOT NULL DEFAULT '',
                sleep_ok INTEGER,
                phone_after_21 INTEGER,
                approved_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_daily_summary (
                date TEXT PRIMARY KEY,
                life_load_score REAL NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO daily_log(date, completed, diary_text, sleep_ok, phone_after_21, approved_at, created_at, updated_at)
            VALUES ('2026-05-04', 1, 'Legacy late phone.', 0, 1, '2026-05-04T20:00:00Z', 'x', 'x')
            """
        )
        conn.execute(
            """
            INSERT INTO derived_daily_summary(date, life_load_score, zone, next_action, calculated_at)
            VALUES ('2026-05-04', 4.0, 'yellow', 'Phone outside bedroom by 21:00 tonight.', 'x')
            """
        )

    store = core_store(tmp_path)
    loaded = get_entry_payload(store, date_value="2026-05-04")

    assert loaded["entry"]["diary_text"] == "Legacy late phone."
    assert loaded["summary"]["zone"] == "yellow"
    assert loaded["summary"]["why"] == []

    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Migrated clean recovery day.",
            "fields": {
                "sleep_ok": True,
                "nutrition_ok": True,
                "binge": False,
                "shutdown_done": True,
                "phone_after_21": False,
                "project_overrun": False,
                "migraine_warning": False,
                "decompression_done": True,
                "stress": 1,
                "energy": 7,
                "mood": 7,
            },
        },
    )
    edited = approve_payload(store, {"date": "2026-05-04"})

    assert edited["entry"]["diary_text"] == "Migrated clean recovery day."
    assert edited["summary"]["zone"] == "green"
    assert "Late phone" not in edited["summary"]["why"]
    assert get_entry_payload(store, date_value="2026-05-04")["draftEntry"] is None


def test_existing_not_null_daily_log_accepts_sparse_approval(tmp_path: Path) -> None:
    db_path = tmp_path / "data/health.sqlite"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn, conn:
        conn.execute(
            """
            CREATE TABLE daily_log (
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-04", "diary_text": "Sparse.", "fields": {"sleep_ok": True}})
    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["entry"]["alcohol"] == "none"
    assert approved["entry"]["binge"] is False


def test_android_trigger_and_activity_fields_survive_approval_and_score(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "CrossFit after fights and no after-work decompression.",
            "fields": {
                "primary_activity_type": "crossfit",
                "activity_duration_min": 60,
                "alone_home": True,
                "wife_conflict_count": 2,
                "wife_conflict_school": True,
                "after_work_decompression_done": False,
                "sleep_ok": True,
                "alcohol": "none",
                "binge": False,
            },
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["entry"]["primary_activity_type"] == "crossfit"
    assert approved["entry"]["alone_home"] is True
    assert approved["entry"]["wife_conflict_count"] == 2
    assert approved["summary"]["training_load"] > 0
    assert "Relationship stress x2" in approved["summary"]["why"]


def test_core_formula_settings_disable_optional_triggers_on_approval(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    save_settings(
        tmp_path,
        {
            "formula": {
                "include_relationship_stress": False,
                "include_alone_home": False,
                "include_after_work_decompression": False,
                "include_project_overrun": False,
                "include_late_phone": False,
                "include_home_office": False,
            }
        },
    )
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Late phone, project overrun, alone at home, and two fights.",
            "fields": {
                "sleep_ok": True,
                "nutrition_ok": True,
                "shutdown_done": True,
                "decompression_done": True,
                "phone_after_21": True,
                "project_overrun": True,
                "alone_home": True,
                "after_work_decompression_done": False,
                "wife_conflict_count": 2,
                "wife_conflict_school": True,
                "home_office": True,
            },
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    assert "Relationship stress x2" not in approved["summary"]["why"]
    assert "Late phone" not in approved["summary"]["why"]
    assert "Project overrun" not in approved["summary"]["why"]
    assert "Alone at home" not in approved["summary"]["why"]
    assert approved["summary"]["zone"] == "green"


def test_core_profile_modifier_provenance_surfaces_on_approval(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    save_settings(
        tmp_path,
        {
            "formula": {
                "profile_modifiers": ["protective", "sports_light"],
            }
        },
    )
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Late phone and project overrun.",
            "fields": {
                "sleep_ok": True,
                "nutrition_ok": True,
                "shutdown_done": False,
                "phone_after_21": True,
                "project_overrun": True,
                "after_work_decompression_done": False,
                "energy": 6,
                "foot_pain": 0,
                "shoulder_pain": 0,
                "primary_activity_type": "run",
                "activity_duration_min": 30,
            },
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})
    summary = approved["summary"]

    assert summary["profile_modifiers"] == ["protective", "sports_light"]
    assert summary["profile_adjusted_score"] > summary["base_score"]
    assert summary["guidance_thresholds"] == {"medium": 32, "high": 65}
    assert "protective increased late-phone strain" in summary["profile_effects"]
    assert "sports_light softened training load" in summary["profile_effects"]
    reloaded = get_entry_payload(store, date_value="2026-05-04")["summary"]
    assert reloaded["profile_modifiers"] == ["protective", "sports_light"]
    assert "protective increased late-phone strain" in reloaded["profile_effects"]


def test_approval_stamps_formula_version_and_settings_snapshot(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    save_settings(
        tmp_path,
        {
            "formula": {
                "include_late_phone": False,
                "include_project_overrun": True,
            }
        },
    )
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Late phone with protected formula toggle.",
            "fields": {"phone_after_21": True, "project_overrun": True},
        },
    )

    approve_payload(store, {"date": "2026-05-04"})

    row = store.fetch_one(
        """
        SELECT scoring_version, formula_settings_json, formula_settings_hash
        FROM derived_daily_summary
        WHERE date = ?
        """,
        ("2026-05-04",),
    )
    assert row is not None
    snapshot = json.loads(row["formula_settings_json"])
    assert row["scoring_version"] == CORE_SCORING_VERSION
    assert snapshot["include_late_phone"] is False
    assert snapshot["include_project_overrun"] is True
    assert len(row["formula_settings_hash"]) == 12
    assert replay_approved_days(store)["changed_days"] == 0


def test_replay_report_detects_stale_formula_summary_without_private_text(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {"date": "2026-05-04", "diary_text": "Private daily text.", "fields": {"phone_after_21": True}},
    )
    approve_payload(store, {"date": "2026-05-04"})
    with store.connect() as conn, conn:
        conn.execute(
            """
            UPDATE derived_daily_summary
            SET scoring_version = 'legacy_formula',
                formula_settings_hash = 'legacy_hash',
                life_load_score = -99,
                zone = 'green',
                mode = 'continue',
                next_action = ?
            WHERE date = ?
            """,
            (json.dumps({"primary_action": "Legacy action"}), "2026-05-04"),
        )

    report = replay_approved_days(store)

    assert report["schema_version"] == "life_load_formula_replay_report_v1"
    assert report["scoring_version_current"] == CORE_SCORING_VERSION
    assert report["total_days"] == 1
    assert report["changed_days"] == 1
    change = report["changes"][0]
    assert change["date"] == "2026-05-04"
    assert {
        "scoring_version",
        "formula_settings_hash",
        "zone",
        "mode",
        "primary_action",
        "life_load_score",
    }.issubset(set(change["changed_fields"]))
    assert "Private daily text" not in json.dumps(change)


def test_replay_report_warms_context_before_ranged_start(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    for date_text in ("2026-05-01", "2026-05-02", "2026-05-03"):
        update_draft_payload(
            store,
            {
                "date": date_text,
                "diary_text": f"Private context day {date_text}.",
                "fields": {"phone_after_21": True},
            },
        )
        approve_payload(store, {"date": date_text})

    report = replay_approved_days(store, start_date="2026-05-03", end_date="2026-05-03")

    assert report["total_days"] == 1
    assert report["changed_days"] == 0


def test_core_preserves_extreme_work_and_common_activity_aliases(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Extreme work and cycling.",
            "fields": {"work_intensity": "extreme", "primary_activity_type": "cycling", "activity_duration_min": 30},
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["entry"]["work_intensity"] == "extreme"
    assert approved["entry"]["primary_activity_type"] == "bike"
    assert "Extreme work" in approved["summary"]["why"]
    assert approved["summary"]["training_load"] == 0.6


def test_recent_history_influences_current_day_status(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    for date_text in ("2026-05-01", "2026-05-02", "2026-05-03"):
        update_draft_payload(
            store,
            {
                "date": date_text,
                "diary_text": f"Drift day {date_text}.",
                "fields": {
                    "phone_after_21": True,
                    "project_overrun": True,
                    "sleep_ok": False,
                    "nutrition_ok": False,
                },
            },
        )
        approve_payload(store, {"date": date_text})
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": "Clean recovery day.",
            "fields": {"sleep_ok": True, "nutrition_ok": True, "phone_after_21": False, "project_overrun": False},
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["summary"]["zone"] in {"yellow", "orange", "red"}
    assert "repeated late phone" in approved["summary"]["why"]
    assert approved["summary"]["recent_context"]["approved_days"] == 3


def test_dashboard_uses_recent_history_for_blank_selected_day(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    for date_text in ("2026-05-01", "2026-05-02"):
        update_draft_payload(
            store,
            {
                "date": date_text,
                "diary_text": f"Late project day {date_text}.",
                "fields": {"phone_after_21": True, "project_overrun": True, "sleep_ok": False},
            },
        )
        approve_payload(store, {"date": date_text})

    payload = dashboard_payload(store, date_value="2026-05-03")

    assert payload["daily_zone"] in {"yellow", "orange", "red"}
    assert "repeated late phone" in payload["why"]
    assert payload["drift_signals"]["recent_context"]["approved_days"] == 2
    assert payload["trend"]["rows"]
    assert payload["history"]


def test_core_dashboard_trend_load_matches_life_load_not_training_only(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {
            "date": "2026-05-01",
            "diary_text": "High stress, no training.",
            "fields": {"stress": 8, "sleep_ok": False, "nutrition_ok": False, "primary_activity_type": "none"},
        },
    )
    approved = approve_payload(store, {"date": "2026-05-01"})

    payload = dashboard_payload(store, date_value="2026-05-01")
    latest = payload["trend"]["rows"][-1]["features"]

    assert approved["summary"]["training_load"] == 0
    assert latest["life_load_rolling_avg_7d"] > 0
    assert latest["acute_load_7d"] == latest["life_load_rolling_avg_7d"]
    assert latest["acute_training_load_7d"] == 0


def test_late_training_project_rumination_and_fragmented_sleep_recommends_no_project_day(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(
        store,
        {
            "date": "2026-05-04",
            "diary_text": (
                "Late training session with the group ending at 20:30. "
                "I had my head full of my new project and couldn't fall asleep. "
                "I woke up at midnight and couldn't sleep again for another 2 hours."
            ),
            "fields": {
                "sleep_ok": False,
                "primary_activity_type": "crossfit",
                "activity_duration_min": 60,
                "project_overrun": True,
            },
        },
    )

    approved = approve_payload(store, {"date": "2026-05-04"})

    assert approved["summary"]["zone"] in {"orange", "red"}
    assert "Sleep disrupted after project/training" in approved["summary"]["why"]
    assert approved["summary"]["next_action"]["primary_action"] == "Take it easy today: no hard training and no project work."
    assert "Do not touch the project today" in approved["summary"]["next_action"]["avoid"]


def test_diary_no_alcohol_overrides_bad_extractor_keyword_match(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    payload = analyze_diary_payload(
        store,
        {"date": "2026-05-05", "diary_text": "I was very good with food. I didn't have alcohol and I slept well."},
        extractor=lambda **_: {
            "date": "2026-05-05",
            "fields": {"alcohol": "home", "tags": ["alcohol"]},
            "summary": "Alcohol",
            "red_flags": [{"type": "alcohol", "severity": "orange", "evidence": "Keyword alcohol."}],
            "next_action": "Protect recovery.",
        },
    )

    assert payload["draftEntry"]["structured"]["alcohol"] == "none"
    assert payload["draftEntry"]["structured"].get("tags", []) == []
    assert payload["proposal"]["red_flags"] == []
    assert payload["proposal"]["summary"] == "No alcohol."


def test_ai_extraction_failure_does_not_apply_heuristic_fields(tmp_path: Path) -> None:
    store = core_store(tmp_path)
    update_draft_payload(store, {"date": "2026-05-05", "diary_text": "Initial", "fields": {"stress": 3}})

    payload = analyze_diary_payload(
        store,
        {"date": "2026-05-05", "diary_text": "Clean food, no alcohol, normal work."},
        extractor=lambda **_: (_ for _ in ()).throw(ValueError("AI unavailable")),
    )

    assert payload["warnings"] == ["AI unavailable"]
    assert payload["proposal"] is None
    assert payload["draftEntry"]["structured"] == {"stress": 3}


def test_extraction_requires_ai_worker_repo_root() -> None:
    try:
        extraction.analyze_diary_entry(date="2026-05-05", diary_text="Clean food, no alcohol.")
    except ValueError as exc:
        assert "requires repo_root" in str(exc)
    else:
        raise AssertionError("analyze_diary_entry should require the AI worker context")
