package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class DailyAnalysisNegativeRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun blankDiaryAnalysisShowsValidationErrorWithoutCreatingLocalData() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)
    compose.activityRule.scenario.recreate()
    compose.waitForIdle()

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.waitForEnabledTag("daily_diary_text")
    compose.onNodeWithTag("daily_diary_text").performTextClearance()
    compose.onNodeWithTag("daily_analyze_button").performClick()
    compose.waitForIdle()

    LifeLoadLocalStore(context).use { store ->
      assertNull(store.getEntry(fixtureDate))
      assertEquals(0, store.pendingOutbox().size)
    }
  }

  @Test
  fun backendUnavailableAnalysisPreservesManualDraftAndAllowsApproval() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val diaryText = "daily analysis unavailable neutral note"

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)
    compose.activityRule.scenario.recreate()
    compose.waitForIdle()

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.waitForEnabledTag("daily_diary_text")
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("daily_analyze_button").performClick()
    compose.waitUntil(25_000) {
      compose.onAllNodesWithText("Analyze diary", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Diary analysis failed", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Failed to connect", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Diary analysis needs attention", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("daily_diary_text").assertIsDisplayed()

    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      LifeLoadLocalStore(context).use { store ->
        store.getEntry(fixtureDate)?.state == "pending_approval"
      }
    }

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      assertEquals("pending_approval", record?.state)
      assertEquals(diaryText, record?.entry?.diaryText)
      assertEquals(true, record?.entry?.sleepOk)
    }
  }
}
