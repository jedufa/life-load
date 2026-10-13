package com.life.lifeload.ui

import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.BuildConfig
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate
import java.time.ZoneId

/** Run each method separately on a disposable emulator. Force-stop between
 * them to verify a separate application process, without clearing app data. */
@RunWith(AndroidJUnit4::class)
class OpenSourceLocalWorkflowInstrumentedTest {
  @get:Rule val compose = createAndroidComposeRule<MainActivity>()
  private val day get() = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
  private fun store() = LifeLoadLocalStore(compose.activity.applicationContext,
    defaultProfileId = BuildConfig.LIFE_LOAD_DEFAULT_PROFILE_ID)

  private fun waitTag(tag: String) {
    compose.waitUntil(20_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
  }
  private fun scroll(tag: String) {
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag(tag))
  }
  private fun screenshot(name: String) {
    if (name == "checkin" || name == "saved") compose.onNodeWithTag("compass-plus-content").performScrollToIndex(0)
    compose.waitForIdle()
    val root = File(compose.activity.getExternalFilesDir(null), "open-source-screenshots")
    root.mkdirs()
    File(root, "$name.png").outputStream().use {
      InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()!!.compress(Bitmap.CompressFormat.PNG, 100, it)
    }
  }

  @Test fun createSyntheticCheckIn() {
    store().use {
      assertEquals(0, it.status().entryCount)
      assertEquals("general_balance", it.selectedProfileConfig().getString("active_profile_id"))
    }
    waitTag("profile_onboarding_start")
    screenshot("onboarding")
    compose.onNodeWithTag("profile_choice_general_balance").performClick()
    compose.onNodeWithTag("profile_onboarding_start").performClick()
    waitTag("compass-plus-content")
    scroll("daily-core-sleep_yes")
    compose.onNodeWithTag("daily-core-sleep_yes").performClick()
    scroll("daily-core-nutrition_yes")
    compose.onNodeWithTag("daily-core-nutrition_yes").performClick()
    screenshot("checkin")
    scroll("daily-approve-button")
    compose.onNodeWithTag("daily-approve-button").performClick()
    compose.waitUntil(20_000) { store().use { it.getEntry(day)?.state == "pending_approval" } }
    store().use {
      val entry = it.getEntry(day)!!
      assertEquals(true, entry.entry.sleepOk)
      assertEquals(true, entry.entry.nutritionOk)
      assertTrue(it.pendingOutbox().any { row -> row.date == day && row.operation == "approve" })
      // Offline queued input must not pretend to be canonical server approval.
      assertEquals("", entry.score.zone)
    }
    scroll("today-hero-card")
    screenshot("saved")
    compose.onNodeWithTag("compass-plus-guidance").performClick()
    scroll("weekly-guidance-quality")
    compose.onNodeWithTag("weekly-guidance-quality").performClick()
    waitTag("weekly-guidance-quality-help-dialog")
    screenshot("interpretation")
    compose.onNodeWithTag("weekly-guidance-quality-help-close").performClick()
  }

  @Test fun verifyRestartAndDeleteThroughUi() {
    waitTag("compass-plus-content")
    compose.onNodeWithTag("profile_onboarding_start").assertDoesNotExist()
    store().use {
      assertEquals("general_balance", it.selectedProfileConfig().getString("active_profile_id"))
      assertEquals(true, it.getEntry(day)!!.entry.sleepOk)
      assertEquals(true, it.getEntry(day)!!.entry.nutritionOk)
    }
    compose.onNodeWithTag("compass-plus-overflow").performClick()
    compose.onNodeWithTag("compass-plus-menu-settings").performClick()
    scroll("settings-section-privacy_header")
    compose.onNodeWithTag("settings-section-privacy_header").performClick()
    scroll("privacy-delete-local-button")
    compose.onNodeWithTag("privacy-delete-local-button").performClick()
    compose.onNodeWithTag("privacy-confirm-delete-button").performClick()
    compose.waitUntil(20_000) { store().use { it.status().entryCount == 0 } }
    store().use { assertTrue(it.pendingOutbox().isEmpty()) }
  }
}
