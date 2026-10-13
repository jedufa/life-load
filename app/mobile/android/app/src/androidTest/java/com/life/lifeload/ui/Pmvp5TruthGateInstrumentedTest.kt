package com.life.lifeload.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import com.life.lifeload.ui.regression.closeKeyboard
import com.life.lifeload.ui.regression.replaceTextAndAssert
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.regression.RegressionFixture
import com.life.lifeload.ui.regression.UiVariantRule
import org.junit.rules.RuleChain
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class Pmvp5TruthGateInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun formulaDialogSettingsTogglesAndApprovalReachPersistedTruth() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)
    GateVisual.pause()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }

    compose.onNodeWithTag("formula_button").performClick()
    GateVisual.pause()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance & scoring").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithText("Current:", substring = true).assertIsDisplayed()
    compose.onNodeWithText("Close").performClick()
    GateVisual.pause()

    compose.onNodeWithContentDescription("Open navigation").performClick()
    GateVisual.pause()
    compose.onNodeWithText("Settings").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("settings_include_late_phone").performScrollTo().performClick()
    GateVisual.pause()
    compose.onNodeWithTag("settings_include_project_overrun").performScrollTo().performClick()
    compose.onNodeWithTag("settings_save_button").performScrollTo().performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Saving settings...", substring = true).fetchSemanticsNodes().isEmpty()
    }
    GateVisual.pause()
    navigateToDaily()

    openDailyDaysBeforeToday(2)
    enterDiary("pmvp5 truth gate neutral note")
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("daily_more_signals_section"))
    compose.onNodeWithTag("daily_more_signals_section").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("daily_recovery_evening_section"))
    compose.onNodeWithTag("daily_recovery_evening_section").performClick()
    compose.onNodeWithTag("phone_after_21_yes").performScrollTo().performClick()
    compose.onNodeWithTag("project_overrun_yes").performScrollTo().performClick()
    GateVisual.pause()

    compose.onRoot().performTouchInput { swipeDown() }
    GateVisual.pause()
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun openDailyDaysBeforeToday(daysBack: Int) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithText("Today").performClick()
    repeat(daysBack) {
      compose.onNodeWithContentDescription("Previous day").performClick()
      compose.waitForIdle()
      GateVisual.pause()
    }
  }

  private fun navigateToDaily() {
    compose.onNodeWithTag("settings_formula_close_button").performScrollTo().performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onNodeWithTag("drawer_daily").performClick()
    GateVisual.pause()
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
