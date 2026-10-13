package com.life.lifeload.ui

import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.regression.UiVariantRule
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@RunWith(AndroidJUnit4::class)
class VisualSnapshotInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule

  @Test
  fun capturePrimaryViewsAndMenus() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val outputDir = "/sdcard/Download/life_load_snapshots/$runId"
    InstrumentationRegistry.getInstrumentation().uiAutomation
      .executeShellCommand("rm -rf ${shellQuote(outputDir)} && mkdir -p ${shellQuote(outputDir)}")
      .close()

    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }

    waitForDaily()
    snapshot(outputDir, "00_daily_top_core")

    compose.onNodeWithContentDescription("Open navigation").performClick()
    snapshot(outputDir, "01_navigation_drawer")
    compose.onNodeWithTag("drawer_daily").performClick()
    compose.waitForIdle()

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("daily_more_signals_section"))
    compose.onNodeWithTag("daily_more_signals_section").performClick()
    snapshot(outputDir, "02_daily_more_signals_collapsed_sections")

    expandDailySection("Movement")
    snapshot(outputDir, "03_daily_movement_parameters")

    expandDailySection("Recovery / Evening")
    snapshot(outputDir, "04_daily_recovery_evening_parameters")

    expandDailySection("Pain / Symptoms")
    snapshot(outputDir, "05_daily_pain_symptoms_parameters")

    expandDailySection("Mood / Stress / Energy")
    snapshot(outputDir, "06_daily_mood_stress_energy_parameters")

    expandDailySection("Work / Family")
    snapshot(outputDir, "07_daily_work_family_parameters")

    expandDailySection("Tags / Notes")
    snapshot(outputDir, "08_daily_tags_notes_parameters")

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("formula_button"))
    compose.onNodeWithTag("formula_button").performClick()
    snapshot(outputDir, "09_formula_dialog")
    compose.onNodeWithText("Close").performClick()

    navigateFromDrawer("Guidance")
    snapshot(outputDir, "10_weekly_view")

    navigateFromDrawer("Settings")
    snapshot(outputDir, "11_settings_connected_data")

    compose.onNodeWithTag("settings_include_training_trend_brake").performScrollTo()
    snapshot(outputDir, "12_settings_daily_formula_display")

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("privacy_controls_card"))
    snapshot(outputDir, "13_settings_status_privacy")

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("local_diagnostics_card"))
    snapshot(outputDir, "14_settings_local_diagnostics")

    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("settings_server_url"))
    snapshot(outputDir, "15_settings_advanced_server")

    ServerConfig.resetBaseUrl(context)
  }

  private fun waitForDaily() {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }
    navigateFromDrawer("Check-in")
    compose.waitForIdle()
  }

  private fun expandDailySection(label: String) {
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasText(label))
    compose.onNodeWithText(label).performClick()
    compose.waitForIdle()
    GateVisual.pause()
  }

  private fun navigateFromDrawer(label: String) {
    compose.onNodeWithContentDescription("Open navigation").performClick()
    GateVisual.pause()
    when (label) {
      "Check-in" -> compose.onNodeWithTag("drawer_daily").performClick()
      "Guidance" -> compose.onNodeWithTag("drawer_weekly").performClick()
      "Settings" -> compose.onNodeWithTag("drawer_settings").performClick()
      else -> compose.onAllNodesWithText(label)[0].performClick()
    }
    compose.waitForIdle()
    GateVisual.pause()
  }

  private fun snapshot(outputDir: String, name: String) {
    compose.waitForIdle()
    GateVisual.pause()
    val path = "$outputDir/$name.png"
    InstrumentationRegistry.getInstrumentation().uiAutomation
      .executeShellCommand("screencap -p ${shellQuote(path)}")
      .close()
  }

  private fun shellQuote(value: String): String = "'${value.replace("'", "'\\''")}'"
}
