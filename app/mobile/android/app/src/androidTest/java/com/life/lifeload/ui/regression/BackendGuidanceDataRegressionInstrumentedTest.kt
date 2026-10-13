package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BackendGuidanceDataCompassRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun backendGuidanceUsesAvailablePastWeekData() {
    assertBackendGuidanceUsesAvailablePastWeekData(compose)
  }
}

@RunWith(AndroidJUnit4::class)
class BackendGuidanceDataCompassPlusRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun backendGuidanceUsesAvailablePastWeekData() {
    assertBackendGuidanceUsesAvailablePastWeekData(compose)
  }
}

private fun assertBackendGuidanceUsesAvailablePastWeekData(
  compose: androidx.compose.ui.test.junit4.AndroidComposeTestRule<androidx.test.ext.junit.rules.ActivityScenarioRule<MainActivity>, MainActivity>,
) {
  val context = compose.activity.applicationContext
  ServerConfig.resetBaseUrl(context)
  RegressionFixture.resetLocalStore(context)

  compose.waitUntil(25_000) {
    compose.onAllNodesWithText("Guidance quality: high", substring = true).fetchSemanticsNodes().isNotEmpty()
  }
  compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
  compose.onAllNodesWithText("Not enough data", substring = true).assertCountEquals(0)
  compose.onAllNodesWithText("Not enough data yet", substring = true).assertCountEquals(0)
  assertTrue(
    compose.onAllNodesWithText("Watch").fetchSemanticsNodes().isNotEmpty() ||
      compose.onAllNodesWithText("Recovery priority").fetchSemanticsNodes().isNotEmpty() ||
      compose.onAllNodesWithText("Stable").fetchSemanticsNodes().isNotEmpty(),
  )

  val scrollHost = when {
    compose.onAllNodesWithTag("compass-plus-content").fetchSemanticsNodes().isNotEmpty() -> "compass-plus-content"
    else -> "compass-content"
  }
  compose.onNodeWithTag(scrollHost).performScrollToNode(hasTestTag("weekly-trend-card"))
  compose.onNodeWithTag("weekly-trend-card").assertIsDisplayed()
  compose.onNodeWithTag("weekly-recent-path-curve").assertIsDisplayed()
  compose.onAllNodesWithText("May 4", substring = true).assertCountEquals(1)
  compose.onAllNodesWithText("May 10", substring = true).assertCountEquals(1)
}
