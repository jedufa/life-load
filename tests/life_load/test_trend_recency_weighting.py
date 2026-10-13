from __future__ import annotations

import datetime as dt
from typing import Any

from life_load import trends


def _row(days_ago: int, **signals: Any) -> dict[str, Any]:
    target = dt.date(2026, 5, 10)
    return {
        "date": (target - dt.timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "sleep_ok": 1,
        "nutrition_ok": 1,
        "recovery_score": 10.0,
        "life_load_score": 8.0,
        "training_load": 0.0,
        "strain_score": 0.0,
        "red_flags": "[]",
        "shutdown_done": 1,
        "decompression_done": 1,
        **signals,
    }


def test_same_late_phone_count_has_higher_weight_when_recent() -> None:
    target = dt.date(2026, 5, 10)
    recent = trends._feature_row([_row(1, phone_after_21=1), _row(2, phone_after_21=1)], target_date=target)
    older = trends._feature_row([_row(5, phone_after_21=1), _row(6, phone_after_21=1)], target_date=target)

    assert recent["phone_after_21_count_7d"] == older["phone_after_21_count_7d"] == 2
    assert recent["phone_after_21_weighted_7d"] > older["phone_after_21_weighted_7d"]
    assert recent["drift_risk_score"] > older["drift_risk_score"]
    assert recent["phone_after_21_trend"] == "recent"
    assert older["phone_after_21_trend"] == "fading"


def test_older_project_spillover_keeps_count_but_marks_fading() -> None:
    target = dt.date(2026, 5, 10)
    rows = [
        _row(6, project_overrun=1),
        _row(5, project_overrun=1),
        _row(4, project_overrun=1),
        _row(2),
        _row(1),
        _row(0),
    ]

    features = trends._feature_row(rows, target_date=target)

    assert features["project_overrun_count_7d"] == 3
    assert features["project_overrun_recent_count_3d"] == 0
    assert features["project_overrun_older_count_4_to_7d"] == 3
    assert features["project_overrun_trend"] == "fading"


def test_recent_project_spillover_marks_active_recency() -> None:
    target = dt.date(2026, 5, 10)
    rows = [_row(2, project_overrun=1), _row(1, project_overrun=1), _row(0, project_overrun=1)]

    features = trends._feature_row(rows, target_date=target)

    assert features["project_overrun_recent_count_3d"] == 3
    assert features["project_overrun_trend"] == "recent"
    assert features["project_overrun_weighted_7d"] >= 2.5


def test_same_weekly_count_is_milder_when_signals_are_stale() -> None:
    target = dt.date(2026, 5, 10)
    older_with_recent_recovery = [
        _row(6, project_overrun=1, phone_after_21=1, alcohol=2),
        _row(5, project_overrun=1, phone_after_21=1, alcohol=2),
        _row(4, project_overrun=1, alcohol=2),
        _row(2, alcohol=2),
        _row(1, alcohol=2),
        _row(0, alcohol=2),
    ]
    recent_worsening = [
        _row(6, alcohol=2),
        _row(5, alcohol=2),
        _row(4, alcohol=2),
        _row(2, project_overrun=1, alcohol=2),
        _row(1, project_overrun=1, phone_after_21=1, alcohol=2),
        _row(0, project_overrun=1, phone_after_21=1, alcohol=2),
    ]

    older = trends._feature_row(older_with_recent_recovery, target_date=target)
    recent = trends._feature_row(recent_worsening, target_date=target)

    assert older["project_overrun_count_7d"] == recent["project_overrun_count_7d"] == 3
    assert older["phone_after_21_count_7d"] == recent["phone_after_21_count_7d"] == 2
    assert older["project_overrun_trend"] == "fading"
    assert older["phone_after_21_trend"] == "fading"
    assert recent["project_overrun_trend"] == "recent"
    assert recent["phone_after_21_trend"] == "recent"
    assert recent["project_overrun_weighted_7d"] > older["project_overrun_weighted_7d"]
    assert recent["phone_after_21_weighted_7d"] > older["phone_after_21_weighted_7d"]
    assert recent["drift_risk_score"] > older["drift_risk_score"]
