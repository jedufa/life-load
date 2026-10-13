@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package com.life.lifeload.ui.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonColors
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchColors
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.life.lifeload.BuildConfig
import com.life.lifeload.R
import com.life.lifeload.domain.LifeLoadBetaGuidanceCardState
import com.life.lifeload.domain.LifeLoadBetaGuidanceLabel
import com.life.lifeload.domain.LifeLoadOptionalPackMetadata
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadProfileDraftState
import com.life.lifeload.domain.LifeLoadProfileFeatureFlags
import com.life.lifeload.domain.LifeLoadProfileSetupState
import com.life.lifeload.domain.LifeLoadProfileTemplateMetadata
import com.life.lifeload.domain.LifeLoadSelectedProfileConfig
import com.life.lifeload.domain.LifeLoadRenderableProfileField
import com.life.lifeload.domain.devProfileSelectorVisible
import com.life.lifeload.domain.onboardingVisibleForNewUser
import com.life.lifeload.domain.profileDrivenCheckInActive
import com.life.lifeload.domain.trackingSetupVisible

fun defaultProfileFeatureFlags(): LifeLoadProfileFeatureFlags =
  LifeLoadProfileFeatureFlags(
    profileSetupEnabled = BuildConfig.LIFE_LOAD_PROFILE_SETUP_ENABLED,
    onboardingEnabled = BuildConfig.LIFE_LOAD_PROFILE_ONBOARDING_ENABLED,
    profileDrivenCheckInEnabled = BuildConfig.LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED,
    devCompatibilityMode = BuildConfig.DEBUG,
  )

@Composable
fun runtimeBetaGuidanceFromProductionBridge(
  selectedConfig: LifeLoadSelectedProfileConfig,
  profileDraftState: LifeLoadProfileDraftState,
): LifeLoadBetaGuidanceCardState {
  val guidance = LifeLoadProfileCatalog.productionGuidanceModel(selectedConfig, profileDraftState)
  val label = guidance.label
  val rationale = when (label) {
    LifeLoadBetaGuidanceLabel.PROTECT_SLEEP -> stringResource(R.string.runtime_beta_guidance_rationale_protect_sleep)
    LifeLoadBetaGuidanceLabel.RECOVER -> stringResource(R.string.runtime_beta_guidance_rationale_recover)
    LifeLoadBetaGuidanceLabel.SIMPLIFY -> stringResource(R.string.runtime_beta_guidance_rationale_simplify)
    LifeLoadBetaGuidanceLabel.PUSH -> stringResource(R.string.runtime_beta_guidance_rationale_push)
    else -> stringResource(R.string.runtime_beta_guidance_rationale_default)
  }
  return LifeLoadBetaGuidanceCardState(
    label = label,
    rationale = rationale,
    topDrivers = guidance.driverKeys.map { driverKey -> productionBridgeDriverLabel(driverKey) },
    recentChange = stringResource(R.string.runtime_beta_guidance_recent_change),
    primaryAction = productionBridgeActionText(guidance.actionKey),
    confidenceNote = if (guidance.confidence == "normal") {
      stringResource(R.string.runtime_beta_guidance_confidence_normal)
    } else {
      stringResource(R.string.runtime_beta_guidance_confidence_limited)
    },
    missingSignalLabels = guidance.missingSignalIds.map { signalId ->
      signalLabelForId(signalId, signalId)
    },
    whyDetails = listOf(
      stringResource(R.string.runtime_beta_guidance_why_bridge),
      stringResource(R.string.runtime_beta_guidance_why_inputs),
    ),
  )
}

@Composable
private fun productionBridgeDriverLabel(driverKey: String): String =
  when (driverKey) {
    "stress" -> stringResource(R.string.runtime_beta_guidance_driver_stress)
    "work_pressure" -> stringResource(R.string.runtime_beta_guidance_driver_work_pressure)
    "work_spillover" -> stringResource(R.string.runtime_beta_guidance_driver_work_spillover)
    "energy" -> stringResource(R.string.runtime_beta_guidance_driver_energy)
    "sleep" -> stringResource(R.string.runtime_beta_guidance_driver_sleep)
    "private_pattern" -> stringResource(R.string.runtime_beta_guidance_driver_private_pattern)
    "decompression" -> stringResource(R.string.runtime_beta_guidance_driver_decompression)
    "training_load" -> stringResource(R.string.runtime_beta_guidance_driver_training_load)
    "body_signal" -> stringResource(R.string.runtime_beta_guidance_driver_body_signal)
    "protective_behavior" -> stringResource(R.string.runtime_beta_guidance_driver_protective_behavior)
    "recovery" -> stringResource(R.string.runtime_beta_guidance_driver_recovery)
    "missing_data" -> stringResource(R.string.runtime_beta_guidance_driver_missing_data)
    "recovery_steady" -> stringResource(R.string.runtime_beta_guidance_driver_recovery_steady)
    else -> stringResource(R.string.runtime_beta_guidance_driver_profile_signal)
  }

