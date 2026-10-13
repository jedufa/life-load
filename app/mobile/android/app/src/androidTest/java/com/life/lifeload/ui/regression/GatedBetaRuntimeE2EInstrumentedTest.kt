package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.core.view.drawToBitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.i18n.LifeLoadLanguageOption
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@RunWith(AndroidJUnit4::class)
class GatedBetaRuntimeE2EInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun gatedBetaE2EGeneralBalanceFlowPasses() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val outputDir = File(context.getExternalFilesDir(null), "gated_beta_runtime_e2e/$runId/screenshots")
    outputDir.deleteRecursively()
    outputDir.mkdirs()
    val screenshots = mutableListOf<String>()

    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }
    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.ENGLISH)
    context.getSharedPreferences("life_load_profile_onboarding", android.content.Context.MODE_PRIVATE).edit().clear().apply()
    context.getSharedPreferences("life_load_settings_cards", android.content.Context.MODE_PRIVATE)
      .edit()
      .clear()
      .putBoolean("expanded_backup", true)
      .putBoolean("expanded_privacy", true)
      .apply()
    compose.activityRule.scenario.recreate()

    waitForTag("compass-plus-check-in")
    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("profile_onboarding")
    screenshot(outputDir, screenshots, "01_onboarding_intro")

    compose.onNodeWithTag("profile_choice_general_balance").performClick()
    screenshot(outputDir, screenshots, "02_choose_profile")
    compose.onNodeWithTag("profile_onboarding_start").performClick()
    waitForTag("profile_driven_check_in")
    screenshot(outputDir, screenshots, "03_general_balance_selected")

    listOf(
      "profile_field_body.foot_pain",
      "profile_field_body.shoulder_pain",
      "profile_field_relationship.wife_conflict_count",
      "profile_field_caregiving.homework_done",
      "profile_field_nutrition.alcohol",
      "profile_field_nutrition.binge",
      "profile_field_training.primary_activity_type",
    ).forEach { tag ->
      assertTrue("Expected $tag to be absent", compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isEmpty())
    }

    compose.onNodeWithTag("profile_input_core.sleep_ok_yes").performClick()
    compose.onNodeWithTag("profile_input_mental.stress_5").performClick()
    compose.onNodeWithTag("profile_input_energy.energy_5").performClick()
    screenshot(outputDir, screenshots, "04_profile_driven_checkin")

    compose.onNodeWithTag("profile_driven_checkin_complete").performClick()
    waitForTag("beta_guidance_card")
    screenshot(outputDir, screenshots, "05_beta_guidance_card")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("beta_guidance_see_why"))
    compose.onNodeWithTag("beta_guidance_see_why").performClick()
    waitForTag("beta_guidance_see_why_dialog")
    screenshot(outputDir, screenshots, "06_see_why")
    compose.onNodeWithText("Close").performClick()

    compose.onNodeWithTag("compass-plus-overflow").performClick()
    compose.onNodeWithTag("compass-plus-menu-settings").performClick()
    waitForTag("settings_tracking_setup_entry")
    screenshot(outputDir, screenshots, "07_settings_tracking_setup")
    compose.onNodeWithTag("settings_tracking_setup_open").performClick()
    waitForTag("optional_pack_toggle_pattern_awareness_pack")
    screenshot(outputDir, screenshots, "08_pattern_awareness_off_default")
    LifeLoadLocalStore(context).use { store ->
      val config = store.selectedProfileConfig()
      assertEquals("general_balance", config.getString("active_profile_id"))
      assertEquals(0, config.getJSONArray("optional_pack_ids").length())
    }

    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings_tracking_setup_close"))
    compose.onNodeWithTag("settings_tracking_setup_close").performClick()
    waitForTag("settings_tracking_setup_entry")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-backup"))
    compose.onNodeWithTag("settings-section-backup").assertIsDisplayed()
    screenshot(outputDir, screenshots, "10_backup_restore")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-privacy_header"))
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("privacy-delete-local-button"))
    compose.onNodeWithTag("privacy-delete-local-button").performClick()
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("privacy-confirm-delete-button"))
    screenshot(outputDir, screenshots, "11_privacy_delete")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("settings-section-about-beta"))
    screenshot(outputDir, screenshots, "12_about_beta_status")
    compose.onNodeWithTag("compass-plus-content").performScrollToNode(hasTestTag("privacy-confirm-delete-button"))
    compose.onNodeWithTag("privacy-confirm-delete-button").performClick()
    compose.waitUntil(20_000) {
      LifeLoadLocalStore(context).use { store -> store.selectedProfileConfig().getString("active_profile_id") == "personal_legacy" }
    }
    assertFalse(context.getSharedPreferences("life_load_profile_onboarding", android.content.Context.MODE_PRIVATE).getBoolean("completed", false))

    writeReport(outputDir.parentFile!!, screenshots)
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun screenshot(outputDir: File, screenshots: MutableList<String>, name: String) {
    compose.waitForIdle()
    val file = File(outputDir, "$name.png")
    FileOutputStream(file).use { out ->
      compose.activity.window.decorView.rootView.drawToBitmap().compress(Bitmap.CompressFormat.PNG, 100, out)
    }
    screenshots += "screenshots/${file.name}"
  }

  private fun writeReport(outputDir: File, screenshots: List<String>) {
    val manifest = JSONObject()
      .put("fake_data_only", true)
      .put("feature_flags_required", JSONObject()
        .put("LIFE_LOAD_PROFILE_SETUP_ENABLED", true)
        .put("LIFE_LOAD_PROFILE_ONBOARDING_ENABLED", true)
        .put("LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED", true))
      .put("screenshots", JSONArray(screenshots))
      .put("result", "passed")
      .put("notes", "Runtime flow uses gated profile components and the production generic-profile beta guidance bridge; formula thresholds are unchanged.")
    File(outputDir, "report.json").writeText(manifest.toString(2), Charsets.UTF_8)
  }
}
