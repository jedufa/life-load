package com.life.lifeload.ui.regression

import android.content.Context
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.core.view.drawToBitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.R
import com.life.lifeload.domain.LifeLoadBetaGuidanceCardState
import com.life.lifeload.domain.LifeLoadBetaGuidanceLabel
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadProfileDraftState
import com.life.lifeload.domain.LifeLoadProfileFeatureFlags
import com.life.lifeload.domain.LifeLoadProfileSetupState
import com.life.lifeload.i18n.LifeLoadLanguageOption
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.ui.LifeLoadUiActions
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.LifeLoadUiVariant
import com.life.lifeload.ui.compass.AboutBetaStatusCard
import com.life.lifeload.ui.compass.BackupRestoreCard
import com.life.lifeload.ui.compass.LanguageSettingsCard
import com.life.lifeload.ui.compass.PrivacyCard
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
class GermanLocalizationSnapshotInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.CompassPlus)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun captureGermanLocalizationReviewSet() {
    val context = compose.activity.applicationContext
    val runId = InstrumentationRegistry.getArguments().getString("snapshot_run_id")
      ?: DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").format(LocalDateTime.now())
    val deviceSlug = InstrumentationRegistry.getArguments().getString("device_slug") ?: "emulator"
    val outputDir = File(context.getExternalFilesDir(null), "german_localization_snapshots/$runId/screenshots")
    outputDir.deleteRecursively()
    outputDir.mkdirs()

    render(outputDir, "${deviceSlug}__A01_settings_language_section_english", LifeLoadLanguageOption.ENGLISH, expandCards = setOf("language")) {
      LanguageSettingsCard()
    }
    render(outputDir, "${deviceSlug}__A02_language_selector_options_english", LifeLoadLanguageOption.ENGLISH, expandCards = setOf("language")) {
      LanguageSettingsCard()
    }
    render(outputDir, "${deviceSlug}__A03_settings_language_section_german", LifeLoadLanguageOption.GERMAN, expandCards = setOf("language")) {
      LanguageSettingsCard()
    }
    render(outputDir, "${deviceSlug}__A04_language_selector_options_german", LifeLoadLanguageOption.GERMAN, expandCards = setOf("language")) {
      LanguageSettingsCard()
    }
    render(outputDir, "${deviceSlug}__A05_language_persistence_after_restart", LifeLoadLanguageOption.GERMAN, expandCards = setOf("about")) {
      AboutBetaStatusCard(state = state("general_balance"), flags = flags())
    }

