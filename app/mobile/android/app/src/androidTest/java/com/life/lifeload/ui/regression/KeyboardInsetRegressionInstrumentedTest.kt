package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
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
class KeyboardInsetRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun diaryFieldRemainsUsableAndPrimaryActionReachableAfterKeyboardInput() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    RegressionFixture.forceBackendUnavailable(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("daily-diary-input")
    val diaryText = "keyboard inset neutral note\nsecond line\nthird line\nfourth line"
    replaceTextAndAssert(compose, "daily-diary-input", diaryText)
    compose.onNodeWithTag("daily-diary-input").assertIsDisplayed()
    closeKeyboard()
    compose.waitForIdle()
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("daily-approve-button"))
    compose.onNodeWithTag("daily-approve-button").assertIsDisplayed()
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
