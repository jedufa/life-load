package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SmokeNavigationRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun launchNavigateCoreSurfacesAndResetLocalTruth() {
    val context = compose.activity.applicationContext
    RegressionFixture.resetAppState(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    compose.onNodeWithTag("daily_diary_text").assertIsDisplayed()
    robot.assertAppForeground()

    robot.navigateDrawer("drawer_weekly", "Guidance")
    robot.navigateDrawer("drawer_settings", "Settings")
    robot.scrollToTag("privacy_controls_card")
    compose.onNodeWithTag("privacy_controls_card").assertIsDisplayed()
    robot.scrollToTag("local_diagnostics_card")
    compose.onNodeWithTag("local_diagnostics_card").assertIsDisplayed()

    robot.navigateDrawer("drawer_daily", "Check-in")
    RegressionFixture.resetLocalStore(context)
    AndroidTruthHelpers.assertNoEntries(context)
  }
}
