@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package com.life.lifeload.ui.compass

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AccessTime
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FileUpload
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.life.lifeload.BuildConfig
import com.life.lifeload.R
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.domain.LifeLoadProfileFeatureFlags
import com.life.lifeload.domain.LifeLoadFormulaSettings
import com.life.lifeload.domain.LifeLoadReminderSettings
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.trackingSetupVisible
import com.life.lifeload.i18n.LifeLoadLanguageOption
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.i18n.findActivity
import com.life.lifeload.ui.LifeLoadUiActions
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.LifeLoadUiVariant
import com.life.lifeload.ui.profile.TrackingSetupCard
import com.life.lifeload.ui.profile.defaultProfileFeatureFlags
import com.life.lifeload.ui.profile.profileDisplayNameForId

fun LazyListScope.compassSettingsItems(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  mode: CompassMode,
  setMode: (CompassMode) -> Unit,
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  val advanced = advancedSettingsVisible(mode)
  val profileFeatureFlags = defaultProfileFeatureFlags()
  if (advanced) {
    item {
      CollapsibleSettingsCard("Developer interface", key = "interface", tag = "debug_ui_variant_card", debug = true) {
        Text("Developer / advanced", color = MaterialTheme.colorScheme.onSurfaceVariant)
        CompassModeSelector(selected = mode, onSelect = setMode)
        CompassVariantSelector(selectedVariant = selectedVariant, onVariantSelected = onVariantSelected)
        Text(selectedVariant.description, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
  }
  if (trackingSetupVisible(profileFeatureFlags)) {
    item {
      CollapsibleSettingsCard(stringResource(R.string.tracking_setup_title), key = "tracking_setup", tag = "settings_tracking_setup_entry") {
        Text(stringResource(R.string.tracking_setup_settings_summary), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
          stringResource(
            R.string.tracking_setup_active_profile,
            profileDisplayNameForId(state.profileSetup.selectedConfig.activeProfileId),
          ),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        TrackingSetupCard(
          flags = profileFeatureFlags,
          state = state.profileSetup,
          onProfileSelected = actions.onProfileSelected,
          onOptionalPackToggled = actions.onOptionalPackToggled,
          onResetDefaults = actions.onResetProfileDefaults,
        )
      }
    }
  }
  if (advanced) {
    item {
      CheckInPreferencesCard(state = state, actions = actions)
    }
  }
  item {
    ReminderSettingsCard(state = state, actions = actions)
  }
  item {
    LanguageSettingsCard()
  }
  item {
    if (advanced) {
      GuidanceFormulaCard(state = state, actions = actions, mode = mode)
    } else {
      GuidanceExplanationCard()
    }
  }
  if (advanced) {
    item {
      ConnectedDataCard(state = state, actions = actions)
    }
  }
  item {
    BackupRestoreCard(state = state, actions = actions)
  }
  item {
    PrivacyCard(state = state, actions = actions)
  }
  item {
    AboutBetaStatusCard(state = state, flags = profileFeatureFlags)
  }
  if (advanced) {
    item {
      DeveloperDiagnosticsCard(state = state, actions = actions)
    }
  }
}

@Composable
fun AboutBetaStatusCard(
  state: LifeLoadUiState,
  flags: LifeLoadProfileFeatureFlags,
  defaultExpanded: Boolean = false,
) {
  val enabled = stringResource(R.string.beta_status_enabled)
  val disabled = stringResource(R.string.beta_status_disabled)
  val context = LocalContext.current
  val activeProfileId = state.profileSetup.selectedConfig.activeProfileId
  val betaReviewBuild = BuildConfig.LIFE_LOAD_BUILD_MODE == "beta_review"
  val buildModeLabel = if (betaReviewBuild) {
    stringResource(R.string.beta_status_build_mode_beta_review)
  } else {
    stringResource(R.string.beta_status_build_mode_personal_legacy)
  }
  val currentMode = if (
    flags.profileSetupEnabled &&
    flags.profileDrivenCheckInEnabled &&
    activeProfileId != "personal_legacy"
  ) {
    stringResource(R.string.beta_status_mode_gated_beta)
  } else {
    stringResource(R.string.beta_status_mode_personal_legacy)
  }
  CollapsibleSettingsCard(
    stringResource(R.string.beta_status_title),
    key = "about_beta",
    tag = "settings-section-about-beta",
    accent = compassGreen(),
    defaultExpanded = defaultExpanded,
  ) {
    BetaStatusSection(title = stringResource(R.string.beta_status_section_build), tag = "beta_status_section_build", defaultExpanded = true) {
      Text(stringResource(R.string.beta_status_version, BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE), color = MaterialTheme.colorScheme.onSurfaceVariant)
      Text(stringResource(R.string.beta_status_build_mode, buildModeLabel), color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("beta_status_build_mode"))
    }
    BetaStatusSection(title = stringResource(R.string.beta_status_section_current_setup), tag = "beta_status_section_current_setup", defaultExpanded = true) {
      Text(stringResource(R.string.beta_status_current_mode, currentMode), color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("beta_status_current_mode"))
      Text(stringResource(R.string.beta_status_active_profile, profileDisplayNameForId(activeProfileId)), color = MaterialTheme.colorScheme.onSurfaceVariant)
      FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        StatusPill(
          stringResource(R.string.beta_status_profile_setup, if (flags.profileSetupEnabled) enabled else disabled),
          if (flags.profileSetupEnabled) compassGreen() else MaterialTheme.colorScheme.outline,
          type = StatusPillType.Neutral,
        )
        StatusPill(
          stringResource(R.string.beta_status_onboarding, if (flags.onboardingEnabled) enabled else disabled),
          if (flags.onboardingEnabled) compassGreen() else MaterialTheme.colorScheme.outline,
          type = StatusPillType.Neutral,
        )
      }
      if (betaReviewBuild) {
        Text(stringResource(R.string.beta_status_pattern_awareness_default_off), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.beta_status_draft_bridge_limitation), color = MaterialTheme.colorScheme.onSurfaceVariant)
      } else {
        Text(stringResource(R.string.beta_status_personal_legacy_explanation), color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
    BetaStatusSection(title = stringResource(R.string.beta_status_section_privacy), tag = "beta_status_section_privacy", defaultExpanded = true) {
      Text(stringResource(R.string.beta_status_local_first), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    BetaStatusSection(title = stringResource(R.string.beta_status_section_boundary), tag = "beta_status_section_boundary", defaultExpanded = true) {
      Text(stringResource(R.string.beta_status_wellness_boundary), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    BetaStatusSection(title = stringResource(R.string.beta_status_section_feedback), tag = "beta_status_section_feedback") {
      Text(stringResource(R.string.beta_status_feedback), color = MaterialTheme.colorScheme.onSurfaceVariant)
      Button(
        onClick = { openFeedbackEmail(context) },
        colors = ButtonDefaults.buttonColors(containerColor = compassGreen()),
        modifier = Modifier.testTag("beta_status_feedback_mailto"),
      ) {
        Text(stringResource(R.string.beta_status_send_feedback))
      }
      Text(stringResource(R.string.beta_status_feedback_mailto), color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("beta_status_feedback_email"))
    }
  }
}

@Composable
private fun BetaStatusSection(
  title: String,
  tag: String,
  defaultExpanded: Boolean = false,
  content: @Composable () -> Unit,
) {
  var expanded by remember(tag) { mutableStateOf(defaultExpanded) }
  val shape = RoundedCornerShape(14.dp)
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag)
      .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.26f), shape)
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.16f), shape)
      .padding(12.dp),
    verticalArrangement = Arrangement.spacedBy(8.dp),
  ) {
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .clickable { expanded = !expanded }
        .testTag("${tag}_header"),
      horizontalArrangement = Arrangement.SpaceBetween,
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      Icon(
        if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
        contentDescription = if (expanded) stringResource(R.string.settings_collapse_section) else stringResource(R.string.settings_expand_section),
      )
    }
    if (expanded) content()
  }
}

private fun openFeedbackEmail(context: Context) {
  val address = context.getString(R.string.beta_status_feedback_mailto)
  val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:$address"))
    .putExtra(Intent.EXTRA_EMAIL, arrayOf(address))
    .putExtra(Intent.EXTRA_SUBJECT, context.getString(R.string.beta_status_feedback_subject))
  runCatching { context.startActivity(intent) }
}

private fun advancedSettingsVisible(mode: CompassMode): Boolean = mode.showsOperatorData()

@Composable
fun LanguageSettingsCard() {
  val context = LocalContext.current
  var selected by rememberSaveable { mutableStateOf(LifeLoadLanguageStore.load(context).storageKey) }
  CollapsibleSettingsCard(stringResource(R.string.settings_language_title), key = "language", tag = "settings-section-language", accent = compassGreen()) {
    SegmentedField(
      label = stringResource(R.string.settings_language_current),
      selected = selected,
      options = listOf(
        LifeLoadLanguageOption.SYSTEM.storageKey to stringResource(R.string.settings_language_system_default),
        LifeLoadLanguageOption.ENGLISH.storageKey to stringResource(R.string.settings_language_english),
        LifeLoadLanguageOption.GERMAN.storageKey to stringResource(R.string.settings_language_german),
      ),
      tagPrefix = "settings-language",
      positiveValues = setOf(LifeLoadLanguageOption.GERMAN.storageKey, LifeLoadLanguageOption.ENGLISH.storageKey),
    ) { value ->
      val option = LifeLoadLanguageOption.entries.firstOrNull { it.storageKey == value } ?: LifeLoadLanguageOption.SYSTEM
      selected = option.storageKey
      LifeLoadLanguageStore.save(context, option)
      context.findActivity()?.recreate()
    }
    Text(stringResource(R.string.settings_language_helper), color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun CollapsibleSettingsCard(
  title: String,
  key: String,
  tag: String,
  accent: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.outline.copy(alpha = 0.28f),
  debug: Boolean = false,
  defaultExpanded: Boolean = false,
  content: @Composable () -> Unit,
) {
  val context = LocalContext.current
  var expanded by rememberSaveable(key) {
    mutableStateOf(if (defaultExpanded) true else SettingsCardStateStore.isExpanded(context, key, defaultExpanded))
  }
  CompassCard("", tag = tag, accent = accent, debug = debug) {
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .testTag("${tag}_header")
        .clickable {
          expanded = !expanded
          SettingsCardStateStore.setExpanded(context, key, expanded)
        },
      horizontalArrangement = Arrangement.SpaceBetween,
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
      Icon(
        if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
        contentDescription = if (expanded) stringResource(R.string.settings_collapse_section) else stringResource(R.string.settings_expand_section),
      )
    }
    if (expanded) content()
  }
}

private object SettingsCardStateStore {
  private const val PREFS_NAME = "life_load_settings_cards"
  private const val KEY_PREFIX = "expanded_"

  fun isExpanded(context: Context, key: String, defaultExpanded: Boolean): Boolean =
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getBoolean(KEY_PREFIX + key, defaultExpanded)

  fun setExpanded(context: Context, key: String, expanded: Boolean) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .putBoolean(KEY_PREFIX + key, expanded)
      .apply()
  }
}

@Composable
private fun AccountSettingsCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  CollapsibleSettingsCard(stringResource(R.string.account), key = "account", tag = "settings-section-account") {
    Row(
      horizontalArrangement = Arrangement.spacedBy(12.dp),
      verticalAlignment = Alignment.CenterVertically,
      modifier = Modifier.fillMaxWidth(),
    ) {
      Icon(
        Icons.Filled.AccountCircle,
        contentDescription = null,
        tint = MaterialTheme.colorScheme.primary,
        modifier = Modifier.size(32.dp),
      )
      Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(stringResource(R.string.signed_in_as), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
          state.authSession.email.ifBlank { stringResource(R.string.signed_in) },
          color = MaterialTheme.colorScheme.onSurface,
          fontWeight = FontWeight.SemiBold,
        )
        Text(stringResource(R.string.alpha_backend), color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
    OutlinedButton(
      onClick = actions.onSignOut,
      modifier = Modifier.testTag("account-sign-out-button"),
      colors = neutralSettingsOutlinedButtonColors(),
    ) {
      Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null)
      Text(stringResource(R.string.sign_out))
    }
  }
}

@Composable
private fun CheckInPreferencesCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val settings = state.settings
  var cacheHelpOpen by rememberSaveable { mutableStateOf(false) }
  if (cacheHelpOpen) {
    AlertDialog(
      onDismissRequest = { cacheHelpOpen = false },
      confirmButton = {
        TextButton(onClick = { cacheHelpOpen = false }) {
          Text(stringResource(R.string.close))
        }
      },
      title = { Text(stringResource(R.string.settings_entry_cache)) },
      text = { Text(stringResource(R.string.settings_entry_cache_explanation)) },
    )
  }
  CollapsibleSettingsCard(stringResource(R.string.settings_checkin_preferences), key = "checkin", tag = "settings-section-checkin") {
    SegmentedField(
      label = stringResource(R.string.settings_default_checkin_date),
      selected = settings.dailyFlow.defaultDate,
      options = listOf("yesterday" to stringResource(R.string.settings_yesterday), "today" to stringResource(R.string.settings_today)),
      tagPrefix = "settings-default-date",
    ) { value ->
      actions.onSettingsChanged(settings.copy(dailyFlow = settings.dailyFlow.copy(defaultDate = value)))
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(stringResource(R.string.settings_entry_cache), color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleSmall)
        IconButton(
          onClick = { cacheHelpOpen = true },
          modifier = Modifier
            .size(36.dp)
            .testTag("settings-cache-days-help"),
        ) {
          Icon(Icons.AutoMirrored.Filled.HelpOutline, contentDescription = stringResource(R.string.settings_entry_cache_explanation), modifier = Modifier.size(18.dp))
        }
      }
      SegmentedField(
        label = "",
        selected = settings.dailyFlow.entryCacheDays.toString(),
        options = listOf("3", "5", "7", "10", "14").map { it to stringResource(R.string.settings_days, it) },
        tagPrefix = "settings-cache-days",
      ) { value ->
        actions.onSettingsChanged(settings.copy(dailyFlow = settings.dailyFlow.copy(entryCacheDays = value.toIntOrNull() ?: settings.dailyFlow.entryCacheDays)))
      }
    }
    ToggleRow(
      label = stringResource(R.string.settings_collapse_details),
      checked = settings.dailyFlow.secondaryCardsCollapsed,
      tag = "settings-secondary-cards-collapsed",
      helper = stringResource(R.string.settings_collapse_details_helper),
    ) {
      actions.onSettingsChanged(settings.copy(dailyFlow = settings.dailyFlow.copy(secondaryCardsCollapsed = it)))
    }
  }
}

@Composable
private fun ReminderSettingsCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val settings = state.settings
  val reminder = settings.reminder
  val context = LocalContext.current
  val notificationPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
    if (granted) {
      actions.onReminderSettingsChanged(reminder.copy(enabled = true))
    }
  }
  val needsNotificationPermission =
    Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
      ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
  LaunchedEffect(reminder.enabled, needsNotificationPermission) {
    if (reminder.enabled && needsNotificationPermission) {
      notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
  }
  var reminderMode by rememberSaveable(reminder.hour, reminder.minute) { mutableStateOf(reminderPresetKey(reminder)) }
  CollapsibleSettingsCard(stringResource(R.string.settings_reminder), key = "reminder", tag = "settings-section-reminder") {
    ToggleRow(
      label = stringResource(R.string.settings_daily_reminder),
      checked = reminder.enabled,
      tag = "settings-reminder-enabled",
      helper = stringResource(R.string.settings_daily_reminder_helper),
    ) { enabled ->
      if (enabled && needsNotificationPermission) {
        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
      } else {
        actions.onReminderSettingsChanged(reminder.copy(enabled = enabled))
      }
    }
    Text(stringResource(R.string.settings_notification_permission_note), color = MaterialTheme.colorScheme.onSurfaceVariant)
    SegmentedField(
      label = stringResource(R.string.settings_reminder_time),
      selected = reminderMode,
      options = reminderTimeOptions(),
      tagPrefix = "settings-reminder-time",
    ) { value ->
      reminderMode = value
      when (value) {
        "07:00", "21:30" -> {
          actions.onReminderSettingsChanged(reminder.withTimeKey(value))
        }
        "custom" -> Unit
      }
    }
    if (reminderMode == "custom") {
      CustomReminderTimePicker(
        reminder = reminder,
        onTimeSelected = { hour, minute ->
          actions.onReminderSettingsChanged(reminder.copy(hour = hour, minute = minute))
        },
      )
    }
    if (state.settingsMessage.isNotBlank()) {
      Text(state.settingsMessage, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (state.error.isNotBlank()) {
      Text(state.error, color = MaterialTheme.colorScheme.error)
    }
  }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CustomReminderTimePicker(
  reminder: LifeLoadReminderSettings,
  onTimeSelected: (Int, Int) -> Unit,
) {
  var showPicker by rememberSaveable { mutableStateOf(false) }
  val label = stringResource(R.string.settings_custom_reminder_time)
  OutlinedButton(
    onClick = { showPicker = true },
    modifier = Modifier
      .fillMaxWidth()
      .testTag("settings-reminder-custom-time"),
  ) {
    Icon(Icons.Filled.AccessTime, contentDescription = null, modifier = Modifier.size(18.dp))
    Spacer(Modifier.width(8.dp))
    Text("${label}: ${reminder.timeKey()}")
  }
  if (showPicker) {
    val pickerState = rememberTimePickerState(
      initialHour = reminder.hour.coerceIn(0, 23),
      initialMinute = reminder.minute.coerceIn(0, 59),
      is24Hour = true,
    )
    AlertDialog(
      onDismissRequest = { showPicker = false },
      title = { Text(label) },
      text = {
        TimePicker(
          state = pickerState,
          modifier = Modifier.fillMaxWidth(),
        )
      },
      confirmButton = {
        TextButton(
          onClick = {
            onTimeSelected(pickerState.hour, pickerState.minute)
            showPicker = false
          },
        ) {
          Text(stringResource(R.string.settings_set_time))
        }
      },
      dismissButton = {
        TextButton(onClick = { showPicker = false }) {
          Text(stringResource(R.string.cancel))
        }
      },
    )
  }
}

@Composable
private fun GuidanceFormulaCard(state: LifeLoadUiState, actions: LifeLoadUiActions, mode: CompassMode) {
  val settings = state.settings
  CollapsibleSettingsCard("Advanced formula settings", key = "guidance", tag = "settings-section-guidance", debug = true) {
    ProfileModifierField(
      label = stringResource(R.string.settings_profile_future),
      selected = activeProfileModifiers(settings.formula),
      options = guidanceProfileOptions(),
      tagPrefix = "settings-formula-profile",
    ) { key ->
      actions.onSettingsChanged(settings.copy(formula = settings.formula.withToggledProfileModifier(key)))
    }
    activeProfileModifiers(settings.formula).map { profileExplanation(it) }.forEach { explanation ->
      Text(explanation, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Text(stringResource(R.string.settings_what_affects_guidance), color = MaterialTheme.colorScheme.onSurfaceVariant)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      FormulaFactorPill(stringResource(R.string.settings_recovery), formulaGroupEnabled(settings.formula, "recovery"))
      FormulaFactorPill(stringResource(R.string.settings_evening_risk), formulaGroupEnabled(settings.formula, "evening"))
      FormulaFactorPill(stringResource(R.string.settings_stress), formulaGroupEnabled(settings.formula, "stress"))
      FormulaFactorPill(stringResource(R.string.settings_context), formulaGroupEnabled(settings.formula, "context"))
    }
    Text(stringResource(R.string.settings_profile_future_helper), color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (mode.showsDetails()) {
      FormulaToggleGroup("Recovery") {
        FormulaToggle("Garmin recovery", settings.formula.includeGarminRecovery, "settings_include_garmin_recovery", actions) {
          settings.copy(formula = settings.formula.copy(includeGarminRecovery = it))
        }
        FormulaToggle("After-work decompression", settings.formula.includeAfterWorkDecompression, "settings_include_after_work_decompression", actions) {
          settings.copy(formula = settings.formula.copy(includeAfterWorkDecompression = it))
        }
      }
      FormulaToggleGroup("Evening risk") {
        FormulaToggle("Late phone", settings.formula.includeLatePhone, "settings_include_late_phone", actions) {
          settings.copy(formula = settings.formula.copy(includeLatePhone = it))
        }
        FormulaToggle("Project overrun", settings.formula.includeProjectOverrun, "settings_include_project_overrun", actions) {
          settings.copy(formula = settings.formula.copy(includeProjectOverrun = it))
        }
      }
      FormulaToggleGroup("Context / Stress") {
        FormulaToggle("Home office", settings.formula.includeHomeOffice, "settings_include_home_office", actions) {
          settings.copy(formula = settings.formula.copy(includeHomeOffice = it))
        }
        FormulaToggle("Alone at home", settings.formula.includeAloneHome, "settings_include_alone_home", actions) {
          settings.copy(formula = settings.formula.copy(includeAloneHome = it))
        }
        FormulaToggle("Relationship stress", settings.formula.includeRelationshipStress, "settings_include_relationship_stress", actions) {
          settings.copy(formula = settings.formula.copy(includeRelationshipStress = it))
        }
        FormulaToggle("Training trend brake", settings.formula.includeTrainingTrendBrake, "settings_include_training_trend_brake", actions) {
          settings.copy(formula = settings.formula.copy(includeTrainingTrendBrake = it))
        }
      }
      Button(onClick = { actions.onSaveSettings("") }, enabled = !state.settingsSaving, modifier = Modifier.testTag("settings_save_button")) {
        Text(if (state.settingsSaving) stringResource(R.string.settings_saving) else stringResource(R.string.settings_save_settings))
      }
      if (state.settingsMessage.isNotBlank()) {
        Text(state.settingsMessage, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
  }
}

@Composable
private fun GuidanceExplanationCard() {
  CollapsibleSettingsCard(stringResource(R.string.settings_guidance), key = "guidance", tag = "settings-section-guidance") {
    Text(stringResource(R.string.settings_guidance_beta_copy), color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun ProfileModifierField(
  label: String,
  selected: Set<String>,
  options: List<Pair<String, String>>,
  tagPrefix: String,
  onToggle: (String) -> Unit,
) {
  Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
    Text(label, color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleSmall)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
      options.forEach { (key, text) ->
        val selectedHere = key in selected
        val color = if (selectedHere) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline
        FilterChip(
          selected = selectedHere,
          onClick = { onToggle(key) },
          label = { Text(text) },
          modifier = Modifier
            .defaultMinSize(minHeight = 42.dp)
            .testTag("${tagPrefix}_${key.lowercase()}"),
          border = FilterChipDefaults.filterChipBorder(
            enabled = true,
            selected = selectedHere,
            borderColor = color.copy(alpha = 0.45f),
            selectedBorderColor = color,
          ),
        )
      }
    }
  }
}

@Composable
private fun FormulaFactorPill(label: String, enabled: Boolean) {
  val suffix = if (enabled) stringResource(R.string.settings_factor_on) else stringResource(R.string.settings_factor_off)
  StatusPill(
    "$label · $suffix",
    if (enabled) compassBlue() else MaterialTheme.colorScheme.outline,
    type = if (enabled) StatusPillType.Info else StatusPillType.Neutral,
  )
}

private fun formulaGroupEnabled(formula: LifeLoadFormulaSettings, group: String): Boolean =
  when (group) {
    "recovery" -> formula.includeGarminRecovery || formula.includeAfterWorkDecompression
    "evening" -> formula.includeLatePhone || formula.includeProjectOverrun
    "stress" -> formula.includeRelationshipStress || formula.includeTrainingTrendBrake
    "context" -> formula.includeHomeOffice || formula.includeAloneHome
    else -> false
  }

@Composable
private fun guidanceProfileOptions(): List<Pair<String, String>> = listOf(
  "balanced" to stringResource(R.string.settings_balanced),
  "protective" to stringResource(R.string.settings_protective),
  "sports_light" to stringResource(R.string.settings_sports_light),
)

private val guidanceProfileKeys = listOf("balanced", "protective", "sports_light")

private fun activeProfileModifiers(formula: LifeLoadFormulaSettings): Set<String> {
  val savedModifiers = formula.profileModifiers.filterTo(linkedSetOf()) { it in guidanceProfileKeys }
  if (savedModifiers.isNotEmpty()) return savedModifiers
  val legacyProfile = formula.profile.takeIf { it in guidanceProfileKeys } ?: "balanced"
  return linkedSetOf(legacyProfile)
}

private fun LifeLoadFormulaSettings.withToggledProfileModifier(key: String): LifeLoadFormulaSettings {
  if (key !in guidanceProfileKeys) return this
  val current = activeProfileModifiers(this)
  val next = if (key in current) current - key else current + key
  val normalized = next.ifEmpty { setOf("balanced") }
  val legacyProfile = guidanceProfileKeys.firstOrNull { it in normalized } ?: "balanced"
  return copy(profile = legacyProfile, profileModifiers = normalized)
}

@Composable
private fun profileExplanation(profile: String): String =
  when (profile) {
    "protective" -> stringResource(R.string.settings_profile_protective_helper)
    "sports_light" -> stringResource(R.string.settings_profile_sports_light_helper)
    else -> stringResource(R.string.settings_profile_balanced_helper)
}

private fun LifeLoadReminderSettings.timeKey(): String = "%02d:%02d".format(hour.coerceIn(0, 23), minute.coerceIn(0, 59))

private fun LifeLoadReminderSettings.withTimeKey(value: String): LifeLoadReminderSettings {
  val parsed = parseTimeKey(value) ?: return this
  return copy(hour = parsed.first, minute = parsed.second)
}

@Composable
private fun reminderTimeOptions(): List<Pair<String, String>> =
  listOf(
    "07:00" to stringResource(R.string.settings_reminder_morning),
    "21:30" to stringResource(R.string.settings_reminder_evening),
    "custom" to stringResource(R.string.settings_reminder_custom),
  )

private fun reminderPresetKey(reminder: LifeLoadReminderSettings): String = when (reminder.timeKey()) {
  "07:00" -> "07:00"
  "21:30" -> "21:30"
  else -> "custom"
}

private fun parseTimeKey(value: String): Pair<Int, Int>? {
  val parts = value.trim().split(":")
  if (parts.size != 2) return null
  val hour = parts[0].toIntOrNull() ?: return null
  val minute = parts[1].toIntOrNull() ?: return null
  if (hour !in 0..23 || minute !in 0..59) return null
  return hour to minute
}

@Composable
private fun ConnectedDataCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val settings = state.settings
  var passwordDraft by rememberSaveable { mutableStateOf("") }
  CollapsibleSettingsCard(stringResource(R.string.settings_connected_data), key = "connected_data", tag = "settings-section-connected-data") {
    ToggleRow(stringResource(R.string.settings_garmin_active), settings.garmin.enabled, "settings_garmin_active") {
      actions.onSettingsChanged(settings.copy(garmin = settings.garmin.copy(enabled = it)))
    }
    ToggleRow(stringResource(R.string.settings_garmin_auto_import), settings.garmin.autoImport, "settings_garmin_auto_import") {
      actions.onSettingsChanged(settings.copy(garmin = settings.garmin.copy(autoImport = it)))
    }
    CompassTextField(stringResource(R.string.settings_garmin_email), settings.garmin.email, "settings_garmin_email") {
      actions.onSettingsChanged(settings.copy(garmin = settings.garmin.copy(email = it)))
    }
    SecureTextField(
      label = if (settings.garmin.passwordSet) stringResource(R.string.settings_garmin_password_replace) else stringResource(R.string.settings_garmin_password),
      value = passwordDraft,
      tag = "settings_garmin_password",
      onValueChange = { passwordDraft = it },
    )
    SegmentedField(
      label = stringResource(R.string.settings_auto_import_days),
      selected = settings.garmin.autoImportDays.toString(),
      options = listOf("1", "2", "3", "5", "7").map { it to it },
      tagPrefix = "settings_garmin_auto_import_days",
    ) { value ->
      actions.onSettingsChanged(settings.copy(garmin = settings.garmin.copy(autoImportDays = value.toIntOrNull() ?: settings.garmin.autoImportDays)))
    }
    Button(onClick = { actions.onSaveSettings(passwordDraft) }, enabled = !state.settingsSaving, modifier = Modifier.testTag("settings_garmin_save")) {
      Text(if (state.settingsSaving) stringResource(R.string.settings_saving) else stringResource(R.string.settings_save_garmin))
    }
  }
}

@Composable
fun BackupRestoreCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  var backupInfoVisible by rememberSaveable { mutableStateOf(false) }
  var email by rememberSaveable(state.authSession.email) { mutableStateOf(state.authSession.email) }
  var password by rememberSaveable { mutableStateOf("") }
  var disclaimerAccepted by rememberSaveable { mutableStateOf(false) }
  val exportLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
    if (uri != null) actions.onExportLocalDataToUri(uri)
  }
  val importLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
    if (uri != null) actions.onImportLocalDataFromUri(uri)
  }
  if (backupInfoVisible) {
    BackupAccountInfoDialog(onDismiss = { backupInfoVisible = false })
  }
  CollapsibleSettingsCard(stringResource(R.string.settings_backup_restore), key = "backup", tag = "settings-section-backup") {
    Row(
      horizontalArrangement = Arrangement.spacedBy(8.dp),
      verticalAlignment = Alignment.CenterVertically,
      modifier = Modifier.fillMaxWidth(),
    ) {
      Text(
        stringResource(R.string.settings_backup_restore_copy),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.weight(1f),
      )
      IconButton(
        onClick = { backupInfoVisible = true },
        modifier = Modifier.testTag("backup-info-button"),
      ) {
        Icon(Icons.AutoMirrored.Filled.HelpOutline, contentDescription = stringResource(R.string.settings_backup_info_title))
      }
    }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
      Button(
        onClick = { exportLauncher.launch("life_load_backup_${state.selectedDate}.json") },
        modifier = Modifier.testTag("backup-export-button"),
        colors = backupExportButtonColors(),
      ) {
        Icon(Icons.Filled.FileDownload, contentDescription = null)
        Text(stringResource(R.string.settings_export_backup))
      }
      OutlinedButton(
        onClick = { importLauncher.launch(arrayOf("application/json", "text/json", "text/plain", "*/*")) },
        modifier = Modifier.testTag("backup-import-button"),
        colors = neutralSettingsOutlinedButtonColors(),
      ) {
        Icon(Icons.Filled.FileUpload, contentDescription = null)
        Text(stringResource(R.string.settings_import_backup))
      }
    }
    Text(stringResource(R.string.settings_import_backup_unavailable), color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (state.backupMessage.isNotBlank()) {
      Text(state.backupMessage, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
      Text(stringResource(R.string.settings_backup_account_title), fontWeight = FontWeight.SemiBold)
      Text(stringResource(R.string.settings_backup_account_copy), color = MaterialTheme.colorScheme.onSurfaceVariant)
      if (state.authSession.isSignedIn) {
        Row(
          horizontalArrangement = Arrangement.spacedBy(12.dp),
          verticalAlignment = Alignment.CenterVertically,
          modifier = Modifier.fillMaxWidth(),
        ) {
          Icon(Icons.Filled.AccountCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
          Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(stringResource(R.string.signed_in_as), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(state.authSession.email.ifBlank { stringResource(R.string.signed_in) }, fontWeight = FontWeight.SemiBold)
          }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
          Button(
            onClick = actions.onRestoreFromServer,
            enabled = !state.authLoading,
            modifier = Modifier.testTag("backup-restore-server-button"),
          ) {
            Text(stringResource(R.string.settings_restore_from_server))
          }
          OutlinedButton(
            onClick = actions.onSyncLocalOutbox,
            enabled = !state.authLoading,
            modifier = Modifier.testTag("backup-sync-server-button"),
            colors = neutralSettingsOutlinedButtonColors(),
          ) {
            Text(stringResource(R.string.operator_sync_outbox))
          }
          OutlinedButton(
            onClick = actions.onSignOut,
            enabled = !state.authLoading,
            modifier = Modifier.testTag("backup-sign-out-button"),
            colors = neutralSettingsOutlinedButtonColors(),
          ) {
            Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null)
            Text(stringResource(R.string.sign_out))
          }
        }
      } else {
        CompassTextField(stringResource(R.string.email), email, "backup-auth-email") { email = it }
        OutlinedTextField(
          value = password,
          onValueChange = { password = it },
          label = { Text(stringResource(R.string.password)) },
          singleLine = true,
          enabled = !state.authLoading,
          visualTransformation = PasswordVisualTransformation(),
          modifier = Modifier
            .fillMaxWidth()
            .testTag("backup-auth-password"),
        )
        Row(
          modifier = Modifier
            .fillMaxWidth()
            .clickable(enabled = !state.authLoading) { disclaimerAccepted = !disclaimerAccepted }
            .testTag("backup-medical-disclaimer-row"),
          horizontalArrangement = Arrangement.spacedBy(8.dp),
          verticalAlignment = Alignment.Top,
        ) {
          Checkbox(
            checked = disclaimerAccepted,
            onCheckedChange = { disclaimerAccepted = it },
            enabled = !state.authLoading,
            modifier = Modifier.testTag("backup-medical-disclaimer-checkbox"),
          )
          Text(
            stringResource(R.string.auth_medical_disclaimer_acknowledgement),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 12.dp),
          )
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
          Button(
            onClick = { actions.onSignIn(email, password) },
            enabled = !state.authLoading,
            modifier = Modifier.testTag("backup-sign-in-button"),
          ) {
            Text(if (state.authLoading) stringResource(R.string.signing_in) else stringResource(R.string.sign_in))
          }
          OutlinedButton(
            onClick = { actions.onRegister(email, password) },
            enabled = !state.authLoading && disclaimerAccepted,
            modifier = Modifier.testTag("backup-create-account-button"),
            colors = neutralSettingsOutlinedButtonColors(),
          ) {
            Text(stringResource(R.string.create_account))
          }
        }
      }
      if (state.authError.isNotBlank()) {
        Text(state.authError, color = MaterialTheme.colorScheme.error)
      } else if (state.authMessage.isNotBlank()) {
        Text(state.authMessage, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
      if (state.localDebug.message.isNotBlank()) {
        Text(state.localDebug.message, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
  }
}

@Composable
private fun BackupAccountInfoDialog(onDismiss: () -> Unit) {
  AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text(stringResource(R.string.settings_backup_info_title)) },
    text = {
      Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(stringResource(R.string.settings_backup_info_local_first))
        Text(stringResource(R.string.settings_backup_info_remote_mirror))
        Text(stringResource(R.string.settings_backup_info_restore))
        Text(stringResource(R.string.settings_backup_info_limits))
      }
    },
    confirmButton = {
      TextButton(onClick = onDismiss) {
        Text(stringResource(R.string.close))
      }
    },
  )
}

@Composable
fun PrivacyCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  var deleteArmed by rememberSaveable { mutableStateOf(false) }
  var securityDialogVisible by rememberSaveable { mutableStateOf(false) }
  if (securityDialogVisible) {
    SecurityNoticeDialog(onDismiss = { securityDialogVisible = false })
  }
  CollapsibleSettingsCard(stringResource(R.string.settings_privacy), key = "privacy", tag = "settings-section-privacy", accent = compassAmber()) {
    Text(stringResource(R.string.settings_privacy_copy), color = MaterialTheme.colorScheme.onSurfaceVariant)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      OutlinedButton(
        onClick = { securityDialogVisible = true },
        modifier = Modifier.testTag("privacy-security-button"),
        colors = neutralSettingsOutlinedButtonColors(),
      ) {
        Icon(Icons.Filled.Security, contentDescription = null)
        Text(stringResource(R.string.settings_security_button))
      }
      if (deleteArmed) {
        Button(
          onClick = {
            actions.onDeleteLocalData()
            deleteArmed = false
          },
          modifier = Modifier.testTag("privacy-confirm-delete-button"),
          colors = privacyDeleteButtonColors(),
        ) {
          Icon(Icons.Filled.Delete, contentDescription = null)
          Text(stringResource(R.string.settings_confirm_delete))
        }
      } else {
        OutlinedButton(
          onClick = { deleteArmed = true },
          modifier = Modifier.testTag("privacy-delete-local-button"),
          colors = privacyDeleteOutlinedButtonColors(),
        ) {
          Icon(Icons.Filled.Delete, contentDescription = null)
          Text(stringResource(R.string.settings_delete_local_data))
        }
      }
    }
    if (deleteArmed) {
      Text(stringResource(R.string.settings_confirm_delete_copy), color = MaterialTheme.colorScheme.error.copy(alpha = 0.88f))
      TextButton(
        onClick = { deleteArmed = false },
        colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurfaceVariant),
      ) { Text(stringResource(R.string.cancel)) }
    }
    if (state.privacyMessage.isNotBlank()) {
      Text(state.privacyMessage, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun backupExportButtonColors() =
  ButtonDefaults.buttonColors(
    containerColor = compassGreen(),
    contentColor = MaterialTheme.colorScheme.onPrimary,
    disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant,
    disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.55f),
  )

@Composable
private fun neutralSettingsOutlinedButtonColors() =
  ButtonDefaults.outlinedButtonColors(
    contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
    disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
  )

@Composable
private fun privacyDeleteButtonColors() =
  ButtonDefaults.buttonColors(
    containerColor = MaterialTheme.colorScheme.error.copy(alpha = 0.90f),
    contentColor = MaterialTheme.colorScheme.onError,
    disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant,
    disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
  )

@Composable
private fun privacyDeleteOutlinedButtonColors() =
  ButtonDefaults.outlinedButtonColors(
    contentColor = MaterialTheme.colorScheme.error.copy(alpha = 0.86f),
    disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
  )

@Composable
private fun SecurityNoticeDialog(onDismiss: () -> Unit) {
  AlertDialog(
    onDismissRequest = onDismiss,
    confirmButton = {
      TextButton(
        onClick = onDismiss,
        modifier = Modifier.testTag("privacy-security-close-button"),
      ) {
        Text(stringResource(R.string.close))
      }
    },
    title = { Text(stringResource(R.string.settings_security_title)) },
    text = {
      Column(
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.testTag("privacy-security-dialog"),
      ) {
        Text(stringResource(R.string.settings_security_intro))
        Text(stringResource(R.string.settings_security_local_first), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.settings_security_minimize), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.settings_security_limits), color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    },
  )
}

@Composable
private fun DeveloperDiagnosticsCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val context = LocalContext.current
  var serverUrlDraft by rememberSaveable { mutableStateOf(ServerConfig.resolveBaseUrl(context)) }
  CollapsibleSettingsCard(stringResource(R.string.settings_developer_diagnostics), key = "developer", tag = "settings-section-developer") {
    CompassTextField(stringResource(R.string.settings_server_url), serverUrlDraft, "operator-server-url") { serverUrlDraft = it }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
      Button(onClick = {
        ServerConfig.saveBaseUrl(context, serverUrlDraft)
        serverUrlDraft = ServerConfig.resolveBaseUrl(context)
      }, modifier = Modifier.testTag("settings_server_apply")) {
        Text(stringResource(R.string.settings_apply))
      }
      TextButton(onClick = {
        ServerConfig.resetBaseUrl(context)
        serverUrlDraft = ServerConfig.resolveBaseUrl(context)
      }, modifier = Modifier.testTag("settings_server_default")) {
        Text(stringResource(R.string.settings_default))
      }
    }

    Column(
      modifier = Modifier
        .fillMaxWidth()
        .testTag("operator-local-diagnostics"),
      verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
      Text(stringResource(R.string.settings_local_diagnostics), color = MaterialTheme.colorScheme.onSurfaceVariant)
      DiagnosticsFields(
        stringResource(R.string.operator_diag_schema) to state.localDebug.schemaVersion.ifBlank { stringResource(R.string.operator_unknown) },
        stringResource(R.string.operator_diag_redaction) to state.localDebug.redaction.ifBlank { stringResource(R.string.operator_unknown) },
        stringResource(R.string.operator_diag_entries) to state.localDebug.entryCount.toString(),
        stringResource(R.string.operator_diag_approved) to state.localDebug.approvedCount.toString(),
        stringResource(R.string.operator_diag_drafts) to state.localDebug.draftCount.toString(),
        stringResource(R.string.operator_diag_outbox) to state.localDebug.outboxCount.toString(),
        stringResource(R.string.operator_diag_conflicts) to state.localDebug.conflictCount.toString(),
        stringResource(R.string.operator_diag_pending) to state.localDebug.pendingApprovalCount.toString(),
      )
      DiagnosticsFields(
        stringResource(R.string.operator_diag_backend) to state.statusLights.backend.name,
        stringResource(R.string.operator_diag_database_short) to state.statusLights.db.name,
        stringResource(R.string.operator_diag_sync) to state.statusLights.sync.name,
        stringResource(R.string.operator_diag_analysis) to state.statusLights.extract.name,
      )
      DiagnosticsFields(
        stringResource(R.string.operator_diag_state) to state.entryState,
        stringResource(R.string.operator_diag_selected) to state.selectedDate,
        stringResource(R.string.operator_diag_approved) to state.approvedAt.ifBlank { stringResource(R.string.operator_none) },
      )
      if (state.localDebug.message.isNotBlank()) Text(state.localDebug.message, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(stringResource(R.string.operator_diagnostics_actions), color = MaterialTheme.colorScheme.onSurfaceVariant)
      FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        OperatorDiagnosticAction(
          label = stringResource(R.string.operator_refresh_diagnostics),
          tag = "operator-refresh-diagnostics",
          onClick = actions.onRefreshLocalDebug,
        )
        OperatorDiagnosticAction(
          label = stringResource(R.string.operator_import_history),
          tag = "operator-import-history",
          onClick = { actions.onImportLocalHistory(14) },
        )
        OperatorDiagnosticAction(
          label = stringResource(R.string.operator_sync_outbox),
          tag = "operator-sync-outbox",
          onClick = actions.onSyncLocalOutbox,
        )
        OperatorDiagnosticAction(
          label = stringResource(R.string.operator_mirror_debug),
          tag = "operator-mirror",
          onClick = actions.onMirrorLocalDebug,
        )
      }
    }
  }
}

@Composable
private fun DiagnosticsFields(vararg fields: Pair<String, String>) {
  FlowRow(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.spacedBy(8.dp),
    verticalArrangement = Arrangement.spacedBy(4.dp),
  ) {
    fields.forEach { (label, value) ->
      Text(
        "$label $value",
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodySmall,
      )
    }
  }
}

@Composable
private fun OperatorDiagnosticAction(
  label: String,
  tag: String,
  onClick: () -> Unit,
) {
  OutlinedButton(
    onClick = onClick,
    modifier = Modifier
      .defaultMinSize(minWidth = 92.dp)
      .testTag(tag),
  ) {
    Text(label)
  }
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, tag: String, helper: String? = null, onChange: (Boolean) -> Unit) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
      Text(label)
      if (helper != null) {
        Text(helper, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
    Switch(checked = checked, onCheckedChange = onChange)
  }
}

@Composable
private fun FormulaToggleGroup(
  title: String,
  content: @Composable () -> Unit,
) {
  Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
    Text(title, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
    content()
  }
}

@Composable
private fun FormulaToggle(
  label: String,
  checked: Boolean,
  tag: String,
  actions: LifeLoadUiActions,
  update: (Boolean) -> LifeLoadSettings,
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Text(label, modifier = Modifier.weight(1f))
    Switch(
      checked = checked,
      onCheckedChange = { actions.onSettingsChanged(update(it)) },
      modifier = Modifier.testTag("$tag-switch"),
    )
  }
}

@Composable
private fun SecureTextField(
  label: String,
  value: String,
  tag: String,
  onValueChange: (String) -> Unit,
) {
  OutlinedTextField(
    value = value,
    onValueChange = onValueChange,
    label = { Text(label) },
    visualTransformation = if (value.isBlank()) VisualTransformation.None else PasswordVisualTransformation(),
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag),
  )
}
