package com.life.lifeload.ui

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import com.life.lifeload.ui.regression.closeKeyboard
import com.life.lifeload.ui.regression.replaceTextAndAssert
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class ImplementedSurfaceGateInstrumentedTest {
  @get:Rule
  val compose = createAndroidComposeRule<MainActivity>()

  @Test
  fun implementedAndroidSurfacesNavigateConfigureAndPersistManualCloseout() {
    val context = compose.activity.applicationContext
    val daysBack = 11
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(daysBack.toLong()).toString()
    val diaryText = "implemented surface gate neutral manual note"

    ServerConfig.resetBaseUrl(context)
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }

    waitForGuidance()
    navigateFromDrawer("Check-in")
    waitForDaily()
    compose.onNodeWithText("Check-in").assertIsDisplayed()
    compose.onNodeWithText("Core").assertIsDisplayed()
    compose.onNodeWithText("More signals").assertIsDisplayed()
    compose.onAllNodesWithText("Movement").assertCountEquals(0)
    compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
    compose.onNodeWithTag("daily_analyze_button").assertIsEnabled()
    compose.onNodeWithTag("daily_approve_button").assertIsEnabled()
    GateVisual.pause()

    navigateFromDrawer("Guidance")
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Weekly review", substring = true).fetchSemanticsNodes().isNotEmpty() ||
      compose.onAllNodesWithText("Weekly view is waiting", substring = true).fetchSemanticsNodes().isNotEmpty() ||
        compose.onAllNodesWithText("Not enough saved check-ins", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    GateVisual.pause()

    navigateFromDrawer("Settings")
    compose.onNodeWithText("Daily flow").assertIsDisplayed()
    compose.onNodeWithText("Garmin import and check-in refresh behavior.").assertIsDisplayed()
    compose.onNodeWithText("Garmin active").assertIsDisplayed()
    compose.onNodeWithTag("settings_include_late_phone").performScrollTo().assertIsDisplayed()
    compose.onNodeWithTag("settings_include_project_overrun").performScrollTo().assertIsDisplayed()
    compose.onNodeWithTag("settings_include_late_phone").performClick()
    compose.onNodeWithTag("settings_include_late_phone").performClick()
    compose.onNodeWithTag("settings_save_button").performScrollTo().performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Settings saved.", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    GateVisual.pause()

    navigateFromDrawer("Check-in")
    waitForDaily()
    compose.onNodeWithTag("formula_button").performClick()
    compose.onNodeWithText("Guidance & scoring").assertIsDisplayed()
    compose.onNodeWithText("Current:", substring = true).assertIsDisplayed()
    compose.onNodeWithText("Close").performClick()
    GateVisual.pause()

    openDailyDaysBeforeToday(daysBack)
    waitForDiaryEnabled()
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("alcohol_none").performClick()
    compose.onNodeWithTag("binge_no").performClick()
    compose.onNodeWithText("More signals").performScrollTo().performClick()
    compose.onNodeWithText("Recovery / Evening").performScrollTo().performClick()
    compose.onNodeWithTag("phone_after_21_yes").performScrollTo().performClick()
    compose.onNodeWithTag("project_overrun_yes").performScrollTo().performClick()
    GateVisual.pause()

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasText("Review before saving"))
    compose.onNodeWithText("Review before saving").assertIsDisplayed()
    compose.onNodeWithText("Only correct items that change today's recommendation.").assertIsDisplayed()
    compose.onNodeWithText("Late phone").assertIsDisplayed()
    compose.onAllNodesWithText("Project overrun")[0].assertIsDisplayed()
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("daily_approve_button"))
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      LifeLoadLocalStore(context).use { store -> store.getEntry(fixtureDate)?.state == "approved" }
    }

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      assertNotNull(record)
      assertEquals("approved", record?.state)
      assertEquals(diaryText, record?.entry?.diaryText)
      assertEquals(true, record?.entry?.sleepOk)
      assertEquals(true, record?.entry?.nutritionOk)
      assertEquals("none", record?.entry?.alcohol)
      assertEquals(false, record?.entry?.binge)
      assertEquals(true, record?.entry?.phoneAfter21)
      assertEquals(true, record?.entry?.projectOverrun)
      assertTrue(record?.score?.nextAction?.isNotBlank() == true)
    }
  }

  private fun waitForGuidance() {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun waitForDaily() {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in").fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun waitForDiaryEnabled() {
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
        true
      }.getOrDefault(false)
    }
  }

  private fun navigateFromDrawer(label: String) {
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasContentDescription("Open navigation"))
    compose.onNodeWithContentDescription("Open navigation").performClick()
    GateVisual.pause()
    compose.onAllNodesWithText(label)[0].performClick()
    compose.waitForIdle()
    GateVisual.pause()
  }

  private fun openDailyDaysBeforeToday(daysBack: Int) {
    waitForDaily()
    compose.onNodeWithText("Today").performClick()
    repeat(daysBack) {
      compose.onNodeWithContentDescription("Previous day").performClick()
      compose.waitForIdle()
      GateVisual.pause()
    }
  }
}
