package com.life.lifeload.ui.regression

import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class DailyTagsPersistenceInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun tagsGuiFieldPersistsToAndroidLocalStore() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.waitForEnabledTag("daily_diary_text")
    val diaryText = "daily tags persistence neutral note"
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()

    robot.scrollToTag("daily_more_signals_section")
    compose.onNodeWithTag("daily_more_signals_section").performClick()
    robot.scrollTo(hasTestTag("daily_tags_notes_section"))
    compose.onNodeWithTag("daily_tags_notes_section").performClick()
    robot.scrollTo(hasTestTag("daily_tags_text"))
    compose.onNodeWithTag("daily_tags_text").performTextInput("golden, regression")
    closeKeyboard()

    robot.scrollTo(hasTestTag("daily_approve_button"))
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    LifeLoadLocalStore(context).use { store ->
      val tags = store.getEntry(fixtureDate)?.entry?.tags.orEmpty()
      assertTrue(tags.containsAll(listOf("golden", "regression")))
    }
  }
}
