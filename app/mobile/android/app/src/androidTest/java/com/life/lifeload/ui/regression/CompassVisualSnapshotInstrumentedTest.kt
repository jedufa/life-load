package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
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
class CompassVisualSnapshotInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun captureCompassPrimaryViews() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val outputDir = File(context.getExternalFilesDir(null), "compass_snapshots/$runId")
    outputDir.deleteRecursively()
    outputDir.mkdirs()

    RegressionFixture.resetAppState(context)
    waitForTag("compass-content")
    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")

    snapshot(outputDir, "00_today_simple")

    compose.onNodeWithTag("nav-week").performClick()
    waitForTag("weekly-hero-card")
    snapshot(outputDir, "01_week_simple")
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag(tag).fetchSemanticsNode()
        true
      }.getOrDefault(false)
    }
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
