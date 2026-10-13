package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LayoutStressRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun compassPlusCoreSurfacesRemainScrollableWithLongInput() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    RegressionFixture.forceBackendUnavailable(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
    compose.onAllNodesWithText("Main drivers", substring = true).assertCountEquals(0)

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    compose.onNodeWithTag("weekly-trend-card").assertIsDisplayed()

    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("quick-checkin-card")
    val diaryText = "layout stress neutral note line one\nline two with enough text to wrap\nline three remains editable"
    replaceTextAndAssert(compose, "daily-diary-input", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("daily-approve-button"))
    compose.onNodeWithTag("daily-approve-button").assertIsDisplayed()
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Forbidden numeric value", substring = true).fetchSemanticsNodes().isEmpty() &&
        compose.onAllNodesWithText("NaN", substring = true).fetchSemanticsNodes().isEmpty() &&
        runCatching {
          compose.onNodeWithTag(tag).fetchSemanticsNode()
          true
        }.getOrDefault(false)
    }
    compose.waitForIdle()
  }

}
