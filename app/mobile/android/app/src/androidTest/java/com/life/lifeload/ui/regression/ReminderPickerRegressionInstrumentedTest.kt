package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReminderPickerRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun customReminderUsesTimePickerDialog() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-overflow").performClick()
    compose.onNodeWithTag("compass-plus-menu-settings").performClick()
    waitForTag("settings-section-reminder")

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-reminder"))
    compose.onNodeWithTag("settings-section-reminder").performClick()
    waitForTag("settings-reminder-time_custom")
    compose.onNodeWithTag("settings-reminder-time_custom").performClick()
    waitForTag("settings-reminder-custom-time")

    compose.onNodeWithTag("settings-reminder-custom-time").assertIsDisplayed().performClick()
    compose.onNodeWithText("Custom time").assertIsDisplayed()
    compose.onNodeWithText("Set time").assertIsDisplayed()
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
  }
}
