from __future__ import annotations

import json
from pathlib import Path

import pytest

from life_load import mobile_web
from life_load import extraction
from life_load import scoring


def test_get_entry_defaults_to_yesterday(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mobile_web, "_today_vienna", lambda: mobile_web.dt.date(2026, 5, 3))
    store = mobile_web.api_store(tmp_path)

    payload = mobile_web.get_entry_payload(store)

    assert payload["date"] == "2026-05-02"
    assert payload["default_date"] == "2026-05-02"
    assert payload["entry_state"] == "blank"
    assert payload["score"] == {}


def test_get_entry_surfaces_garmin_only_passive_day_without_approval(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, wellness_steps, activity_count,
                sleep_total_sleep_min, source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, '{}', ?)
            """,
            ("2024-06-12", 12345, 1, 430, "sha", "2026-05-03T00:00:00Z"),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2024-06-12")
    history = mobile_web.history_payload(store, selected_date="2024-06-12")
    ranged = mobile_web.range_payload(store, start_value="2024-06-12", end_value="2024-06-12")

    assert payload["entry_state"] == "garmin_only"
    assert payload["entry_exists"] is True
    assert payload["has_garmin_passive"] is True
    assert payload["garmin_passive"]["wellness_steps"] == 12345
    assert store.fetch_one("SELECT * FROM daily_log WHERE date = ?", ("2024-06-12",)) is None
    assert history["selected_entry"]["state"] == "garmin_only"
    assert ranged["entries"][0]["entry_state"] == "garmin_only"


def test_draft_save_does_not_create_canonical_completed_entry(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)

    payload = mobile_web.save_entry_payload(
        store,
        {
            "action": "draft",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Draft only note",
                "stress": 6,
                "coffee_cups": 12,
                "mood": 4,
                "sleep_ok": False,
            },
        },
    )

    assert payload["entry_state"] == "draft"
    assert store.fetch_one("SELECT * FROM daily_log WHERE date = ?", ("2026-05-02",)) is None
    draft_row = store.fetch_daily_log_draft("2026-05-02")
    assert draft_row is not None
    assert draft_row["draft_payload"]["diary_text"] == "Draft only note"
    assert draft_row["draft_payload"]["coffee_cups"] == 8
    history = mobile_web.history_payload(store, limit=10, selected_date="2026-05-02")
    assert history["entries"][0]["state"] == "draft"
    assert history["entries"][0]["canonical_completed"] is False


def test_empty_approved_entry_is_saved_but_has_no_guidance_or_weekly_evidence(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)

    payload = mobile_web.save_entry_payload(
        store,
        {"action": "approve", "entry": {"date": "2026-05-02"}},
    )

    assert payload["entry_state"] == "approved"
    assert payload["score_available"] is False
    history = mobile_web.history_payload(store, selected_date="2026-05-02")
    assert history["selected_entry"]["score_available"] is False
    dashboard = mobile_web.dashboard_payload(store, date_value="2026-05-02")
    assert dashboard["dashboard_state"]["approved_days"] == []
    assert dashboard["current_week"]["completed_days"] == 0
    assert dashboard["dashboard_state"]["daily_summary_dates"] == []
    assert dashboard["trend"]["rows"] == []


def test_history_score_availability_uses_all_structured_signal_columns(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)

    mobile_web.save_entry_payload(
        store,
        {"action": "approve", "entry": {"date": "2026-05-02", "sleep_ok": False}},
    )

    row = mobile_web.history_payload(store, selected_date="2026-05-02")["entries"][0]
    assert row["score_available"] is True
    assert row["zone"]


def test_history_score_availability_counts_explicit_heavy_work(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)

    mobile_web.save_entry_payload(
        store,
        {"action": "approve", "entry": {"date": "2026-05-02", "work_intensity": "heavy"}},
    )

    row = mobile_web.history_payload(store, selected_date="2026-05-02")["entries"][0]
    assert row["score_available"] is True


def test_approve_promotes_to_canonical_recalculates_and_clears_draft(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    mobile_web.save_entry_payload(
        store,
        {
            "action": "draft",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Rough day but captured honestly.",
                "diary_summary": "rough",
                "sleep_ok": False,
                "nutrition_ok": False,
                "stress": 8,
                "energy": 3,
                "phone_after_21": True,
            },
        },
    )

    payload = mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Rough day but captured honestly.",
                "diary_summary": "rough",
                "sleep_ok": False,
                "nutrition_ok": False,
                "stress": 8,
                "energy": 3,
                "phone_after_21": True,
            },
        },
    )

    assert payload["entry_state"] == "approved"
    row = store.fetch_one(
        "SELECT completed, user_approved_at, diary_text FROM daily_log WHERE date = ?",
        ("2026-05-02",),
    )
    assert row is not None
    assert row["completed"] == 1
    assert row["user_approved_at"]
    assert row["diary_text"] == "Rough day but captured honestly."
    assert store.fetch_daily_log_draft("2026-05-02") is None
    daily = store.fetch_one(
        """
        SELECT zone, next_action, scoring_version, formula_settings_json, formula_settings_hash
        FROM derived_daily_summary
        WHERE date = ?
        """,
        ("2026-05-02",),
    )
    weekly = store.fetch_one("SELECT completed_days, zone FROM derived_weekly_summary WHERE week_start = ?", ("2026-04-27",))
    assert daily is not None
    assert daily["scoring_version"] == scoring.SCORING_CONTRACT_VERSION
    assert json.loads(daily["formula_settings_json"])["include_late_phone"] is True
    assert len(daily["formula_settings_hash"]) == 12
    assert weekly is not None
    assert weekly["completed_days"] == 1


def test_manual_activity_changes_live_training_and_life_load_score() -> None:
    base = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "energy": 5,
            "mood": 5,
        }
    )
    short_run = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "energy": 5,
            "mood": 5,
            "primary_activity_type": "run",
            "activity_duration_min": 15,
        }
    )
    longer_run = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "energy": 5,
            "mood": 5,
            "primary_activity_type": "run",
            "activity_duration_min": 60,
        }
    )

    assert short_run["training_load"] > base["training_load"]
    assert short_run["life_load_score"] > base["life_load_score"]
    assert longer_run["training_load"] > short_run["training_load"]
    assert longer_run["life_load_score"] > short_run["life_load_score"]
    assert longer_run["hard_sessions"] == 1


def test_recovery_inputs_change_visible_day_score() -> None:
    neutral = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "stress": 0,
            "energy": 0,
            "mood": 0,
        }
    )
    recovered = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 0,
            "energy": 8,
            "mood": 8,
            "shutdown_done": True,
            "decompression_done": True,
            "homework_done": True,
        }
    )

    assert recovered["recovery_score"] > neutral["recovery_score"]
    assert recovered["life_load_score"] < neutral["life_load_score"]
    assert recovered["life_load_score"] < 0


def test_multiple_manual_activity_types_split_duration_without_hiding_load() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "energy": 5,
        "mood": 5,
        "activity_types": ["run", "crossfit"],
        "activity_duration_min": 60,
    }

    result = scoring.score_entry(entry)

    assert result["training_load"] == 4.4
    assert result["hard_sessions"] == 2


def test_formula_settings_can_disable_optional_trigger_strain() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "shutdown_done": True,
        "decompression_done": True,
        "after_work_decompression_done": False,
        "phone_after_21": True,
        "project_overrun": True,
        "alone_home": True,
        "wife_conflict_count": 2,
        "wife_conflict_school": True,
        "home_office": True,
    }

    baseline = scoring.score_entry(entry)
    reduced = scoring.score_entry(
        entry,
        formula_settings={
            "include_relationship_stress": False,
            "include_alone_home": False,
            "include_after_work_decompression": False,
            "include_project_overrun": False,
            "include_late_phone": False,
            "include_home_office": False,
        },
    )

    assert reduced["strain_score"] < baseline["strain_score"] - 10
    assert "relationship conflict" not in reduced["warnings"]
    assert "late phone" not in reduced["warnings"]
    assert "project spillover" not in reduced["warnings"]
    assert "alone at home trigger" not in reduced["warnings"]


def test_bike_commute_counts_less_than_sport_bike() -> None:
    base_entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "energy": 5,
        "mood": 5,
        "activity_duration_min": 60,
    }

    commute = scoring.score_entry({**base_entry, "primary_activity_type": "bike_commute"})
    sport = scoring.score_entry({**base_entry, "primary_activity_type": "bike"})

    assert commute["training_load"] > 0
    assert commute["training_load"] < sport["training_load"]
    assert commute["hard_sessions"] == 0
    assert commute["acute_training_load"] == 0
    assert commute["chronic_training_load"] == 0


def test_bike_commute_counts_as_load_but_not_sport_progression_spike() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 4)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "energy": 8,
        "mood": 8,
        "stress": 2,
        "decompression_done": True,
        "after_work_decompression_done": True,
        "shutdown_done": True,
        "primary_activity_type": "crossfit",
        "activity_duration_min": 45,
    }
    crossfit_only = scoring.score_entry(entry, prior_training_loads=[1.0] * 42)
    crossfit_plus_commute = scoring.score_entry(
        entry,
        activity_rows=[
            {
                "date": "2026-05-04",
                "activity_type": "bike_commute",
                "duration_min": 82,
                "intensity": "moderate",
                "source": "garmin_activity",
            }
        ],
        prior_training_loads=[1.0] * 42,
    )

    assert crossfit_plus_commute["training_load"] > crossfit_only["training_load"]
    assert crossfit_plus_commute["acute_training_load"] == crossfit_only["acute_training_load"]
    assert crossfit_plus_commute["zone"] == crossfit_only["zone"]
    assert "acute training spike" not in crossfit_plus_commute["warnings"]


def test_manual_sport_bike_overrides_matching_garmin_commute_inference() -> None:
    garmin_commute_row = {
        "date": "2026-05-05",
        "activity_type": "bike_commute",
        "duration_min": 55,
        "intensity": "moderate",
        "source": "garmin_activity",
    }
    with_manual_sport_bike = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 5)),
            "primary_activity_type": "bike",
            "activity_duration_min": 55,
        },
        activity_rows=[garmin_commute_row],
    )
    manual_sport_bike = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 5)),
            "primary_activity_type": "bike",
            "activity_duration_min": 55,
        }
    )

    assert with_manual_sport_bike["training_load"] == manual_sport_bike["training_load"]


def test_training_spike_warning_uses_recent_load_context() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "primary_activity_type": "run",
        "activity_duration_min": 60,
    }
    cold_start = scoring.score_entry(entry, prior_training_loads=[0.0] * 42)
    consistent_base = scoring.score_entry(entry, prior_training_loads=[4.0] * 42)

    assert cold_start["training_load"] == consistent_base["training_load"]
    assert cold_start["strain_score"] > consistent_base["strain_score"]
    assert "training spike from low base" in cold_start["warnings"]
    assert cold_start["acute_training_load"] > cold_start["chronic_training_load"]


def test_profile_modifiers_adjust_scoring_with_provenance() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "shutdown_done": False,
        "after_work_decompression_done": False,
        "phone_after_21": True,
        "project_overrun": True,
        "stress": 7,
        "energy": 6,
    }

    balanced = scoring.score_entry(entry, formula_settings={"formula": {"profile_modifiers": ["balanced"]}})
    protective = scoring.score_entry(entry, formula_settings={"formula": {"profile_modifiers": ["protective"]}})

    assert balanced["profile_modifiers"] == []
    assert protective["profile_modifiers"] == ["protective"]
    assert protective["profile_adjusted_score"] > protective["base_score"]
    assert protective["base_score"] == balanced["life_load_score"]
    assert protective["guidance_thresholds"] == {"medium": 32, "high": 65}
    assert "protective increased late-phone strain" in protective["profile_effects"]
    assert "protective increased project-overrun strain" in protective["profile_effects"]


def test_sports_light_softens_only_eligible_training_spike_penalty() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "energy": 6,
        "foot_pain": 0,
        "shoulder_pain": 0,
        "primary_activity_type": "run",
        "activity_duration_min": 60,
    }

    baseline = scoring.score_entry(entry, prior_training_loads=[0.0] * 42)
    sports_light = scoring.score_entry(
        entry,
        prior_training_loads=[0.0] * 42,
        formula_settings={"formula": {"profile_modifiers": ["sports_light"]}},
    )
    pain_blocked = scoring.score_entry(
        {**entry, "foot_pain": 5},
        prior_training_loads=[0.0] * 42,
        formula_settings={"formula": {"profile_modifiers": ["sports_light"]}},
    )
    energy_blocked = scoring.score_entry(
        {**entry, "energy": 3},
        prior_training_loads=[0.0] * 42,
        formula_settings={"formula": {"profile_modifiers": ["sports_light"]}},
    )

    assert sports_light["strain_score"] < baseline["strain_score"]
    assert "sports_light softened training spike penalty" in sports_light["profile_effects"]
    assert "sports_light not applied because pain >= 5" in pain_blocked["profile_effects"]
    assert "sports_light not applied because energy <= 3" in energy_blocked["profile_effects"]


def test_profile_modifiers_can_be_combined_without_hiding_effects() -> None:
    entry = {
        **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
        "sleep_ok": True,
        "nutrition_ok": True,
        "energy": 6,
        "shutdown_done": False,
        "phone_after_21": True,
        "primary_activity_type": "run",
        "activity_duration_min": 60,
    }

    combined = scoring.score_entry(
        entry,
        prior_training_loads=[0.0] * 42,
        formula_settings={"formula": {"profile_modifiers": ["protective", "sports_light"]}},
    )

    assert combined["profile_modifiers"] == ["protective", "sports_light"]
    assert "protective increased late-phone strain" in combined["profile_effects"]
    assert "sports_light softened training spike penalty" in combined["profile_effects"]


def test_emotional_overload_moves_score_without_training() -> None:
    supported_hard_day = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 8,
            "family_stress": 8,
            "energy": 3,
            "mood": 3,
            "work_intensity": "heavy",
            "decompression_done": True,
            "shutdown_done": True,
        }
    )
    unreleased_hard_day = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 8,
            "family_stress": 8,
            "energy": 3,
            "mood": 3,
            "work_intensity": "heavy",
            "decompression_done": False,
            "shutdown_done": False,
            "phone_after_21": True,
            "project_overrun": True,
        }
    )

    assert unreleased_hard_day["training_load"] == 0
    assert unreleased_hard_day["strain_score"] > supported_hard_day["strain_score"] + 8
    assert unreleased_hard_day["life_load_score"] > supported_hard_day["life_load_score"] + 8
    assert "emotional overload" in unreleased_hard_day["warnings"]
    assert "decompression missed" in unreleased_hard_day["warnings"]
    assert unreleased_hard_day["zone"] in {"orange", "red"}
    assert "decompress" in unreleased_hard_day["next_action"].lower()


def test_evening_chain_and_wife_conflict_persist_and_raise_strain(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)

    baseline = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "sleep_ok": True,
            "nutrition_ok": True,
            "stress": 5,
            "family_stress": 5,
            "decompression_done": True,
            "after_work_decompression_done": True,
            "shutdown_done": True,
            "alone_home": False,
        }
    )
    payload = mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Two fights with wife about son's school, no decompression after work, evening went off rails.",
                "sleep_ok": True,
                "nutrition_ok": True,
                "stress": 5,
                "family_stress": 5,
                "decompression_done": False,
                "after_work_decompression_done": False,
                "evening_chain_broken": True,
                "shutdown_done": True,
                "alone_home": True,
                "wife_conflict_count": 2,
                "wife_conflict_school": True,
                "wife_conflict_chores": False,
                "wife_conflict_other": False,
            },
        },
    )

    row = store.fetch_one(
        """
        SELECT after_work_decompression_done, evening_chain_broken, alone_home, wife_conflict_count,
               wife_conflict_school, wife_conflict_chores, wife_conflict_other
        FROM daily_log
        WHERE date = ?
        """,
        ("2026-05-02",),
    )

    assert row == {
        "after_work_decompression_done": 0,
        "evening_chain_broken": 1,
        "alone_home": 1,
        "wife_conflict_count": 2,
        "wife_conflict_school": 1,
        "wife_conflict_chores": 0,
        "wife_conflict_other": 0,
    }
    assert payload["entry"]["after_work_decompression_done"] is False
    assert payload["entry"]["evening_chain_broken"] is True
    assert payload["entry"]["alone_home"] is True
    assert payload["entry"]["wife_conflict_count"] == 2
    assert payload["score"]["training_load"] == 0
    assert payload["score"]["strain_score"] > baseline["strain_score"] + 10
    assert "relationship conflict" in payload["score"]["warnings"]
    assert "repeated relationship conflict" in payload["score"]["warnings"]
    assert "school conflict" in payload["score"]["warnings"]
    assert "after-work decompression missed" in payload["score"]["warnings"]
    assert "evening chain broken" in payload["score"]["warnings"]
    assert "alone at home trigger" in payload["score"]["warnings"]
    assert payload["score"]["zone"] in {"orange", "red"}


def test_garmin_activity_and_passive_data_influence_garmin_only_day_score(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, activity_type, duration_min, moving_duration_min,
                hard_session_est, aerobic_training_effect, anaerobic_training_effect,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            ("act-1", "2026-05-02", "running", 50.0, 45.0, 1, 3.1, 0.5, "sha"),
        )
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, wellness_steps, wellness_avg_stress,
                wellness_active_kcal, activity_count, activity_hard_session_count_est,
                sleep_total_sleep_min, source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
            """,
            ("2026-05-02", 15500, 72.0, 950.0, 1, 1, 330.0, "sha", "2026-05-03T00:00:00Z"),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2026-05-02")

    assert payload["entry_state"] == "garmin_only"
    assert payload["score"]["training_load"] > 0
    assert payload["score"]["life_load_score"] > 0
    assert "garmin short sleep" in payload["score"]["warnings"]
    assert "garmin high stress" in payload["score"]["warnings"]
    assert payload["score"]["hard_sessions"] == 1
    assert payload["score_available"] is True


