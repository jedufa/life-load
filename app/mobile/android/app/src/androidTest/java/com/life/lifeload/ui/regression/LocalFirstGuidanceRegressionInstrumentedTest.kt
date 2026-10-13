package com.life.lifeload.ui.regression

import android.content.Context
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.data.AuthConfig
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TestRule
import org.junit.rules.RuleChain
import org.junit.runner.Description
import org.junit.runner.RunWith
import org.junit.runners.model.Statement
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class LocalFirstGuidanceRegressionInstrumentedTest {
  private val fixtureRule = LocalFirstGuidanceFixtureRule()
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(fixtureRule).around(variantRule).around(compose)

  @Test
  fun guidanceCountsFivePendingLocalCheckInsWithoutSignIn() {
    compose.waitUntil(25_000) {
      compose.onAllNodesWithText("Guidance quality:", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("weekly-hero-card").assertIsDisplayed()
    compose.onAllNodesWithText("Not enough data yet:", substring = true).assertCountEquals(0)
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-data-card"))
    compose.onNodeWithTag("weekly-data-card").assertIsDisplayed()
    compose.waitUntil(5_000) {
      compose.onAllNodesWithText("5 in 10 days saved", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("weekly-trend-card"))
    compose.onNodeWithTag("weekly-trend-card").assertIsDisplayed()
    compose.onNodeWithTag("weekly-recent-path-curve").assertIsDisplayed()
  }
}

private class LocalFirstGuidanceFixtureRule : TestRule {
  override fun apply(base: Statement, description: Description): Statement =
    object : Statement() {
      override fun evaluate() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        seedFivePendingLocalCheckIns(context)
        try {
          base.evaluate()
        } finally {
          RegressionFixture.resetAppState(context)
          AuthConfig.clear(context)
        }
      }
    }

  private fun seedFivePendingLocalCheckIns(context: Context) {
    val anchor = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1)
    RegressionFixture.resetAppState(context)
    AuthConfig.clear(context)
    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
    repeat(5) { offset ->
      RegressionFixture.seedPendingApproval(
        context,
        RegressionFixture.entry(anchor.minusDays(offset.toLong()), note = "local guidance pending day ${offset + 1}"),
      )
    }
  }
}
