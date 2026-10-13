package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.After
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LargeFontRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @After
  fun restoreFontScale() {
    shell("settings put system font_scale 1.0")
  }

  @Test
  fun compassPlusCoreFlowRemainsReachableAtLargeFont() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    RegressionFixture.forceBackendUnavailable(compose.activity.applicationContext)
    shell("settings put system font_scale 1.5")
    compose.activityRule.scenario.recreate()

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    compose.onNodeWithTag("weekly-trend-card").assertIsDisplayed()

    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("quick-checkin-card")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("daily-approve-button"))
    compose.onNodeWithTag("daily-approve-button").assertIsDisplayed()
  }

  private fun shell(command: String) {
    InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(command).close()
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

}