def test_garmin_critical_short_sleep_forces_recovery_first_guidance(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, sleep_total_sleep_min,
                source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, '{}', ?)
            """,
            ("2026-05-02", 239.0, "sha", "2026-05-03T00:00:00Z"),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2026-05-02")

    assert payload["entry_state"] == "garmin_only"
    assert payload["score"]["zone"] == "red"
    assert "critical short sleep" in payload["score"]["red_flags"]
    assert "garmin critical short sleep" in payload["score"]["warnings"]
    assert "short sleep" in payload["score"]["next_action"].lower()
    assert "no extra training" in payload["score"]["next_action"].lower()


def test_garmin_very_short_sleep_holds_progression_without_red_override(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, sleep_total_sleep_min,
                source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, '{}', ?)
            """,
            ("2026-05-02", 270.0, "sha", "2026-05-03T00:00:00Z"),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2026-05-02")

    assert "garmin very short sleep" in payload["score"]["warnings"]
    assert "critical short sleep" not in payload["score"]["red_flags"]
    assert payload["score"]["zone"] in {"orange", "red"}
    assert "hold progression" in payload["score"]["next_action"].lower()


def test_garmin_cycling_commute_pattern_counts_as_bike_commute(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, start_time_local_iso, name, activity_type, duration_min,
                moving_duration_min, distance_km, hard_session_est, aerobic_training_effect,
                anaerobic_training_effect, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "commute-1",
                "2026-05-05",
                "2026-05-05T06:55:00",
                "Vienna Cycling",
                "cycling",
                56.0,
                55.0,
                17.9,
                0,
                2.1,
                0.0,
                "sha",
                '{"elapsed_duration_min": 58.0}',
            ),
        )
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, activity_hard_session_count_est,
                source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, '{}', ?)
            """,
            ("2026-05-05", 2, "sha", "2026-05-05T22:00:00Z"),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2026-05-05")
    commute = scoring.score_entry(
        mobile_web._default_entry(mobile_web.dt.date(2026, 5, 5)),
        activity_rows=[{"date": "2026-05-05", "activity_type": "bike_commute", "duration_min": 55, "intensity": "moderate", "source": "garmin_activity"}],
    )
    sport = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 5)),
            "primary_activity_type": "bike",
            "activity_duration_min": 55,
        }
    )

    assert payload["score"]["training_load"] == commute["training_load"]
    assert payload["score"]["training_load"] < sport["training_load"]
    assert payload["score"]["hard_sessions"] == 0
    assert "multiple hard sessions" not in payload["score"]["warnings"]


def test_garmin_all_day_cycling_recording_counts_as_commute(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, start_time_local_iso, name, activity_type, duration_min,
                moving_duration_min, distance_km, hard_session_est, aerobic_training_effect,
                anaerobic_training_effect, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "commute-day",
                "2026-05-05",
                "2026-05-05T07:07:00",
                "Vienna Cycling",
                "cycling",
                492.0,
                82.0,
                27.5,
                0,
                2.0,
                0.0,
                "sha",
                '{"elapsedDuration": 29967.9}',
            ),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2026-05-05")
    commute = scoring.score_entry(
        mobile_web._default_entry(mobile_web.dt.date(2026, 5, 5)),
        activity_rows=[{"date": "2026-05-05", "activity_type": "bike_commute", "duration_min": 82, "intensity": "moderate", "source": "garmin_activity"}],
    )

    assert payload["score"]["training_load"] == commute["training_load"]
    assert payload["score"]["hard_sessions"] == 0


def test_low_aerobic_garmin_hike_does_not_become_hard_session_just_because_garmin_flags_it(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, activity_type, duration_min, moving_duration_min,
                hard_session_est, aerobic_training_effect, anaerobic_training_effect,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            ("easy-hike", "2026-05-02", "hiking", 90.0, 76.0, 1, 0.4, 0.0, "sha"),
        )

    payload = mobile_web.get_entry_payload(store, date_value="2026-05-02")

    assert payload["score"]["training_load"] > 0
    assert payload["score"]["hard_sessions"] == 0
    assert "multiple hard sessions" not in payload["score"]["warnings"]


def test_approved_daily_summary_uses_garmin_activity_context(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, activity_type, duration_min, moving_duration_min,
                hard_session_est, aerobic_training_effect, anaerobic_training_effect,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            ("act-1", "2026-05-02", "running", 50.0, 45.0, 1, 3.1, 0.5, "sha"),
        )

    payload = mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Garmin recorded the run.",
                "sleep_ok": True,
                "nutrition_ok": True,
                "energy": 6,
                "mood": 6,
            },
        },
    )
    daily = store.fetch_one(
        "SELECT life_load_score, training_load, recovery_score, strain_score FROM derived_daily_summary WHERE date = ?",
        ("2026-05-02",),
    )

    assert payload["score"]["training_load"] > 0
    assert daily is not None
    assert daily["training_load"] > 0
    assert daily["life_load_score"] == pytest.approx(
        daily["strain_score"] + daily["training_load"] - daily["recovery_score"],
        abs=0.01,
    )


def test_manual_primary_activity_does_not_double_count_matching_garmin_activity(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, activity_type, duration_min, moving_duration_min,
                hard_session_est, aerobic_training_effect, anaerobic_training_effect,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            ("act-1", "2026-05-02", "running", 50.0, 45.0, 1, 3.1, 0.5, "sha"),
        )

    garmin_only = mobile_web.get_entry_payload(store, date_value="2026-05-02")
    with_manual_match = mobile_web.save_entry_payload(
        store,
        {
            "action": "draft",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Same run as Garmin.",
                "primary_activity_type": "run",
                "activity_duration_min": 45,
            },
        },
    )

    assert with_manual_match["score"]["training_load"] == garmin_only["score"]["training_load"]


def test_manual_crossfit_overrides_matching_garmin_strength_without_double_count(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_activity(
                activity_id, date, activity_type, duration_min, moving_duration_min,
                hard_session_est, aerobic_training_effect, anaerobic_training_effect,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            ("act-strength", "2026-05-02", "strength_training", 55.0, 50.0, 1, 2.4, 0.5, "sha"),
        )

    garmin_only = mobile_web.get_entry_payload(store, date_value="2026-05-02")
    with_manual_crossfit = mobile_web.save_entry_payload(
        store,
        {
            "action": "draft",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "CrossFit group session also recorded by Garmin as strength.",
                "primary_activity_type": "crossfit",
                "activity_duration_min": 50,
            },
        },
    )
    manual_only = scoring.score_entry(
        {
            **mobile_web._default_entry(mobile_web.dt.date(2026, 5, 2)),
            "primary_activity_type": "crossfit",
            "activity_duration_min": 50,
        }
    )

    assert garmin_only["score"]["training_load"] > 0
    assert with_manual_crossfit["score"]["training_load"] == manual_only["training_load"]
    assert with_manual_crossfit["score"]["training_load"] < garmin_only["score"]["training_load"] + manual_only["training_load"]
    assert with_manual_crossfit["score"]["hard_sessions"] == 1


def test_editing_prior_approved_day_updates_same_canonical_date(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {"date": "2026-05-01", "diary_text": "Initial", "diary_summary": "first", "mood": 5},
        },
    )

    payload = mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {"date": "2026-05-01", "diary_text": "Edited prior day text", "diary_summary": "edited", "mood": 6},
        },
    )

    assert payload["save_action"] == "updated"
    row = store.fetch_one("SELECT diary_text, diary_summary, mood FROM daily_log WHERE date = ?", ("2026-05-01",))
    assert row == {"diary_text": "Edited prior day text", "diary_summary": "edited", "mood": 6}
    history = mobile_web.history_payload(store, selected_date="2026-05-01")
    assert history["entries"][0]["diary_summary"] == "edited"


def test_repeated_approvals_do_not_json_nest_tags(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    first = mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {
                "date": "2026-05-01",
                "diary_text": "Tagged day",
                "diary_summary": "tagged",
                "tags": ["sleep-drift", "work-heavy"],
            },
        },
    )

    second = mobile_web.save_entry_payload(store, {"action": "approve", "entry": first["entry"]})
    third = mobile_web.save_entry_payload(store, {"action": "approve", "entry": second["entry"]})
    loaded = mobile_web.get_entry_payload(store, date_value="2026-05-01")
    row = store.fetch_one("SELECT tags FROM daily_log WHERE date = ?", ("2026-05-01",))

    assert third["entry"]["tags"] == ["sleep-drift", "work-heavy"]
    assert loaded["entry"]["tags"] == ["sleep-drift", "work-heavy"]
    assert row == {"tags": '["sleep-drift", "work-heavy"]'}


def test_existing_nested_json_tag_strings_are_flattened_on_load_and_save(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    nested = '["[\\"[\\\\\\"sleep-drift\\\\\\"]\\"]"]'
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO daily_log(
                date, completed, diary_text, diary_summary, tags, alcohol, binge, migraine_warning,
                work_intensity, other_symptoms, created_at, updated_at
            ) VALUES (?, 1, ?, ?, ?, 0, 0, 0, '', '', ?, ?)
            """,
            ("2026-05-01", "Nested tags", "nested", nested, "2026-05-01T00:00:00Z", "2026-05-01T00:00:00Z"),
        )

    loaded = mobile_web.get_entry_payload(store, date_value="2026-05-01")
    saved = mobile_web.save_entry_payload(store, {"action": "approve", "entry": loaded["entry"]})

    assert loaded["entry"]["tags"] == ["sleep-drift"]
    assert saved["entry"]["tags"] == ["sleep-drift"]
    assert store.fetch_one("SELECT tags FROM daily_log WHERE date = ?", ("2026-05-01",)) == {"tags": '["sleep-drift"]'}


