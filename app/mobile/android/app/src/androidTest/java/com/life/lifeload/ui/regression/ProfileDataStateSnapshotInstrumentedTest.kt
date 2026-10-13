package com.life.lifeload.ui.regression

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollTo
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
class ProfileDataStateSnapshotInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun captureProfileDataStateGuidanceMatrix() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val deviceSlug = InstrumentationRegistry.getArguments().getString("device_slug") ?: "emulator"
    val outputDir = File(context.getExternalFilesDir(null), "profile_data_state_snapshots/$runId/screenshots")
    outputDir.deleteRecursively()
    outputDir.mkdirs()

    scenarios().forEach { scenario ->
      render(outputDir, "${deviceSlug}__${scenario.id}__card") {
        ScenarioGuidanceReview(scenario)
      }
      render(outputDir, "${deviceSlug}__${scenario.id}__see_why") {
        ScenarioGuidanceReview(scenario, showExpandedWhy = true)
      }
    }

    render(outputDir, "${deviceSlug}__H01_general_balance_no_personal_fields__checkin") {
      ProfileCheckInReview("general_balance")
    }
    render(outputDir, "${deviceSlug}__H02_pattern_awareness_disabled__tracking_setup") {
      TrackingSetupReview("general_balance")
    }
    render(outputDir, "${deviceSlug}__H03_pattern_awareness_enabled__tracking_setup") {
      TrackingSetupReview("general_balance", optionalPackIds = setOf("pattern_awareness_pack"))
    }
    render(outputDir, "${deviceSlug}__G01_dark_mode_tracking_setup", darkTheme = true) {
      TrackingSetupReview("general_balance")
    }
    render(outputDir, "${deviceSlug}__G02_dark_mode_guidance", darkTheme = true) {
      ScenarioGuidanceReview(scenarios().first { it.id == "E02_general_balance_recent_overload" })
    }
    render(outputDir, "${deviceSlug}__G03_about_beta_status") {
      AboutBetaStatusCard(
        state = LifeLoadUiState(profileSetup = setupState("general_balance")),
        flags = flags(),
      )
    }
    render(outputDir, "${deviceSlug}__G03_large_font_about_beta_status", fontScale = 1.8f) {
      AboutBetaStatusCard(
        state = LifeLoadUiState(profileSetup = setupState("general_balance")),
        flags = flags(),
      )
    }
    render(outputDir, "${deviceSlug}__G04_large_font_tracking_setup", fontScale = 1.8f) {
      TrackingSetupReview("general_balance")
    }
    render(outputDir, "${deviceSlug}__G05_small_screen_general_balance_checkin_top", widthDp = 320) {
      ProfileCheckInReview("general_balance")
    }
    render(
      outputDir,
      "${deviceSlug}__G06_small_screen_general_balance_checkin_bottom",
      widthDp = 320,
      scrollToTag = "profile_field_recovery.shutdown_done",
    ) {
      ProfileCheckInReview("general_balance")
    }
  }

  private fun flags(): LifeLoadProfileFeatureFlags =
    LifeLoadProfileFeatureFlags(profileSetupEnabled = true, onboardingEnabled = true, profileDrivenCheckInEnabled = true)

  private fun setupState(profileId: String, optionalPackIds: Set<String> = emptySet()): LifeLoadProfileSetupState =
    LifeLoadProfileSetupState(
      selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId, optionalPackIds = optionalPackIds),
      optionalPackIds = optionalPackIds,
    )

  @Composable
  private fun TrackingSetupReview(profileId: String, optionalPackIds: Set<String> = emptySet()) {
    TrackingSetupCard(
      flags = flags(),
      state = setupState(profileId, optionalPackIds),
      onProfileSelected = {},
      onOptionalPackToggled = { _, _ -> },
      onResetDefaults = {},
    )
  }

  @Composable
  private fun ProfileCheckInReview(profileId: String, optionalPackIds: Set<String> = emptySet()) {
    GatedProfileDrivenCheckInCard(
      flags = flags(),
      config = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId, optionalPackIds = optionalPackIds),
      draftState = LifeLoadProfileDraftState(profileId = profileId),
      onDraftChange = { _, _ -> },
    )
  }

  @Composable
  private fun ScenarioGuidanceReview(scenario: SnapshotScenario, showExpandedWhy: Boolean = false) {
    Column(
      verticalArrangement = Arrangement.spacedBy(12.dp),
      modifier = Modifier
        .fillMaxWidth()
        .testTag("scenario_preview"),
    ) {
      Text(scenario.title, style = MaterialTheme.typography.titleMedium)
      Text(scenario.summary, color = MaterialTheme.colorScheme.onSurfaceVariant)
      GatedBetaGuidanceCard(flags = flags(), guidance = scenario.guidance, onSeeWhy = {})
      if (showExpandedWhy) {
        Card(modifier = Modifier.fillMaxWidth()) {
          Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("See why", style = MaterialTheme.typography.titleSmall)
            scenario.guidance.whyDetails.forEach { detail ->
              Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
          }
        }
      }
    }
  }

  private fun scenarios(): List<SnapshotScenario> = listOf(
    SnapshotScenario(
      id = "E01_general_balance_first_day_sparse",
      title = "General Balance - first day / sparse data",
      summary = "Today: moderate energy, moderate stress, partial recovery data.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.MAINTAIN,
        "Life Load is still learning your baseline, so keep the day steady.",
        listOf("Energy moderate", "Stress moderate", "Some signals missing"),
        "First day with sparse history.",
        "Keep the plan simple and avoid adding optional demands.",
        "Limited confidence while your baseline builds.",
        listOf("Personal compatibility fields are not part of General Balance."),
        missing = listOf("Recovery"),
      ),
    ),
    SnapshotScenario(
      id = "E02_general_balance_recent_overload",
      title = "General Balance - recent overload",
      summary = "Recent context: last few days high stress, low energy, poor recovery.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.SIMPLIFY,
        "Recent stress is stacked with lower energy and weaker recovery.",
        listOf("Stress high", "Energy low", "Recovery low"),
        "The last few days are heavier than your recent baseline.",
        "Remove one optional demand and protect the evening routine.",
        "Normal confidence from recent signals.",
        listOf("The recommendation emphasizes the recent stack instead of old history."),
      ),
    ),
    SnapshotScenario(
      id = "E03_general_balance_old_overload_recent_recovery",
      title = "General Balance - old overload, recent recovery",
      summary = "Recent pattern: older load was high, while the last few days improved.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.MAINTAIN,
        "Recent recovery has improved, so old load is not dominating today.",
        listOf("Energy improving", "Stress moderate", "Recovery better"),
        "The last few days look steadier than the older heavy stretch.",
        "Keep the recovery pattern and avoid a catch-up surge.",
        "Normal confidence from recent signals.",
        listOf("Older overload is acknowledged without overruling recent improvement."),
      ),
    ),
    SnapshotScenario(
      id = "E04_work_stress_high_pressure",
      title = "Work Stress - high work pressure",
      summary = "Today: high work pressure, high stress, lower decompression.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.PROTECT_SLEEP,
        "Work pressure is high and recovery margin is low.",
        listOf("Work pressure", "Stress", "Decompression missed"),
        "Work load has stayed elevated for several days.",
        "Cut one late task and make the shutdown routine non-negotiable.",
        "Normal confidence from work-stress signals.",
        listOf("Personal compatibility fields are excluded by default."),
      ),
    ),
    SnapshotScenario(
      id = "E05_training_recovery_high_load_low_recovery",
      title = "Training Recovery - high load and low recovery",
      summary = "Today: high training load, soreness, low energy.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.RECOVER,
        "Training load is high while recovery signals are low.",
        listOf("Training load", "Body load", "Energy low"),
        "Recent training load is outpacing recovery.",
        "Choose recovery work and skip extra intensity.",
        "Normal confidence from training-recovery signals.",
        listOf("Personal compatibility fields are not part of this profile."),
      ),
    ),
    SnapshotScenario(
      id = "E06_training_recovery_good_recovery",
      title = "Training Recovery - good recovery",
      summary = "Today: good energy, low soreness, manageable load.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.PUSH,
        "Recovery looks steady enough for a normal training day.",
        listOf("Energy good", "Body load low", "Sleep steady"),
        "Recent signals are stable.",
        "Use the planned session and stop before adding bonus intensity.",
        "Normal confidence from recovery signals.",
        listOf("The card does not invent risk when recovery is good."),
      ),
    ),
    SnapshotScenario(
      id = "E07_body_signal_awareness_high_signal",
      title = "Body Signal Awareness - high body signal",
      summary = "Today: general body signal high, energy mixed.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.SIMPLIFY,
        "Body signal is elevated, so reduce load with non-medical wording.",
        listOf("Body signal high", "Energy mixed", "Recovery uneven"),
        "Body signal has been rising recently.",
        "Keep movement gentle and make the day smaller.",
        "Normal confidence from body-signal inputs.",
        listOf("This uses general body-signal wording, not fixed body-part assumptions."),
      ),
    ),
    SnapshotScenario(
      id = "E08_custom_admin_load",
      title = "Custom - Admin load",
      summary = "Custom signal: Admin load, Life load category, Strong effect.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.SIMPLIFY,
        "Admin load is high and energy is lower than usual.",
        listOf("Admin load", "Energy lower", "Stress rising"),
        "Admin load has been high for 2 days.",
        "Pick one admin task and defer the rest.",
        "Normal confidence from selected custom signals.",
        listOf("The custom label appears as a private user label without raw formula sliders."),
      ),
    ),
    SnapshotScenario(
      id = "E09_pattern_awareness_disabled",
      title = "Pattern Awareness disabled",
      summary = "Recent context: private pattern-like inputs stay inactive because the pack is off.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.MAINTAIN,
        "Pattern Awareness is off, so private pattern signals are not used.",
        listOf("Stress moderate", "Energy steady", "Pack off"),
        "No private pattern input is active.",
        "Keep the normal plan and review only enabled signals.",
        "Normal confidence from enabled signals.",
        listOf("Disabled optional pack data does not become visible guidance."),
      ),
    ),
    SnapshotScenario(
      id = "E10_pattern_awareness_enabled_high_pull",
      title = "Pattern Awareness enabled - high pull",
      summary = "Opt-in path: private pattern pull high, stabilizing routine missed.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.PROTECT_SLEEP,
        "Private pattern pull is high, so make the evening simple.",
        listOf("Private pattern", "Stress high", "Routine missed"),
        "The private pattern signal is elevated today.",
        "Choose one stabilizing action and keep the evening low-friction.",
        "Normal confidence from explicitly enabled private signals.",
        listOf("Wording stays private, opt-in, calm, and non-judgmental."),
      ),
    ),
    SnapshotScenario(
      id = "E11_missing_data_limited_confidence",
      title = "Missing data / limited confidence",
      summary = "Today: only a few fields answered.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.MAINTAIN,
        "Only a few signals are present, so treat this as a light suggestion.",
        listOf("Energy present", "Stress present", "Recovery missing"),
        "Sparse data limits certainty.",
        "Answer one recovery signal or keep the day steady.",
        "Limited confidence because optional data is missing.",
        listOf("Missing optional data is uncertainty, not failure."),
        missing = listOf("Sleep on time", "Recovery"),
      ),
    ),
    SnapshotScenario(
      id = "E12_explicit_false_zero_absent",
      title = "Explicit false / zero / absent",
      summary = "Today: one false value, one zero value, one absent value.",
      guidance = guidance(
        LifeLoadBetaGuidanceLabel.MAINTAIN,
        "Explicit no and zero values are present; absent values remain unknown.",
        listOf("Routine: no", "Admin load: 0", "Sleep unknown"),
        "Present low values are not treated as missing.",
        "Keep steady and fill the unknown sleep signal if useful.",
        "Limited confidence because one signal is absent.",
        listOf("False, zero, and absent states remain distinct in the review evidence."),
        missing = listOf("Sleep"),
      ),
    ),
  )

  private fun guidance(
    label: LifeLoadBetaGuidanceLabel,
    rationale: String,
    drivers: List<String>,
    recentChange: String,
    action: String,
    confidence: String,
    why: List<String>,
    missing: List<String> = emptyList(),
  ): LifeLoadBetaGuidanceCardState =
    LifeLoadBetaGuidanceCardState(
      label = label,
      rationale = rationale,
      topDrivers = drivers,
      recentChange = recentChange,
      primaryAction = action,
      confidenceNote = confidence,
      missingSignalLabels = missing,
      whyDetails = why,
    )

  private fun render(
    outputDir: File,
    name: String,
    darkTheme: Boolean = false,
    fontScale: Float = 1.0f,
    widthDp: Int? = null,
    scrollToTag: String? = null,
    content: @Composable () -> Unit,
  ) {
    compose.activity.setContent {
      LifeLoadTheme(darkTheme = darkTheme) {
        Surface(Modifier.fillMaxSize()) {
          val density = LocalDensity.current
          CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale = fontScale)) {
            Box(modifier = Modifier.fillMaxSize()) {
              Column(
                modifier = Modifier
                  .then(if (widthDp != null) Modifier.width(widthDp.dp) else Modifier.fillMaxWidth())
                  .fillMaxSize()
                  .statusBarsPadding()
                  .verticalScroll(rememberScrollState())
                  .padding(start = 16.dp, top = 12.dp, end = 16.dp, bottom = 16.dp)
                  .testTag("scenario_preview_safe_area"),
                verticalArrangement = Arrangement.spacedBy(12.dp),
              ) {
                content()
              }
            }
          }
        }
      }
    }
    compose.waitForIdle()
    scrollToTag?.let { tag ->
      compose.onNodeWithTag(tag).performScrollTo()
      compose.waitForIdle()
    }
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

data class SnapshotScenario(
  val id: String,
  val title: String,
  val summary: String,
  val guidance: LifeLoadBetaGuidanceCardState,
)
