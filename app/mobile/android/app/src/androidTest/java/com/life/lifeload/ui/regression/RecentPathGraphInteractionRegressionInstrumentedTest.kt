package com.life.lifeload.ui.regression

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeRight
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RecentPathGraphInteractionRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun recentPathGraphShowsRightEdgeDateAndCommitsDragOnRelease() {
    RegressionFixture.resetAppState(compose.activity.applicationContext)

    waitForTag("compass-plus-content")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    waitForTag("weekly-recent-path-curve")
    waitForTag("weekly-recent-path-active-date")

    val initialLabel = activeDateLabel()
    assertTrue(initialLabel.startsWith("Through "))

    compose.onNodeWithTag("weekly-recent-path-curve").assertIsDisplayed()
    compose.onNodeWithTag("weekly-recent-path-curve").performTouchInput {
      swipeRight()
    }

    compose.waitUntil(20_000) {
      activeDateLabel() != initialLabel
    }
    val shiftedLabel = activeDateLabel()
    assertTrue(shiftedLabel.startsWith("Through "))
    assertNotEquals(initialLabel, shiftedLabel)
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun activeDateLabel(): String {
    val texts = compose
      .onNodeWithTag("weekly-recent-path-active-date")
      .fetchSemanticsNode()
      .config[SemanticsProperties.Text]
    return texts.joinToString(separator = "") { it.text }
  }
}
