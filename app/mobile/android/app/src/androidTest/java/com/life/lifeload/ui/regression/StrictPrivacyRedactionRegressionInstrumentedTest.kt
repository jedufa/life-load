package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class StrictPrivacyRedactionRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun privacySecretStaysOutOfRedactedDiagnosticsAndNonDailyScreens() {
    val context = compose.activity.applicationContext
    val secret = RegressionFixture.privacySecret

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.waitForEnabledTag("daily_diary_text")
    replaceTextAndAssert(compose, "daily_diary_text", secret)
    closeKeyboard()
    tap("sleep_ok_yes")
    tap("nutrition_ok_yes")
    tap("alcohol_none")
    tap("binge_no")
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    LifeLoadLocalStore(context).use { store ->
      val fullBundle = store.exportDebugBundle(redacted = false)
      val redactedBundle = store.exportDebugBundle(redacted = true)
      assertTrue(fullBundle.contains(secret))
      assertFalse(redactedBundle.contains(secret))
      assertTrue(redactedBundle.contains("\"redaction\":\"redacted\""))
    }

    robot.navigateDrawer("drawer_weekly", "Guidance")
    compose.onAllNodesWithText(secret, substring = true).assertCountEquals(0)

    robot.navigateDrawer("drawer_settings", "Settings")
    compose.onAllNodesWithText(secret, substring = true).assertCountEquals(0)
    robot.scrollTo(hasTestTag("local_diagnostics_card"))
    compose.onNodeWithTag("local_diagnostics_refresh").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Redacted diagnostics loaded.", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onAllNodesWithText(secret, substring = true).assertCountEquals(0)
  }

  private fun tap(tag: String) {
    robot.scrollToTag(tag)
    compose.onNodeWithTag(tag).performClick()
  }
}