@Composable
private fun productionBridgeActionText(actionKey: String): String =
  when (actionKey) {
    "check_in_first" -> stringResource(R.string.runtime_beta_guidance_action_check_in_first)
    "protect_private_pattern" -> stringResource(R.string.runtime_beta_guidance_action_protect_private_pattern)
    "protect_sleep" -> stringResource(R.string.runtime_beta_guidance_action_protect_sleep)
    "recover_body_signal" -> stringResource(R.string.runtime_beta_guidance_action_recover_body_signal)
    "keep_training_easy" -> stringResource(R.string.runtime_beta_guidance_action_keep_training_easy)
    "take_recovery_break" -> stringResource(R.string.runtime_beta_guidance_action_take_recovery_break)
    "reduce_optional_work" -> stringResource(R.string.runtime_beta_guidance_action_reduce_optional_work)
    "simplify_evening" -> stringResource(R.string.runtime_beta_guidance_action_simplify_evening)
    "avoid_extra_commitment" -> stringResource(R.string.runtime_beta_guidance_action_simplify)
    "use_good_capacity" -> stringResource(R.string.runtime_beta_guidance_action_push)
    "maintain_recovery_protected" -> stringResource(R.string.runtime_beta_guidance_action_maintain_recovery_protected)
    "maintain_stable" -> stringResource(R.string.runtime_beta_guidance_action_maintain_stable)
    else -> stringResource(R.string.runtime_beta_guidance_action_maintain)
  }

@Composable
fun profileDisplayNameForId(profileId: String): String =
  when (profileId) {
    "personal_legacy" -> stringResource(R.string.profile_name_personal_legacy)
    "general_balance" -> stringResource(R.string.profile_name_general_balance)
    "work_stress" -> stringResource(R.string.profile_name_work_stress)
    "training_recovery" -> stringResource(R.string.profile_name_training_recovery)
    "body_signal_awareness" -> stringResource(R.string.profile_name_body_signal_awareness)
    "custom_stub" -> stringResource(R.string.profile_name_custom)
    else -> LifeLoadProfileCatalog.profiles[profileId]?.publicName ?: profileId
  }

@Composable
private fun profileDescriptionForId(profileId: String, fallback: String): String =
  when (profileId) {
    "personal_legacy" -> stringResource(R.string.profile_description_personal_legacy)
    "general_balance" -> stringResource(R.string.profile_description_general_balance)
    "work_stress" -> stringResource(R.string.profile_description_work_stress)
    "training_recovery" -> stringResource(R.string.profile_description_training_recovery)
    "body_signal_awareness" -> stringResource(R.string.profile_description_body_signal_awareness)
    "custom_stub" -> stringResource(R.string.profile_description_custom)
    else -> fallback
  }

@Composable
private fun signalLabelForId(signalId: String, fallback: String): String =
  when (signalId) {
    "core.sleep_ok" -> stringResource(R.string.signal_label_core_sleep_ok)
    "core.nutrition_ok" -> stringResource(R.string.signal_label_core_nutrition_ok)
    "mental.stress" -> stringResource(R.string.signal_label_mental_stress)
    "energy.energy" -> stringResource(R.string.signal_label_energy_energy)
    "mood.mood" -> stringResource(R.string.signal_label_mood_mood)
    "recovery.shutdown_done" -> stringResource(R.string.signal_label_recovery_shutdown_done)
    "recovery.decompression_done" -> stringResource(R.string.signal_label_recovery_decompression_done)
    "recovery.after_work_decompression_done" -> stringResource(R.string.signal_label_recovery_after_work_decompression_done)
    "work.work_intensity" -> stringResource(R.string.signal_label_work_work_intensity)
    "work.home_office" -> stringResource(R.string.signal_label_work_home_office)
    "work.project_overrun" -> stringResource(R.string.signal_label_work_project_overrun)
    "training.primary_activity_type" -> stringResource(R.string.signal_label_training_primary_activity_type)
    "training.activity_duration_min" -> stringResource(R.string.signal_label_training_activity_duration_min)
    "training.rehab_done" -> stringResource(R.string.signal_label_training_rehab_done)
    "training.soreness" -> stringResource(R.string.signal_label_training_soreness)
    "body.migraine_warning" -> stringResource(R.string.signal_label_body_migraine_warning)
    "body.foot_pain" -> stringResource(R.string.signal_label_body_foot_pain)
    "body.shoulder_pain" -> stringResource(R.string.signal_label_body_shoulder_pain)
    "body.body_signal" -> stringResource(R.string.signal_label_body_body_signal)
    "nutrition.alcohol" -> stringResource(R.string.signal_label_nutrition_alcohol)
    "nutrition.binge" -> stringResource(R.string.signal_label_nutrition_binge)
    "evening.phone_after_21" -> stringResource(R.string.signal_label_evening_phone_after_21)
    "evening.evening_chain_broken" -> stringResource(R.string.signal_label_evening_chain_broken)
    "relationship.family_stress" -> stringResource(R.string.signal_label_relationship_family_stress)
    "relationship.wife_conflict_count" -> stringResource(R.string.signal_label_relationship_wife_conflict_count)
    "relationship.wife_conflict_school" -> stringResource(R.string.signal_label_relationship_wife_conflict_school)
    "relationship.wife_conflict_chores" -> stringResource(R.string.signal_label_relationship_wife_conflict_chores)
    "relationship.wife_conflict_other" -> stringResource(R.string.signal_label_relationship_wife_conflict_other)
    "caregiving.alone_home" -> stringResource(R.string.signal_label_caregiving_alone_home)
    "caregiving.homework_done" -> stringResource(R.string.signal_label_caregiving_homework_done)
    "caregiving.homework_status" -> stringResource(R.string.signal_label_caregiving_homework_status)
    "stimulant.coffee_cups" -> stringResource(R.string.signal_label_stimulant_coffee_cups)
    "pattern.private_pull" -> stringResource(R.string.signal_label_pattern_private_pull)
    "pattern.protective_routine" -> stringResource(R.string.signal_label_pattern_protective_routine)
    else -> fallback
  }

