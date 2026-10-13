import json
from pathlib import Path

from life_load.engine import LifeLoadStore, dashboard_payload, save_entry_payload, get_entry_payload


def test_running_caps_and_hard_sessions(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(store, {"entry": {"date": "2026-04-27", "completed": True, "run": True, "run_distance_km": 50}})
    payload = dashboard_payload(store, date_value="2026-04-27", weeks=1)
    week = payload["current_week"]
    assert week["run_sessions"] == 1
    assert week["max_run_km"] == 50
    assert week["weekly_run_km"] == 50
    assert week["hard_sessions"] == 1
    assert week["status"] == "Red"
    assert "run distance cap" in week["running_cap_status"].lower()


def test_completed_days_are_not_hard_sessions(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    for day in range(4, 11):
        save_entry_payload(store, {"entry": {"date": f"2026-05-{day:02d}", "completed": True, "sleep_on_time": True, "nutrition_clean": True}})
    week = dashboard_payload(store, date_value="2026-05-04", weeks=1)["current_week"]
    assert week["completed_days"] == 7
    assert week["run_sessions"] == 0
    assert week["crossfit_sessions"] == 0
    assert week["hard_sessions"] == 0


def test_weekend_homework_na_is_neutral(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(store, {"entry": {"date": "2026-05-02", "completed": True, "homework_done": "No"}})
    payload = get_entry_payload(store, date_value="2026-05-02")
    assert payload["entry"]["homework_done"] == "N/A"
    assert payload["score"]["field_status"]["homework_done"]["level"] == "neutral"


def test_alcohol_home_is_red_override(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(store, {"entry": {"date": "2026-05-01", "completed": True, "alcohol": "Home"}})
    week = dashboard_payload(store, date_value="2026-05-01", weeks=1)["current_week"]
    assert week["alcohol_at_home"] == 1
    assert week["status"] == "Red"


def test_hard_sessions_equal_runs_plus_crossfit(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(store, {"entry": {"date": "2026-05-04", "completed": True, "run": True, "run_distance_km": 4}})
    save_entry_payload(store, {"entry": {"date": "2026-05-05", "completed": True, "run": True, "run_distance_km": 5}})
    save_entry_payload(store, {"entry": {"date": "2026-05-06", "completed": True, "crossfit": True}})
    week = dashboard_payload(store, date_value="2026-05-06", weeks=1)["current_week"]
    assert week["run_sessions"] == 2
    assert week["crossfit_sessions"] == 1
    assert week["hard_sessions"] == 3


def test_future_blank_days_are_ignored_in_current_week_targets(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(
        store,
        {"entry": {"date": "2026-05-04", "completed": True, "sleep_on_time": True, "nutrition_clean": True, "shutdown_done": True}},
    )
    week = dashboard_payload(store, date_value="2026-05-04", weeks=1)["current_week"]
    assert week["completed_days"] == 1
    assert week["targets_applied"]["elapsed_days"] == 1
    assert week["success_items"]["sleep"] is True
    assert week["success_items"]["nutrition"] is True
    assert week["success_items"]["review"] is True


def test_blank_week_is_missing_data_not_success(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    week = dashboard_payload(store, date_value="2026-05-04", weeks=1)["current_week"]
    assert week["completed_days"] == 0
    assert week["success_score"] == 0.0
    assert all(flag is False for flag in week["success_items"].values())
    assert week["next_action"] == "Complete one real day first. Treat blank weeks as missing data, not success."
    assert "No completed days recorded" in week["warnings"]


def test_editing_existing_entry_overwrites_json_and_appends_update_event(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(store, {"entry": {"date": "2026-05-04", "completed": True, "nutrition_clean": False}})
    updated = save_entry_payload(store, {"entry": {"date": "2026-05-04", "completed": True, "nutrition_clean": True}})
    entry = get_entry_payload(store, date_value="2026-05-04")
    assert updated["save_action"] == "updated"
    assert entry["entry"]["nutrition_clean"] is True
    lines = [json.loads(line) for line in store.events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [line["event_type"] for line in lines] == ["entry_created", "entry_updated"]


def test_dashboard_current_week_contains_next_action(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    save_entry_payload(store, {"entry": {"date": "2026-05-04", "completed": True}})
    week = dashboard_payload(store, date_value="2026-05-04", weeks=1)["current_week"]
    assert isinstance(week["next_action"], str)
    assert week["next_action"]


def test_three_run_sessions_is_warning_not_ok(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    for index, day in enumerate((4, 5, 6), start=1):
        save_entry_payload(store, {"entry": {"date": f"2026-05-{day:02d}", "completed": True, "run": True, "run_distance_km": 5}})
    week = dashboard_payload(store, date_value="2026-05-06", weeks=1)["current_week"]
    assert week["run_sessions"] == 3
    assert week["status"] == "Orange"
    assert "running cap exceeded" in week["running_cap_status"].lower()


def test_four_run_sessions_is_red(tmp_path: Path) -> None:
    store = LifeLoadStore(repo_root=tmp_path)
    for day in (4, 5, 6, 7):
        save_entry_payload(store, {"entry": {"date": f"2026-05-{day:02d}", "completed": True, "run": True, "run_distance_km": 5}})
    week = dashboard_payload(store, date_value="2026-05-07", weeks=1)["current_week"]
    assert week["run_sessions"] == 4
    assert week["status"] == "Red"
    assert "too many run sessions" in week["running_cap_status"].lower()
