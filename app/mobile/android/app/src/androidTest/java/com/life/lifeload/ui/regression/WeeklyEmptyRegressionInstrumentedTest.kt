package com.life.lifeload.ui.regression

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class WeeklyEmptyRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun weeklyEmptyStateDoesNotInventSignalsWhenLocalStoreIsEmpty() {
    val context = compose.activity.applicationContext

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.navigateDrawer("drawer_weekly", "Guidance")
    robot.waitForText("Weekly review", substring = true)
    robot.assertAppForeground()

    RegressionFixture.resetLocalStore(context)
    LifeLoadLocalStore(context).use { store ->
      val status = store.status()
      assertEquals(0, status.entryCount)
      assertEquals(0, status.pendingOutboxCount)
    }
  }
}