@Composable
private fun guidanceLabelFor(label: LifeLoadBetaGuidanceLabel): String =
  when (label) {
    LifeLoadBetaGuidanceLabel.PUSH -> stringResource(R.string.guidance_label_push)
    LifeLoadBetaGuidanceLabel.MAINTAIN -> stringResource(R.string.guidance_label_maintain)
    LifeLoadBetaGuidanceLabel.RECOVER -> stringResource(R.string.guidance_label_recover)
    LifeLoadBetaGuidanceLabel.SIMPLIFY -> stringResource(R.string.guidance_label_simplify)
    LifeLoadBetaGuidanceLabel.PROTECT_SLEEP -> stringResource(R.string.guidance_label_protect_sleep)
  }

@Composable
fun DevProfileSelectorCard(
  flags: LifeLoadProfileFeatureFlags,
  selectedProfileId: String,
  onProfileSelected: (String) -> Unit,
) {
  if (!devProfileSelectorVisible(flags)) return
  ProfileSelectionCard(
    title = stringResource(R.string.profile_setup_dev_selector_title),
    profiles = LifeLoadProfileCatalog.devProfiles(),
    selectedProfileId = selectedProfileId,
    onProfileSelected = onProfileSelected,
    testTag = "dev_profile_selector",
  )
}

