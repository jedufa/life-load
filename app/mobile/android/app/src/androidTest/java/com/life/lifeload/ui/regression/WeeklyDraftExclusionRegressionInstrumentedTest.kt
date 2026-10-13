package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.approvedWeeklyHistoryDays
import com.life.lifeload.ui.weeklyReviewSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class WeeklyDraftExclusionRegressionInstrumentedTest {
  @Test
  fun weeklyHelpersCountOnlyApprovedTruthAndIgnoreDraftsFutureBlankDays() {
    val days = listOf(
      LifeLoadHistoryDay(date = "2026-05-04", state = "approved", approvedAt = "2026-05-04T20:00:00Z", lifeLoadScore = 30.0),
      LifeLoadHistoryDay(date = "2026-05-05", state = "draft", lifeLoadScore = 99.0),
      LifeLoadHistoryDay(date = "2026-05-06", state = "blank", lifeLoadScore = 88.0),
      LifeLoadHistoryDay(date = "2026-05-07", canonicalCompleted = true, lifeLoadScore = 55.0),
      LifeLoadHistoryDay(date = "2026-05-11", state = "future", lifeLoadScore = 100.0),
    )

    val approved = approvedWeeklyHistoryDays(days)
    assertEquals(listOf("2026-05-04", "2026-05-07"), approved.map { it.date })
    assertFalse(approved.any { it.state == "draft" || it.state == "future" || it.state == "blank" })

    val snapshot = weeklyReviewSnapshot(LifeLoadUiState(dashboard = LifeLoadDashboard(date = "2026-05-09", historyDays = days)))
    assertEquals(2, snapshot.approvedDayCount)
    assertEquals("2026-05-07", snapshot.highestRiskDay)

    assertThrows(AssertionError::class.java) {
      assertEquals("negative control must fail if drafts/future days are counted", 5, approved.size)
    }
  }
}
