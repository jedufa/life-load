package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.core.view.drawToBitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.BuildConfig
import com.life.lifeload.MainActivity
import com.life.lifeload.R
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.i18n.LifeLoadLanguageOption
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@RunWith(AndroidJUnit4::class)
class InstalledApkRealityCheckInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun captureInstalledRuntimeRealityCheck() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val outputRoot = File(context.getExternalFilesDir(null), "installed_apk_reality_check/$runId")
    val outputDir = File(outputRoot, "screenshots")
    outputRoot.deleteRecursively()
    outputDir.mkdirs()
    val screenshots = mutableListOf<JSONObject>()

    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }
    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.GERMAN)
    context.getSharedPreferences("life_load_profile_onboarding", android.content.Context.MODE_PRIVATE).edit().clear().apply()
    context.getSharedPreferences("life_load_settings_cards", android.content.Context.MODE_PRIVATE)
      .edit()
      .clear()
      .putBoolean("expanded_language", true)
      .putBoolean("expanded_reminder", true)
      .putBoolean("expanded_backup", true)
      .putBoolean("expanded_privacy", true)
      .apply()
    compose.activityRule.scenario.recreate()

    val flagsOn = BuildConfig.LIFE_LOAD_PROFILE_SETUP_ENABLED &&
      BuildConfig.LIFE_LOAD_PROFILE_ONBOARDING_ENABLED &&
      BuildConfig.LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED

    if (!flagsOn) {
      openSettings()
      screenshot(outputDir, screenshots, "17_flag_off_personal_legacy_status", "flag_off_status")
      writeReport(outputRoot, screenshots, mode = "default_flag_off")
      return
    }

    waitForTag("compass-plus-check-in")
    screenshot(outputDir, screenshots, "02_top_navigation_german", "top_navigation")
    openSettings()
    screenshot(outputDir, screenshots, "01_settings_main_german", "settings_main")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-about-beta"))
    screenshot(outputDir, screenshots, "02_about_beta_status_collapsed_german", "about_collapsed")
    compose.onNodeWithTag("beta_status_section_feedback_header").performClick()
    screenshot(outputDir, screenshots, "03_about_beta_status_feedback_german", "about_feedback")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-language"))
    screenshot(outputDir, screenshots, "04_language_selector_german", "language_selector")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings_tracking_setup_entry"))
    screenshot(outputDir, screenshots, "05_tracking_setup_visible_german", "tracking_entry")
    compose.onNodeWithTag("settings_tracking_setup_open").performClick()
    waitForTag("tracking_setup")
    screenshot(outputDir, screenshots, "06_tracking_setup_main_german", "tracking_setup")
    screenshot(outputDir, screenshots, "07_profile_selector_german", "profile_selector")
    compose.onNodeWithTag("profile_choice_general_balance").performClick()
    screenshot(outputDir, screenshots, "08_general_balance_selected_german", "profile_selected")
    screenshot(outputDir, screenshots, "15_pattern_awareness_off_default_german", "pattern_awareness_off")
    compose.onNodeWithTag("profile_choice_custom_stub").performClick()
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("custom_signal_influence_level"))
    screenshot(outputDir, screenshots, "14_custom_profile_picker_german", "custom_profile_picker")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("profile_choice_general_balance"))
    compose.onNodeWithTag("profile_choice_general_balance").performClick()
    compose.onNodeWithTag("settings_tracking_setup_close").performClick()
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-reminder"))
    screenshot(outputDir, screenshots, "16_reminder_screen_german", "reminder")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-backup"))
    screenshot(outputDir, screenshots, "17_backup_restore_german", "backup_restore")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-privacy"))
    screenshot(outputDir, screenshots, "18_privacy_delete_german", "privacy_delete")

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("compass-plus-check-in"))
    compose.onNodeWithTag("compass-plus-check-in").performClick()
    compose.waitUntil(20_000) {
      hasNodeWithTag("profile_driven_check_in") || hasNodeWithTag("profile_onboarding")
    }
    if (hasNodeWithTag("profile_onboarding")) {
      screenshot(outputDir, screenshots, "00_onboarding_german", "onboarding")
      compose.onNodeWithTag("profile_onboarding_start").performClick()
    }
    waitForTag("profile_driven_check_in")
    screenshot(outputDir, screenshots, "09_general_balance_checkin_top_german", "checkin_top")
    compose.onNodeWithTag("profile_input_core.sleep_ok_yes").performClick()
    compose.onNodeWithTag("profile_input_mental.stress_5").performClick()
    compose.onNodeWithTag("profile_input_energy.energy_5").performClick()
    screenshot(outputDir, screenshots, "13_checkin_pick_buttons_german", "checkin_controls")
    compose.onNodeWithTag("profile_driven_check_in").performScrollToNode(hasTestTag("profile_driven_checkin_complete"))
    screenshot(outputDir, screenshots, "10_general_balance_checkin_bottom_german", "checkin_bottom")
    compose.onNodeWithTag("profile_driven_checkin_complete").performClick()
    waitForTag("beta_guidance_card")
    screenshot(outputDir, screenshots, "11_guidance_card_german", "guidance_card")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("beta_guidance_see_why"))
    compose.onNodeWithTag("beta_guidance_see_why").performClick()
    waitForTag("beta_guidance_see_why_dialog")
    screenshot(outputDir, screenshots, "12_see_why_german", "see_why")
    clickText(compose.activity.getString(R.string.close), fallback = "Close")

    writeReport(outputRoot, screenshots, mode = "gated_beta_review")
  }

  private fun openSettings() {
    compose.onNodeWithTag("compass-plus-overflow").performClick()
    clickText(compose.activity.getString(R.string.nav_settings), fallback = "Settings")
    waitForTag("compass-plus-content")
  }

  private fun clickText(primary: String, fallback: String) {
    if (compose.onAllNodesWithText(primary).fetchSemanticsNodes().isNotEmpty()) {
      compose.onNodeWithText(primary).performClick()
    } else {
      compose.onNodeWithText(fallback).performClick()
    }
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      hasNodeWithTag(tag)
    }
  }

  private fun hasNodeWithTag(tag: String): Boolean =
    compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()

  private fun screenshot(outputDir: File, screenshots: MutableList<JSONObject>, name: String, screenId: String) {
    compose.waitForIdle()
    val file = File(outputDir, "$name.png")
    FileOutputStream(file).use { out ->
      compose.activity.window.decorView.rootView.drawToBitmap().compress(Bitmap.CompressFormat.PNG, 100, out)
    }
    screenshots += JSONObject()
      .put("filename", "screenshots/${file.name}")
      .put("screen_id", screenId)
      .put("locale", "de")
      .put("selected_language_setting", "de")
      .put("feature_flags", JSONObject()
        .put("LIFE_LOAD_PROFILE_SETUP_ENABLED", BuildConfig.LIFE_LOAD_PROFILE_SETUP_ENABLED)
        .put("LIFE_LOAD_PROFILE_ONBOARDING_ENABLED", BuildConfig.LIFE_LOAD_PROFILE_ONBOARDING_ENABLED)
        .put("LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED", BuildConfig.LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED))
      .put("fake_data_only", true)
  }

  private fun writeReport(outputRoot: File, screenshots: List<JSONObject>, mode: String) {
    val context = compose.activity.applicationContext
    val selectedProfile = LifeLoadLocalStore(context).use { store -> store.selectedProfileConfig().getString("active_profile_id") }
    val report = JSONObject()
      .put("mode", mode)
      .put("selected_profile_id", selectedProfile)
      .put("language_setting", LifeLoadLanguageStore.load(context).storageKey)
      .put("visible_main_checkin_route", if (mode == "gated_beta_review") "profile-driven check-in path" else "fixed CompassToday/personal_legacy path")
      .put("pattern_awareness_default", "off")
      .put("fake_data_only", true)
      .put("screenshots", JSONArray(screenshots))
    File(outputRoot, "report.json").writeText(report.toString(2), Charsets.UTF_8)
  }
}