@Composable
fun ProfileOnboardingForFlag(
  flags: LifeLoadProfileFeatureFlags,
  hasExistingSelection: Boolean,
  selectedProfileId: String,
  onProfileSelected: (String) -> Unit,
  onStartFirstCheckIn: () -> Unit,
) {
  if (!onboardingVisibleForNewUser(flags, hasExistingSelection)) return
  AlertDialog(
    onDismissRequest = {},
    modifier = Modifier.testTag("profile_onboarding"),
    containerColor = MaterialTheme.colorScheme.surface,
    titleContentColor = MaterialTheme.colorScheme.onSurface,
    textContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
    shape = RoundedCornerShape(20.dp),
    tonalElevation = 0.dp,
    title = {
      Text(stringResource(R.string.profile_onboarding_title), fontWeight = FontWeight.SemiBold)
    },
    text = {
      Column(
        modifier = Modifier
          .heightIn(max = 560.dp)
          .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        Text(stringResource(R.string.profile_onboarding_choose_focus), color = MaterialTheme.colorScheme.onSurfaceVariant)
        ProfileChoices(
          profiles = LifeLoadProfileCatalog.publicProfiles(flags.copy(devCompatibilityMode = false)),
          selectedProfileId = selectedProfileId,
          onProfileSelected = onProfileSelected,
        )
        Text(stringResource(R.string.profile_onboarding_preview_fields), fontWeight = FontWeight.SemiBold)
        LifeLoadProfileCatalog.renderableFields(LifeLoadProfileCatalog.buildSelectedProfileConfig(selectedProfileId))
          .take(6)
          .forEach { field ->
            ProfileSignalLabelRow(
              field = field,
              color = MaterialTheme.colorScheme.onSurfaceVariant,
              compact = true,
            )
          }
        Text(stringResource(R.string.profile_onboarding_privacy_boundary), color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    },
    confirmButton = {
      Button(
        onClick = onStartFirstCheckIn,
        modifier = Modifier.testTag("profile_onboarding_start"),
        colors = profilePrimaryButtonColors(),
      ) {
        Text(stringResource(R.string.profile_onboarding_start))
      }
    },
  )
}

@Composable
fun TrackingSetupCard(
  flags: LifeLoadProfileFeatureFlags,
  state: LifeLoadProfileSetupState,
  onProfileSelected: (String) -> Unit,
  onOptionalPackToggled: (String, Boolean) -> Unit,
  onResetDefaults: () -> Unit,
) {
  if (!trackingSetupVisible(flags)) return
  ElevatedCard(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("tracking_setup"),
    shape = RoundedCornerShape(24.dp),
    colors = CardDefaults.elevatedCardColors(containerColor = MaterialTheme.colorScheme.surface),
    elevation = CardDefaults.elevatedCardElevation(defaultElevation = 3.dp),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .background(MaterialTheme.colorScheme.surface)
        .padding(horizontal = 16.dp, vertical = 18.dp)
        .navigationBarsPadding()
        .testTag("tracking_setup_bottom_safe_area"),
      verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .testTag("tracking_setup_top_inset_safe"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
      ) {
        Text(stringResource(R.string.tracking_setup_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        Text(stringResource(R.string.tracking_setup_intro), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
          stringResource(R.string.tracking_setup_history_note),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
          style = MaterialTheme.typography.bodySmall,
        )
        Text(
          stringResource(
            R.string.tracking_setup_active_profile,
            profileDisplayNameForId(state.selectedConfig.activeProfileId),
          ),
          color = MaterialTheme.colorScheme.primary,
          fontWeight = FontWeight.SemiBold,
        )
      }
      TrackingSectionCard(title = stringResource(R.string.tracking_setup_section_current_profile)) {
        ProfileChoices(
          profiles = LifeLoadProfileCatalog.publicProfiles(flags),
          selectedProfileId = state.selectedConfig.activeProfileId,
          onProfileSelected = onProfileSelected,
        )
      }
      TrackingSectionCard(title = stringResource(R.string.tracking_setup_section_packs), modifier = Modifier.testTag("optional_pack_section_card")) {
        OptionalPackChoices(
          profileId = state.selectedConfig.activeProfileId,
          enabledPackIds = state.optionalPackIds,
          onOptionalPackToggled = onOptionalPackToggled,
        )
      }
      if (state.selectedConfig.activeProfileId == "custom_stub") {
        TrackingSectionCard(title = stringResource(R.string.tracking_setup_section_custom_setup)) {
          CustomProfileSetupSection()
        }
      }
      TrackingSectionCard(title = stringResource(R.string.tracking_setup_section_active_signals), modifier = Modifier.testTag("active_signals_section")) {
        Text(
          stringResource(R.string.tracking_setup_active_signals_privacy_note),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
          style = MaterialTheme.typography.bodySmall,
          modifier = Modifier.testTag("active_signals_privacy_note"),
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
          LifeLoadProfileCatalog.renderableFields(state.selectedConfig).forEach { field ->
            Row(verticalAlignment = Alignment.CenterVertically) {
              FilterChip(
                selected = field.requiredForConfidence,
                onClick = {},
                label = { Text(signalLabelForId(field.signalId, field.label)) },
                modifier = Modifier
                  .testTag("active_signal_${field.signalId}")
              )
              ProfileSignalInfoButton(field = field, compact = true)
            }
          }
        }
      }
      Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        OutlinedButton(
          onClick = onResetDefaults,
          modifier = Modifier.testTag("tracking_setup_reset_defaults"),
          colors = profileNeutralOutlinedButtonColors(),
        ) {
          Text(stringResource(R.string.tracking_setup_reset_defaults))
        }
        if (state.message.isNotBlank()) Text(state.message, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
  }
}

@Composable
fun TrackingSetupSettingsEntryCard(
  flags: LifeLoadProfileFeatureFlags,
  state: LifeLoadProfileSetupState,
  expanded: Boolean,
  onOpen: () -> Unit,
  onClose: () -> Unit,
  onProfileSelected: (String) -> Unit,
  onOptionalPackToggled: (String, Boolean) -> Unit,
  onResetDefaults: () -> Unit,
) {
  if (!trackingSetupVisible(flags)) return
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("settings_tracking_setup_entry"),
    shape = RoundedCornerShape(20.dp),
    colors = profileSurfaceCardColors(),
  ) {
    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(stringResource(R.string.tracking_setup_title), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      Text(stringResource(R.string.tracking_setup_settings_summary))
      Text(
          stringResource(
            R.string.tracking_setup_active_profile,
            profileDisplayNameForId(state.selectedConfig.activeProfileId),
          ),
      )
      if (expanded) {
        TrackingSetupCard(
          flags = flags,
          state = state,
          onProfileSelected = onProfileSelected,
          onOptionalPackToggled = onOptionalPackToggled,
          onResetDefaults = onResetDefaults,
        )
        OutlinedButton(
          onClick = onClose,
          modifier = Modifier.testTag("settings_tracking_setup_close"),
          colors = profileNeutralOutlinedButtonColors(),
        ) {
          Text(stringResource(R.string.tracking_setup_close))
        }
      } else {
        Button(
          onClick = onOpen,
          modifier = Modifier.testTag("settings_tracking_setup_open"),
          colors = profilePrimaryButtonColors(),
        ) {
          Text(stringResource(R.string.tracking_setup_open))
        }
      }
    }
  }
}

@Composable
fun GatedProfileDrivenCheckInCard(
  flags: LifeLoadProfileFeatureFlags,
  config: LifeLoadSelectedProfileConfig,
  draftState: LifeLoadProfileDraftState,
  onDraftChange: (String, Any?) -> Unit,
  onCompleteCheckIn: (() -> Unit)? = null,
) {
  if (!profileDrivenCheckInActive(flags)) return
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("profile_driven_check_in"),
    shape = RoundedCornerShape(20.dp),
    colors = profileSurfaceCardColors(),
  ) {
    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(stringResource(R.string.profile_driven_checkin_title), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      LifeLoadProfileCatalog.renderableFields(config).forEach { field ->
        ProfileDrivenFieldRow(field = field, draftState = draftState, onDraftChange = onDraftChange)
      }
      onCompleteCheckIn?.let { complete ->
        Button(
          onClick = complete,
          modifier = Modifier.testTag("profile_driven_checkin_complete"),
          colors = profilePrimaryButtonColors(),
        ) {
          Text(stringResource(R.string.profile_driven_checkin_complete))
        }
      }
    }
  }
}

@Composable
fun GatedBetaGuidanceCard(
  flags: LifeLoadProfileFeatureFlags,
  guidance: LifeLoadBetaGuidanceCardState,
  onSeeWhy: () -> Unit,
) {
  if (!profileDrivenCheckInActive(flags)) return
  ElevatedCard(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("beta_guidance_card"),
    shape = RoundedCornerShape(18.dp),
    colors = CardDefaults.elevatedCardColors(
      containerColor = MaterialTheme.colorScheme.surface,
      contentColor = MaterialTheme.colorScheme.onSurface,
    ),
  ) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
      Text(stringResource(R.string.guidance_beta_today_suggestion), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
      Text(guidanceLabelFor(guidance.label), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
      Text(guidance.rationale, style = MaterialTheme.typography.bodyMedium)
      if (guidance.topDrivers.isNotEmpty()) {
        Text(stringResource(R.string.guidance_beta_top_drivers), fontWeight = FontWeight.SemiBold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
          guidance.topDrivers.take(3).forEach { driver ->
            FilterChip(
              selected = false,
              onClick = {},
              label = { Text(driver) },
              colors = profileNeutralChipColors(),
            )
          }
        }
      }
      guidance.recentChange?.takeIf(String::isNotBlank)?.let { change ->
        Text(stringResource(R.string.guidance_beta_recent_change, change))
      }
      Text(stringResource(R.string.guidance_beta_primary_action), fontWeight = FontWeight.SemiBold)
      Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.10f)),
      ) {
        Text(
          guidance.primaryAction,
          modifier = Modifier
            .padding(12.dp)
            .testTag("beta_guidance_primary_action"),
          fontWeight = FontWeight.SemiBold,
        )
      }
      Text(guidance.confidenceNote, color = MaterialTheme.colorScheme.onSurfaceVariant)
      if (guidance.missingSignalLabels.isNotEmpty()) {
        Text(
          stringResource(R.string.guidance_beta_limited_confidence, guidance.missingSignalLabels.joinToString(", ")),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
      }
      OutlinedButton(
        onClick = onSeeWhy,
        modifier = Modifier.testTag("beta_guidance_see_why"),
        colors = profileNeutralOutlinedButtonColors(),
      ) {
        Text(stringResource(R.string.guidance_beta_see_why))
      }
    }
  }
}

@Composable
private fun CustomProfileSetupSection() {
  var customSignalName by rememberSaveable { mutableStateOf("") }
  val categories = listOf(
    stringResource(R.string.custom_signal_category_recovery),
    stringResource(R.string.custom_signal_category_energy),
    stringResource(R.string.custom_signal_category_stress),
    stringResource(R.string.custom_signal_category_body),
    stringResource(R.string.custom_signal_category_physical_load),
    stringResource(R.string.custom_signal_category_life_load),
    stringResource(R.string.custom_signal_category_private_pattern),
    stringResource(R.string.custom_signal_category_protective_behavior),
  )
  val effects = listOf(
    stringResource(R.string.custom_signal_guidance_track_only),
    stringResource(R.string.custom_signal_guidance_light),
    stringResource(R.string.custom_signal_guidance_normal),
    stringResource(R.string.custom_signal_guidance_strong),
    stringResource(R.string.custom_signal_guidance_guardrail),
  )
  Column(
    modifier = Modifier.testTag("custom_profile_setup"),
    verticalArrangement = Arrangement.spacedBy(8.dp),
  ) {
    Text(stringResource(R.string.custom_profile_title), fontWeight = FontWeight.SemiBold)
    Text(stringResource(R.string.custom_profile_intro), color = MaterialTheme.colorScheme.onSurfaceVariant)
    Text(stringResource(R.string.custom_profile_core_signals), fontWeight = FontWeight.SemiBold)
    Text(stringResource(R.string.custom_profile_core_signal_summary), color = MaterialTheme.colorScheme.onSurfaceVariant)
    OutlinedTextField(
      value = customSignalName,
      onValueChange = { customSignalName = it },
      label = { Text(stringResource(R.string.custom_signal_name_label)) },
      placeholder = { Text(stringResource(R.string.custom_signal_name_placeholder)) },
      modifier = Modifier
        .fillMaxWidth()
        .testTag("custom_signal_name_entry"),
      singleLine = true,
    )
    Text(stringResource(R.string.custom_profile_limit), color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("custom_profile_limit"))
    Text(stringResource(R.string.custom_signal_category), fontWeight = FontWeight.SemiBold)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      categories.forEach { category ->
        val sensitiveCategory = category == stringResource(R.string.custom_signal_category_private_pattern)
        FilterChip(
          selected = false,
          onClick = {},
          label = { Text(category) },
          modifier = Modifier.testTag("custom_signal_category"),
          colors = if (sensitiveCategory) profileWarningChipColors() else profileNeutralChipColors(),
          border = FilterChipDefaults.filterChipBorder(
            enabled = true,
            selected = false,
            borderColor = if (sensitiveCategory) MaterialTheme.colorScheme.tertiary.copy(alpha = 0.54f) else MaterialTheme.colorScheme.outline.copy(alpha = 0.34f),
            selectedBorderColor = MaterialTheme.colorScheme.primary,
          ),
        )
      }
    }
    Text(stringResource(R.string.custom_signal_influence), fontWeight = FontWeight.SemiBold)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      effects.forEach { effect ->
        FilterChip(
          selected = effect == stringResource(R.string.custom_signal_guidance_track_only),
          onClick = {},
          label = { Text(effect) },
          modifier = Modifier.testTag("custom_signal_influence_level"),
          colors = profileInputChipColors(),
        )
      }
    }
    Text(stringResource(R.string.custom_signal_preview), fontWeight = FontWeight.SemiBold)
    Text(
      customSignalName.ifBlank { stringResource(R.string.custom_signal_name_placeholder) },
      color = MaterialTheme.colorScheme.onSurfaceVariant,
      modifier = Modifier.testTag("custom_signal_preview"),
    )
    Text(stringResource(R.string.custom_signal_private_boundary), color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun ProfileSelectionCard(
  title: String,
  profiles: List<LifeLoadProfileTemplateMetadata>,
  selectedProfileId: String,
  onProfileSelected: (String) -> Unit,
  testTag: String,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag(testTag),
    shape = RoundedCornerShape(18.dp),
    colors = profileSurfaceCardColors(),
  ) {
    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(title, fontWeight = FontWeight.SemiBold)
      ProfileChoices(
        profiles = profiles,
        selectedProfileId = selectedProfileId,
        onProfileSelected = onProfileSelected,
      )
    }
  }
}

