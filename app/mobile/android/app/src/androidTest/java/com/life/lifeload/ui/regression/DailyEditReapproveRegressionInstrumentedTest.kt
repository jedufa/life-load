package com.life.lifeload.ui.regression

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
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class DailyEditReapproveRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun reapprovingSameDayReplacesPersistedValuesInsteadOfMergingOldTruth() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val firstNote = "daily edit reapprove first neutral note"
    val secondNote = "daily edit reapprove replacement neutral note"

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    enterCoreCloseout(firstNote, sleepTag = "sleep_ok_yes", nutritionTag = "nutrition_ok_yes", alcoholTag = "alcohol_none", bingeTag = "binge_no")
    approveAndWait()

    LifeLoadLocalStore(context).use { store ->
      val entry = store.getEntry(fixtureDate)?.entry
      assertEquals(firstNote, entry?.diaryText)
      assertEquals(true, entry?.sleepOk)
      assertEquals(true, entry?.nutritionOk)
      assertEquals("none", entry?.alcohol)
      assertEquals(false, entry?.binge)
    }

    enterCoreCloseout(secondNote, sleepTag = "sleep_ok_no", nutritionTag = "nutrition_ok_no", alcoholTag = "alcohol_home", bingeTag = "binge_yes")
    approveAndWait()

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      val entry = record?.entry
      assertEquals("pending_approval", record?.state)
      assertEquals(secondNote, entry?.diaryText)
      assertEquals(false, entry?.sleepOk)
      assertEquals(false, entry?.nutritionOk)
      assertEquals("home", entry?.alcohol)
      assertEquals(true, entry?.binge)
      assertTrue(store.pendingOutbox().count { it.date == fixtureDate && it.operation == "approve" } >= 2)
    }
  }

  private fun enterCoreCloseout(note: String, sleepTag: String, nutritionTag: String, alcoholTag: String, bingeTag: String) {
    robot.scrollToTag("daily_diary_text")
    robot.waitForEnabledTag("daily_diary_text")
    replaceTextAndAssert(compose, "daily_diary_text", note)
    closeKeyboard()
    tap(sleepTag)
    tap(nutritionTag)
    tap(alcoholTag)
    tap(bingeTag)
  }

  private fun approveAndWait() {
    robot.scrollTo(hasTestTag("daily_approve_button"))
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun tap(tag: String) {
    robot.scrollToTag(tag)
    compose.onNodeWithTag(tag).performClick()
  }
}