def test_analyze_diary_creates_proposal_and_applies_it_to_active_draft(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)

    def _fake_codex(**kwargs):
        return {
            "ok": True,
            "content": json.dumps(
                {
                    "date": "2026-05-03",
                    "fields": {
                        "work_intensity": "heavy",
                        "nutrition_ok": True,
                        "phone_after_21": True,
                        "foot_pain": 6,
                    },
                    "summary": "Heavy work, clean food, late videos, foot pain.",
                    "red_flags": [{"type": "late_phone", "severity": "yellow", "evidence": "Watched videos late."}],
                    "next_action": "Protect shutdown tonight.",
                    "status": "pending",
                }
            ),
            "stderr": "",
        }

    original_runner = extraction.run_codex_oneshot
    extraction.run_codex_oneshot = _fake_codex
    try:
        payload = mobile_web.analyze_diary_payload(
            store,
            {
                "entry": {
                    "date": "2026-05-03",
                    "diary_text": "Heavy work, clean food, watched videos late, foot pain 6/10.",
                }
            },
        )
    finally:
        extraction.run_codex_oneshot = original_runner

    assert payload["entry_state"] == "draft"
    assert payload["entry"]["work_intensity"] == "heavy"
    assert payload["entry"]["nutrition_ok"] is True
    assert payload["entry"]["phone_after_21"] is True
    assert payload["entry"]["foot_pain"] == 6
    assert payload["proposal"]["summary"]
    proposal = store.fetch_latest_ai_proposal_for_date("2026-05-03")
    assert proposal is not None
    assert proposal["status"] == "applied_to_draft"


