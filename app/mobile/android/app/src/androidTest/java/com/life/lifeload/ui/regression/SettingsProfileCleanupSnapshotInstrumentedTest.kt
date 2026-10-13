package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.domain.LifeLoadBetaGuidanceCardState
import com.life.lifeload.domain.LifeLoadBetaGuidanceLabel
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadProfileDraftState
import com.life.lifeload.domain.LifeLoadProfileFeatureFlags
import com.life.lifeload.domain.LifeLoadProfileSetupState
import com.life.lifeload.ui.GateVisual
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.LifeLoadUiVariant
import com.life.lifeload.ui.compass.AboutBetaStatusCard
import com.life.lifeload.ui.profile.GatedBetaGuidanceCard
import com.life.lifeload.ui.profile.GatedProfileDrivenCheckInCard
import com.life.lifeload.ui.profile.TrackingSetupCard
import com.life.lifeload.ui.profile.TrackingSetupSettingsEntryCard
import com.life.lifeload.ui.theme.LifeLoadTheme
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@RunWith(AndroidJUnit4::class)
class SettingsProfileCleanupSnapshotInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun captureSettingsProfileCleanupReview() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val deviceSlug = InstrumentationRegistry.getArguments().getString("device_slug") ?: "emulator"
    val outputDir = File(context.getExternalFilesDir(null), "settings_profile_cleanup_snapshots/$runId/screenshots")
    outputDir.deleteRecursively()
    outputDir.mkdirs()

    render(outputDir, "${deviceSlug}__flags_on__general_balance__S05__settings_tracking_setup_entry") {
      TrackingSetupSettingsEntryCard(
        flags = flags(),
        state = setupState("general_balance"),
        expanded = false,
        onOpen = {},
        onClose = {},
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S06__tracking_setup_main") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("general_balance"),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S07__profile_list") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("general_balance"),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S08__general_balance_active_signals") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("general_balance"),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S09__optional_packs_default") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("general_balance"),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S10__pattern_awareness_info") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("general_balance", optionalPackIds = setOf("pattern_awareness_pack")),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S11__large_font_tracking_setup") {
      val density = LocalDensity.current
      CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale = 1.8f)) {
        TrackingSetupCard(
          flags = flags(),
          state = setupState("general_balance"),
          onProfileSelected = {},
          onOptionalPackToggled = { _, _ -> },
          onResetDefaults = {},
        )
      }
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__S12__small_width_tracking_setup") {
      Box(Modifier.width(320.dp)) {
        TrackingSetupCard(
          flags = flags(),
          state = setupState("general_balance"),
          onProfileSelected = {},
          onOptionalPackToggled = { _, _ -> },
          onResetDefaults = {},
        )
      }
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__P01__polished_beta_guidance") {
      GatedBetaGuidanceCard(
        flags = flags(),
        guidance = betaGuidance(),
        onSeeWhy = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__P02__guidance_missing_data") {
      GatedBetaGuidanceCard(
        flags = flags(),
        guidance = betaGuidance(missingSignalLabels = listOf("Sleep on time", "Energy")),
        onSeeWhy = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__P03__guidance_large_font") {
      val density = LocalDensity.current
      CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale = 1.8f)) {
        GatedBetaGuidanceCard(
          flags = flags(),
          guidance = betaGuidance(),
          onSeeWhy = {},
        )
      }
    }
    render(outputDir, "${deviceSlug}__flags_on__custom_stub__P04__custom_profile_setup") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("custom_stub"),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__custom_stub__P05__custom_signal_category_picker") {
      TrackingSetupCard(
        flags = flags(),
        state = setupState("custom_stub"),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__D01__checkin_controls") {
      ProfileCheckInReview("general_balance")
    }
    render(outputDir, "${deviceSlug}__flags_on__work_stress__D02__checkin_controls") {
      ProfileCheckInReview("work_stress")
    }
    render(outputDir, "${deviceSlug}__flags_on__training_recovery__D03__checkin_controls") {
      ProfileCheckInReview("training_recovery")
    }
    render(outputDir, "${deviceSlug}__flags_on__body_signal_awareness__D04__checkin_controls") {
      ProfileCheckInReview("body_signal_awareness")
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__A04__about_beta_status") {
      AboutBetaStatusCard(
        state = LifeLoadUiState(profileSetup = setupState("general_balance")),
        flags = flags(),
      )
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__G02__small_width_checkin_controls") {
      Box(Modifier.width(320.dp)) {
        ProfileCheckInReview("general_balance")
      }
    }
    render(outputDir, "${deviceSlug}__flags_on__general_balance__G03__dark_mode_guidance") {
      LifeLoadTheme(darkTheme = true) {
        GatedBetaGuidanceCard(
          flags = flags(),
          guidance = betaGuidance(),
          onSeeWhy = {},
        )
      }
    }
  }

  private fun flags(): LifeLoadProfileFeatureFlags =
    LifeLoadProfileFeatureFlags(profileSetupEnabled = true, onboardingEnabled = true, profileDrivenCheckInEnabled = true)

  private fun setupState(profileId: String, optionalPackIds: Set<String> = emptySet()): LifeLoadProfileSetupState =
    LifeLoadProfileSetupState(
      selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId, optionalPackIds = optionalPackIds),
      optionalPackIds = optionalPackIds,
    )

  private fun betaGuidance(missingSignalLabels: List<String> = emptyList()): LifeLoadBetaGuidanceCardState =
    LifeLoadBetaGuidanceCardState(
      label = LifeLoadBetaGuidanceLabel.SIMPLIFY,
      rationale = "Stress and overall load are higher than usual, while energy is lower.",
      topDrivers = listOf("Stress high", "Energy low", "Load high"),
      recentChange = "Stress rose this week.",
      primaryAction = "Remove one optional demand today.",
      confidenceNote = if (missingSignalLabels.isEmpty()) "Normal confidence." else "Limited confidence because some signals are missing.",
      missingSignalLabels = missingSignalLabels,
      whyDetails = listOf("Recent signals suggest reducing optional load."),
    )

  @Composable
  private fun ProfileCheckInReview(profileId: String) {
    GatedProfileDrivenCheckInCard(
      flags = flags(),
      config = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId),
      draftState = LifeLoadProfileDraftState(profileId = profileId),
      onDraftChange = { _, _ -> },
    )
  }

  private fun render(outputDir: File, name: String, content: @Composable () -> Unit) {
    compose.activity.setContent {
      LifeLoadTheme {
        Surface(Modifier.fillMaxSize()) {
          Column(
            modifier = Modifier
              .fillMaxSize()
              .verticalScroll(rememberScrollState())
              .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
          ) {
            content()
          }
        }
      }
    }
    compose.waitForIdle()
    GateVisual.pause()
    snapshot(outputDir, name)
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