@Composable
private fun TrackingSectionCard(
  title: String,
  modifier: Modifier = Modifier,
  content: @Composable ColumnScope.() -> Unit,
) {
  Card(
    modifier = modifier.fillMaxWidth(),
    shape = RoundedCornerShape(18.dp),
    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.34f)),
  ) {
    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
      Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      content()
    }
  }
}

@Composable
private fun profileSurfaceCardColors() =
  CardDefaults.cardColors(
    containerColor = MaterialTheme.colorScheme.surface,
    contentColor = MaterialTheme.colorScheme.onSurface,
  )

@Composable
private fun ProfileChoices(
  profiles: List<LifeLoadProfileTemplateMetadata>,
  selectedProfileId: String,
  onProfileSelected: (String) -> Unit,
) {
  Column(
    verticalArrangement = Arrangement.spacedBy(8.dp),
    modifier = Modifier.testTag("profile_choice_list"),
  ) {
    profiles.forEach { profile ->
      val selected = selectedProfileId == profile.id
      Card(
        modifier = Modifier
          .fillMaxWidth()
          .heightIn(min = 56.dp)
          .border(
            width = 1.dp,
            color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline.copy(alpha = 0.28f),
            shape = RoundedCornerShape(16.dp),
          )
          .clickable { onProfileSelected(profile.id) }
          .testTag("profile_choice_${profile.id}"),
        shape = RoundedCornerShape(16.dp),
    colors = CardDefaults.cardColors(
      containerColor = if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f) else MaterialTheme.colorScheme.surface,
    ),
      ) {
        Row(
          modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 10.dp),
          horizontalArrangement = Arrangement.spacedBy(10.dp),
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(profileDisplayNameForId(profile.id), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyLarge)
            Text(profileDescriptionForId(profile.id, profile.description), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
          }
          Text(
            if (selected) stringResource(R.string.tracking_setup_selected_profile) else "",
            color = MaterialTheme.colorScheme.primary,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.testTag("profile_selected_marker_${profile.id}"),
          )
        }
      }
    }
  }
}

