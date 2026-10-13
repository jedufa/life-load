package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
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
class CompassPlusShellRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun floatingShellSwitchesGuidanceCheckInAndExposesHeaderActions() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-header").assertIsDisplayed()
    compose.onNodeWithTag("compass-plus-date-pill").assertIsDisplayed()
    compose.onNodeWithTag("compass-plus-segmented-toggle").assertIsDisplayed()
    compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
    compose.onAllNodesWithTag("compass-bottom-nav").assertCountEquals(0)
    compose.onAllNodesWithTag("compass-plus-help").assertCountEquals(0)

    compose.onNodeWithTag("compass-plus-brand-container").performClick()
    compose.onNodeWithText("How Life Load works").assertIsDisplayed()
    compose.onNodeWithText("Close").performClick()

    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("today-hero-card")
    compose.onNodeWithTag("compass-plus-date-label").assertIsDisplayed()

    compose.onNodeWithTag("compass-plus-guidance").performClick()
    waitForTag("weekly-hero-card")

    clickOverflowMenuItem("compass-plus-menu-help")
    compose.onNodeWithText("Why this exists").assertIsDisplayed()
    compose.onNodeWithText("Close").performClick()

    compose.onAllNodesWithTag("compass-plus-header-settings").assertCountEquals(0)
    compose.onNodeWithTag("compass-plus-overflow").performClick()
    compose.onNodeWithTag("compass-plus-menu-settings").assertIsDisplayed()
    compose.onNodeWithTag("compass-plus-menu-backup").assertIsDisplayed()
  }

  @Test
  fun guidanceSurfaceKeepsSimpleModeCalmAndPathNonTechnical() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
    compose.onNodeWithTag("weekly-recommendation-visual").assertIsDisplayed()
    assertTrue(
      listOf("Recovery priority", "Watch", "Stable", "Not enough data").any { label ->
        compose.onAllNodesWithText(label).fetchSemanticsNodes().isNotEmpty()
      },
    )

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("weekly-driver-list"))
    compose.onNodeWithTag("weekly-driver-list").assertIsDisplayed()
    compose.onAllNodesWithText("Late phone appeared in the recent window.", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Project spillover appeared in the recent window.", substring = true).assertCountEquals(0)

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    compose.onNodeWithTag("weekly-trend-card").assertIsDisplayed()
    if (compose.onAllNodesWithTag("weekly-recent-path-curve").fetchSemanticsNodes().isNotEmpty()) {
      compose.onNodeWithTag("weekly-recent-path-curve").assertIsDisplayed()
    } else {
      assertTrue(compose.onAllNodesWithText("Not enough data", substring = true).fetchSemanticsNodes().isNotEmpty())
    }
    compose.onAllNodesWithText("Load:", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Recovery margin:", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("Risk:", substring = true).assertCountEquals(0)
  }

  @Test
  fun guidanceReasonModalUsesCompassPlusGroupedReasoning() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("weekly-next-action").performClick()
    compose.onNodeWithTag("weekly-guidance-reason-dialog").assertIsDisplayed()
    assertTrue(compose.onAllNodesWithText("Why this guidance?").fetchSemanticsNodes().isNotEmpty())
    compose.onNodeWithText("Why active").assertIsDisplayed()
    compose.onNodeWithText("Why not higher").assertIsDisplayed()
    compose.onNodeWithText("Why not lower").assertIsDisplayed()
    compose.onNodeWithText("What would ease it").assertIsDisplayed()
    compose.onNodeWithText("Close").performClick()
  }

  @Test
  fun datePillCanMoveBackThenForwardToToday() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-date-label").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Today", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("compass-plus-previous-day").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Yest.", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Yesterday", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("compass-plus-next-day").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Today", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
  }

  @Test
  fun checkInSurfaceKeepsBasicsFirstLanguage() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("quick-checkin-card")
    compose.onNodeWithText("Save the basics first. Add details only if they matter today.").assertIsDisplayed()
    assertTrue(compose.onAllNodesWithText("Not sure").fetchSemanticsNodes().isNotEmpty())
    waitForTag("daily-approve-button")
    compose.onNodeWithTag("daily-approve-button").assertIsDisplayed()
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
    compose.waitForIdle()
  }

  private fun clickOverflowMenuItem(tag: String) {
    compose.onNodeWithTag("compass-plus-overflow").performClick()
    compose.waitUntil(5_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNode(hasTestTag(tag) and hasClickAction(), useUnmergedTree = true).performClick()
    compose.waitForIdle()
  }
}
