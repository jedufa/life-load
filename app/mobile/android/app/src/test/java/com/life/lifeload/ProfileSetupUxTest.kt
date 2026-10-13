package com.life.lifeload

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.life.lifeload.domain.LifeLoadBetaGuidanceCardState
import com.life.lifeload.domain.LifeLoadBetaGuidanceLabel
import com.life.lifeload.data.local.LIFE_LOAD_DEBUG_BUNDLE_VERSION
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadProfileDraftState
import com.life.lifeload.domain.LifeLoadProfileFeatureFlags
import com.life.lifeload.domain.devProfileSelectorVisible
import com.life.lifeload.domain.onboardingVisibleForNewUser
import com.life.lifeload.domain.profileCopyHasForbiddenTerms
import com.life.lifeload.domain.profileCopyUsesInstructionLanguage
import com.life.lifeload.domain.profileDrivenCheckInActive
import com.life.lifeload.domain.trackingSetupVisible
import com.life.lifeload.i18n.LifeLoadLanguageOption
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.compass.AboutBetaStatusCard
import com.life.lifeload.ui.compass.LanguageSettingsCard
import com.life.lifeload.ui.profile.DevProfileSelectorCard
import com.life.lifeload.ui.profile.GatedBetaGuidanceCard
import com.life.lifeload.ui.profile.GatedProfileDrivenCheckInCard
import com.life.lifeload.ui.profile.ProfileOnboardingForFlag
import com.life.lifeload.ui.profile.TrackingSetupCard
import com.life.lifeload.ui.profile.TrackingSetupSettingsEntryCard
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ProfileSetupUxTest {
  @get:Rule
  val composeRule = createComposeRule()

  private val stores = mutableListOf<LifeLoadLocalStore>()

  @After
  fun tearDown() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    stores.forEach { store ->
      store.close()
      context.deleteDatabase(store.databaseName)
    }
    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.SYSTEM)
  }

  @Test
  fun dev_profile_selector_hidden_by_default() {
    assertFalse(devProfileSelectorVisible(flags()))
    composeRule.setContent {
      DevProfileSelectorCard(
        flags = flags(),
        selectedProfileId = "personal_legacy",
        onProfileSelected = {},
      )
    }

    composeRule.onNodeWithTag("dev_profile_selector").assertDoesNotExist()
  }

  @Test
  fun profile_selection_persists_across_restart() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val name = "block7_profile_restart.db"
    context.deleteDatabase(name)
    LifeLoadLocalStore(context, name).use { store ->
      store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())
    }

    LifeLoadLocalStore(context, name).use { reopened ->
      assertEquals("general_balance", reopened.selectedProfileConfig().getString("active_profile_id"))
    }
    context.deleteDatabase(name)
  }

  @Test
  fun profile_selection_export_import_roundtrip() {
    val source = localStore("block7_profile_export_source.db")
    source.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("training_recovery").toJson())
    val target = localStore("block7_profile_export_target.db")

    target.restoreDebugBundle(source.exportDebugBundle(redacted = false))

    assertEquals("training_recovery", target.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun profile_switch_does_not_delete_legacy_values() {
    val store = localStore("block7_switch_keeps_legacy.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", footPain = 7, wifeConflictCount = 2))
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())

    val entry = store.getEntry("2026-05-17")?.entry

    assertEquals(7, entry?.footPain)
    assertEquals(2, entry?.wifeConflictCount)
  }

  @Test
  fun reset_returns_to_safe_default() {
    val store = localStore("block7_reset_default.db")
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())

    store.resetLocalData()

    assertEquals("personal_legacy", store.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun beta_review_default_profile_is_general_balance() {
    val store = localStore("block_beta_review_default.db", defaultProfileId = "general_balance")

    val config = store.selectedProfileConfig()

    assertEquals("general_balance", config.getString("active_profile_id"))
    assertEquals(0, config.getJSONArray("optional_pack_ids").length())
  }

  @Test
  fun beta_review_reset_returns_to_general_balance_and_pattern_awareness_off() {
    val store = localStore("block_beta_review_reset.db", defaultProfileId = "general_balance")
    store.saveSelectedProfileConfig(
      LifeLoadProfileCatalog.buildSelectedProfileConfig(
        "general_balance",
        optionalPackIds = setOf("pattern_awareness_pack"),
      ).toJson(),
    )

    store.resetLocalData()
    val config = store.selectedProfileConfig()

    assertEquals("general_balance", config.getString("active_profile_id"))
    assertEquals(0, config.getJSONArray("optional_pack_ids").length())
  }

  @Test
  fun personal_legacy_still_available() {
    assertTrue(LifeLoadProfileCatalog.devProfiles().any { it.id == "personal_legacy" })
  }

  @Test
  fun onboarding_hidden_when_feature_flag_off() {
    assertFalse(onboardingVisibleForNewUser(flags(), hasExistingSelection = false))
    composeRule.setContent {
      ProfileOnboardingForFlag(
        flags = flags(),
        hasExistingSelection = false,
        selectedProfileId = "general_balance",
        onProfileSelected = {},
        onStartFirstCheckIn = {},
      )
    }

    composeRule.onNodeWithTag("profile_onboarding").assertDoesNotExist()
  }

  @Test
  fun onboarding_shown_for_new_user_when_flag_on() {
    composeRule.setContent {
      ProfileOnboardingForFlag(
        flags = flags(onboardingEnabled = true),
        hasExistingSelection = false,
        selectedProfileId = "general_balance",
        onProfileSelected = {},
        onStartFirstCheckIn = {},
      )
    }

    composeRule.onNodeWithTag("profile_onboarding").assertExists()
    composeRule.onNodeWithText("Life Load helps choose the next sustainable step.").assertExists()
  }

  @Test
  fun user_can_select_general_balance() {
    var selected = ""
    composeRule.setContent {
      ProfileOnboardingForFlag(
        flags = flags(onboardingEnabled = true),
        hasExistingSelection = false,
        selectedProfileId = "work_stress",
        onProfileSelected = { selected = it },
        onStartFirstCheckIn = {},
      )
    }

    composeRule.onNodeWithTag("profile_choice_general_balance").performClick()

    assertEquals("general_balance", selected)
  }

  @Test
  fun selected_general_balance_does_not_show_personal_fields() {
    val fields = LifeLoadProfileCatalog.renderableFields(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
    )
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue(generalExcludedFields.intersect(legacyKeys).isEmpty())
  }

  @Test
  fun onboarding_privacy_safety_copy_visible() {
    composeRule.setContent {
      ProfileOnboardingForFlag(
        flags = flags(onboardingEnabled = true),
        hasExistingSelection = false,
        selectedProfileId = "general_balance",
        onProfileSelected = {},
        onStartFirstCheckIn = {},
      )
    }

    composeRule.onNodeWithText("Private wellness signal tracking. Not emergency support.").assertExists()
  }

  @Test
  fun onboarding_signal_info_button_shows_help() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    composeRule.setContent {
      ProfileOnboardingForFlag(
        flags = flags(onboardingEnabled = true),
        hasExistingSelection = false,
        selectedProfileId = "general_balance",
        onProfileSelected = {},
        onStartFirstCheckIn = {},
      )
    }

    composeRule.onNodeWithTag("profile_signal_info_core.sleep_ok", useUnmergedTree = true)
      .performScrollTo()
      .performClick()

    composeRule.onNodeWithText(context.getString(R.string.field_sleep_helper), useUnmergedTree = true).assertExists()
  }

  @Test
  fun profile_driven_checkin_signal_info_button_shows_help() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState("general_balance"),
        onDraftChange = { _, _ -> },
      )
    }

    composeRule.onNodeWithTag("profile_signal_info_energy.energy", useUnmergedTree = true).performClick()

    composeRule.onNodeWithText(context.getString(R.string.field_energy_helper), useUnmergedTree = true).assertExists()
  }

  @Test
  fun tracking_setup_active_signal_info_buttons_are_visible() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("profile_signal_info_core.sleep_ok").assertExists()
    composeRule.onNodeWithTag("profile_signal_info_energy.energy").assertExists()
  }

  @Test
  fun personal_legacy_not_offered_as_public_profile_by_default() {
    val publicProfiles = LifeLoadProfileCatalog.publicProfiles(flags(onboardingEnabled = true))

    assertFalse(publicProfiles.any { it.id == "personal_legacy" })
  }

  @Test
  fun pattern_awareness_not_offered_as_official_profile() {
    assertFalse(LifeLoadProfileCatalog.profiles.containsKey("pattern_awareness_pack"))
    assertFalse(LifeLoadProfileCatalog.publicProfiles(flags(onboardingEnabled = true)).any { it.publicName.contains("Pattern") })
  }

  @Test
  fun tracking_setup_hidden_when_flag_off() {
    assertFalse(trackingSetupVisible(flags()))
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("tracking_setup").assertDoesNotExist()
  }

  @Test
  fun settings_profile_setup_hidden_when_flag_off() {
    composeRule.setContent {
      TrackingSetupSettingsEntryCard(
        flags = flags(),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(),
        expanded = false,
        onOpen = {},
        onClose = {},
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("settings_tracking_setup_entry").assertDoesNotExist()
    composeRule.onNodeWithText("Customize Profile").assertDoesNotExist()
  }

  @Test
  fun settings_profile_setup_visible_when_flag_on() {
    composeRule.setContent {
      TrackingSetupSettingsEntryCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        expanded = false,
        onOpen = {},
        onClose = {},
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("settings_tracking_setup_entry").assertExists()
    composeRule.onNodeWithText("Customize Profile").assertExists()
    composeRule.onNodeWithText("Choose your profile and daily signals.").assertExists()
    composeRule.onNodeWithText("Active profile: General Balance").assertExists()
  }

  @Test
  fun settings_tracking_setup_opens_profile_setup() {
    val expanded = mutableStateOf(false)
    composeRule.setContent {
      TrackingSetupSettingsEntryCard(
        flags = flags(profileSetupEnabled = true, devCompatibilityMode = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        expanded = expanded.value,
        onOpen = { expanded.value = true },
        onClose = { expanded.value = false },
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("settings_tracking_setup_open").performClick()

    composeRule.onNodeWithTag("tracking_setup").assertExists()
    assertTrue(expanded.value)
  }

  @Test
  fun active_profile_visible_when_flag_on() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Active profile: General Balance").assertExists()
  }

  @Test
  fun user_can_change_profile_without_data_loss() {
    val store = localStore("block7_change_profile_no_loss.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", diaryText = "keep fixed row", shoulderPain = 4))
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("work_stress").toJson())

    assertEquals("keep fixed row", store.getEntry("2026-05-17")?.entry?.diaryText)
    assertEquals(4, store.getEntry("2026-05-17")?.entry?.shoulderPain)
    assertEquals("work_stress", store.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun optional_pack_requires_explicit_opt_in() {
    val baseline = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance")
    val withPack = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance", optionalPackIds = setOf("pattern_awareness_pack"))

    assertFalse("pattern_awareness_pack" in baseline.optionalPackIds)
    assertTrue("pattern_awareness_pack" in withPack.optionalPackIds)
    assertTrue(LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack").requiresExplicitOptIn)
    assertFalse(LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack").defaultEnabled)
  }

  @Test
  fun pattern_awareness_copy_avoids_forbidden_clinical_terms() {
    val pack = LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack")

    assertFalse(profileCopyHasForbiddenTerms("${pack.name} ${pack.description}"))
  }

  @Test
  fun custom_signal_limit_enforced() {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig(
      "custom_stub",
      userAddedSignalIds = (1..12).map { "custom.signal_$it" }.toSet(),
    )

    assertTrue(config.enabledSignalIds.size <= config.maxActiveSignals)
  }

  @Test
  fun reset_to_profile_defaults_preserves_history_but_changes_active_config() {
    val store = localStore("block7_reset_profile_defaults.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", diaryText = "history remains"))
    store.saveSelectedProfileConfig(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance", optionalPackIds = setOf("pattern_awareness_pack")).toJson(),
    )

    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())

    assertEquals("history remains", store.getEntry("2026-05-17")?.entry?.diaryText)
    assertEquals(0, store.selectedProfileConfig().getJSONArray("optional_pack_ids").length())
  }

  @Test
  fun check_in_page_does_not_embed_profile_checkin() {
    assertFalse(profileDrivenCheckInActive(flags()))
    assertProductionSourceLacks(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt",
      "profileDrivenCheckInActive(flags)",
      "GatedProfileDrivenCheckInCard",
      "GatedBetaGuidanceCard",
    )
    assertProductionSourceLacks(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadScreen.kt",
      "profileDrivenCheckInActive(profileFeatureFlags)",
      "GatedProfileDrivenCheckInCard",
      "GatedBetaGuidanceCard",
    )
  }

  @Test
  fun accepted_check_in_page_uses_selected_profile_to_gate_legacy_fields() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt",
      "missingFieldsForProfile(state)",
      "activeLegacyFieldKeys(state)",
      "if (\"alcohol\" in activeFields)",
      "if (\"foot_pain\" in activeFields)",
      "if (activeFields.hasAny(MovementFieldKeys))",
    )
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadViewModel.kt",
      "sanitizedForActiveProfile()",
      "draftFieldActive(field)",
      "sanitizedForProfile(activeFields)",
    )
  }

  @Test
  fun feature_flag_on_uses_profile_driven_path() {
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance"),
        onDraftChange = { _, _ -> },
      )
    }

    composeRule.onNodeWithTag("profile_driven_check_in").assertExists()
    composeRule.onNodeWithText("Profile check-in").assertExists()
  }

  @Test
  fun profile_driven_general_balance_excludes_personal_fields() {
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance"),
        onDraftChange = { _, _ -> },
      )
    }

    listOf("Foot pain", "Shoulder pain", "Relationship conflict count", "Homework done", "Alcohol", "Eating episode", "Primary activity type")
      .forEach { label -> composeRule.onNodeWithText(label).assertDoesNotExist() }
  }

  @Test
  fun pattern_awareness_not_visible_without_opt_in() {
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance"),
        onDraftChange = { _, _ -> },
      )
    }

    composeRule.onNodeWithText("Phone after 21:00").assertDoesNotExist()
  }

  @Test
  fun draft_save_preserves_absent_false_zero() {
    val draft = LifeLoadProfileDraftState(profileId = "general_balance")
    val explicitFalse = draft.update("evening.phone_after_21", false)
    val explicitZero = explicitFalse.update("body.foot_pain", 0)

    assertFalse("evening.phone_after_21" in draft.valuesBySignalId)
    assertEquals(false, explicitZero.valuesBySignalId["evening.phone_after_21"]?.value)
    assertEquals(0, explicitZero.valuesBySignalId["body.foot_pain"]?.value)
  }

  @Test
  fun generic_signal_entries_not_consumed_by_scoring() {
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/domain",
      "signal_entries",
      "local_signal_entry",
    )
  }

  @Test
  fun personal_legacy_path_matches_existing_behavior() {
    val fields = LifeLoadProfileCatalog.renderableFields(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("personal_legacy"),
    )
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue(personalLegacyFields.all { it in legacyKeys })
  }

  @Test
  fun guidance_scoring_legacy_controls_still_available() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadScreen.kt",
      "legacy_settings_formula_helper",
      "settings_include_training_trend_brake",
      "settings_include_late_phone",
    )
  }

  @Test
  fun general_balance_excludes_personal_fields_from_settings_preview() {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance")
    val fields = LifeLoadProfileCatalog.renderableFields(config)
    val labels = fields.map { it.label }.toSet()

    assertTrue(generalExcludedLabels.intersect(labels).isEmpty())
  }

  @Test
  fun public_build_defaults_to_generic_beta_review() {
    assertTrue(BuildConfig.LIFE_LOAD_PROFILE_SETUP_ENABLED)
    assertTrue(BuildConfig.LIFE_LOAD_PROFILE_ONBOARDING_ENABLED)
    assertTrue(BuildConfig.LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED)
    assertEquals("beta_review", BuildConfig.LIFE_LOAD_BUILD_MODE)
    assertEquals("general_balance", BuildConfig.LIFE_LOAD_DEFAULT_PROFILE_ID)
  }

  @Test
  fun default_settings_hides_beta_prototype_sections() {
    val source = repoFile("app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt").readText()

    assertTrue(source.contains("if (advanced)"))
    assertTrue(source.contains("CheckInPreferencesCard(state = state, actions = actions)"))
    assertTrue(source.contains("ConnectedDataCard(state = state, actions = actions)"))
    assertTrue(source.contains("Developer interface"))
  }

  @Test
  fun default_settings_keeps_reminder_backup_and_privacy() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "ReminderSettingsCard(state = state, actions = actions)",
      "BackupRestoreCard(state = state, actions = actions)",
      "PrivacyCard(state = state, actions = actions)",
    )
  }

  @Test
  fun beta_settings_guidance_explanation_replaces_modifier_cockpit() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "GuidanceExplanationCard()",
      "Advanced formula settings",
      "settings_guidance_beta_copy",
    )
  }

  @Test
  fun privacy_section_does_not_duplicate_backup_export_by_default() {
    val source = repoFile("app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt").readText()

    assertFalse(source.contains("privacy-export-button"))
    assertTrue(source.contains("backup-export-button"))
    assertTrue(source.contains("state.backupMessage"))
    assertTrue(source.contains("settings_delete_local_data"))
  }

  @Test
  fun backup_restore_contains_save_backup_file_copy() {
    val source = repoFile("app/mobile/android/app/src/main/res/values/strings.xml").readText()

    assertTrue(source.contains("Save backup file"))
    assertTrue(source.contains("Life Load stores your data on this phone. Save a backup file"))
    assertTrue(source.contains("Import reads a Life Load backup JSON file"))
    assertTrue(source.contains("Optional server backup"))
    assertTrue(source.contains("Life Load still works without internet or an account."))
    assertTrue(source.contains("Restore from server"))
  }

  @Test
  fun tracking_setup_entry_copy_is_profile_specific() {
    composeRule.setContent {
      TrackingSetupSettingsEntryCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        expanded = false,
        onOpen = {},
        onClose = {},
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Choose your profile and daily signals.").assertExists()
  }

  @Test
  fun profile_copy_has_no_forbidden_terms() {
    LifeLoadProfileCatalog.profiles.values.forEach { profile ->
      assertFalse(profileCopyHasForbiddenTerms("${profile.publicName} ${profile.description}"))
    }
  }

  @Test
  fun profile_descriptions_present_and_short() {
    LifeLoadProfileCatalog.profiles.values.forEach { profile ->
      assertTrue(profile.description.isNotBlank())
      assertTrue("${profile.id} description is too long", profile.description.length <= 140)
    }
  }

  @Test
  fun general_balance_description_mentions_everyday_balance() {
    val description = LifeLoadProfileCatalog.profiles.getValue("general_balance").description.lowercase()

    assertTrue(description.contains("everyday balance"))
    assertTrue(description.contains("energy"))
    assertTrue(description.contains("stress"))
  }

  @Test
  fun body_signal_description_avoids_fixed_foot_shoulder_assumption() {
    val description = LifeLoadProfileCatalog.profiles.getValue("body_signal_awareness").description.lowercase()

    assertTrue(description.contains("without fixed body-part assumptions"))
    assertFalse(description.contains("foot"))
    assertFalse(description.contains("shoulder"))
  }

  @Test
  fun pattern_awareness_copy_has_no_forbidden_terms() {
    val pack = LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack")

    assertFalse(profileCopyHasForbiddenTerms("${pack.name} ${pack.description}"))
  }

  @Test
  fun sensitive_signals_marked_private() {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance", optionalPackIds = setOf("pattern_awareness_pack"))
    val privateFields = LifeLoadProfileCatalog.renderableFields(config).filter { it.signalId in listOf("evening.phone_after_21", "work.project_overrun") }

    assertTrue(privateFields.isNotEmpty())
    assertTrue(privateFields.all { it.sensitive })
  }

  @Test
  fun no_medical_claims_in_onboarding_copy() {
    val copy = "Life Load helps choose the next sustainable step. Private wellness signal tracking. Not emergency support."

    assertFalse(profileCopyHasForbiddenTerms(copy))
    assertFalse(copy.lowercase().contains("medical"))
    assertFalse(copy.lowercase().contains("clinical"))
  }

  @Test
  fun selected_profile_config_exports_and_imports_with_additive_bundle() {
    val store = localStore("block7_export_import_bundle.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", diaryText = "fixed compatibility truth"))
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())
    val bundle = JSONObject(store.exportDebugBundle(redacted = false))

    assertEquals(LIFE_LOAD_DEBUG_BUNDLE_VERSION, bundle.getString("schema_version"))
    assertEquals("general_balance", bundle.getJSONObject("selected_profile_config").getString("active_profile_id"))
    assertEquals("fixed compatibility truth", bundle.getJSONArray("entries").getJSONObject(0).getJSONObject("entry_json").getString("diary_text"))
  }

  @Test
  fun profile_guidance_card_shows_beta_label_when_flagged() {
    composeRule.setContent {
      GatedBetaGuidanceCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        guidance = betaGuidance(),
        onSeeWhy = {},
      )
    }

    composeRule.onNodeWithTag("beta_guidance_card").assertExists()
    composeRule.onNodeWithText("Today’s suggestion").assertExists()
    composeRule.onNodeWithText("Simplify").assertExists()
    composeRule.onNodeWithText("Recent change: Stress rose this week.").assertExists()
  }

  @Test
  fun guidance_card_shows_missing_data_confidence() {
    composeRule.setContent {
      GatedBetaGuidanceCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        guidance = betaGuidance(missingSignalLabels = listOf("Sleep on time", "Energy")),
        onSeeWhy = {},
      )
    }

    composeRule.onNodeWithText("Limited confidence: Sleep on time, Energy missing.").assertExists()
  }

  @Test
  fun guidance_card_shows_one_primary_action() {
    composeRule.setContent {
      GatedBetaGuidanceCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        guidance = betaGuidance(primaryAction = "Make the day smaller before adding extra work."),
        onSeeWhy = {},
      )
    }

    composeRule.onAllNodesWithText("Primary action").assertCountEquals(1)
    composeRule.onNodeWithTag("beta_guidance_primary_action").assertExists()
    composeRule.onNodeWithText("Make the day smaller before adding extra work.").assertExists()
  }

  @Test
  fun guidance_card_does_not_show_raw_score_as_primary_output() {
    composeRule.setContent {
      GatedBetaGuidanceCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        guidance = betaGuidance(),
        onSeeWhy = {},
      )
    }

    composeRule.onNodeWithText("Life Load score").assertDoesNotExist()
    composeRule.onNodeWithText("87").assertDoesNotExist()
    composeRule.onNodeWithText("See why").assertExists()
  }

  @Test
  fun beta_guidance_card_has_headline_rationale_drivers_action_confidence() {
    composeRule.setContent {
      GatedBetaGuidanceCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        guidance = betaGuidance(missingSignalLabels = listOf("Sleep on time")),
        onSeeWhy = {},
      )
    }

    composeRule.onNodeWithText("Today’s suggestion").assertExists()
    composeRule.onNodeWithText("Simplify").assertExists()
    composeRule.onNodeWithText("Recent signals suggest today has limited margin.").assertExists()
    composeRule.onNodeWithText("Top drivers").assertExists()
    composeRule.onNodeWithTag("beta_guidance_primary_action").assertExists()
    composeRule.onNodeWithText("Limited confidence: Sleep on time missing.").assertExists()
    composeRule.onNodeWithText("See why").assertExists()
  }

  @Test
  fun beta_guidance_card_primary_action_visible_large_font() {
    composeRule.setContent {
      CompositionLocalProvider(LocalDensity provides Density(density = 1f, fontScale = 1.8f)) {
        GatedBetaGuidanceCard(
          flags = flags(profileDrivenCheckInEnabled = true),
          guidance = betaGuidance(),
          onSeeWhy = {},
        )
      }
    }

    composeRule.onNodeWithTag("beta_guidance_primary_action").assertExists()
  }

  @Test
  fun flag_off_keeps_current_guidance_surface() {
    composeRule.setContent {
      GatedBetaGuidanceCard(
        flags = flags(),
        guidance = betaGuidance(),
        onSeeWhy = {},
      )
    }

    composeRule.onNodeWithTag("beta_guidance_card").assertDoesNotExist()
  }

  @Test
  fun no_forbidden_sensitive_terms_in_beta_copy() {
    val betaCopy = buildList {
      LifeLoadProfileCatalog.profiles.values.forEach { profile ->
        add(profile.publicName)
        add(profile.description)
      }
      LifeLoadProfileCatalog.optionalPacks.values.forEach { pack ->
        add(pack.name)
        add(pack.description)
      }
      add("Private wellness signal tracking. Not emergency support.")
      add("Private pattern signals require explicit opt-in.")
      add(betaGuidance().rationale)
      add(betaGuidance().primaryAction)
      add(betaGuidance().confidenceNote)
    }.joinToString(" ")

    assertFalse(profileCopyHasForbiddenTerms(betaCopy))
  }

  @Test
  fun pattern_awareness_copy_is_private_opt_in_non_clinical() {
    val pack = LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack")
    val copy = "${pack.name} ${pack.description} Private pattern signals require explicit opt-in."

    assertTrue(pack.sensitive)
    assertTrue(pack.requiresExplicitOptIn)
    assertFalse(pack.defaultEnabled)
    assertFalse(profileCopyHasForbiddenTerms(copy))
  }

  @Test
  fun guidance_copy_uses_suggestion_not_instruction() {
    val guidance = betaGuidance(
      rationale = "Recent signals suggest today has limited margin.",
      primaryAction = "Make the day smaller before adding extra work.",
    )
    val copy = "${guidance.rationale} ${guidance.primaryAction} ${guidance.confidenceNote}"

    assertFalse(profileCopyUsesInstructionLanguage(copy))
    assertFalse(copy.lowercase().contains("must"))
    assertFalse(copy.lowercase().contains("failure"))
  }

  @Test
  fun safety_boundary_copy_visible_in_onboarding_or_settings() {
    composeRule.setContent {
      ProfileOnboardingForFlag(
        flags = flags(onboardingEnabled = true),
        hasExistingSelection = false,
        selectedProfileId = "general_balance",
        onProfileSelected = {},
        onStartFirstCheckIn = {},
      )
    }

    composeRule.onNodeWithText("Private wellness signal tracking. Not emergency support.").assertExists()
  }

  @Test
  fun export_includes_profile_signal_sections() {
    val store = localStore("block8_export_sections.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", diaryText = "fixed entry"))
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())
    store.saveSignalDefinition(JSONObject().put("id", "custom.block8_signal").put("label", "Private signal"))
    store.saveSignalEntry(JSONObject().put("date", "2026-05-17").put("signal_id", "custom.block8_signal").put("value", 0).put("is_present", true))

    val bundle = JSONObject(store.exportDebugBundle(redacted = false))

    assertEquals("general_balance", bundle.getJSONObject("selected_profile_config").getString("active_profile_id"))
    assertEquals("custom.block8_signal", bundle.getJSONArray("signal_definitions").getJSONObject(0).getString("id"))
    assertEquals(0, bundle.getJSONArray("signal_entries").getJSONObject(0).getInt("value"))
  }

  @Test
  fun delete_reset_clears_profile_signal_sections() {
    val store = localStore("block8_delete_reset.db")
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())
    store.saveSignalDefinition(JSONObject().put("id", "custom.block8_signal").put("label", "Private signal"))
    store.saveSignalEntry(JSONObject().put("date", "2026-05-17").put("signal_id", "custom.block8_signal").put("value", false).put("is_present", true))

    store.resetLocalData()

    assertEquals("personal_legacy", store.selectedProfileConfig().getString("active_profile_id"))
    assertEquals(0, store.signalDefinitions().size)
    assertEquals(0, store.signalEntries().size)
  }

  @Test
  fun privacy_copy_available_from_profile_setup_or_settings() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance", optionalPackIds = setOf("pattern_awareness_pack")),
          optionalPackIds = setOf("pattern_awareness_pack"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Private pattern awareness. Optional. Wellness-only.").assertExists()
  }

  @Test
  fun pattern_awareness_privacy_note_visible_when_enabled() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance", optionalPackIds = setOf("pattern_awareness_pack")),
          optionalPackIds = setOf("pattern_awareness_pack"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Private pattern awareness. Optional. Wellness-only.").assertExists()
    composeRule.onNodeWithTag("optional_pack_pattern_awareness_pack").assertExists()
  }

  @Test
  fun large_font_profile_onboarding_safe() {
    composeRule.setContent {
      CompositionLocalProvider(LocalDensity provides Density(density = 1f, fontScale = 1.8f)) {
        ProfileOnboardingForFlag(
          flags = flags(onboardingEnabled = true),
          hasExistingSelection = false,
          selectedProfileId = "general_balance",
          onProfileSelected = {},
          onStartFirstCheckIn = {},
        )
      }
    }

    composeRule.onNodeWithTag("profile_onboarding_start").assertExists()
  }

  @Test
  fun small_phone_profile_checkin_scrolls() {
    composeRule.setContent {
      Box(modifier = Modifier.size(width = 320.dp, height = 480.dp)) {
        GatedProfileDrivenCheckInCard(
          flags = flags(profileDrivenCheckInEnabled = true),
          config = LifeLoadProfileCatalog.buildSelectedProfileConfig("personal_legacy"),
          draftState = LifeLoadProfileDraftState(profileId = "personal_legacy"),
          onDraftChange = { _, _ -> },
        )
      }
    }

    composeRule.onNodeWithTag("profile_driven_check_in").assertExists()
    composeRule.onNodeWithText("Profile check-in").assertExists()
  }

  @Test
  fun tracking_setup_primary_actions_visible() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true, devCompatibilityMode = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("tracking_setup_reset_defaults").assertExists()
    composeRule.onNodeWithText("Active profile: General Balance").assertExists()
  }

  @Test
  fun general_balance_no_personal_fields_layout() {
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance"),
        onDraftChange = { _, _ -> },
      )
    }

    generalExcludedLabels.forEach { label ->
      composeRule.onNodeWithText(label).assertDoesNotExist()
    }
  }

  @Test
  fun pattern_awareness_hidden_by_default_layout() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Private: Phone after 21:00").assertDoesNotExist()
    composeRule.onNodeWithText("Phone after 21:00").assertDoesNotExist()
  }

  @Test
  fun max_active_signals_scroll_safe() {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig("personal_legacy")

    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = config,
        draftState = LifeLoadProfileDraftState(profileId = "personal_legacy"),
        onDraftChange = { _, _ -> },
      )
    }

    assertTrue(config.enabledSignalIds.size <= config.maxActiveSignals)
    composeRule.onNodeWithTag("profile_driven_check_in").assertExists()
  }

  @Test
  fun custom_profile_starts_with_core_signals() {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig("custom_stub")

    assertTrue("core.sleep_ok" in config.enabledSignalIds)
    assertTrue("mental.stress" in config.enabledSignalIds)
    assertTrue("energy.energy" in config.enabledSignalIds)
  }

  @Test
  fun custom_profile_limits_added_signals() {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig(
      "custom_stub",
      userAddedSignalIds = (1..8).map { "custom.extra_$it" }.toSet(),
    )

    assertTrue(config.enabledSignalIds.size <= 3)
  }

  @Test
  fun custom_signal_categories_are_simple_and_guided() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("custom_stub"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    listOf("Recovery", "Energy", "Stress / mental load", "Body signal", "Physical load", "Life load", "Private pattern", "Protective behavior")
      .forEach { assertTrue(composeRule.onAllNodesWithText(it).fetchSemanticsNodes().isNotEmpty()) }
    listOf("Track only", "Light", "Normal", "Strong", "Guardrail")
      .forEach { assertTrue(composeRule.onAllNodesWithText(it).fetchSemanticsNodes().isNotEmpty()) }
    composeRule.onNodeWithText("Raw weight").assertDoesNotExist()
  }

  @Test
  fun private_pattern_custom_signal_shows_safety_copy() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("custom_stub"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Custom signal labels stay private. Private pattern signals need calm safety wording and explicit opt-in.").assertExists()
  }

  @Test
  fun about_beta_status_not_empty() {
    composeRule.setContent {
      AboutBetaStatusCard(
        state = LifeLoadUiState(
          profileSetup = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
          ),
        ),
        flags = flags(profileSetupEnabled = true, onboardingEnabled = true, profileDrivenCheckInEnabled = true),
        defaultExpanded = true,
      )
    }

    composeRule.onNodeWithTag("settings-section-about-beta").assertExists()
    composeRule.onNodeWithText("About / beta status").assertExists()
    composeRule.onNodeWithText("Build mode: Beta review").assertExists()
    composeRule.onNodeWithText("Version ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})").assertExists()
  }

  @Test
  fun about_beta_status_shows_active_profile() {
    composeRule.setContent {
      AboutBetaStatusCard(
        state = LifeLoadUiState(
          profileSetup = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("work_stress"),
          ),
        ),
        flags = flags(profileSetupEnabled = true),
        defaultExpanded = true,
      )
    }

    composeRule.onNodeWithText("Active profile: Work Stress").assertExists()
  }

  @Test
  fun about_beta_status_shows_current_mode() {
    composeRule.setContent {
      AboutBetaStatusCard(
        state = LifeLoadUiState(
          profileSetup = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
          ),
        ),
        flags = flags(profileSetupEnabled = true, profileDrivenCheckInEnabled = true),
        defaultExpanded = true,
      )
    }

    composeRule.onNodeWithTag("beta_status_current_mode").assertExists()
    composeRule.onNodeWithText("Current mode: Gated profile beta").assertExists()
  }

  @Test
  fun about_beta_status_shows_flag_state() {
    composeRule.setContent {
      AboutBetaStatusCard(
        state = LifeLoadUiState(),
        flags = flags(profileSetupEnabled = true, onboardingEnabled = false, profileDrivenCheckInEnabled = true),
        defaultExpanded = true,
      )
    }

    composeRule.onNodeWithText("Profile setup: enabled").assertExists()
    composeRule.onNodeWithText("Onboarding: disabled").assertExists()
    composeRule.onNodeWithText("Profile check-in: enabled").assertDoesNotExist()
  }

  @Test
  fun about_beta_status_shows_local_first_copy() {
    composeRule.setContent {
      AboutBetaStatusCard(state = LifeLoadUiState(), flags = flags(), defaultExpanded = true)
    }

    composeRule.onNodeWithText("Data stored on this phone. Export and delete controls are available in Settings.", useUnmergedTree = true).assertExists()
  }

  @Test
  fun about_beta_status_has_non_medical_boundary() {
    composeRule.setContent {
      Box(Modifier.size(width = 480.dp, height = 1200.dp)) {
        AboutBetaStatusCard(state = LifeLoadUiState(), flags = flags(), defaultExpanded = true)
      }
    }

    composeRule.onNodeWithText("Wellness guidance only. Not medical advice or emergency support.", useUnmergedTree = true).assertExists()
  }

  @Test
  fun about_beta_status_grouped_sections_visible() {
    composeRule.setContent {
      AboutBetaStatusCard(
        state = LifeLoadUiState(
          profileSetup = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
          ),
        ),
        flags = flags(profileSetupEnabled = true, onboardingEnabled = true, profileDrivenCheckInEnabled = true),
        defaultExpanded = true,
      )
    }

    composeRule.onNodeWithTag("beta_status_section_build").assertExists()
    composeRule.onNodeWithTag("beta_status_section_current_setup").assertExists()
    composeRule.onNodeWithTag("beta_status_section_privacy").assertExists()
    composeRule.onNodeWithTag("beta_status_section_boundary").assertExists()
    composeRule.onNodeWithTag("beta_status_section_feedback").assertExists()
  }

  @Test
  fun large_font_about_beta_status_scrolls() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/androidTest/java/com/life/lifeload/ui/regression/ProfileDataStateSnapshotInstrumentedTest.kt",
      "G03_large_font_about_beta_status",
      ".verticalScroll(rememberScrollState())",
    )
  }

  @Test
  fun about_beta_status_boundary_visible() {
    composeRule.setContent {
      CompositionLocalProvider(LocalDensity provides Density(density = 1f, fontScale = 1.8f)) {
        Box(Modifier.size(width = 480.dp, height = 1400.dp)) {
          AboutBetaStatusCard(state = LifeLoadUiState(), flags = flags(), defaultExpanded = true)
        }
      }
    }

    composeRule.onNodeWithTag("beta_status_section_boundary").assertExists()
    composeRule.onNodeWithText("Wellness guidance only. Not medical advice or emergency support.", useUnmergedTree = true).assertExists()
  }

  @Test
  fun about_beta_status_groups_are_collapsible() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "var expanded by remember(tag)",
      ".clickable { expanded = !expanded }",
      ".testTag(\"${'$'}{tag}_header\")",
    )
  }

  @Test
  fun about_beta_status_feedback_mailto_visible() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "beta_status_section_feedback",
      "beta_status_send_feedback",
      "beta_status_feedback_mailto",
    )
  }

  @Test
  fun about_beta_status_feedback_mailto_uses_correct_address() {
    val source = repoFile("app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt").readText()
    assertTrue("Intent.ACTION_SENDTO" in source)
    assertTrue("mailto:" in source)
    assertTrue("beta_status_feedback_mailto" in source)
  }

  @Test
  fun reminder_save_settings_button_hidden_if_immediate_save() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "actions.onReminderSettingsChanged",
    )
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "settings_reminder_save",
    )
  }

  @Test
  fun reminder_toggle_persists_without_save_button() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadViewModel.kt",
      "fun updateReminderSettings",
      "repository.saveSettings(settings, \"\")",
      "LifeLoadReminderScheduler.apply",
    )
  }

  @Test
  fun reminder_enabled_state_prompts_for_missing_notification_permission() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "val needsNotificationPermission",
      "LaunchedEffect(reminder.enabled, needsNotificationPermission)",
      "if (reminder.enabled && needsNotificationPermission)",
      "notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)",
    )
  }

  @Test
  fun reminder_alarm_reschedules_after_firing() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/notifications/LifeLoadReminderReceiver.kt",
      "LifeLoadReminderScheduler.onReminderAlarm(context)",
    )
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/notifications/LifeLoadReminderScheduler.kt",
      "fun onReminderAlarm(context: Context)",
      "postReminder(appContext)",
      "rescheduleFromLocalSettings(appContext)",
    )
  }

  @Test
  fun reminder_scheduler_uses_idle_tolerant_one_shot_alarm() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/notifications/LifeLoadReminderScheduler.kt",
      "alarmManager.setAndAllowWhileIdle",
      "nextTriggerMillis(settings)",
      "reminderPendingIntent(context)",
    )
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/notifications/LifeLoadReminderScheduler.kt",
      "setInexactRepeating",
    )
  }

  @Test
  fun language_picker_uses_life_load_style() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassControls.kt",
      "FilterChipDefaults.filterChipColors",
      "selectedContainerColor = color.copy(alpha = 0.16f)",
      "containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f)",
    )
  }

  @Test
  fun scenario_preview_title_not_under_status_bar() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/androidTest/java/com/life/lifeload/ui/regression/ProfileDataStateSnapshotInstrumentedTest.kt",
      ".statusBarsPadding()",
      "scenario_preview_safe_area",
    )
  }

  @Test
  fun guidance_preview_respects_top_inset() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/androidTest/java/com/life/lifeload/ui/regression/ProfileDataStateSnapshotInstrumentedTest.kt",
      "ScenarioGuidanceReview",
      ".statusBarsPadding()",
    )
  }

  @Test
  fun large_font_preview_respects_top_inset() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/androidTest/java/com/life/lifeload/ui/regression/ProfileDataStateSnapshotInstrumentedTest.kt",
      "fontScale = 1.8f",
      ".statusBarsPadding()",
    )
  }

  @Test
  fun scenario_preview_does_not_show_fake_history_label() {
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/androidTest/java/com/life/lifeload/ui/regression/ProfileDataStateSnapshotInstrumentedTest.kt",
      "Fake history:",
      "Fake current day:",
      "Fake state:",
    )
  }

  @Test
  fun manifest_still_records_seeded_fake_data() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/androidTest/java/com/life/lifeload/ui/regression/ProfileDataStateSnapshotInstrumentedTest.kt",
      "SnapshotScenario",
    )
  }

  @Test
  fun guidance_card_uses_life_load_surface_tokens() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/profile/ProfileSetupUx.kt",
      "CardDefaults.elevatedCardColors",
      "containerColor = MaterialTheme.colorScheme.surface",
      "contentColor = MaterialTheme.colorScheme.onSurface",
    )
  }

  @Test
  fun tracking_setup_intro_uses_user_facing_copy() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Choose the profile and daily signals Life Load uses.").assertExists()
    composeRule.onNodeWithText("Changing profiles keeps your history.").assertExists()
  }

  @Test
  fun tracking_setup_intro_does_not_mention_current_scoring_stays_unchanged() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Choose a simple daily tracking shape. Current scoring stays unchanged.").assertDoesNotExist()
  }

  @Test
  fun tracking_setup_respects_top_insets() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("tracking_setup_top_inset_safe").assertExists()
    composeRule.onNodeWithText("Customize Profile").assertExists()
  }

  @Test
  fun tracking_setup_uses_compass_card_style() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("tracking_setup").assertExists()
    composeRule.onNodeWithTag("optional_pack_section_card").assertExists()
    composeRule.onNodeWithTag("active_signals_section").assertExists()
  }

  @Test
  fun tracking_setup_bottom_content_scrolls_above_gesture_bar() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("tracking_setup_bottom_safe_area").assertExists()
    composeRule.onNodeWithTag("tracking_setup_reset_defaults").assertExists()
  }

  @Test
  fun tracking_setup_large_font_primary_action_reachable() {
    composeRule.setContent {
      CompositionLocalProvider(LocalDensity provides Density(density = 1f, fontScale = 1.8f)) {
        TrackingSetupCard(
          flags = flags(profileSetupEnabled = true),
          state = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
          ),
          onProfileSelected = {},
          onOptionalPackToggled = { _, _ -> },
          onResetDefaults = {},
        )
      }
    }

    composeRule.onNodeWithTag("tracking_setup_reset_defaults").assertExists()
  }

  @Test
  fun profile_cards_fit_reasonable_count_on_screen() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    listOf("General Balance", "Work Stress", "Training Recovery", "Body Signal Awareness", "Custom")
      .forEach { composeRule.onNodeWithText(it).assertExists() }
  }

  @Test
  fun public_profile_list_excludes_personal_legacy() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true, devCompatibilityMode = false),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Personal Legacy").assertDoesNotExist()
  }

  @Test
  fun selected_profile_is_visually_marked() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("work_stress"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Selected").assertExists()
  }

  @Test
  fun profile_descriptions_do_not_overflow_large_font() {
    composeRule.setContent {
      CompositionLocalProvider(LocalDensity provides Density(density = 1f, fontScale = 1.8f)) {
        TrackingSetupCard(
          flags = flags(profileSetupEnabled = true),
          state = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
          ),
          onProfileSelected = {},
          onOptionalPackToggled = { _, _ -> },
          onResetDefaults = {},
        )
      }
    }

    listOf(
      "Everyday balance across energy, stress, recovery, body status, and load.",
      "Work pressure, recovery breaks, decompression, and energy.",
      "Training load, body load, recovery, sleep, and energy.",
      "Body signals, recovery, energy, and simple next steps.",
      "Start with core signals and add a small private set.",
    ).forEach { description ->
      composeRule.onNodeWithText(description).assertExists()
    }
  }

  @Test
  fun optional_packs_render_as_secondary_rows() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Life Load").assertExists()
    composeRule.onNodeWithText("Pattern Awareness").assertExists()
    composeRule.onNodeWithTag("optional_pack_toggle_life_load_pack").assertExists()
    composeRule.onNodeWithTag("optional_pack_toggle_pattern_awareness_pack").assertExists()
  }

  @Test
  fun pattern_awareness_off_by_default() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Pattern Awareness").assertExists()
    assertFalse("pattern_awareness_pack" in LifeLoadProfileCatalog.defaultSelectedProfileConfig().optionalPackIds)
  }

  @Test
  fun pattern_awareness_requires_explicit_opt_in() {
    composeRule.setContent {
      Box(modifier = Modifier.size(width = 800.dp, height = 2000.dp)) {
        TrackingSetupCard(
          flags = flags(profileSetupEnabled = true),
          state = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("work_stress"),
          ),
          onProfileSelected = {},
          onOptionalPackToggled = { _, _ -> },
          onResetDefaults = {},
        )
      }
    }

    composeRule.onNodeWithTag("optional_pack_pattern_awareness_pack").assertExists()
    composeRule.onNodeWithTag("optional_pack_toggle_pattern_awareness_pack").assertExists()
    assertTrue(LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack").requiresExplicitOptIn)
    assertFalse(LifeLoadProfileCatalog.optionalPacks.getValue("pattern_awareness_pack").defaultEnabled)
  }

  @Test
  fun pattern_awareness_copy_forbidden_terms_scan() {
    val rowCopy = "Pattern Awareness Private pattern awareness. Optional. Wellness-only."

    assertFalse(profileCopyHasForbiddenTerms(rowCopy))
  }

  @Test
  fun boolean_control_does_not_show_raw_test_buttons() {
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance"),
        onDraftChange = { _, _ -> },
      )
    }

    composeRule.onNodeWithText("Draft present: true").assertDoesNotExist()
    composeRule.onNodeWithText("Set").assertDoesNotExist()
    composeRule.onNodeWithText("Clear").assertDoesNotExist()
    assertTrue(composeRule.onAllNodesWithText("Not sure").fetchSemanticsNodes().isNotEmpty())
  }

  @Test
  fun ordinal_control_preserves_zero() {
    var draftChange: Pair<String, Any?>? = null
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance"),
        onDraftChange = { id, value -> draftChange = id to value },
      )
    }

    composeRule.onNodeWithTag("profile_field_mental.stress").assertExists()
    composeRule.onAllNodesWithText("0").onFirst().performClick()

    assertEquals("mental.stress" to 0, draftChange)
  }

  @Test
  fun absent_false_zero_distinctions_preserved() {
    val state = LifeLoadProfileDraftState(profileId = "test")
      .update("boolean.false", false)
      .update("number.zero", 0)

    assertTrue(state.valuesBySignalId.getValue("boolean.false").isPresent)
    assertEquals(false, state.valuesBySignalId.getValue("boolean.false").value)
    assertTrue(state.valuesBySignalId.getValue("number.zero").isPresent)
    assertEquals(0, state.valuesBySignalId.getValue("number.zero").value)
    assertFalse("absent" in state.valuesBySignalId)
  }

  @Test
  fun draft_present_debug_text_not_visible() {
    composeRule.setContent {
      GatedProfileDrivenCheckInCard(
        flags = flags(profileDrivenCheckInEnabled = true),
        config = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        draftState = LifeLoadProfileDraftState(profileId = "general_balance").update("core.sleep_ok", true),
        onDraftChange = { _, _ -> },
      )
    }

    composeRule.onNodeWithText("Draft present: true").assertDoesNotExist()
  }

  @Test
  fun language_selector_visible_in_settings() {
    composeRule.setContent {
      LanguageSettingsCard()
    }

    composeRule.onNodeWithTag("settings-section-language").assertExists()
    composeRule.onNodeWithText("Language").performClick()
    composeRule.onNodeWithTag("settings-language_system").assertExists()
    composeRule.onNodeWithTag("settings-language_en").assertExists()
    composeRule.onNodeWithTag("settings-language_de").assertExists()
  }

  @Test
  fun default_language_is_system_default() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    assertEquals(LifeLoadLanguageOption.SYSTEM, LifeLoadLanguageStore.load(context))
  }

  @Test
  fun selecting_german_changes_settings_text() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val german = LifeLoadLanguageStore.localizedContext(context, LifeLoadLanguageOption.GERMAN)

    assertEquals("Sprache", german.getString(R.string.settings_language_title))
    assertEquals("Profil anpassen", german.getString(R.string.tracking_setup_title))
    assertEquals("Alltagsbalance", german.getString(R.string.profile_name_general_balance))
  }

  @Test
  fun selecting_english_changes_settings_text() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val english = LifeLoadLanguageStore.localizedContext(context, LifeLoadLanguageOption.ENGLISH)

    assertEquals("Language", english.getString(R.string.settings_language_title))
    assertEquals("Customize Profile", english.getString(R.string.tracking_setup_title))
    assertEquals("General Balance", english.getString(R.string.profile_name_general_balance))
  }

  @Test
  fun language_choice_persists_after_restart() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.GERMAN)

    assertEquals(LifeLoadLanguageOption.GERMAN, LifeLoadLanguageStore.load(context))
  }

  @Test
  fun language_change_does_not_reset_selected_profile() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val store = localStore("language_keeps_profile.db")
    store.saveSelectedProfileConfig(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance").toJson())

    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.GERMAN)

    assertEquals("general_balance", store.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun language_change_does_not_change_scoring_or_entries() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val store = localStore("language_keeps_entries.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-18", energy = 4, stress = 7, sleepOk = false))

    LifeLoadLanguageStore.save(context, LifeLoadLanguageOption.GERMAN)

    val entry = store.getEntry("2026-05-18")?.entry
    assertEquals(4, entry?.energy)
    assertEquals(7, entry?.stress)
    assertEquals(false, entry?.sleepOk)
  }

  @Test
  fun german_strings_file_contains_required_beta_keys() {
    val source = repoFile("app/mobile/android/app/src/main/res/values-de/strings.xml").readText()
    val requiredKeys = listOf(
      "nav_guidance",
      "nav_check_in",
      "nav_settings",
      "check_in_header_with_status",
      "check_in_status_open",
      "settings_language_title",
      "tracking_setup_title",
      "profile_name_general_balance",
      "profile_name_work_stress",
      "profile_name_training_recovery",
      "profile_name_body_signal_awareness",
      "profile_name_custom",
      "pattern_awareness_name",
      "guidance_label_push",
      "guidance_label_maintain",
      "guidance_label_recover",
      "guidance_label_simplify",
      "guidance_label_protect_sleep",
      "beta_status_title",
      "beta_status_current_mode",
      "beta_status_mode_personal_legacy",
      "beta_status_mode_gated_beta",
      "beta_status_send_feedback",
      "beta_status_feedback_mailto",
      "settings_reminder_updated",
      "settings_backup_restore",
      "settings_privacy",
    )

    assertEquals(emptyList<String>(), requiredKeys.filterNot { "name=\"$it\"" in source })
  }

  @Test
  fun german_beta_copy_avoids_forbidden_sensitive_terms() {
    val source = repoFile("app/mobile/android/app/src/main/res/values-de/strings.xml").readText().lowercase()
    val forbidden = listOf("sucht", "bulimie", "essstörung", "rückfall", "diagnose", "störung")

    assertEquals(emptyList<String>(), forbidden.filter { it in source })
    assertTrue("keine behandlung" in source)
  }

  @Test
  fun german_settings_has_no_english_beta_surface_strings() {
    val source = repoFile("app/mobile/android/app/src/main/res/values-de/strings.xml").readText()
    val unexpected = listOf(
      "Guidance",
      "Tracking setup",
      "Customize Profile",
      "Tracking einrichten",
      "Backup &amp; restore",
      "See why",
      "Profile-Check-in",
      "Check-in is still open",
      "Current setup",
      "Onboarding:",
      "Beta status:",
      "Save settings",
      "Personal Legacy",
      "General Balance",
      "Pattern Awareness",
      ">Open<",
      ">English<",
    )

    assertEquals(emptyList<String>(), unexpected.filter { it in source })
  }

  @Test
  fun german_runtime_navigation_and_status_are_localized() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val german = LifeLoadLanguageStore.localizedContext(context, LifeLoadLanguageOption.GERMAN)

    assertEquals("Empfehlung", german.getString(R.string.nav_guidance))
    assertEquals("Eintrag", german.getString(R.string.nav_check_in))
    assertEquals("Täglicher Eintrag · Offen", german.getString(R.string.check_in_header_with_status, german.getString(R.string.check_in_status_open)))
    assertEquals("Kompatibilitätsprofil", german.getString(R.string.beta_status_mode_personal_legacy))
    assertEquals("Profilbasierter Eintrag", german.getString(R.string.profile_driven_checkin_title))
    assertEquals("Warum?", german.getString(R.string.guidance_beta_see_why))
  }

  @Test
  fun german_mode_no_english_guidance_tracking_open_or_see_why_labels() {
    val source = repoFile("app/mobile/android/app/src/main/res/values-de/strings.xml").readText()
    val forbidden = listOf(
      ">Guidance<",
      ">Tracking setup<",
      ">Customize Profile<",
      ">Open<",
      ">See why<",
      "Profile-Check-in",
      "Check-in is still open",
      "Personal Legacy",
      "Pattern Awareness",
    )

    assertEquals(emptyList<String>(), forbidden.filter { it in source })
  }

  @Test
  fun no_hardcoded_user_facing_beta_strings_in_kotlin() {
    listOf(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/profile/ProfileSetupUx.kt",
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassControls.kt",
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt",
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassWeek.kt",
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassPlusRoot.kt",
    ).forEach { path ->
      assertProductionSourceDoesNotReference(
        path,
        "\"Guidance\"",
        "\"Tracking setup\"",
        "\"Customize Profile\"",
        "\"Open\"",
        "\"See why\"",
        "\"Check-in is still open\"",
        "\"Profile-Check-in\"",
        "\"Beta status\"",
        "\"Current setup\"",
        "\"Privacy\"",
        "\"Boundary\"",
        "\"Feedback\"",
        "\"Save settings\"",
        "\"Pattern Awareness\"",
      )
    }
  }

  @Test
  fun german_beta_ui_copy_uses_string_resources() {
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java",
      "Sprache",
      "Profil anpassen",
      "Alltagsbalance",
      "Arbeitsstress",
      "Trainingserholung",
      "Körpersignale",
      "Private Muster",
      "Aktiv angehen",
      "Stabil bleiben",
      "Schlaf schützen",
    )
  }

  @Test
  fun onboarding_enabled_for_fresh_public_demo() {
    assertTrue(BuildConfig.LIFE_LOAD_PROFILE_ONBOARDING_ENABLED)
    assertTrue(BuildConfig.LIFE_LOAD_PROFILE_SETUP_ENABLED)
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadScreen.kt",
      "onboardingVisibleForNewUser(profileFeatureFlags, state.profileOnboardingCompleted)",
    )
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassPlusRoot.kt",
      "onboardingVisibleForNewUser(profileFeatureFlags, state.profileOnboardingCompleted)",
    )
  }

  @Test
  fun onboarding_shown_when_flag_on_and_not_completed() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadScreen.kt",
      "ProfileOnboardingForFlag(",
      "onCompleteProfileOnboarding()",
    )
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassPlusRoot.kt",
      "ProfileOnboardingForFlag(",
      "actions.onCompleteProfileOnboarding()",
      "surface = CompassPlusSurface.CheckIn",
    )
  }

  @Test
  fun onboarding_completion_persists() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadViewModel.kt",
      "PREFS_PROFILE_ONBOARDING",
      "KEY_PROFILE_ONBOARDING_COMPLETED",
      "putBoolean(KEY_PROFILE_ONBOARDING_COMPLETED, true)",
      "profileOnboardingCompleted = false",
    )
  }

  @Test
  fun runtime_guidance_card_not_embedded_on_daily_checkin_pages() {
    assertProductionSourceLacks(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/LifeLoadScreen.kt",
      "profileDrivenCheckInActive(profileFeatureFlags)",
      "GatedBetaGuidanceCard(",
      "betaGuidanceWhyOpen = true",
    )
    assertProductionSourceLacks(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt",
      "profileDrivenCheckInActive(flags)",
      "GatedBetaGuidanceCard(",
      "betaGuidanceWhyOpen = true",
    )
  }

  @Test
  fun runtime_guidance_bridge_does_not_change_scoring() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/profile/ProfileSetupUx.kt",
      "runtimeBetaGuidanceFromProductionBridge",
      "LifeLoadProfileCatalog.productionGuidanceModel",
    )
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/domain",
      "runtimeBetaGuidanceFromDraft",
    )
  }

  @Test
  fun new_profile_beta_ui_copy_uses_string_resources() {
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/profile/ProfileSetupUx.kt",
      "Choose a simple daily tracking shape. Current scoring stays unchanged.",
      "Choose what Life Load tracks each day.",
      "Changing profiles keeps your history.",
      "These signals stay local unless you export them.",
      "Private pattern awareness. Optional. Wellness-only.",
      "Today’s suggestion",
      "Top drivers",
      "Primary action",
      "See why",
      "Draft present:",
      "Custom signal labels stay private.",
    )
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "About / beta status",
      "Beta status: gated review build",
      "Wellness guidance only. Not medical advice or emergency support.",
      "Current mode:",
      "Gated profile beta",
      "Send feedback",
      "Report confusing guidance",
      "maintainer@example.invalid",
    )
  }

  @Test
  fun active_signals_do_not_show_redundant_private_prefixes() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithText("Private: Stress").assertDoesNotExist()
    composeRule.onNodeWithText("Private: Mood").assertDoesNotExist()
    composeRule.onNodeWithText("Stress").assertExists()
    composeRule.onNodeWithText("Mood").assertExists()
  }

  @Test
  fun active_signals_include_privacy_note() {
    composeRule.setContent {
      TrackingSetupCard(
        flags = flags(profileSetupEnabled = true),
        state = com.life.lifeload.domain.LifeLoadProfileSetupState(
          selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
        ),
        onProfileSelected = {},
        onOptionalPackToggled = { _, _ -> },
        onResetDefaults = {},
      )
    }

    composeRule.onNodeWithTag("active_signals_privacy_note").assertExists()
    composeRule.onNodeWithText("These signals stay local unless you export them.").assertExists()
  }

  @Test
  fun active_signal_chips_wrap_large_font() {
    composeRule.setContent {
      CompositionLocalProvider(LocalDensity provides Density(density = 1f, fontScale = 1.8f)) {
        TrackingSetupCard(
          flags = flags(profileSetupEnabled = true),
          state = com.life.lifeload.domain.LifeLoadProfileSetupState(
            selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
          ),
          onProfileSelected = {},
          onOptionalPackToggled = { _, _ -> },
          onResetDefaults = {},
        )
      }
    }

    composeRule.onNodeWithTag("active_signals_section").assertExists()
  }

  @Test
  fun general_balance_active_signals_exclude_personal_fields() {
    val fields = LifeLoadProfileCatalog.renderableFields(LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"))
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue(generalExcludedFields.intersect(legacyKeys).isEmpty())
  }

  @Test
  fun profile_beta_actions_use_life_load_action_colors() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/profile/ProfileSetupUx.kt",
      "profilePrimaryButtonColors",
      "profileNeutralOutlinedButtonColors",
      "profileWarningChipColors",
      "profileInputChipColors",
      "optionalPackSwitchColors",
      "MaterialTheme.colorScheme.primary",
      "MaterialTheme.colorScheme.tertiary",
    )
  }

  @Test
  fun backup_privacy_actions_use_compass_action_colors() {
    assertProductionSourceContains(
      "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassSettings.kt",
      "backupExportButtonColors",
      "neutralSettingsOutlinedButtonColors",
      "privacyDeleteButtonColors",
      "privacyDeleteOutlinedButtonColors",
      "compassGreen()",
      "MaterialTheme.colorScheme.error.copy(alpha = 0.90f)",
    )
  }

  @Test
  fun production_bridge_preserves_false_zero_absent_distinctions() {
    val snapshot = LifeLoadProfileCatalog.buildProductionGuidanceBridge(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("personal_legacy"),
      LifeLoadProfileDraftState("personal_legacy")
        .update("evening.phone_after_21", false)
        .update("work.project_overrun", false)
        .update("body.foot_pain", 0)
        .update("body.shoulder_pain", 0),
    )

    assertFalse("core.sleep_ok" in snapshot.presentSignalValues)
    assertEquals(false, snapshot.presentSignalValues["evening.phone_after_21"])
    assertEquals(0, snapshot.presentSignalValues["body.foot_pain"])
    assertFalse("evening_boundary_broken" in snapshot.inputs)
    assertFalse("body_signal_high" in snapshot.inputs)
  }

  @Test
  fun production_bridge_general_balance_excludes_personal_legacy_fields() {
    val snapshot = LifeLoadProfileCatalog.buildProductionGuidanceBridge(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
      LifeLoadProfileDraftState("general_balance")
        .update("core.sleep_ok", true)
        .update("core.nutrition_ok", true)
        .update("mental.stress", 2)
        .update("energy.energy", 7)
        .update("nutrition.alcohol", true)
        .update("nutrition.binge", true)
        .update("body.foot_pain", 10)
        .update("body.shoulder_pain", 10)
        .update("relationship.wife_conflict_count", 2)
        .update("caregiving.homework_done", false)
        .update("training.primary_activity_type", "crossfit"),
    )

    val forbidden = setOf(
      "nutrition.alcohol",
      "nutrition.binge",
      "body.foot_pain",
      "body.shoulder_pain",
      "relationship.wife_conflict_count",
      "caregiving.homework_done",
      "training.primary_activity_type",
    )
    assertTrue(forbidden.intersect(snapshot.presentSignalValues.keys).isEmpty())
    assertFalse("body_signal_high" in snapshot.inputs)
    assertFalse("private_pattern_active" in snapshot.inputs)
    assertFalse("physical_load_high" in snapshot.inputs)
  }

  @Test
  fun production_bridge_pattern_awareness_disabled_and_enabled_behave_differently() {
    val disabled = LifeLoadProfileCatalog.buildProductionGuidanceBridge(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
      LifeLoadProfileDraftState("general_balance")
        .update("evening.phone_after_21", true)
        .update("work.project_overrun", true),
    )
    val enabled = LifeLoadProfileCatalog.buildProductionGuidanceBridge(
      LifeLoadProfileCatalog.buildSelectedProfileConfig(
        "general_balance",
        optionalPackIds = setOf("pattern_awareness_pack"),
      ),
      LifeLoadProfileDraftState("general_balance")
        .update("evening.phone_after_21", true)
        .update("work.project_overrun", true),
    )

    assertFalse("private_pattern_active" in disabled.inputs)
    assertFalse("evening.phone_after_21" in disabled.presentSignalValues)
    assertTrue("private_pattern_active" in enabled.inputs)
    assertTrue("evening.phone_after_21" in enabled.presentSignalValues)
  }

  @Test
  fun production_guidance_model_uses_bridge_inputs_for_general_balance() {
    val guidance = LifeLoadProfileCatalog.productionGuidanceModel(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
      LifeLoadProfileDraftState("general_balance")
        .update("core.sleep_ok", true)
        .update("core.nutrition_ok", true)
        .update("mental.stress", 8)
        .update("energy.energy", 2),
    )

    assertEquals(LifeLoadBetaGuidanceLabel.SIMPLIFY, guidance.label)
    assertTrue("mental_load_high" in guidance.bridgeInputKeys)
    assertTrue("energy_low" in guidance.bridgeInputKeys)
    assertTrue("stress" in guidance.driverKeys)
    assertTrue("energy" in guidance.driverKeys)
  }

  @Test
  fun production_guidance_empty_day_uses_experiment_one_no_data_behavior() {
    val guidance = LifeLoadProfileCatalog.productionGuidanceModel(
      LifeLoadProfileCatalog.buildSelectedProfileConfig("general_balance"),
      LifeLoadProfileDraftState("general_balance"),
    )

    assertEquals(LifeLoadBetaGuidanceLabel.MAINTAIN, guidance.label)
    assertEquals("limited", guidance.confidence)
    assertEquals("check_in_first", guidance.actionKey)
    assertEquals(listOf("missing_data"), guidance.driverKeys)
  }

  private fun flags(
    profileSetupEnabled: Boolean = false,
    onboardingEnabled: Boolean = false,
    profileDrivenCheckInEnabled: Boolean = false,
    devCompatibilityMode: Boolean = false,
  ): LifeLoadProfileFeatureFlags =
    LifeLoadProfileFeatureFlags(
      profileSetupEnabled = profileSetupEnabled,
      onboardingEnabled = onboardingEnabled,
      profileDrivenCheckInEnabled = profileDrivenCheckInEnabled,
      devCompatibilityMode = devCompatibilityMode,
    )

  private fun localStore(name: String, defaultProfileId: String = "personal_legacy"): LifeLoadLocalStore {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    context.deleteDatabase(name)
    return LifeLoadLocalStore(context, name, defaultProfileId = defaultProfileId).also { stores += it }
  }

  private fun betaGuidance(
    rationale: String = "Recent signals suggest today has limited margin.",
    primaryAction: String = "Make the day smaller before adding extra work.",
    missingSignalLabels: List<String> = emptyList(),
  ): LifeLoadBetaGuidanceCardState =
    LifeLoadBetaGuidanceCardState(
      label = LifeLoadBetaGuidanceLabel.SIMPLIFY,
      rationale = rationale,
      topDrivers = listOf("Stress", "Sleep on time"),
      recentChange = "Stress rose this week.",
      primaryAction = primaryAction,
      confidenceNote = if (missingSignalLabels.isEmpty()) "Normal confidence." else "Limited confidence because data is missing.",
      missingSignalLabels = missingSignalLabels,
      whyDetails = listOf("Recent signals suggest reducing optional load."),
    )

  private fun assertProductionSourceDoesNotReference(relativePath: String, vararg forbiddenReferences: String) {
    val target = repoFile(relativePath)
    val matches = if (target.isDirectory) {
      target.walkTopDown()
        .filter { it.isFile && it.extension == "kt" }
        .flatMap { file ->
          val text = file.readText(Charsets.UTF_8)
          forbiddenReferences
            .filter { it in text }
            .map { "${file.relativeTo(repoFile(""))}:$it" }
        }
        .toList()
    } else {
      val text = target.readText(Charsets.UTF_8)
      forbiddenReferences.filter { it in text }
    }

    assertEquals(emptyList<String>(), matches)
  }

  private fun assertProductionSourceContains(relativePath: String, vararg requiredReferences: String) {
    val text = repoFile(relativePath).readText(Charsets.UTF_8)
    val missing = requiredReferences.filterNot { it in text }

    assertEquals(emptyList<String>(), missing)
  }

  private fun assertProductionSourceLacks(relativePath: String, vararg forbiddenReferences: String) {
    val text = repoFile(relativePath).readText(Charsets.UTF_8)
    val present = forbiddenReferences.filter { it in text }

    assertEquals(emptyList<String>(), present)
  }

  private fun repoFile(relativePath: String): File {
    val userDir = System.getProperty("user.dir") ?: "."
    var current: File? = File(userDir).canonicalFile
    while (current != null) {
      if (File(current, "app/mobile/android").isDirectory && File(current, "app/backend/life_load").isDirectory) {
        return File(current, relativePath)
      }
      current = current.parentFile
    }
    throw AssertionError("Could not find repo root from $userDir")
  }

  companion object {
    private val generalExcludedFields = setOf(
      "foot_pain",
      "shoulder_pain",
      "wife_conflict_count",
      "wife_conflict_school",
      "wife_conflict_chores",
      "wife_conflict_other",
      "homework_done",
      "homework_status",
      "alcohol",
      "binge",
      "primary_activity_type",
    )
    private val personalLegacyFields = generalExcludedFields + setOf(
      "migraine_warning",
      "phone_after_21",
      "project_overrun",
      "alone_home",
    )
    private val generalExcludedLabels = setOf(
      "Foot pain",
      "Shoulder pain",
      "Relationship conflict count",
      "Homework done",
      "Alcohol",
      "Eating episode",
      "Primary activity type",
    )
  }
}
