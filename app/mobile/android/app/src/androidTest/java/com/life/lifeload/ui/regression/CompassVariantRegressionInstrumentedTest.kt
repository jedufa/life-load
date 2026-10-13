package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CompassVariantRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  private val robot by lazy { ComposeRobot(compose) }

  @Test
  fun switchToCompassAndExerciseCoreWeekAndCheckInDestinations() {
    val context = compose.activity.applicationContext
    RegressionFixture.resetAppState(context)

    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag("compass-content").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
    compose.onNodeWithTag("compass-header-brand-mark").assertIsDisplayed()
    compose.onNodeWithContentDescription("Life Load").assertIsDisplayed()
    compose.onAllNodesWithText("Guidance").assertCountEquals(2)
    assertTrue(compose.onAllNodesWithText("Check-in").fetchSemanticsNodes().isNotEmpty())
    compose.onAllNodesWithText("Approved", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Buffer", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("stabilization block", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Recovery compliance falling", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("0 need review", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("mode: unknown", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("RED").assertCountEquals(0)
    compose.onAllNodesWithText("YELLOW").assertCountEquals(0)
    compose.onAllNodesWithText("GREEN").assertCountEquals(0)
    compose.onAllNodesWithText("Main drivers").assertCountEquals(0)
    assertTrue(compose.onAllNodesWithText("Guidance quality:", substring = true).fetchSemanticsNodes().isNotEmpty())
    compose.onNodeWithTag("weekly-recommendation-visual").assertIsDisplayed()
    val heroStateVisible = listOf("Recovery priority", "Watch", "Stable", "Not enough data").any { label ->
      compose.onAllNodesWithText(label).fetchSemanticsNodes().isNotEmpty()
    }
    assertTrue(heroStateVisible)
    val recoveryPriority = compose.onAllNodesWithText("Recovery priority").fetchSemanticsNodes().isNotEmpty()
    if (recoveryPriority) {
      compose.onNodeWithTag("weekly-recovery-priority-visual").assertIsDisplayed()
      compose.onNodeWithContentDescription("Recovery priority").assertIsDisplayed()
      compose.onNodeWithText("Sleep first.", substring = true).assertIsDisplayed()
      compose.onNodeWithText("No late projects.", substring = true).assertIsDisplayed()
    }
    compose.onAllNodesWithText("Reduce optional commitments", substring = true).assertCountEquals(0)
    compose.onNodeWithTag("weekly-next-action").performClick()
    compose.onNodeWithTag("weekly-guidance-reason-dialog").assertIsDisplayed()
    assertTrue(compose.onAllNodesWithText("Why this guidance?").fetchSemanticsNodes().isNotEmpty())
    compose.onNodeWithTag("weekly-guidance-reason-close").performClick()
    compose.onNodeWithTag("weekly-guidance-quality").performClick()
    compose.onNodeWithTag("weekly-guidance-quality-help-dialog").assertIsDisplayed()
    compose.onNodeWithText("Guidance quality reflects how complete and recent your check-ins are.").assertIsDisplayed()
    compose.onNodeWithTag("weekly-guidance-quality-help-close").performClick()
    compose.onNodeWithTag("weekly-risk-status").performClick()
    compose.onNodeWithTag("weekly-risk-help-dialog").assertIsDisplayed()
    compose.onNodeWithText("Risk means your recent pattern is more likely to need a recovery-focused adjustment.").assertIsDisplayed()
    compose.onNodeWithTag("weekly-risk-help-close").performClick()
    compose.onNodeWithTag("weekly-driver-list").assertIsDisplayed()
    assertTrue(compose.onAllNodesWithText("Why this guidance?").fetchSemanticsNodes().isNotEmpty())
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-why-this-matters"))
    compose.onNodeWithText("Why this matters").assertIsDisplayed()
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-watch-next"))
    compose.onNodeWithText("What to watch next").assertIsDisplayed()
    compose.onAllNodesWithText("Add tonight’s check-in to see whether the pattern is changing.").assertCountEquals(0)
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    compose.onNodeWithTag("weekly-trend-card").assertIsDisplayed()
    compose.onNodeWithText("Recent path").assertIsDisplayed()
    compose.onNodeWithTag("weekly-recent-path-curve").assertIsDisplayed()
    compose.onAllNodesWithText("Load:", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Recovery margin:", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Recent demand", substring = true).assertCountEquals(0)
    assertTrue(
      compose.onAllNodesWithText("last few days", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("recent pattern", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Add a few more check-ins", substring = true).fetchSemanticsNodes().isNotEmpty(),
    )
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-data-card"))
    compose.onNodeWithTag("weekly-data-card").assertIsDisplayed()
    compose.onAllNodesWithText("7-day focus window complete", substring = true).assertCountEquals(0)
    clickNav("nav-today")
    compose.onNodeWithTag("today-hero-card").assertIsDisplayed()
    compose.onNodeWithTag("quick-checkin-card").assertIsDisplayed()
    compose.onNodeWithTag("today-daily-meaning").assertIsDisplayed()
    assertTrue(
      compose.onAllNodesWithText("saved, but some details are still missing", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Save the basics first", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Add details only if they matter today", substring = true).fetchSemanticsNodes().isNotEmpty(),
    )
    compose.onAllNodesWithTag("system-status-card").assertCountEquals(0)
    assertTrue(compose.onAllNodesWithText("Check-in").fetchSemanticsNodes().isNotEmpty())
    compose.onNodeWithText("Did you sleep on time?").assertIsDisplayed()
    compose.onNodeWithText("Did food stay on track?").assertIsDisplayed()
    compose.onAllNodesWithText("Not sure").fetchSemanticsNodes().isNotEmpty()
    compose.onAllNodesWithText("Unknown").assertCountEquals(0)
    compose.onAllNodesWithText("Set not sure").assertCountEquals(0)
    compose.onAllNodesWithText("Approve Entry").assertCountEquals(0)
    compose.onAllNodesWithText("Approve today").assertCountEquals(0)
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("daily-approve-button"))
    compose.onNodeWithTag("daily-approve-button").assertIsDisplayed()
    compose.onAllNodesWithTag("compass-mode_simple").assertCountEquals(0)
    if (compose.onAllNodesWithTag("daily-quick-checkin-button").fetchSemanticsNodes().isNotEmpty()) {
      compose.onNodeWithTag("daily-quick-checkin-button").performClick()
      compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("daily-more-movement-summary"))
      compose.onNodeWithTag("daily-more-movement-summary").assertIsDisplayed()
      compose.onNodeWithText("Roughly how long?").assertIsDisplayed()
      assertTrue(compose.onAllNodesWithTag("daily-activity-types").fetchSemanticsNodes().isNotEmpty())
    }
    clickNav("nav-week")
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag("weekly-hero-card").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("weekly-driver-list").assertIsDisplayed()
    compose.onAllNodesWithTag("compass-mode_simple").assertCountEquals(0)
    compose.onAllNodesWithText("10/7", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Buffer", substring = true).assertCountEquals(0)
    robot.assertAppForeground()
  }

  private fun clickNav(tag: String) {
    compose.onNode(hasTestTag(tag) and hasClickAction(), useUnmergedTree = true).performClick()
    compose.waitForIdle()
  }
}
