package com.life.lifeload.ui

import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadBackendStatus
import com.life.lifeload.domain.LifeLoadDriftSnapshot
import com.life.lifeload.domain.LifeLoadExtractStatus
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadStatusLights
import com.life.lifeload.domain.LifeLoadTrendPoint
import com.life.lifeload.domain.LifeLoadWeeklyMini
import com.life.lifeload.ui.compass.dailyHelpfulStep
import com.life.lifeload.ui.compass.dailyMeaning
import com.life.lifeload.ui.compass.dailySavedStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

class LifeLoadNavigationTest {
  @Test
  fun defaultDestinationIsGuidance() {
    assertEquals(LifeLoadDestination.Weekly.name, defaultLifeLoadDestinationName())
  }

  @Test
  fun weeklyEscalationRequiresMeaningfulDrift() {
    assertFalse(weeklyEscalationActive(LifeLoadUiState()))

    val elevated = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-08",
        drift = LifeLoadDriftSnapshot(riskLevel = "orange", nextAction = "Protect sleep"),
      ),
    )

    assertTrue(weeklyEscalationActive(elevated))
  }

  @Test
  fun weeklyEscalationCanUseRiskScoreWhenDriftSnapshotIsAbsent() {
    val elevated = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-08",
        trendPoints = listOf(LifeLoadTrendPoint(date = "2026-05-08", driftRiskScore = 68.0)),
      ),
    )

    assertTrue(weeklyEscalationActive(elevated))
  }

  @Test
  fun dailyFieldsAllowLocalModeWhenNotBusy() {
    assertFalse(dailyFieldsEnabled(LifeLoadUiState(loading = true)))
    assertFalse(dailyFieldsEnabled(LifeLoadUiState(statusLights = LifeLoadStatusLights(extract = LifeLoadExtractStatus.ANALYZING), analysisLocked = true)))
    assertTrue(dailyFieldsEnabled(LifeLoadUiState(statusLights = LifeLoadStatusLights(backend = LifeLoadBackendStatus.ERROR))))
    assertTrue(dailyFieldsEnabled(LifeLoadUiState(statusLights = LifeLoadStatusLights(backend = LifeLoadBackendStatus.ONLINE))))
  }

  @Test
  fun dailyFieldBurdenDefaultsToCoreOnly() {
    assertTrue(defaultCoreFieldsExpanded())
    assertFalse(defaultSecondaryFieldsExpanded())
  }

  @Test
  fun missedDayRecoveryOnlyPromptsForUnapprovedOlderDays() {
    val today = LocalDate.parse("2026-05-08")

    assertTrue(missingDayRecoveryActive("2026-05-06", approvedAt = "", currentDate = today))
    assertFalse(missingDayRecoveryActive("2026-05-07", approvedAt = "", currentDate = today))
    assertFalse(missingDayRecoveryActive("2026-05-06", approvedAt = "2026-05-08T06:00:00", currentDate = today))
    assertFalse(missingDayRecoveryActive("2026-05-06", approvedAt = "", currentDate = today, entryState = "pending_approval"))
  }

  @Test
  fun approvalFeedbackAvoidsCatchupLanguage() {
    val approved = LifeLoadUiState(
      approvedAt = "2026-05-08T06:00:00",
      score = com.life.lifeload.domain.LifeLoadScore(nextAction = "Keep dinner normal"),
    )

    assertEquals("Check-in saved. Next: Keep dinner normal", approvalFeedbackText(approved))
  }

  @Test
  fun pendingLocalApprovalCountsAsSavedCheckInForDailyUi() {
    val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
    val pending = LifeLoadUiState(
      selectedDate = today.toString(),
      entryState = "pending_approval",
      hasDraft = true,
      approvedAt = "",
      score = com.life.lifeload.domain.LifeLoadScore(zone = "green"),
    )

    assertTrue(isCheckInSaved(pending))
    assertEquals("Check-in saved. Continue with the next normal step.", approvalFeedbackText(pending))
    assertEquals("Your core check-in is saved.", dailySavedStatus(pending, emptyList()))
    assertEquals("Today looks steady.", dailyMeaning(pending, emptyList()))
    assertEquals("• Protect sleep.\n• Keep food simple.\n• Repeat what worked.", dailyHelpfulStep(pending, emptyList()))
  }

  @Test
  fun unsavedEditIsVisibleAcrossDailyStatusAndMeaning() {
    val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
    val state = LifeLoadUiState(
      selectedDate = today.toString(),
      entryState = "draft_over_approved",
      hasDraft = true,
      hasUnsavedChanges = true,
      approvedAt = "2026-05-08T06:00:00Z",
      score = com.life.lifeload.domain.LifeLoadScore(zone = "green"),
    )

    assertEquals("This check-in has unsaved changes.", dailyMeaning(state, emptyList()))
    assertEquals("Unsaved changes are stored locally; save when ready.", dailySavedStatus(state, emptyList()))
    assertEquals("Unsaved changes are stored locally. Save the check-in when ready.", approvalFeedbackText(state))
  }

  @Test
  fun explicitUnavailableScoresDoNotCountAgainstWeeklyEvidence() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-08",
        weekly = LifeLoadWeeklyMini(approvedDayDates = listOf("2026-05-08", "2026-05-07")),
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-08", state = "approved", canonicalCompleted = true, scoreAvailable = false),
          LifeLoadHistoryDay(date = "2026-05-07", state = "approved", canonicalCompleted = true, scoreAvailable = false),
        ),
      ),
    )

    assertEquals(0, approvedWeeklyDayCount(state))
  }

  @Test
  fun checkInHeroMeaningSeparatesDayStateFromStorageState() {
    val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
    val stable = LifeLoadUiState(
      selectedDate = today.toString(),
      approvedAt = "2026-05-08T06:00:00",
      score = com.life.lifeload.domain.LifeLoadScore(zone = "green"),
    )
    val partial = stable.copy(score = com.life.lifeload.domain.LifeLoadScore(zone = "green"))
    val highLoad = stable.copy(score = com.life.lifeload.domain.LifeLoadScore(zone = "yellow"))
    val recovery = stable.copy(score = com.life.lifeload.domain.LifeLoadScore(zone = "red"))
    val missed = LifeLoadUiState(selectedDate = today.minusDays(2).toString(), approvedAt = "")

    assertEquals("Today looks steady.", dailyMeaning(stable, emptyList()))
    assertEquals("Your core check-in is saved.", dailySavedStatus(stable, emptyList()))
    assertEquals("• Protect sleep.\n• Keep food simple.\n• Repeat what worked.", dailyHelpfulStep(stable, emptyList()))

    assertEquals("Today looks mostly steady.", dailyMeaning(partial, listOf("stress")))
    assertEquals("Today is saved, but some details are still missing.", dailySavedStatus(partial, listOf("stress")))
    assertEquals("• Add missing details if useful.\n• Treat guidance as partial.\n• Keep the core check-in saved.", dailyHelpfulStep(partial, listOf("stress")))

    assertEquals("Today carried more load.", dailyMeaning(highLoad, emptyList()))
    assertEquals("• Keep tonight simple.\n• Avoid late projects.\n• Protect sleep.", dailyHelpfulStep(highLoad, emptyList()))
    assertEquals("Today points toward recovery priority.", dailyMeaning(recovery, emptyList()))
    assertEquals("• Sleep first.\n• Reduce optional load.\n• Keep the next 48 hours simple.", dailyHelpfulStep(recovery, emptyList()))

    assertEquals("This day was missed.", dailyMeaning(missed, listOf("sleep")))
    assertEquals("• Add what you remember.\n• Approximate is fine.\n• Skip what you do not know.", dailyHelpfulStep(missed, listOf("sleep")))
  }

  @Test
  fun checkInHeroDoesNotFlattenOrangeScoreToSteady() {
    val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
    val orange = LifeLoadUiState(
      selectedDate = today.toString(),
      approvedAt = "2026-05-08T06:00:00",
      score = com.life.lifeload.domain.LifeLoadScore(zone = "orange", lifeLoadScore = 7.0),
    )

    assertEquals("Today carried more load.", dailyMeaning(orange, emptyList()))
    assertEquals("• Keep tonight simple.\n• Avoid late projects.\n• Protect sleep.", dailyHelpfulStep(orange, emptyList()))
  }

  @Test
  fun checkInHeroUsesBackendScoreScaleForThresholdFallback() {
    val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
    val mediumLoad = LifeLoadUiState(
      selectedDate = today.toString(),
      approvedAt = "2026-05-08T06:00:00",
      score = com.life.lifeload.domain.LifeLoadScore(
        zone = "",
        lifeLoadScore = 4.0,
        guidanceMediumThreshold = 35,
      ),
    )

    assertEquals("Today carried more load.", dailyMeaning(mediumLoad, emptyList()))
    assertEquals("• Keep tonight simple.\n• Avoid late projects.\n• Protect sleep.", dailyHelpfulStep(mediumLoad, emptyList()))
  }

  @Test
  fun checkInHeroMeaningAvoidsMoralDayLabels() {
    val state = LifeLoadUiState(
      selectedDate = LocalDate.now(ZoneId.of("Europe/Vienna")).toString(),
      approvedAt = "2026-05-08T06:00:00",
      score = com.life.lifeload.domain.LifeLoadScore(zone = "green"),
    )
    val copy = listOf(
      dailyMeaning(state, emptyList()),
      dailySavedStatus(state, emptyList()),
      dailyHelpfulStep(state, emptyList()),
    ).joinToString(" ").lowercase()

    assertFalse(copy.contains("good day"))
    assertFalse(copy.contains("bad day"))
    assertFalse(copy.contains("failed day"))
    assertFalse(copy.contains("perfect day"))
  }

  @Test
  fun closeoutPromptMatchesSelectedDate() {
    val today = LocalDate.parse("2026-05-08")

    assertTrue(dailyCloseoutPrompt("2026-05-08", today).startsWith("Describe today"))
    assertTrue(dailyCloseoutPrompt("2026-05-07", today).startsWith("Describe yesterday"))
    assertTrue(dailyCloseoutPrompt("2026-05-01", today).startsWith("Describe this day"))
  }

  @Test
  fun weeklyReviewSnapshotUsesApprovedDaysOnly() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-08",
        weekly = LifeLoadWeeklyMini(nextAction = "Keep shutdown protected."),
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-08", state = "draft", lifeLoadScore = 99.0, nextAction = "Ignore draft"),
          LifeLoadHistoryDay(date = "2026-05-07", state = "approved", canonicalCompleted = true, lifeLoadScore = 42.0, nextAction = "Protect dinner"),
          LifeLoadHistoryDay(date = "2026-05-06", state = "draft_over_approved", approvedAt = "2026-05-06T20:00:00Z", lifeLoadScore = 55.0, nextAction = "Reduce evening load"),
          LifeLoadHistoryDay(date = "2026-05-05", state = "pending_approval", lifeLoadScore = 35.0, nextAction = "Local save pending sync"),
        ),
      ),
    )

    val approved = approvedWeeklyHistoryDays(state.dashboard.historyDays)
    val snapshot = weeklyReviewSnapshot(state)

    assertEquals(listOf("2026-05-07", "2026-05-06", "2026-05-05"), approved.map { it.date })
    assertEquals(3, snapshot.approvedDayCount)
    assertEquals("2026-05-06", snapshot.highestRiskDay)
    assertEquals("Keep shutdown protected.", snapshot.oneCorrection)
  }

  @Test
  fun weeklyCorrectionFallsBackFromVagueAdviceToSignalSpecificAction() {
    val state = LifeLoadUiState(
      dashboard = LifeLoadDashboard(
        date = "2026-05-08",
        weekly = LifeLoadWeeklyMini(nextAction = "Protect sleep."),
        drift = LifeLoadDriftSnapshot(
          riskLevel = "orange",
          nextAction = "Protect sleep.",
          contributingSignals = listOf("project overrun", "late phone"),
        ),
        historyDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-07", state = "approved", canonicalCompleted = true, lifeLoadScore = 42.0, nextAction = "Take it easy."),
        ),
      ),
    )

    val snapshot = weeklyReviewSnapshot(state)

    assertEquals("No project work after 20:45 for the next two evenings.", snapshot.oneCorrection)
  }
}