def test_dashboard_payload_contains_trend_drift_and_reviews_context(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    mobile_web.save_entry_payload(
        store,
        {
            "action": "approve",
            "entry": {
                "date": "2026-05-02",
                "diary_text": "Bad sleep, heavy work, late phone, project spillover.",
                "diary_summary": "drift day",
                "sleep_ok": False,
                "nutrition_ok": False,
                "stress": 8,
                "energy": 3,
                "phone_after_21": True,
                "project_overrun": True,
            },
        },
    )
    mobile_web.save_review_payload(
        store,
        {
            "review": {
                "date": "2026-05-03",
                "review_type": "weekly",
                "what_worked": "logged the day",
                "what_failed": "late phone",
                "notes": "keep the baseline boring",
            }
        },
    )

    payload = mobile_web.dashboard_payload(store, date_value="2026-05-03", weeks=4)

    assert payload["dashboard_state"] is not None
    assert "next_action" in payload["dashboard_state"]
    assert payload["trend"]["rows"]
    assert payload["drift"]["snapshot"] is not None
    assert payload["reviews"]["recent_reviews"]


def test_dashboard_payload_uses_latest_available_week_when_requested_week_is_empty(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    for day in range(4, 7):
        mobile_web.save_entry_payload(
            store,
            {
                "action": "approve",
                "entry": {
                    "date": f"2026-05-{day:02d}",
                    "diary_text": "steady baseline",
                    "sleep_ok": True,
                    "nutrition_ok": True,
                    "energy": 7,
                    "mood": 7,
                    "stress": 3,
                    "decompression_done": True,
                    "shutdown_done": True,
                },
            },
        )

    payload = mobile_web.dashboard_payload(store, date_value="2026-05-16", weeks=4)

    assert payload["date"] == "2026-05-16"
    assert payload["current_week"]["week_start"] == "2026-05-04"
    assert payload["dashboard_state"]["week_start"] == "2026-05-04"
    assert payload["dashboard_state"]["approved_days"] == ["2026-05-04", "2026-05-05", "2026-05-06"]


def test_dashboard_state_counts_imported_activity_for_approved_blank_day(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    mobile_web.save_entry_payload(store, {"action": "approve", "entry": {"date": "2026-05-05"}})
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO activity_log(
                date, activity_type, duration_min, intensity, hard_session,
                recovery_activity, notes, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-05-05", "walk", 35, "light", 0, 1, "imported", "garmin_activity", "2026-05-05T22:00:00Z"),
        )
    mobile_web.refresh_derived_for_date(store, "2026-05-05")

    payload = mobile_web.dashboard_payload(store, date_value="2026-05-05")

    assert payload["dashboard_state"]["approved_days"] == ["2026-05-05"]
    assert payload["dashboard_state"]["daily_summary_dates"] == ["2026-05-05"]


def test_weekly_replay_report_is_privacy_safe_and_actionable(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    private_phrase = "private family work diary phrase"
    for day in range(1, 4):
        mobile_web.save_entry_payload(
            store,
            {
                "action": "approve",
                "entry": {
                    "date": f"2026-05-{day:02d}",
                    "diary_text": f"{private_phrase} {day}",
                    "diary_summary": f"private summary {day}",
                    "sleep_ok": False,
                    "nutrition_ok": day == 1,
                    "stress": 8,
                    "energy": 3,
                    "phone_after_21": True,
                    "project_overrun": True,
                    "decompression_done": False,
                    "shutdown_done": False,
                },
            },
        )
    mobile_web.dashboard_payload(store, date_value="2026-05-03", weeks=4)

    report = mobile_web.weekly_replay_payload(store, date_value="2026-05-03", weeks=4)
    text = json.dumps(report, sort_keys=True)

    assert report["schema_version"] == "life_load_weekly_replay_report_v1"
    assert report["weeks_replayed"] >= 1
    assert report["approved_day_total"] == 3
    assert report["reports"][0]["approved_day_count"] == 3
    assert report["reports"][0]["one_correction"]
    assert report["privacy"] == {
        "contains_diary_text": False,
        "contains_diary_summary": False,
        "contains_raw_payload": False,
    }
    assert private_phrase not in text
    assert "private summary" not in text
    assert "\"diary_text\":" not in text
    assert "\"diary_summary\":" not in text


def test_trend_payload_contains_trainingpeaks_style_capacity_margin_and_risk(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.executemany(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, body_weight_kg_est_from_bmi, source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, 'weight-test', '{}', '2026-05-11T00:00:00Z')
            """,
            [
                ("2026-04-27", 100.0),
                ("2026-05-04", 100.6),
                ("2026-05-11", 101.4),
            ],
        )
    for day in range(1, 9):
        mobile_web.save_entry_payload(
            store,
            {
                "action": "approve",
                "entry": {
                    "date": f"2026-05-{day:02d}",
                    "diary_text": "steady baseline",
                    "sleep_ok": True,
                    "nutrition_ok": True,
                    "energy": 7,
                    "mood": 7,
                    "stress": 3,
                    "decompression_done": True,
                    "shutdown_done": True,
                },
            },
        )
    for day in range(9, 12):
        mobile_web.save_entry_payload(
            store,
            {
                "action": "approve",
                "entry": {
                    "date": f"2026-05-{day:02d}",
                    "diary_text": "late phone, project spillover, stress rising",
                    "sleep_ok": False,
                    "nutrition_ok": False,
                    "energy": 3,
                    "mood": 4,
                    "stress": 8,
                    "phone_after_21": True,
                    "project_overrun": True,
                    "decompression_done": False,
                    "shutdown_done": False,
                },
            },
        )

    payload = mobile_web.dashboard_payload(store, date_value="2026-05-11", weeks=4)
    features = payload["trend"]["rows"][-1]["features"]

    assert features["acute_load_7d"] > 0
    assert features["chronic_capacity_42d"] > 0
    assert features["life_margin_7d"] == pytest.approx(features["chronic_capacity_42d"] - features["acute_load_7d"], abs=0.02)
    assert features["weight_kg_latest"] == pytest.approx(101.4)
    assert features["weight_latest_days_old"] == 0
    assert features["weight_change_14d"] == pytest.approx(1.4)
    assert features["weight_change_30d"] == pytest.approx(1.4)
    assert features["weight_change_14d_usable"] is True
    assert features["weight_change_30d_usable"] is True
    assert 0 <= features["drift_risk_score"] <= 100
    assert features["recommended_mode"] in {"normal", "caution", "hold", "stabilize"}
    assert payload["drift"]["snapshot"]["mode"] in {"caution", "hold", "stabilize"}
    assert "weight trend rising" in payload["drift"]["snapshot"]["contributing_signals"]


def test_weight_drift_ignores_stale_or_sparse_weigh_ins(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    with store.connect() as conn, conn:
        conn.executemany(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, body_weight_kg_est_from_bmi, source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, 'weight-test', '{}', '2026-05-11T00:00:00Z')
            """,
            [
                ("2026-01-01", 99.0),
                ("2026-03-01", 101.5),
            ],
        )
    for day in range(5, 12):
        mobile_web.save_entry_payload(
            store,
            {
                "action": "approve",
                "entry": {
                    "date": f"2026-05-{day:02d}",
                    "diary_text": "steady baseline",
                    "sleep_ok": True,
                    "nutrition_ok": True,
                    "energy": 7,
                    "mood": 7,
                    "stress": 3,
                    "decompression_done": True,
                    "shutdown_done": True,
                },
            },
        )

    payload = mobile_web.dashboard_payload(store, date_value="2026-05-11", weeks=4)
    features = payload["trend"]["rows"][-1]["features"]

    assert features["weight_kg_latest"] == pytest.approx(101.5)
    assert features["weight_latest_days_old"] > 14
    assert features["weight_change_14d_usable"] is False
    assert features["weight_change_30d_usable"] is False
    assert "weight trend rising" not in payload["drift"]["snapshot"]["contributing_signals"]


def test_social_alcohol_does_not_count_as_alcohol_home_trend(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    for day in range(1, 4):
        mobile_web.save_entry_payload(
            store,
            {
                "action": "approve",
                "entry": {
                    "date": f"2026-05-{day:02d}",
                    "sleep_ok": True,
                    "nutrition_ok": True,
                    "alcohol": "social",
                    "energy": 7,
                    "mood": 7,
                    "stress": 3,
                    "decompression_done": True,
                    "shutdown_done": True,
                },
            },
        )

    payload = mobile_web.dashboard_payload(store, date_value="2026-05-03", weeks=4)
    features = payload["trend"]["rows"][-1]["features"]

    assert features["alcohol_home_count_30d"] == 0
    assert "recent alcohol exposure" not in payload["drift"]["snapshot"]["contributing_signals"]


def test_drift_caution_stack_with_hold_score_is_not_forced_red(tmp_path: Path) -> None:
    store = mobile_web.api_store(tmp_path)
    store.upsert_derived_trend_feature(
        {
            "date": "2026-05-09",
            "features_json": {
                "project_overrun_count_7d": 2,
                "binge_count_30d": 1,
                "alcohol_home_count_30d": 1,
                "drift_risk_score": 64.0,
                "weight_change_30d": 2.17,
                "weight_change_30d_usable": True,
                "life_margin_7d": 3.99,
                "recommended_mode": "hold",
            },
            "rules_version": "test",
            "calculated_at": "2026-05-10T00:00:00Z",
        }
    )

    mobile_web.rebuild_drift_snapshots(store)
    snapshot = store.fetch_drift_detection_snapshot("2026-05-09")

    assert snapshot is not None
    assert snapshot["risk_level"] == "orange"
    assert snapshot["mode"] == "hold"


def test_analyze_diary_uses_codex_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = mobile_web.api_store(tmp_path)
    monkeypatch.setenv("LIFE_LOAD_CODEX_TURN_CMD", "codex exec")

    def _fake_codex(**kwargs):
        assert kwargs["binding_type"] == "life_load"
        assert kwargs["binding_id"] == "2026-05-03"
        assert kwargs["timeout_s"] == 30
        assert "--model" in kwargs["command"]
        assert "gpt-5.4-mini" in kwargs["command"]
        assert any("model_reasoning_effort" in str(part) and "low" in str(part) for part in kwargs["command"])
        request = json.loads(kwargs["message"])
        assert request["output_contract"]["schema_version"] == extraction.OUTPUT_CONTRACT_VERSION
        assert "conversion_rules" in request["output_contract"]
        return {
            "ok": True,
            "content": """{
              "date": "2026-05-03",
              "fields": {
                "sleep_ok": false,
                "nutrition_ok": true,
                "stress": 7,
                "phone_after_21": true,
                "work_intensity": "heavy",
                "tags": ["work-heavy", "evening-drift"]
              },
              "summary": "Heavy work and late phone.",
              "red_flags": [{"type": "late_phone", "severity": "yellow", "evidence": "Videos after 21:00."}],
              "next_action": "Protect shutdown tonight.",
              "status": "pending"
            }""",
            "stderr": "",
            "stdout": "",
            "usage": {"total_tokens": 100},
            "exit_code": 0,
        }

    monkeypatch.setattr(extraction, "run_codex_oneshot", _fake_codex)

    payload = mobile_web.analyze_diary_payload(
        store,
        {"entry": {"date": "2026-05-03", "diary_text": "Heavy work and videos late."}},
    )

    assert payload["proposal"]["extractor_version"] == extraction.CODEX_EXTRACTOR_VERSION
    assert payload["proposal"]["extractor_model"] == "gpt-5.4-mini"
    assert payload["proposal"]["extractor_timeout_s"] == 30
    assert payload["proposal"]["contract_version"] == extraction.OUTPUT_CONTRACT_VERSION
    assert payload["extractor_model"] == "gpt-5.4-mini"
    assert payload["extractor_timeout_s"] == 30
    assert payload["entry"]["nutrition_ok"] is True
    assert payload["entry"]["work_intensity"] == "heavy"
    assert payload["entry"]["phone_after_21"] is True


def test_analyze_diary_coerces_common_codex_field_format_mistakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = mobile_web.api_store(tmp_path)

    def _messy_codex(**kwargs):
        return {
            "ok": True,
            "content": json.dumps(
                {
                    "date": "2026-05-03",
                    "fields": {
                        "sleep_ok": "no",
                        "nutrition_ok": "yes",
                        "stress": "7/10",
                        "foot_pain": "6/10",
                        "phone_after_21": "true",
                        "primary_activity_type": "running",
                        "activity_duration_min": "35 minutes",
                        "work_intensity": "very heavy",
                        "after_work_decompression_done": "no",
                        "evening_chain_broken": "yes",
                        "wife_conflict_count": "2 fights",
                        "wife_conflict_school": "yes",
                        "alone_home": "yes",
                        "tags": ["Work Heavy", "late_phone"],
                        "unknown_model_field": "ignored",
                    },
                    "summary": "Heavy day with run and late phone.",
                    "red_flags": [
                        {"type": "late_phone", "severity": "YELLOW", "evidence": "late phone"},
                        {"type": "nonsense", "severity": "red", "evidence": "ignored"},
                    ],
                    "next_action": "Protect shutdown.",
                    "status": "pending",
                }
            ),
            "stderr": "",
            "stdout": "",
            "usage": {},
            "exit_code": 0,
        }

    monkeypatch.setattr(extraction, "run_codex_oneshot", _messy_codex)

    payload = mobile_web.analyze_diary_payload(
        store,
        {"entry": {"date": "2026-05-03", "diary_text": "Very heavy work, ran 35 minutes, late phone, foot pain 6/10."}},
    )

    assert payload["entry"]["sleep_ok"] is False
    assert payload["entry"]["nutrition_ok"] is True
    assert payload["entry"]["stress"] == 7
    assert payload["entry"]["foot_pain"] == 6
    assert payload["entry"]["phone_after_21"] is True
    assert payload["entry"]["primary_activity_type"] == "run"
    assert payload["entry"]["activity_duration_min"] == 35
    assert payload["entry"]["work_intensity"] == "heavy"
    assert payload["entry"]["after_work_decompression_done"] is False
    assert payload["entry"]["evening_chain_broken"] is True
    assert payload["entry"]["wife_conflict_count"] == 2
    assert payload["entry"]["wife_conflict_school"] is True
    assert payload["entry"]["alone_home"] is True
    assert payload["entry"]["tags"] == ["work-heavy", "late-phone"]
    assert payload["proposal"]["red_flags"] == [{"type": "late_phone", "severity": "yellow", "evidence": "late phone"}]
    assert "unknown_field:unknown_model_field" in payload["proposal"]["validation_issues"]
    assert "unknown_red_flag:nonsense" in payload["proposal"]["validation_issues"]


def test_analyze_diary_reports_error_on_invalid_codex_json_without_heuristic_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = mobile_web.api_store(tmp_path)

    def _bad_codex(**kwargs):
        return {"ok": True, "content": "not json", "stderr": "", "stdout": "", "usage": {}, "exit_code": 0}

    monkeypatch.setattr(extraction, "run_codex_oneshot", _bad_codex)

    with pytest.raises(Exception):
        mobile_web.analyze_diary_payload(
            store,
            {"entry": {"date": "2026-05-03", "diary_text": "Clean food, watched videos late."}},
        )


def test_diary_analysis_requires_background_ai_worker() -> None:
    with pytest.raises(ValueError):
        extraction.analyze_diary_entry(
            date="2026-05-03",
            diary_text=(
                "Heavy work. Two fights with wife about son's homework and school. "
                "I was alone at home. No decompression after work and the evening went off rails into junk food."
            ),
        )
