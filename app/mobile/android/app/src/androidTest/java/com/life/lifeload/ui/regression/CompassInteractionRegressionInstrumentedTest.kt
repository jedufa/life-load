package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class CompassInteractionRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun emptyTodayDoesNotShowNanAndAddMissingDetailsHighlightsUnsetFields() {
    resetOfflineAndRecreate()

    waitForTag("compass-content")
    compose.onAllNodesWithText("NaN", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Forbidden numeric value", substring = true).assertCountEquals(0)

    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")
    compose.onAllNodesWithText("NaN", substring = true).assertCountEquals(0)
    compose.onNodeWithTag("daily-add-details-button").assertIsDisplayed().performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag("daily-core-sleep_missing", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    }
    assertTrue(compose.onAllNodesWithTag("daily-core-sleep_missing", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())
    assertTrue(compose.onAllNodesWithTag("daily-core-nutrition_missing", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())
  }

  @Test
  fun profileModifiersAreCombinableAndFormulaFactorPillsReflectSwitches() {
    resetOfflineAndRecreate()

    waitForTag("compass-content")
    compose.onNodeWithTag("nav-settings").performClick()
    waitForTag("settings-section-checkin")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("settings-section-guidance"))

    compose.onNodeWithTag("settings-formula-profile_protective").performClick()
    compose.onNodeWithTag("settings-formula-profile_sports_light").performClick()
    compose.onNodeWithTag("settings-formula-profile_balanced").assertIsSelected()
    compose.onNodeWithTag("settings-formula-profile_protective").assertIsSelected()
    compose.onNodeWithTag("settings-formula-profile_sports_light").assertIsSelected()

    compose.onNodeWithTag("nav-week").performClick()
    waitForTag("weekly-hero-card")
    compose.onNodeWithTag("nav-settings").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("settings-section-guidance"))
    compose.onNodeWithTag("settings-formula-profile_protective").assertIsSelected()
    compose.onNodeWithTag("settings-formula-profile_sports_light").assertIsSelected()

    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("debug_ui_variant_card"))
    compose.onNodeWithTag("compass-mode_detailed").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("settings_include_late_phone"))
    compose.onNodeWithTag("settings_include_late_phone-switch").performClick()
    compose.onNodeWithTag("settings_include_project_overrun-switch").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("settings-section-guidance"))
    compose.onNodeWithText("Evening risk · off").assertIsDisplayed()
  }

  @Test
  fun profileProvenanceIsVisibleInCheckInExplanation() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna"))
    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)
    RegressionFixture.seedServerApproved(
      context = context,
      entry = RegressionFixture.entry(
        date = fixtureDate,
        note = "profile provenance fixture",
        sleepOk = true,
        nutritionOk = true,
      ),
      score = LifeLoadScore(
        zone = "yellow",
        mode = "protect",
        nextAction = "Keep tonight simple.",
        why = listOf("Late phone"),
        lifeLoadScore = 5.0,
        baseScore = 4.5,
        profileAdjustedScore = 5.0,
        guidanceMediumThreshold = 32,
        guidanceHighThreshold = 65,
        profileModifiers = listOf("protective", "sports_light"),
        profileEffects = listOf("protective increased late-phone strain", "sports_light softened training load"),
      ),
    )
    compose.activityRule.scenario.recreate()

    waitForTag("compass-content")
    openOperatorMode()
    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("formula-card"))
    assertTrue(compose.onAllNodesWithTag("formula-card", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())
  }

  @Test
  fun coffeeNotSureStepperMovesToNumberAndBackToNotSure() {
    resetOfflineAndRecreate()

    waitForTag("compass-content")
    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")
    openSimpleMode()
    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("daily-detailed-signals-summary"))
    compose.onNodeWithTag("daily-quick-checkin-button").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("daily-more-mood-summary"))
    compose.onNodeWithTag("daily-more-mood-summary_toggle").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("daily-coffee-stepper"))

    compose.onNodeWithTag("daily-coffee-stepper-not-sure").performScrollTo()
    compose.onNodeWithTag("daily-coffee-stepper-not-sure").performClick()
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag("daily-coffee-stepper-not-sure").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Selected]
      }.getOrDefault(false)
    }
    compose.onNodeWithTag("daily-coffee-stepper-not-sure").assertIsSelected()
    compose.onNodeWithText("--").assertIsDisplayed()
    compose.onNodeWithTag("daily-coffee-stepper-increase").performScrollTo()
    compose.onNodeWithTag("daily-coffee-stepper-increase").performClick()
    compose.waitUntil(20_000) { compose.onAllNodesWithText("0").fetchSemanticsNodes().isNotEmpty() }
    compose.onNodeWithTag("daily-coffee-stepper-increase").performScrollTo()
    compose.onNodeWithTag("daily-coffee-stepper-increase").performClick()
    compose.waitUntil(20_000) { compose.onAllNodesWithText("1").fetchSemanticsNodes().isNotEmpty() }
    compose.onNodeWithTag("daily-coffee-stepper-decrease").performScrollTo()
    compose.onNodeWithTag("daily-coffee-stepper-decrease").performClick()
    compose.waitUntil(20_000) { compose.onAllNodesWithText("0").fetchSemanticsNodes().isNotEmpty() }
    compose.onNodeWithTag("daily-coffee-stepper-decrease").performScrollTo()
    compose.onNodeWithTag("daily-coffee-stepper-decrease").performClick()
    compose.onNodeWithTag("daily-coffee-stepper-not-sure").assertIsSelected()
    compose.onNodeWithText("--").assertIsDisplayed()
    compose.onAllNodesWithText("Choose a number", substring = true).assertCountEquals(0)
  }

  @Test
  fun detailedRecentPathAndOperatorDiagnosticsRemainReachable() {
    resetOfflineAndRecreate()

    waitForTag("compass-content")
    compose.onNodeWithTag("nav-settings").performClick()
    waitForTag("settings-section-checkin")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("debug_ui_variant_card"))
    compose.onNodeWithTag("compass-mode_detailed").performClick()
    compose.onNodeWithTag("nav-week").performClick()
    waitForTag("weekly-hero-card")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    assertTrue(compose.onAllNodesWithTag("weekly-trend-card", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())
    assertTrue(compose.onAllNodesWithTag("weekly-recent-path-curve", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())

    compose.onNodeWithTag("nav-settings").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("debug_ui_variant_card"))
    compose.onNodeWithTag("compass-mode_operator").performClick()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("settings-section-developer"))
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("operator-refresh-diagnostics"))
    compose.onNodeWithTag("operator-refresh-diagnostics").assertIsDisplayed()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("operator-import-history"))
    compose.onNodeWithTag("operator-import-history").assertIsDisplayed()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("operator-sync-outbox"))
    compose.onNodeWithTag("operator-sync-outbox").assertIsDisplayed()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("operator-mirror"))
    compose.onNodeWithTag("operator-mirror").assertIsDisplayed()
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag(tag).fetchSemanticsNode()
        true
      }.getOrDefault(false)
    }
    compose.waitForIdle()
  }

  private fun resetAndRecreate() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    compose.activityRule.scenario.recreate()
    waitForTag("compass-content")
  }

  private fun resetOfflineAndRecreate() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    RegressionFixture.forceBackendUnavailable(compose.activity.applicationContext)
    compose.activityRule.scenario.recreate()
    waitForTag("compass-content")
  }

  private fun openSimpleMode() {
    compose.onNodeWithTag("nav-settings").performClick()
    waitForTag("settings-section-checkin")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("debug_ui_variant_card"))
    compose.onNodeWithTag("compass-mode_simple").performClick()
  }

  private fun openDetailedMode() {
    compose.onNodeWithTag("nav-settings").performClick()
    waitForTag("settings-section-checkin")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("debug_ui_variant_card"))
    compose.onNodeWithTag("compass-mode_detailed").performClick()
  }

  private fun openOperatorMode() {
    compose.onNodeWithTag("nav-settings").performClick()
    waitForTag("settings-section-checkin")
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("debug_ui_variant_card"))
    compose.onNodeWithTag("compass-mode_operator").performClick()
  }
}
