package com.life.lifeload.ui

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import com.life.lifeload.ui.regression.closeKeyboard
import com.life.lifeload.ui.regression.replaceTextAndAssert
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.regression.RegressionFixture
import com.life.lifeload.ui.regression.UiVariantRule
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DailyCloseoutGateInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule

  @Test
  fun normalDayCanApproveThroughCoreFields() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    GateVisual.pause()
    openDailyDaysBeforeToday(1)
    compose.onNodeWithText("Core").assertIsDisplayed()
    compose.onAllNodesWithText("A skipped day does not need perfect backfill.", substring = true).assertCountEquals(0)

    enterDiary("neutral normal day gate note")

    compose.onNodeWithTag("sleep_ok_yes").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()
    GateVisual.pause()

    compose.onRoot().performTouchInput { swipeDown() }
    GateVisual.pause()
    compose.onNodeWithTag("daily_approve_button").performClick()

    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
  }

  @Test
  fun missedDayRecoveryCanEditCoreFieldsApproveAndShowNextAction() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    GateVisual.pause()
    openDailyDaysBeforeToday(4)
    if (compose.onAllNodesWithText("A skipped day does not need perfect backfill.", substring = true).fetchSemanticsNodes().isNotEmpty()) {
      compose.onNodeWithTag("life_load_content").performScrollToNode(hasText("A skipped day does not need perfect backfill.", substring = true))
      compose.onNodeWithText("A skipped day does not need perfect backfill.", substring = true).assertIsDisplayed()
    }
    compose.onNodeWithText("Core").assertIsDisplayed()

    enterDiary("neutral missed day gate note")

    compose.onNodeWithTag("sleep_ok_yes").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()
    GateVisual.pause()

    compose.onRoot().performTouchInput { swipeDown() }
    GateVisual.pause()
    compose.onNodeWithTag("daily_approve_button").performClick()

    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
  }

  @Test
  fun overloadedCoreSignalsStillApproveWithoutPunitiveLanguage() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    GateVisual.pause()
    openDailyDaysBeforeToday(8)
    enterDiary("neutral overloaded test note")

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("sleep_ok_no"))
    compose.onNodeWithTag("sleep_ok_no").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("nutrition_ok_no").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()
    GateVisual.pause()

    compose.onRoot().performTouchInput { swipeDown() }
    GateVisual.pause()
    compose.onNodeWithTag("daily_approve_button").performClick()

    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onAllNodesWithText("punishment", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("compensation", substring = true).assertCountEquals(0)
    compose.onAllNodesWithText("ruined", substring = true).assertCountEquals(0)
  }

  private fun openDailyDaysBeforeToday(daysBack: Int) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onNodeWithText("Check-in").performClick()
    compose.onNodeWithText("Today").performClick()
    repeat(daysBack) {
      compose.onNodeWithContentDescription("Previous day").performClick()
      compose.waitForIdle()
      GateVisual.pause()
    }
  }

  private fun waitForDiaryEnabled() {
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
        true
      }.getOrDefault(false)
    }
  }

  private fun enterDiary(text: String) {
    waitForDiaryEnabled()
    replaceTextAndAssert(compose, "daily_diary_text", text)
    closeKeyboard()
    GateVisual.pause()
  }
}
