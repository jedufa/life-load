package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ConfigurationStateRestorationRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun selectedSurfaceDateAndDiaryDraftSurviveActivityRecreate() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    RegressionFixture.forceBackendUnavailable(compose.activity.applicationContext)
    val draftText = "state restoration neutral draft"

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-previous-day").performClick()
    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("daily-diary-input")
    replaceTextAndAssert(compose, "daily-diary-input", draftText)
    closeKeyboard()

    compose.activityRule.scenario.recreate()

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("today-hero-card").assertIsDisplayed()
    compose.onNodeWithTag("daily-diary-input").assertIsDisplayed()
    compose.onNodeWithTag("compass-plus-date-label").assertIsDisplayed()
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