@Composable
private fun OptionalPackChoices(
  profileId: String,
  enabledPackIds: Set<String>,
  onOptionalPackToggled: (String, Boolean) -> Unit,
) {
  val profile = LifeLoadProfileCatalog.profiles[profileId] ?: return
  Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("optional_pack_section")) {
    profile.allowedOptionalPackIds
      .mapNotNull { LifeLoadProfileCatalog.optionalPacks[it] }
      .forEach { pack ->
        OptionalPackRow(pack = pack, enabled = pack.id in enabledPackIds, onOptionalPackToggled = onOptionalPackToggled)
      }
    if (profile.allowedOptionalPackIds.isEmpty()) {
      Text(stringResource(R.string.tracking_setup_no_packs), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun OptionalPackRow(
  pack: LifeLoadOptionalPackMetadata,
  enabled: Boolean,
  onOptionalPackToggled: (String, Boolean) -> Unit,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(
        width = 1.dp,
        color = optionalPackBorderColor(pack, enabled),
        shape = RoundedCornerShape(14.dp),
      ),
    shape = RoundedCornerShape(14.dp),
    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
  ) {
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .testTag("optional_pack_${pack.id}")
        .clickable { onOptionalPackToggled(pack.id, !enabled) }
        .padding(horizontal = 12.dp, vertical = 10.dp),
      horizontalArrangement = Arrangement.spacedBy(12.dp),
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(packDisplayName(pack), fontWeight = FontWeight.SemiBold)
        Text(packRowDescription(pack), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
      }
      Text(
        if (enabled) stringResource(R.string.tracking_setup_pack_on) else stringResource(R.string.tracking_setup_pack_off),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.labelMedium,
      )
      Switch(
        checked = enabled,
        onCheckedChange = { onOptionalPackToggled(pack.id, it) },
        colors = optionalPackSwitchColors(pack),
        modifier = Modifier
          .testTag("optional_pack_toggle_${pack.id}"),
      )
    }
  }
}

@Composable
private fun packDisplayName(pack: LifeLoadOptionalPackMetadata): String =
  when (pack.id) {
    "life_load_pack" -> stringResource(R.string.optional_pack_life_load_name)
    "pattern_awareness_pack" -> stringResource(R.string.pattern_awareness_name)
    else -> pack.name
  }

@Composable
private fun packRowDescription(pack: LifeLoadOptionalPackMetadata): String =
  when (pack.id) {
    "life_load_pack" -> stringResource(R.string.optional_pack_life_load_description)
    "pattern_awareness_pack" -> stringResource(R.string.pattern_awareness_description)
    else -> pack.description
  }

@Composable
private fun ProfileDrivenFieldRow(
  field: LifeLoadRenderableProfileField,
  draftState: LifeLoadProfileDraftState,
  onDraftChange: (String, Any?) -> Unit,
) {
  val currentValue = draftState.valuesBySignalId[field.signalId]?.value
  Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.testTag("profile_field_${field.signalId}")) {
    ProfileSignalLabelRow(field = field)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
      when (field.scaleType) {
        "boolean" -> {
          ProfileInputChip(
            label = stringResource(R.string.profile_field_yes),
            selected = currentValue == true,
            onClick = { onDraftChange(field.signalId, true) },
            testTag = "profile_input_${field.signalId}_yes",
          )
          ProfileInputChip(
            label = stringResource(R.string.profile_field_no),
            selected = currentValue == false,
            onClick = { onDraftChange(field.signalId, false) },
            testTag = "profile_input_${field.signalId}_no",
          )
        }
        "ordinal_0_10" -> {
          listOf(0, 5, 10).forEach { value ->
            ProfileInputChip(
              label = value.toString(),
              selected = currentValue == value,
              onClick = { onDraftChange(field.signalId, value) },
              testTag = "profile_input_${field.signalId}_$value",
            )
          }
        }
        "bounded_int" -> {
          listOf(0, 1, 2).forEach { value ->
            ProfileInputChip(
              label = value.toString(),
              selected = currentValue == value,
              onClick = { onDraftChange(field.signalId, value) },
              testTag = "profile_input_${field.signalId}_$value",
            )
          }
        }
        "duration_minutes" -> {
          listOf(15, 30, 45).forEach { minutes ->
            ProfileInputChip(
              label = stringResource(R.string.profile_field_minutes_short, minutes),
              selected = currentValue == minutes,
              onClick = { onDraftChange(field.signalId, minutes) },
              testTag = "profile_input_${field.signalId}_$minutes",
            )
          }
        }
        "text" -> {
          OutlinedTextField(
            value = currentValue as? String ?: "",
            onValueChange = { onDraftChange(field.signalId, it) },
            label = { Text(stringResource(R.string.profile_field_note_label)) },
            modifier = Modifier.fillMaxWidth(),
          )
        }
        "derived" -> {
          Text(stringResource(R.string.profile_field_readonly_derived), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        else -> {
          listOf(
            stringResource(R.string.profile_field_enum_low),
            stringResource(R.string.profile_field_enum_medium),
            stringResource(R.string.profile_field_enum_high),
          ).forEach { value ->
            ProfileInputChip(
              label = value,
              selected = currentValue == value,
              onClick = { onDraftChange(field.signalId, value) },
              testTag = "profile_input_${field.signalId}_${value.lowercase()}",
            )
          }
        }
      }
      ProfileInputChip(
        label = stringResource(R.string.profile_field_not_sure),
        selected = field.signalId !in draftState.valuesBySignalId,
        onClick = { onDraftChange(field.signalId, null) },
        testTag = "profile_input_${field.signalId}_not_sure",
      )
    }
  }
}

@Composable
private fun ProfileSignalLabelRow(
  field: LifeLoadRenderableProfileField,
  color: Color = MaterialTheme.colorScheme.onSurface,
  compact: Boolean = false,
) {
  var open by remember(field.signalId) { mutableStateOf(false) }
  val label = signalLabelForId(field.signalId, field.label)
  val help = profileSignalHelpFor(field.signalId)
  Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
    Row(
      modifier = Modifier.fillMaxWidth(),
      horizontalArrangement = Arrangement.SpaceBetween,
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Text(
        label,
        color = color,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.weight(1f),
      )
      IconButton(
        onClick = { open = !open },
        modifier = Modifier
          .size(if (compact) 32.dp else 40.dp)
          .testTag("profile_signal_info_${field.signalId}"),
      ) {
        Icon(
          Icons.Filled.Info,
          contentDescription = stringResource(R.string.compass_help_for, label),
          tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.72f),
        )
      }
    }
    if (open) {
      Text(
        help,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.testTag("profile_signal_help_${field.signalId}"),
      )
    }
  }
}