    render(outputDir, "${deviceSlug}__B01_en_settings_main", LifeLoadLanguageOption.ENGLISH, expandCards = setOf("language")) { SettingsReview("general_balance") }
    render(outputDir, "${deviceSlug}__B02_en_tracking_setup", LifeLoadLanguageOption.ENGLISH) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__B03_en_profile_selector", LifeLoadLanguageOption.ENGLISH) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__B04_en_beta_guidance_card", LifeLoadLanguageOption.ENGLISH) { GuidanceReview(LifeLoadBetaGuidanceLabel.MAINTAIN) }
    render(outputDir, "${deviceSlug}__B05_en_about_beta_status", LifeLoadLanguageOption.ENGLISH) { AboutBetaStatusCard(state = state("general_balance"), flags = flags()) }

    render(outputDir, "${deviceSlug}__C01_de_settings_main", LifeLoadLanguageOption.GERMAN, expandCards = setOf("language")) { SettingsReview("general_balance") }
    render(outputDir, "${deviceSlug}__C02_de_tracking_setup", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__C03_de_profile_selector", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__C04_de_optional_packs", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__C05_de_pattern_awareness_info", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance", setOf("pattern_awareness_pack")) }
    render(outputDir, "${deviceSlug}__C06_de_about_beta_status", LifeLoadLanguageOption.GERMAN) { AboutBetaStatusCard(state = state("general_balance"), flags = flags()) }
    render(outputDir, "${deviceSlug}__C07_de_backup_restore", LifeLoadLanguageOption.GERMAN, expandCards = setOf("backup")) { BackupRestoreCard(state("general_balance"), actions()) }
    render(outputDir, "${deviceSlug}__C08_de_privacy_data", LifeLoadLanguageOption.GERMAN, expandCards = setOf("privacy")) { PrivacyCard(state("general_balance"), actions()) }
    render(
      outputDir,
      "${deviceSlug}__C09_de_delete_reset_confirmation",
      LifeLoadLanguageOption.GERMAN,
      expandCards = setOf("privacy"),
      clickTagBeforeCapture = "privacy-delete-local-button",
    ) { PrivacyCard(state("general_balance"), actions()) }

    render(outputDir, "${deviceSlug}__D01_de_general_balance_active", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__D02_de_work_stress_profile_card", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("work_stress") }
    render(outputDir, "${deviceSlug}__D03_de_training_recovery_profile_card", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("training_recovery") }
    render(outputDir, "${deviceSlug}__D04_de_body_signal_awareness_profile_card", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("body_signal_awareness") }
    render(outputDir, "${deviceSlug}__D05_de_custom_profile_intro", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("custom_stub") }
    render(outputDir, "${deviceSlug}__D06_de_custom_signal_name_entry", LifeLoadLanguageOption.GERMAN, scrollToTag = "custom_signal_name_entry") { TrackingSetupReview("custom_stub") }
    render(outputDir, "${deviceSlug}__D07_de_custom_signal_category_picker", LifeLoadLanguageOption.GERMAN, scrollToTag = "custom_signal_category") { TrackingSetupReview("custom_stub") }
    render(outputDir, "${deviceSlug}__D08_de_custom_signal_guidance_effect_picker", LifeLoadLanguageOption.GERMAN, scrollToTag = "custom_signal_influence_level") { TrackingSetupReview("custom_stub") }

    render(outputDir, "${deviceSlug}__E01_de_general_balance_checkin_top", LifeLoadLanguageOption.GERMAN) { CheckInReview("general_balance") }
    render(outputDir, "${deviceSlug}__E02_de_general_balance_checkin_bottom", LifeLoadLanguageOption.GERMAN, scrollToTag = "profile_field_recovery.shutdown_done") { CheckInReview("general_balance") }
    render(outputDir, "${deviceSlug}__E03_de_work_stress_checkin_top", LifeLoadLanguageOption.GERMAN) { CheckInReview("work_stress") }
    render(outputDir, "${deviceSlug}__E04_de_training_recovery_checkin_top", LifeLoadLanguageOption.GERMAN) { CheckInReview("training_recovery") }
    render(outputDir, "${deviceSlug}__E05_de_body_signal_awareness_checkin_top", LifeLoadLanguageOption.GERMAN) { CheckInReview("body_signal_awareness") }
    render(outputDir, "${deviceSlug}__E06_de_custom_checkin_top", LifeLoadLanguageOption.GERMAN) { CheckInReview("custom_stub") }

    render(outputDir, "${deviceSlug}__F01_de_guidance_stabil_bleiben", LifeLoadLanguageOption.GERMAN) { GuidanceReview(LifeLoadBetaGuidanceLabel.MAINTAIN) }
    render(outputDir, "${deviceSlug}__F02_de_guidance_vereinfachen", LifeLoadLanguageOption.GERMAN) { GuidanceReview(LifeLoadBetaGuidanceLabel.SIMPLIFY) }
    render(outputDir, "${deviceSlug}__F03_de_guidance_schlaf_schuetzen", LifeLoadLanguageOption.GERMAN) { GuidanceReview(LifeLoadBetaGuidanceLabel.PROTECT_SLEEP) }
    render(outputDir, "${deviceSlug}__F04_de_guidance_missing_data_limited_confidence", LifeLoadLanguageOption.GERMAN) { GuidanceReview(LifeLoadBetaGuidanceLabel.SIMPLIFY, missing = true) }
    render(outputDir, "${deviceSlug}__F05_de_guidance_aktiv_nutzen", LifeLoadLanguageOption.GERMAN) { GuidanceReview(LifeLoadBetaGuidanceLabel.PUSH) }
    render(outputDir, "${deviceSlug}__F06_de_guidance_erholen", LifeLoadLanguageOption.GERMAN) { GuidanceReview(LifeLoadBetaGuidanceLabel.RECOVER) }
    render(outputDir, "${deviceSlug}__F07_de_guidance_see_why_expanded", LifeLoadLanguageOption.GERMAN) { SeeWhyReview() }

    render(outputDir, "${deviceSlug}__G01_de_pattern_awareness_default_off", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__G02_de_pattern_awareness_info", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__G03_de_pattern_awareness_opt_in_confirmation", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance", setOf("pattern_awareness_pack")) }
    render(outputDir, "${deviceSlug}__G04_de_pattern_awareness_enabled", LifeLoadLanguageOption.GERMAN) { TrackingSetupReview("general_balance", setOf("pattern_awareness_pack")) }
    render(outputDir, "${deviceSlug}__G05_de_pattern_awareness_guidance_card", LifeLoadLanguageOption.GERMAN) { PatternGuidanceReview() }

    render(outputDir, "${deviceSlug}__H01_de_large_font_settings", LifeLoadLanguageOption.GERMAN, fontScale = 1.8f, expandCards = setOf("language")) { SettingsReview("general_balance") }
    render(outputDir, "${deviceSlug}__H02_de_large_font_tracking_setup", LifeLoadLanguageOption.GERMAN, fontScale = 1.8f) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__H03_de_large_font_profile_selector", LifeLoadLanguageOption.GERMAN, fontScale = 1.8f) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__H04_de_large_font_guidance_card", LifeLoadLanguageOption.GERMAN, fontScale = 1.8f) { GuidanceReview(LifeLoadBetaGuidanceLabel.MAINTAIN) }
    render(outputDir, "${deviceSlug}__H05_de_large_font_about_beta_status", LifeLoadLanguageOption.GERMAN, fontScale = 1.8f) { AboutBetaStatusCard(state = state("general_balance"), flags = flags()) }
    render(outputDir, "${deviceSlug}__H06_de_small_screen_settings", LifeLoadLanguageOption.GERMAN, widthDp = 320, expandCards = setOf("language")) { SettingsReview("general_balance") }
    render(outputDir, "${deviceSlug}__H07_de_small_screen_tracking_setup", LifeLoadLanguageOption.GERMAN, widthDp = 320) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__H08_de_small_screen_general_balance_checkin_top", LifeLoadLanguageOption.GERMAN, widthDp = 320) { CheckInReview("general_balance") }
    render(outputDir, "${deviceSlug}__H09_de_small_screen_general_balance_checkin_bottom", LifeLoadLanguageOption.GERMAN, widthDp = 320, scrollToTag = "profile_field_recovery.shutdown_done") { CheckInReview("general_balance") }
    render(outputDir, "${deviceSlug}__H10_de_small_screen_guidance_card", LifeLoadLanguageOption.GERMAN, widthDp = 320) { GuidanceReview(LifeLoadBetaGuidanceLabel.SIMPLIFY) }
    render(outputDir, "${deviceSlug}__H11_de_dark_mode_settings", LifeLoadLanguageOption.GERMAN, darkTheme = true, expandCards = setOf("language")) { SettingsReview("general_balance") }
    render(outputDir, "${deviceSlug}__H12_de_dark_mode_tracking_setup", LifeLoadLanguageOption.GERMAN, darkTheme = true) { TrackingSetupReview("general_balance") }
    render(outputDir, "${deviceSlug}__H13_de_dark_mode_guidance_card", LifeLoadLanguageOption.GERMAN, darkTheme = true) { GuidanceReview(LifeLoadBetaGuidanceLabel.PROTECT_SLEEP) }
    render(outputDir, "${deviceSlug}__H14_de_dark_mode_about_beta_status", LifeLoadLanguageOption.GERMAN, darkTheme = true) { AboutBetaStatusCard(state = state("general_balance"), flags = flags()) }
    render(outputDir, "${deviceSlug}__H15_de_keyboard_custom_signal_name_entry", LifeLoadLanguageOption.GERMAN, scrollToTag = "custom_signal_name_entry") { TrackingSetupReview("custom_stub") }

    render(outputDir, "${deviceSlug}__I01_de_flags_off_settings_no_tracking_setup", LifeLoadLanguageOption.GERMAN, expandCards = setOf("language")) {
      TrackingSetupSettingsEntryCard(
        flags = flags(profileSetup = false),
        state = state("personal_legacy").profileSetup,
        expanded = false,
        onOpen = {},
        onClose = {},
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
      LanguageSettingsCard()
    }
  }

  private fun render(
    outputDir: File,
    name: String,
    language: LifeLoadLanguageOption,
    fontScale: Float = 1f,
    widthDp: Int = 393,
    darkTheme: Boolean = false,
    expandCards: Set<String> = emptySet(),
    scrollToTag: String? = null,
    clickTagBeforeCapture: String? = null,
    content: @Composable () -> Unit,
  ) {
    val baseContext = compose.activity.applicationContext
    LifeLoadLanguageStore.save(baseContext, language)
    setExpandedCards(baseContext, expandCards)
    compose.activity.setContent {
      val localizedContext = LifeLoadLanguageStore.localizedContext(LocalContext.current, language)
      CompositionLocalProvider(
        LocalContext provides localizedContext,
        LocalDensity provides Density(density = 1f, fontScale = fontScale),
      ) {
        LifeLoadTheme(darkTheme = darkTheme) {
          Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxSize()) {
            Box(
              modifier = Modifier
                .width(widthDp.dp)
                .fillMaxSize()
                .statusBarsPadding()
                .padding(12.dp),
            ) {
              Column(
                modifier = Modifier
                  .fillMaxWidth()
                  .verticalScroll(rememberScrollState()),
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
    clickTagBeforeCapture?.let { tag ->
      compose.onNodeWithTag(tag).performClick()
      compose.waitForIdle()
    }
    scrollToTag?.let { tag ->
      compose.onAllNodesWithTag(tag).onFirst().performScrollTo()
      compose.waitForIdle()
    }
    val bitmap = compose.activity.window.decorView.rootView.drawToBitmap()
    FileOutputStream(File(outputDir, "$name.png")).use { out ->
      bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
    }
  }

  @Composable
  private fun SettingsReview(profileId: String) {
    LanguageSettingsCard()
    TrackingSetupSettingsEntryCard(
      flags = flags(),
      state = state(profileId).profileSetup,
      expanded = false,
      onOpen = {},
      onClose = {},
      onProfileSelected = {},
      onOptionalPackToggled = { _, _ -> },
      onResetDefaults = {},
    )
    BackupRestoreCard(state(profileId), actions())
    PrivacyCard(state(profileId), actions())
    AboutBetaStatusCard(state(profileId), flags())
  }

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
  private fun CheckInReview(profileId: String) {
    GatedProfileDrivenCheckInCard(
      flags = flags(),
      config = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId),
      draftState = LifeLoadProfileDraftState(profileId = profileId),
      onDraftChange = { _, _ -> },
    )
  }

  @Composable
  private fun GuidanceReview(label: LifeLoadBetaGuidanceLabel, missing: Boolean = false) {
    val context = LocalContext.current
    GatedBetaGuidanceCard(
      flags = flags(),
      guidance = LifeLoadBetaGuidanceCardState(
        label = label,
        rationale = context.getString(R.string.german_snapshot_guidance_rationale),
        topDrivers = listOf(
          context.getString(R.string.signal_label_mental_stress),
          context.getString(R.string.signal_label_energy_energy),
          context.getString(R.string.signal_label_core_sleep_ok),
        ),
        recentChange = context.getString(R.string.german_snapshot_recent_change),
        primaryAction = context.getString(R.string.german_snapshot_primary_action),
        confidenceNote = if (missing) context.getString(R.string.german_snapshot_limited_confidence) else context.getString(R.string.german_snapshot_normal_confidence),
        missingSignalLabels = if (missing) listOf(context.getString(R.string.signal_label_mood_mood)) else emptyList(),
        whyDetails = listOf(context.getString(R.string.german_snapshot_why_detail)),
      ),
      onSeeWhy = {},
    )
  }

  @Composable
  private fun PatternGuidanceReview() {
    val context = LocalContext.current
    GatedBetaGuidanceCard(
      flags = flags(),
      guidance = LifeLoadBetaGuidanceCardState(
        label = LifeLoadBetaGuidanceLabel.SIMPLIFY,
        rationale = context.getString(R.string.german_snapshot_pattern_rationale),
        topDrivers = listOf(context.getString(R.string.signal_label_pattern_private_pull), context.getString(R.string.signal_label_pattern_protective_routine)),
        primaryAction = context.getString(R.string.german_snapshot_pattern_action),
        confidenceNote = context.getString(R.string.german_snapshot_normal_confidence),
        whyDetails = listOf(context.getString(R.string.german_snapshot_pattern_why)),
      ),
      onSeeWhy = {},
    )
  }

  @Composable
  private fun SeeWhyReview() {
    GuidanceReview(label = LifeLoadBetaGuidanceLabel.SIMPLIFY)
    Text(
      text = LocalContext.current.getString(R.string.german_snapshot_why_detail),
      color = MaterialTheme.colorScheme.onSurfaceVariant,
      modifier = Modifier.padding(top = 8.dp),
    )
  }

  private fun setExpandedCards(context: Context, expandedKeys: Set<String>) {
    val prefs = context.getSharedPreferences("life_load_settings_cards", Context.MODE_PRIVATE)
    val editor = prefs.edit()
    listOf("language", "backup", "privacy", "about").forEach { key ->
      editor.putBoolean("expanded_$key", key in expandedKeys)
    }
    editor.apply()
  }

  private fun state(profileId: String): LifeLoadUiState =
    LifeLoadUiState(profileSetup = setupState(profileId))

  private fun setupState(profileId: String, optionalPackIds: Set<String> = emptySet()): LifeLoadProfileSetupState =
    LifeLoadProfileSetupState(
      selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId, optionalPackIds = optionalPackIds),
      optionalPackIds = optionalPackIds,
    )

  private fun flags(profileSetup: Boolean = true): LifeLoadProfileFeatureFlags =
    LifeLoadProfileFeatureFlags(
      profileSetupEnabled = profileSetup,
      onboardingEnabled = profileSetup,
      profileDrivenCheckInEnabled = profileSetup,
      devCompatibilityMode = false,
    )

  private fun actions(): LifeLoadUiActions =
    LifeLoadUiActions(
      onRefresh = {},
      onPreviousDate = {},
      onNextDate = {},
      onShiftDate = { _ -> },
      onToday = {},
      onYesterday = {},
      onDiaryChanged = { _ -> },
      onAnalyzeDiary = {},
      onApprove = {},
      onOpenSettings = {},
      onCloseSettings = {},
      onSettingsChanged = { _ -> },
      onSaveSettings = { _ -> },
      onRefreshLocalDebug = {},
      onImportLocalHistory = { _ -> },
      onSyncLocalOutbox = {},
      onMirrorLocalDebug = {},
      onExportLocalData = {},
      onDeleteLocalData = {},
      onTagsChanged = { _ -> },
      onBooleanField = { _, _ -> },
      onIntField = { _, _ -> },
      onStringField = { _, _ -> },
    )
}
