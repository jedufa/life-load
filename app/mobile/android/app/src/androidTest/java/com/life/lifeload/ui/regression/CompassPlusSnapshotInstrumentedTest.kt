package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.espresso.Espresso.pressBack
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.ui.GateVisual
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@RunWith(AndroidJUnit4::class)
class CompassPlusSnapshotInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun captureCompassPlusReviewViews() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val deviceSlug = InstrumentationRegistry.getArguments().getString("device_slug") ?: "emulator"
    val outputDir = File(context.getExternalFilesDir(null), "compass_plus_snapshots/$runId/screenshots")
    outputDir.deleteRecursively()
    outputDir.mkdirs()

    RegressionFixture.resetAppState(context)
    waitForTag("compass-plus-content")
    waitForTag("weekly-hero-card")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP01__guidance_home")

    compose.onNodeWithTag("weekly-next-action").performClick()
    waitForTag("weekly-guidance-reason-dialog")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP02__guidance_reason_dialog")
    dismissTopWindow()

    compose.onNodeWithTag("weekly-guidance-quality").performClick()
    waitForTag("weekly-guidance-quality-help-dialog")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP03__guidance_quality_dialog")
    dismissTopWindow()

    compose.onNodeWithTag("compass-plus-brand-container").performClick()
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithText("How Life Load works").fetchSemanticsNode()
        true
      }.getOrDefault(false)
    }
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP04__help_dialog")
    dismissTopWindow()

    compose.onNodeWithTag("compass-plus-date-label").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag("compass-plus-previous-day").fetchSemanticsNodes().isNotEmpty()
    }
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP05__date_controls")

    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("quick-checkin-card")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP06__checkin_top")

    compose.onNodeWithTag("compass-plus-overflow").performClick()
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag("compass-plus-menu-settings").fetchSemanticsNode()
        true
      }.getOrDefault(false)
    }
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP08__overflow_menu")
    compose.onNodeWithTag("compass-plus-menu-settings").performClick()
    waitForTag("settings-section-reminder")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP09__settings_reminder")

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-guidance"))
    compose.onNodeWithTag("settings-section-guidance").performClick()
    waitForTag("settings-section-guidance")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP10__settings_guidance_scoring")

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-backup"))
    compose.onNodeWithTag("settings-section-backup").performClick()
    waitForTag("settings-section-backup")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP11__settings_backup_restore")

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-privacy"))
    compose.onNodeWithTag("settings-section-privacy").performClick()
    waitForTag("settings-section-privacy")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP12__settings_privacy")

    compose.onNodeWithTag("privacy-security-button").performClick()
    waitForTag("privacy-security-dialog")
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP13__privacy_security_dialog")
    dismissTopWindow()

    compose.onNodeWithTag("privacy-delete-local-button").performClick()
    compose.waitForIdle()
    GateVisual.pause()
    snapshot(outputDir, "${deviceSlug}__flags_off__compass_plus__CP14__delete_reset_area")
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
    compose.waitForIdle()
    GateVisual.pause()
  }

  private fun dismissTopWindow() {
    pressBack()
    compose.waitForIdle()
    GateVisual.pause()
  }

  private fun snapshot(outputDir: File, name: String) {
    compose.waitForIdle()
    GateVisual.pause()
    val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
    FileOutputStream(File(outputDir, "$name.png")).use { out ->
      bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
    }
    bitmap.recycle()
  }
}
