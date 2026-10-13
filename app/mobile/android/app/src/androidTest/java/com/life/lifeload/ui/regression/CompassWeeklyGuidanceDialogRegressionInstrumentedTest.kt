package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CompassWeeklyGuidanceDialogRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun weeklyGuidanceRecommendationOpensReasonDialog() {
    val context = compose.activity.applicationContext
    RegressionFixture.resetAppState(context)

    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag("weekly-hero-card").fetchSemanticsNodes().isNotEmpty()
    }

    compose.onNodeWithTag("weekly-next-action").assertIsDisplayed().performClick()
    compose.onNodeWithTag("weekly-guidance-reason-dialog").assertIsDisplayed()
    assertTrue(compose.onAllNodesWithText("Why this guidance?").fetchSemanticsNodes().isNotEmpty())
    assertTrue(compose.onAllNodesWithText("Why active").fetchSemanticsNodes().isNotEmpty())
    assertTrue(compose.onAllNodesWithText("Why not higher").fetchSemanticsNodes().isNotEmpty())
    assertTrue(compose.onAllNodesWithText("Why not lower").fetchSemanticsNodes().isNotEmpty())
    compose.onNodeWithText("Close").assertIsDisplayed().performClick()
  }
}
