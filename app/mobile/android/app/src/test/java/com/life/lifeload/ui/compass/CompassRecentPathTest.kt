package com.life.lifeload.ui.compass

import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.domain.LifeLoadTrendPoint
import com.life.lifeload.ui.LifeLoadUiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

class CompassRecentPathTest {
  @Test
  fun simplePathUsesDailyZoneBeforeRollingRisk() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-09",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-03", zone = "green", approvedAt = "2026-05-03T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-04", zone = "yellow", approvedAt = "2026-05-04T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-05", zone = "red", approvedAt = "2026-05-05T21:00:00Z"),
        ),
        trendPoints = (0..6).map { offset ->
          LifeLoadTrendPoint(
            date = "2026-05-0${3 + offset}",
            driftRiskScore = 100.0,
          )
        },
      ),
    )

    val scores = recentPathPointsForTest(state).map { it?.pathScore }

    assertEquals(20.0, scores[0] ?: 0.0, 0.001)
    assertEquals(45.0, scores[1] ?: 0.0, 0.001)
    assertEquals(85.0, scores[2] ?: 0.0, 0.001)
    assertEquals(100.0, scores[3] ?: 0.0, 0.001)
  }

  @Test
  fun simplePathPreservesMissingCalendarDays() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-09",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-03", zone = "green", approvedAt = "2026-05-03T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-09", zone = "yellow", approvedAt = "2026-05-09T21:00:00Z"),
        ),
        trendPoints = listOf(
          LifeLoadTrendPoint(date = "2026-05-03", driftRiskScore = 100.0),
          LifeLoadTrendPoint(date = "2026-05-09", driftRiskScore = 100.0),
        ),
      ),
    )

    val points = recentPathPointsForTest(state)

    assertEquals(7, points.size)
    assertEquals("2026-05-03", points[0]?.date)
    assertNull(points[1])
    assertNull(points[5])
    assertEquals("2026-05-09", points[6]?.date)
  }

  @Test
  fun simplePathPlotsLocalHistoryWhenBackendTrendPointsAreMissing() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-09",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-06", state = "pending_approval", canonicalCompleted = true, zone = "green"),
          LifeLoadHistoryDay(date = "2026-05-07", state = "pending_approval", canonicalCompleted = true, zone = "yellow"),
          LifeLoadHistoryDay(date = "2026-05-08", state = "pending_approval", canonicalCompleted = true, zone = "red"),
          LifeLoadHistoryDay(date = "2026-05-09", state = "pending_approval", canonicalCompleted = true, zone = ""),
        ),
      ),
    )

    val points = recentPathPointsForTest(state)

    assertEquals(4, points.filterNotNull().size)
    assertEquals("2026-05-06", points[3]?.date)
    assertEquals(20.0, points[3]?.pathScore ?: 0.0, 0.001)
    assertEquals(45.0, points[4]?.pathScore ?: 0.0, 0.001)
    assertEquals(85.0, points[5]?.pathScore ?: 0.0, 0.001)
    assertEquals(45.0, points[6]?.pathScore ?: 0.0, 0.001)
  }

  @Test
  fun simplePathKeepsSelectedDateWindowWhenRecentDaysHaveNoData() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-16",
        historyDays = (4..10).map { day ->
          LifeLoadHistoryDay(
            date = "2026-05-${day.toString().padStart(2, '0')}",
            zone = "yellow",
            approvedAt = "2026-05-${day.toString().padStart(2, '0')}T21:00:00Z",
          )
        },
        trendPoints = (4..10).map { day ->
          LifeLoadTrendPoint(
            date = "2026-05-${day.toString().padStart(2, '0')}",
            driftRiskScore = 45.0,
          )
        },
      ),
    )

    val points = recentPathPointsForTest(state)

    assertEquals("2026-05-10", points.first()?.date)
    assertNull(points[1])
    assertNull(points.last())
    assertEquals(1, points.filterNotNull().size)
  }

  @Test
  fun simplePathMissingRecentDaysMoveLeftAsDashboardDateAdvances() {
    fun stateFor(date: String) = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = date,
        historyDays = (14..16).map { day ->
          LifeLoadHistoryDay(
            date = "2026-05-$day",
            zone = "yellow",
            approvedAt = "2026-05-${day}T21:00:00Z",
          )
        },
        trendPoints = (14..16).map { day ->
          LifeLoadTrendPoint(
            date = "2026-05-$day",
            driftRiskScore = 45.0,
          )
        },
      ),
    )

    val may17 = recentPathPointsForTest(stateFor("2026-05-17"))
    val may18 = recentPathPointsForTest(stateFor("2026-05-18"))

    assertEquals("2026-05-14", may17[3]?.date)
    assertEquals("2026-05-16", may17[5]?.date)
    assertNull(may17[6])
    assertEquals("2026-05-14", may18[2]?.date)
    assertEquals("2026-05-16", may18[4]?.date)
    assertNull(may18[5])
    assertNull(may18[6])
  }

  @Test
  fun simplePathPreviewAnchorCanMoveWithoutChangingDashboardDate() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = (14..16).map { day ->
          LifeLoadHistoryDay(
            date = "2026-05-$day",
            zone = "yellow",
            approvedAt = "2026-05-${day}T21:00:00Z",
          )
        },
        trendPoints = (14..16).map { day ->
          LifeLoadTrendPoint(
            date = "2026-05-$day",
            driftRiskScore = 45.0,
          )
        },
      ),
    )

    val committedWindow = recentPathPointsForTest(state)
    val previewWindow = recentPathPointsForTest(state, LocalDate.parse("2026-05-18"))

    assertEquals("2026-05-14", committedWindow[3]?.date)
    assertEquals("2026-05-16", committedWindow[5]?.date)
    assertNull(committedWindow[6])
    assertEquals("2026-05-14", previewWindow[2]?.date)
    assertEquals("2026-05-16", previewWindow[4]?.date)
    assertNull(previewWindow[5])
    assertNull(previewWindow[6])
  }

  @Test
  fun simplePathIgnoresFutureFixtureHistoryRows() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-16",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2032-02-04", zone = "red", approvedAt = "2032-02-04T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-10", zone = "yellow", approvedAt = "2026-05-10T21:00:00Z"),
        ),
        trendPoints = listOf(
          LifeLoadTrendPoint(date = "2026-05-10", driftRiskScore = 45.0),
          LifeLoadTrendPoint(date = "2032-02-04", driftRiskScore = 100.0),
        ),
      ),
    )

    val points = recentPathPointsForTest(state)

    assertEquals("2026-05-10", points.first()?.date)
    assertEquals(45.0, points.first()?.pathScore ?: 0.0, 0.001)
    assertNull(points.last())
  }

  @Test
  fun recentPathSummaryMarksOlderSignalsAsImprovedRecently() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-09",
        trendPoints = listOf(
          LifeLoadTrendPoint(
            date = "2026-05-09",
            phoneAfter21Count7d = 2,
            phoneAfter21RecentCount3d = 0,
            phoneAfter21OlderCount4To7d = 2,
            projectOverrunCount7d = 3,
            projectOverrunRecentCount3d = 0,
            projectOverrunOlderCount4To7d = 3,
          ),
        ),
      ),
    )

    val point = recentPathPointsForTest(state).last()

    assertEquals("Late phone improved recently and project spillover improved recently", point?.summary)
  }

  @Test
  fun guidanceThresholdCountsRecentApprovedEntriesAcrossCurrentWeekBoundary() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-08", zone = "yellow", approvedAt = "2026-05-08T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-10", zone = "yellow", approvedAt = "2026-05-10T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-16", zone = "red", approvedAt = "2026-05-16T21:00:00Z"),
        ),
      ),
    )

    assertEquals(3, recentGuidanceApprovedDayCount(state))
  }

  @Test
  fun guidanceThresholdIgnoresApprovedEntriesOutsideRecentWindow() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-07", zone = "yellow", approvedAt = "2026-05-07T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-10", zone = "yellow", approvedAt = "2026-05-10T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-16", zone = "red", approvedAt = "2026-05-16T21:00:00Z"),
        ),
      ),
    )

    assertEquals(2, recentGuidanceApprovedDayCount(state))
  }

  @Test
  fun guidanceThresholdIncludesSelectedPendingLocalApproval() {
    val state = LifeLoadUiState(
      selectedDate = "2026-05-17",
      entryState = "pending_approval",
      hasDraft = true,
      approvedAt = "",
      score = LifeLoadScore(zone = "green"),
      scoreAvailable = true,
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-10", zone = "yellow", approvedAt = "2026-05-10T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-16", zone = "red", approvedAt = "2026-05-16T21:00:00Z"),
        ),
      ),
    )

    assertEquals(3, recentGuidanceApprovedDayCount(state))
    assertEquals(
      listOf("2026-05-17", "2026-05-16", "2026-05-10"),
      recentGuidanceApprovedDates(state).map { it.toString() },
    )
  }

  @Test
  fun guidanceDoesNotCountSavedDayUntilItsScoreIsAvailable() {
    val state = LifeLoadUiState(
      selectedDate = "2026-05-17",
      entryState = "pending_approval",
      hasDraft = true,
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-16", state = "approved", approvedAt = "2026-05-16T21:00:00Z", scoreAvailable = false),
        ),
      ),
    )

    assertEquals(0, recentGuidanceApprovedDayCount(state))
  }

  @Test
  fun recentPathDoesNotPlotExplicitlyUnavailableSavedDay() {
    val state = LifeLoadUiState(
      selectedDate = "2026-05-17",
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-17", state = "approved", canonicalCompleted = true, scoreAvailable = false),
        ),
        trendPoints = listOf(LifeLoadTrendPoint(date = "2026-05-17", driftRiskScore = 90.0)),
      ),
    )

    assertEquals(0, recentPathPointsForTest(state, LocalDate.parse("2026-05-17")).count { it != null })
  }

  @Test
  fun guidanceThresholdDoesNotDoubleCountSelectedDayAlreadyInHistory() {
    val state = LifeLoadUiState(
      selectedDate = "2026-05-16",
      entryState = "pending_approval",
      hasDraft = true,
      approvedAt = "",
      dashboard = LifeLoadDashboard(
        date = "2026-05-17",
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-10", zone = "yellow", approvedAt = "2026-05-10T21:00:00Z"),
          LifeLoadHistoryDay(date = "2026-05-16", state = "pending_approval", zone = "red"),
        ),
      ),
    )

    assertEquals(2, recentGuidanceApprovedDayCount(state))
  }
}
