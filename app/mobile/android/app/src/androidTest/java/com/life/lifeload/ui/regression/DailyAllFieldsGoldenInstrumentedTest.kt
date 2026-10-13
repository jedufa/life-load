package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsEnabled
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
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class DailyAllFieldsGoldenInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun allDailyGuiFieldsPersistToAndroidLocalStore() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val diaryText = "daily all fields golden neutral note"
    val symptomsText = "synthetic tight calf"

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
        true
      }.getOrDefault(false)
    }
    compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()

    tap("sleep_ok_no")
    tap("nutrition_ok_yes")
    tap("alcohol_social")
    tap("binge_no")

    expand("daily_more_signals_section")
    expand("daily_movement_section")
    tap("primary_activity_type_crossfit")
    tap("activity_duration_min_45")

    expand("daily_recovery_evening_section")
    tap("rehab_done_yes")
    tap("decompression_done_no")
    tap("shutdown_done_no")
    tap("phone_after_21_yes")
    tap("project_overrun_yes")

    expand("daily_pain_symptoms_section")
    tap("foot_pain_6")
    tap("shoulder_pain_4")
    tap("migraine_warning_yes")
    robot.scrollToTag("other_symptoms")
    compose.onNodeWithTag("other_symptoms").performTextInput(symptomsText)
    closeKeyboard()

    expand("daily_mood_stress_energy_section")
    tap("mood_4")
    tap("stress_8")
    tap("energy_2")
    tap("coffee_cups_3")

    robot.scrollTo(hasTestTag("daily_approve_button"))
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      val entry = record?.entry
      assertEquals("pending_approval", record?.state)
      assertEquals(diaryText, entry?.diaryText)
      assertEquals(false, entry?.sleepOk)
      assertEquals(true, entry?.nutritionOk)
      assertEquals("social", entry?.alcohol)
      assertEquals(false, entry?.binge)
      assertEquals("crossfit", entry?.primaryActivityType)
      assertEquals(listOf("crossfit"), entry?.activityTypes)
      assertEquals(45, entry?.activityDurationMin)
      assertEquals(true, entry?.rehabDone)
      assertEquals(false, entry?.decompressionDone)
      assertEquals(false, entry?.shutdownDone)
      assertEquals(true, entry?.phoneAfter21)
      assertEquals(true, entry?.projectOverrun)
      assertEquals(6, entry?.footPain)
      assertEquals(4, entry?.shoulderPain)
      assertEquals(true, entry?.migraineWarning)
      assertEquals(symptomsText, entry?.otherSymptoms)
      assertEquals(4, entry?.mood)
      assertEquals(8, entry?.stress)
      assertEquals(2, entry?.energy)
      assertEquals(3, entry?.coffeeCups)
      assertTrue(store.pendingOutbox().any { it.date == fixtureDate && it.operation == "approve" })
    }
  }

  private fun expand(tag: String) {
    robot.scrollToTag(tag)
    compose.onNodeWithTag(tag).performClick()
  }

  private fun tap(tag: String) {
    robot.scrollToTag(tag)
    compose.onNodeWithTag(tag).performClick()
  }
}
