package com.life.lifeload.ui.regression

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.DebugUiVariantStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class UiVariantSelectionRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun variantRuleSelectsCompassBeforeActivityLaunch() {
    val context = compose.activity.applicationContext
    RegressionFixture.resetAppState(context)

    assertEquals(LifeLoadUiVariant.Compass, DebugUiVariantStore.resolve(context))
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag("compass-content").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("compass-content").fetchSemanticsNode()
  }

  @Test
  fun defaultVariantIsCompassPlus() {
    assertEquals(LifeLoadUiVariant.CompassPlus, com.life.lifeload.ui.LifeLoadUiVariantRegistry.default)
  }
}
