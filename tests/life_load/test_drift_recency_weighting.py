from __future__ import annotations

from life_load import drift


def _base_features(**overrides: object) -> dict[str, object]:
    features: dict[str, object] = {
        "sleep_compliance_7d": 1.0,
        "nutrition_compliance_7d": 1.0,
        "recovery_compliance_7d": 1.0,
        "life_load_rolling_avg_7d": 6.0,
        "life_margin_7d": 4.0,
        "drift_risk_score": 20.0,
        "recommended_mode": "normal",
        "red_flag_count_7d": 0,
    }
    features.update(overrides)
    return features


def test_fading_project_spillover_is_lower_severity_than_active_pattern() -> None:
    fading = drift._classify(
        _base_features(
            project_overrun_count_7d=3,
            project_overrun_weighted_7d=0.86,
            project_overrun_recent_count_3d=0,
            project_overrun_older_count_4_to_7d=3,
            project_overrun_trend="fading",
        )
    )
    active = drift._classify(
        _base_features(
            project_overrun_count_7d=3,
            project_overrun_weighted_7d=2.55,
            project_overrun_recent_count_3d=3,
            project_overrun_older_count_4_to_7d=0,
            project_overrun_trend="recent",
        )
    )

    assert "project spillover fading" in fading["contributing_signals"]
    assert "project spillover active" not in fading["contributing_signals"]
    assert fading["risk_level"] == "green"
    assert "project spillover active" in active["contributing_signals"]
    assert active["risk_level"] == "yellow"


def test_recent_late_phone_is_active_but_old_late_phone_can_fade() -> None:
    active = drift._classify(
        _base_features(
            phone_after_21_count_7d=2,
            phone_after_21_weighted_7d=1.55,
            phone_after_21_recent_count_3d=2,
            phone_after_21_older_count_4_to_7d=0,
        )
    )
    fading = drift._classify(
        _base_features(
            phone_after_21_count_7d=2,
            phone_after_21_weighted_7d=0.46,
            phone_after_21_recent_count_3d=0,
            phone_after_21_older_count_4_to_7d=2,
        )
    )

    assert "late phone active" in active["contributing_signals"]
    assert "late phone active" not in fading["contributing_signals"]
    assert fading["risk_level"] == "green"


def test_alcohol_context_does_not_escalate_by_itself() -> None:
    result = drift._classify(_base_features(alcohol_home_count_30d=1))

    assert "recent alcohol exposure" not in result["contributing_signals"]
    assert "alcohol recovery context" not in result["contributing_signals"]
    assert result["risk_level"] == "green"


def test_alcohol_context_can_contribute_with_poor_recovery() -> None:
    result = drift._classify(
        _base_features(
            alcohol_home_count_30d=1,
            recovery_compliance_7d=0.25,
        )
    )

    assert "recent alcohol exposure" not in result["contributing_signals"]
    assert "alcohol recovery context" in result["contributing_signals"]
    assert result["risk_level"] == "yellow"


def test_operator_case_softens_stale_counts_but_keeps_recent_counts_active() -> None:
    older = drift._classify(
        _base_features(
            project_overrun_count_7d=3,
            project_overrun_weighted_7d=0.86,
            project_overrun_recent_count_3d=0,
            project_overrun_older_count_4_to_7d=3,
            phone_after_21_count_7d=2,
            phone_after_21_weighted_7d=0.46,
            phone_after_21_recent_count_3d=0,
            phone_after_21_older_count_4_to_7d=2,
            alcohol_home_count_30d=0,
            drift_risk_score=36.3,
            recommended_mode="caution",
        )
    )
    recent = drift._classify(
        _base_features(
            project_overrun_count_7d=3,
            project_overrun_weighted_7d=1.55,
            project_overrun_recent_count_3d=2,
            project_overrun_older_count_4_to_7d=0,
            phone_after_21_count_7d=2,
            phone_after_21_weighted_7d=1.85,
            phone_after_21_recent_count_3d=2,
            phone_after_21_older_count_4_to_7d=0,
            drift_risk_score=44.9,
            recommended_mode="caution",
        )
    )

    assert older["risk_level"] == "yellow"
    assert "project spillover fading" in older["contributing_signals"]
    assert "late phone fading" in older["contributing_signals"]
    assert "alcohol recovery context" not in older["contributing_signals"]
    assert "project spillover active" in recent["contributing_signals"]
    assert "late phone active" in recent["contributing_signals"]
    assert len(recent["contributing_signals"]) >= len(older["contributing_signals"])
