from __future__ import annotations

import json
import datetime as dt
from pathlib import Path

import pytest

from life_load import garmin_connect_probe as probe
from life_load.sqlite_core import HealthObservabilityStore


class FakeGarminClient:
    def get_stats(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"totalSteps": 12345, "activeKilocalories": 710}

    def get_user_summary(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"totalSteps": 11111}

    def get_heart_rates(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"restingHeartRate": 54}

    def get_resting_heart_rate(self, date_text: str) -> int:
        assert date_text == "2026-05-04"
        return 55

    def get_sleep_data(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"dailySleepDTO": {"sleepTimeSeconds": 7 * 3600}}

    def get_all_day_stress(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"avgStressLevel": 42}

    def get_stress_data(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"averageStressLevel": 41}

    def get_body_battery(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        assert start_date == "2026-05-04"
        assert end_date == "2026-05-04"
        return [{"charged": 20, "drained": 50}]

    def get_activities_by_date(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        assert start_date == "2026-05-04"
        assert end_date == "2026-05-04"
        return [{"activityId": 1}, {"activityId": 2}]

    def get_activities_fordate(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"ActivitiesForDay": {"payload": [{"activityId": 1}, {"activityId": 2}], "successful": True}}

    def get_steps_data(self, date_text: str) -> list[dict[str, object]]:
        assert date_text == "2026-05-04"
        return [{"steps": 12000}, {"steps": 345}]

    def get_intensity_minutes_data(self, date_text: str) -> dict[str, object]:
        assert date_text == "2026-05-04"
        return {"moderateMinutes": 20, "vigorousMinutes": 10, "endDayMinutes": 40}


class PartialFailureClient(FakeGarminClient):
    def get_sleep_data(self, date_text: str) -> dict[str, object]:
        raise RuntimeError("sleep endpoint unavailable")


class MissingMethodClient:
    def get_stats(self, date_text: str) -> dict[str, object]:
        return {"steps": "9876"}


class ActivityClient(FakeGarminClient):
    def get_activities_by_date(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        assert start_date == "2026-05-04"
        assert end_date == "2026-05-04"
        return [
            {
                "activityId": 123,
                "activityName": "Vienna Cycling",
                "activityType": {"typeKey": "cycling"},
                "sportType": {"typeKey": "cycling"},
                "startTimeLocal": "2026-05-04 07:10:00",
                "duration": 1800,
                "movingDuration": 1740,
                "distance": 9000,
                "averageHR": 121,
                "maxHR": 150,
                "aerobicTrainingEffect": 2.1,
                "calories": 320,
            }
        ]


def test_fetch_day_bundle_summarizes_daily_health_signals() -> None:
    bundle = probe.fetch_day_bundle(FakeGarminClient(), "2026-05-04")
    summary = probe.summarize_day_bundle(bundle)

    assert summary["steps"] == 12345
    assert summary["steps_source"] == "steps_data"
    assert summary["stats_steps"] == 12345
    assert summary["interval_steps"] == 12345
    assert summary["active_kcal"] == 710
    assert summary["resting_hr"] == 54
    assert summary["avg_stress"] == 42
    assert summary["sleep_total_min"] == 420
    assert summary["activity_count"] == 2
    assert set(summary["successful_calls"]) == {
        "stats",
        "user_summary",
        "heart_rates",
        "resting_heart_rate",
        "sleep",
        "all_day_stress",
        "stress",
        "body_battery",
        "activities",
        "activities_for_day",
        "steps_data",
        "intensity_minutes",
    }
    assert summary["failed_calls"] == {}


def test_endpoint_failure_is_captured_without_losing_other_calls() -> None:
    bundle = probe.fetch_day_bundle(PartialFailureClient(), "2026-05-04")
    summary = probe.summarize_day_bundle(bundle)

    assert summary["steps"] == 12345
    assert summary["sleep_total_min"] is None
    assert summary["failed_calls"] == {"sleep": "sleep endpoint unavailable"}
    assert "stats" in summary["successful_calls"]


def test_missing_library_methods_are_reported_as_skipped() -> None:
    bundle = probe.fetch_day_bundle(MissingMethodClient(), "2026-05-04")
    summary = probe.summarize_day_bundle(bundle)

    assert summary["steps"] == 9876
    assert "sleep" in summary["skipped_calls"]
    assert "activities" in summary["skipped_calls"]
    assert "steps_data" in summary["skipped_calls"]
    assert summary["failed_calls"] == {}


def test_malformed_raw_bundle_summarizes_closed_without_crashing() -> None:
    summary = probe.summarize_day_bundle({"date": "2026-05-04", "calls": ["not", "a", "mapping"]})

    assert summary["date"] == "2026-05-04"
    assert summary["steps"] is None
    assert summary["successful_calls"] == []
    assert summary["failed_calls"] == {}
    assert summary["skipped_calls"] == []


def test_write_probe_artifact_stays_under_runtime_state(tmp_path: Path) -> None:
    output_dir = tmp_path / probe.DEFAULT_OUTPUT_REL
    output_path = probe.write_probe_artifact(
        output_dir,
        "2026-05-04",
        {"summary": {"steps": 123}, "raw_bundle": {"calls": {}}},
    )

    assert output_path == output_dir / "2026-05-04.json"
    assert json.loads(output_path.read_text(encoding="utf-8"))["summary"]["steps"] == 123
    assert output_dir.stat().st_mode & 0o777 == 0o700
    assert output_path.stat().st_mode & 0o777 == 0o600


def test_harden_private_path_tightens_token_tree_permissions(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    nested_dir = token_dir / "nested"
    token_file = nested_dir / "garmin_tokens.json"
    nested_dir.mkdir(parents=True)
    token_file.write_text("{}", encoding="utf-8")
    token_dir.chmod(0o755)
    nested_dir.chmod(0o755)
    token_file.chmod(0o644)

    probe.harden_private_path(token_dir)

    assert token_dir.stat().st_mode & 0o777 == 0o700
    assert nested_dir.stat().st_mode & 0o777 == 0o700
    assert token_file.stat().st_mode & 0o777 == 0o600


def test_import_recent_days_from_client_upserts_without_duplicate_rows(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)

    first = probe.import_recent_days_from_client(store, ActivityClient(), end_date="2026-05-04", days=1)
    second = probe.import_recent_days_from_client(store, ActivityClient(), end_date="2026-05-04", days=1)

    assert first["passive_upserted"] == 1
    assert first["activity_upserted"] == 1
    assert second["passive_upserted"] == 1
    assert second["activity_upserted"] == 1
    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_daily_passive_summary") == {"c": 1}
    assert store.fetch_one("SELECT COUNT(*) AS c FROM garmin_activity") == {"c": 1}
    passive = store.fetch_garmin_passive_summary("2026-05-04")
    assert passive is not None
    assert passive["wellness_steps"] == 12345
    assert passive["activity_count"] == 1
    assert passive["activity_total_duration_min"] == 30.0
    assert passive["raw_json"]["source_confidence"]["steps"]["source"] == "steps_data"
    activity = store.fetch_one("SELECT * FROM garmin_activity WHERE activity_id = ?", ("123",))
    assert activity is not None
    assert activity["date"] == "2026-05-04"
    assert activity["activity_type"] == "cycling"
    assert activity["distance_km"] == 9.0
    latest = store.fetch_latest_garmin_live_import_batch()
    assert latest is not None
    assert latest["mode"] == "manual"
    assert latest["days_imported"] == 1
    assert latest["passive_unchanged"] == 1
    assert latest["activity_unchanged"] == 1
    assert latest["endpoint_status_json"]["2026-05-04"]["source_confidence"]["steps"]["source"] == "steps_data"


def test_dates_needing_import_uses_missing_and_stale_passive_rows(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)
    store.migrate()
    with store.connect() as conn, conn:
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, source_sha256, raw_json, updated_at
            ) VALUES (?, 1, 'old', '{}', ?)
            """,
            ("2026-05-03", "2026-05-04T08:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, source_sha256, raw_json, updated_at
            ) VALUES (?, 1, 'fresh', '{}', ?)
            """,
            ("2026-05-04", "2026-05-04T11:30:00Z"),
        )

    stale = probe.dates_needing_import(
        store,
        end_date="2026-05-04",
        days=3,
        max_age_minutes=180,
        now=dt.datetime(2026, 5, 4, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert stale == ["2026-05-02", "2026-05-03"]


def test_import_recent_days_if_stale_skips_when_tokenstore_missing(tmp_path: Path) -> None:
    store = HealthObservabilityStore(repo_root=tmp_path)

    result = probe.import_recent_days_if_stale(
        store,
        end_date="2026-05-04",
        days=1,
        tokenstore=str(tmp_path / "missing_tokens"),
    )

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["skipped_reason"] == "missing_tokenstore"
    assert result["stale_dates"] == ["2026-05-04"]
    latest = store.fetch_latest_garmin_live_import_batch()
    assert latest is not None
    assert latest["mode"] == "auto"
    assert latest["skipped"] == 1
    assert latest["skipped_reason"] == "missing_tokenstore"


def test_invalid_date_fails_before_touching_network() -> None:
    with pytest.raises(probe.GarminConnectProbeError, match="Invalid date"):
        probe.parse_date_text("04-05-2026")
