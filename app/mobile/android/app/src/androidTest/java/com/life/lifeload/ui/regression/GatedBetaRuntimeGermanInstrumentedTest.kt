package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.core.view.drawToBitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.i18n.LifeLoadLanguageOption
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.ui.LifeLoadUiVariant
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
class GatedBetaRuntimeGermanInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun germanRuntimeOnboardingStringsVisible() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val outputDir = File(context.getExternalFilesDir(null), "gated_beta_runtime_e2e/$runId/german/screenshots")
    outputDir.deleteRecursively()
    outputDir.mkdirs()

    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }
    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.GERMAN)
    context.getSharedPreferences("life_load_profile_onboarding", android.content.Context.MODE_PRIVATE).edit().clear().apply()
    compose.activityRule.scenario.recreate()

    waitForTag("compass-plus-check-in")
    compose.onNodeWithTag("compass-plus-check-in").performClick()
    waitForTag("profile_onboarding")
    compose.onNodeWithText("Life Load hilft, den nächsten tragbaren Schritt zu wählen.").assertIsDisplayed()
    screenshot(outputDir, "09_german_onboarding")

    val report = JSONObject()
      .put("result", "passed")
      .put("locale", "de")
      .put("selected_language", "de")
      .put("screenshot", "german/screenshots/09_german_onboarding.png")
      .put("notes", "German strings rendered in the real gated runtime onboarding path.")
    File(outputDir.parentFile!!.parentFile, "german_report.json").writeText(report.toString(2), Charsets.UTF_8)
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
  }

  private fun screenshot(outputDir: File, name: String) {
    compose.waitForIdle()
    val file = File(outputDir, "$name.png")
    FileOutputStream(file).use { out ->
      compose.activity.window.decorView.rootView.drawToBitmap().compress(Bitmap.CompressFormat.PNG, 100, out)
    }
  }
}