@Composable
private fun ProfileSignalInfoButton(field: LifeLoadRenderableProfileField, compact: Boolean = false) {
  var open by remember(field.signalId) { mutableStateOf(false) }
  val label = signalLabelForId(field.signalId, field.label)
  val help = profileSignalHelpFor(field.signalId)
  IconButton(
    onClick = { open = true },
    modifier = Modifier
      .size(if (compact) 32.dp else 40.dp)
      .testTag("profile_signal_info_${field.signalId}"),
  ) {
    Icon(
      Icons.Filled.Info,
      contentDescription = stringResource(R.string.compass_help_for, label),
      tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.72f),
    )
  }
  if (open) {
    AlertDialog(
      onDismissRequest = { open = false },
      containerColor = MaterialTheme.colorScheme.surface,
      titleContentColor = MaterialTheme.colorScheme.onSurface,
      textContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
      shape = RoundedCornerShape(20.dp),
      tonalElevation = 0.dp,
      title = { Text(stringResource(R.string.compass_help_for, label)) },
      text = { Text(help) },
      confirmButton = {
        TextButton(onClick = { open = false }) {
          Text(stringResource(R.string.close))
        }
      },
    )
  }
}

@Composable
private fun profileSignalHelpFor(signalId: String): String =
  when (signalId) {
    "core.sleep_ok" -> stringResource(R.string.field_sleep_helper)
    "core.nutrition_ok" -> stringResource(R.string.field_food_helper)
    "mental.stress" -> stringResource(R.string.field_stress_helper)
    "energy.energy" -> stringResource(R.string.field_energy_helper)
    "mood.mood" -> stringResource(R.string.field_mood_helper)
    "recovery.shutdown_done" -> stringResource(R.string.field_shutdown_helper)
    "recovery.decompression_done", "recovery.after_work_decompression_done" -> stringResource(R.string.field_decompression_helper)
    "work.project_overrun" -> stringResource(R.string.field_project_overrun_helper)
    "training.primary_activity_type" -> stringResource(R.string.field_activity_type_helper)
    "training.activity_duration_min" -> stringResource(R.string.field_movement_minutes_helper)
    "training.rehab_done" -> stringResource(R.string.field_rehab_helper)
    "body.migraine_warning" -> stringResource(R.string.field_migraine_helper)
    "body.foot_pain" -> stringResource(R.string.field_foot_pain_helper)
    "body.shoulder_pain" -> stringResource(R.string.field_shoulder_pain_helper)
    "nutrition.alcohol" -> stringResource(R.string.field_alcohol_helper)
    "nutrition.binge" -> stringResource(R.string.field_eating_episode_helper)
    "evening.phone_after_21" -> stringResource(R.string.field_phone_after_21_helper)
    "relationship.wife_conflict_count" -> stringResource(R.string.field_relationship_tension_helper)
    else -> stringResource(R.string.profile_signal_help_default)
  }

