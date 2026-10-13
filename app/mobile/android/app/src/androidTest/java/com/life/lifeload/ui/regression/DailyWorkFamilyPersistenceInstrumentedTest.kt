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
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class DailyWorkFamilyPersistenceInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun workAndFamilyGuiFieldsPersistToAndroidLocalStore() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.waitForEnabledTag("daily_diary_text")
    val diaryText = "daily work family persistence neutral note"
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()

    robot.scrollToTag("daily_more_signals_section")
    compose.onNodeWithTag("daily_more_signals_section").performClick()
    robot.scrollTo(hasTestTag("daily_work_family_section"))
    compose.onNodeWithTag("daily_work_family_section").performClick()
    tap("work_intensity_heavy")
    tap("home_office_yes")
    tap("family_stress_high")
    tap("wife_conflict_count_3")
    tap("alone_home_yes")
    tap("wife_conflict_school_yes")
    tap("wife_conflict_chores_no")
    tap("homework_done_no")

    robot.scrollTo(hasTestTag("daily_approve_button"))
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    LifeLoadLocalStore(context).use { store ->
      val entry = store.getEntry(fixtureDate)?.entry
      assertEquals("heavy", entry?.workIntensity)
      assertEquals(true, entry?.homeOffice)
      assertEquals(8, entry?.familyStress)
      assertEquals(3, entry?.wifeConflictCount)
      assertEquals(true, entry?.aloneHome)
      assertEquals(true, entry?.wifeConflictSchool)
      assertEquals(false, entry?.wifeConflictChores)
      assertEquals(false, entry?.homeworkDone)
      assertEquals("no", entry?.homeworkStatus)
    }
  }

  private fun tap(tag: String) {
    robot.scrollToTag(tag)
    compose.onNodeWithTag(tag).performClick()
  }
}