@Composable
private fun ProfileInputChip(
  label: String,
  selected: Boolean,
  onClick: () -> Unit,
  testTag: String = "profile_input_control",
) {
  FilterChip(
    selected = selected,
    onClick = onClick,
    label = { Text(label) },
    colors = profileInputChipColors(),
    border = FilterChipDefaults.filterChipBorder(
      enabled = true,
      selected = selected,
      borderColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.34f),
      selectedBorderColor = MaterialTheme.colorScheme.primary,
    ),
    modifier = Modifier.testTag(testTag),
  )
}

@Composable
private fun profilePrimaryButtonColors(): ButtonColors =
  ButtonDefaults.buttonColors(
    containerColor = MaterialTheme.colorScheme.primary,
    contentColor = MaterialTheme.colorScheme.onPrimary,
    disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant,
    disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.58f),
  )

@Composable
private fun profileNeutralOutlinedButtonColors(): ButtonColors =
  ButtonDefaults.outlinedButtonColors(
    contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
    disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
  )

@Composable
private fun profileNeutralChipColors() =
  FilterChipDefaults.filterChipColors(
    containerColor = MaterialTheme.colorScheme.surface,
    labelColor = MaterialTheme.colorScheme.onSurfaceVariant,
    selectedContainerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
    selectedLabelColor = MaterialTheme.colorScheme.primary,
    disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.42f),
    disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
  )

@Composable
private fun profileWarningChipColors() =
  FilterChipDefaults.filterChipColors(
    containerColor = MaterialTheme.colorScheme.tertiary.copy(alpha = 0.08f),
    labelColor = MaterialTheme.colorScheme.onSurface,
    selectedContainerColor = MaterialTheme.colorScheme.tertiary.copy(alpha = 0.18f),
    selectedLabelColor = MaterialTheme.colorScheme.onSurface,
  )

@Composable
private fun profileInputChipColors() =
  FilterChipDefaults.filterChipColors(
    containerColor = MaterialTheme.colorScheme.surface,
    labelColor = MaterialTheme.colorScheme.onSurfaceVariant,
    selectedContainerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.16f),
    selectedLabelColor = MaterialTheme.colorScheme.primary,
    disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.38f),
    disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
  )

@Composable
private fun optionalPackSwitchColors(pack: LifeLoadOptionalPackMetadata): SwitchColors {
  val checkedColor = if (pack.sensitive) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.primary
  return SwitchDefaults.colors(
    checkedThumbColor = MaterialTheme.colorScheme.surface,
    checkedTrackColor = checkedColor,
    uncheckedThumbColor = MaterialTheme.colorScheme.outline,
    uncheckedTrackColor = MaterialTheme.colorScheme.surfaceVariant,
    disabledCheckedThumbColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.32f),
    disabledCheckedTrackColor = MaterialTheme.colorScheme.surfaceVariant,
    disabledUncheckedThumbColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.24f),
    disabledUncheckedTrackColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.50f),
  )
}

@Composable
private fun optionalPackBorderColor(pack: LifeLoadOptionalPackMetadata, enabled: Boolean) =
  when {
    enabled && pack.sensitive -> MaterialTheme.colorScheme.tertiary.copy(alpha = 0.58f)
    enabled -> MaterialTheme.colorScheme.primary.copy(alpha = 0.52f)
    pack.sensitive -> MaterialTheme.colorScheme.tertiary.copy(alpha = 0.28f)
    else -> MaterialTheme.colorScheme.outline.copy(alpha = 0.24f)
  }
