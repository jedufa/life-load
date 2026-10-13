package com.life.lifeload.domain

import org.json.JSONArray
import org.json.JSONObject

data class LifeLoadProfileFeatureFlags(
  val profileSetupEnabled: Boolean = false,
  val onboardingEnabled: Boolean = false,
  val profileDrivenCheckInEnabled: Boolean = false,
  val devCompatibilityMode: Boolean = false,
)

data class LifeLoadSignalMetadata(
  val id: String,
  val legacyFieldKey: String?,
  val label: String,
  val scaleType: String,
  val sensitive: Boolean = false,
)

data class LifeLoadOptionalPackMetadata(
  val id: String,
  val name: String,
  val description: String,
  val signalIds: List<String>,
  val sensitive: Boolean,
  val requiresExplicitOptIn: Boolean,
  val defaultEnabled: Boolean,
)

data class LifeLoadProfileTemplateMetadata(
  val id: String,
  val name: String,
  val publicName: String,
  val description: String,
  val visibleSignalIds: List<String>,
  val optionalSignalIds: List<String>,
  val hiddenSignalIds: List<String>,
  val disabledSignalIds: List<String>,
  val requiredForConfidenceSignalIds: List<String>,
  val allowedOptionalPackIds: List<String>,
  val maxActiveSignals: Int,
  val version: Int = 1,
  val publicChoice: Boolean = true,
  val devChoice: Boolean = true,
)

data class LifeLoadSelectedProfileConfig(
  val activeProfileId: String = "personal_legacy",
  val templateVersion: Int = 1,
  val enabledSignalIds: List<String> = emptyList(),
  val optionalSignalIds: List<String> = emptyList(),
  val hiddenSignalIds: List<String> = emptyList(),
  val disabledSignalIds: List<String> = emptyList(),
  val requiredForConfidenceSignalIds: List<String> = emptyList(),
  val optionalPackIds: List<String> = emptyList(),
  val userAddedSignalIds: List<String> = emptyList(),
  val userOverriddenSignalIds: List<String> = emptyList(),
  val guidanceBridgePolicyId: String? = null,
  val defaultFormulaModifierId: String? = null,
  val maxActiveSignals: Int = 8,
) {
  fun toJson(): JSONObject =
    JSONObject()
      .put("active_profile_id", activeProfileId)
      .put("template_version", templateVersion)
      .put("enabled_signal_ids", JSONArray(enabledSignalIds))
      .put("optional_signal_ids", JSONArray(optionalSignalIds))
      .put("hidden_signal_ids", JSONArray(hiddenSignalIds))
      .put("disabled_signal_ids", JSONArray(disabledSignalIds))
      .put("required_for_confidence_signal_ids", JSONArray(requiredForConfidenceSignalIds))
      .put("optional_pack_ids", JSONArray(optionalPackIds))
      .put("user_added_signal_ids", JSONArray(userAddedSignalIds))
      .put("user_overridden_signal_ids", JSONArray(userOverriddenSignalIds))
      .put("guidance_bridge_policy_id", guidanceBridgePolicyId ?: JSONObject.NULL)
      .put("default_formula_modifier_id", defaultFormulaModifierId ?: JSONObject.NULL)
      .put("max_active_signals", maxActiveSignals)

  companion object {
    fun fromJson(json: JSONObject): LifeLoadSelectedProfileConfig =
      LifeLoadSelectedProfileConfig(
        activeProfileId = json.optString("active_profile_id", "personal_legacy"),
        templateVersion = json.optInt("template_version", 1),
        enabledSignalIds = json.optJSONArray("enabled_signal_ids").toStringList(),
        optionalSignalIds = json.optJSONArray("optional_signal_ids").toStringList(),
        hiddenSignalIds = json.optJSONArray("hidden_signal_ids").toStringList(),
        disabledSignalIds = json.optJSONArray("disabled_signal_ids").toStringList(),
        requiredForConfidenceSignalIds = json.optJSONArray("required_for_confidence_signal_ids").toStringList(),
        optionalPackIds = json.optJSONArray("optional_pack_ids").toStringList(),
        userAddedSignalIds = json.optJSONArray("user_added_signal_ids").toStringList(),
        userOverriddenSignalIds = json.optJSONArray("user_overridden_signal_ids").toStringList(),
        guidanceBridgePolicyId = json.optNullableString("guidance_bridge_policy_id"),
        defaultFormulaModifierId = json.optNullableString("default_formula_modifier_id"),
        maxActiveSignals = json.optInt("max_active_signals", 8),
      )
  }
}

data class LifeLoadProfileSetupState(
  val selectedConfig: LifeLoadSelectedProfileConfig = LifeLoadProfileCatalog.defaultSelectedProfileConfig(),
  val optionalPackIds: Set<String> = emptySet(),
  val message: String = "",
)

data class LifeLoadRenderableProfileField(
  val signalId: String,
  val legacyFieldKey: String?,
  val label: String,
  val scaleType: String,
  val requiredForConfidence: Boolean,
  val sensitive: Boolean,
)

data class LifeLoadProfileDraftValue(
  val signalId: String,
  val value: Any?,
  val isPresent: Boolean,
  val source: String = "profile_driven_flagged_path",
)

data class LifeLoadProfileDraftState(
  val profileId: String,
  val valuesBySignalId: Map<String, LifeLoadProfileDraftValue> = emptyMap(),
) {
  fun update(signalId: String, value: Any?): LifeLoadProfileDraftState =
    copy(
      valuesBySignalId = valuesBySignalId + (
        signalId to LifeLoadProfileDraftValue(
          signalId = signalId,
          value = value,
          isPresent = value != null,
        )
        ),
    )

  fun clear(signalId: String): LifeLoadProfileDraftState =
    copy(valuesBySignalId = valuesBySignalId - signalId)
}

enum class LifeLoadBetaGuidanceLabel(val displayName: String) {
  PUSH("Push"),
  MAINTAIN("Maintain"),
  RECOVER("Recover"),
  SIMPLIFY("Simplify"),
  PROTECT_SLEEP("Protect Sleep"),
}

data class LifeLoadBetaGuidanceCardState(
  val label: LifeLoadBetaGuidanceLabel,
  val rationale: String,
  val topDrivers: List<String>,
  val recentChange: String? = null,
  val primaryAction: String,
  val confidenceNote: String,
  val missingSignalLabels: List<String> = emptyList(),
  val whyDetails: List<String> = emptyList(),
)

data class LifeLoadProductionBridgeInput(
  val key: String,
  val value: Any,
  val sourceSignalIds: List<String>,
)

data class LifeLoadProductionBridgeSnapshot(
  val activeProfileId: String,
  val inputs: Map<String, LifeLoadProductionBridgeInput>,
  val presentSignalValues: Map<String, Any>,
  val dataConfidence: Double,
  val missingRequiredSignalIds: List<String>,
  val inertUnknownSignalIds: List<String>,
  val optionalPackIds: List<String>,
)

data class LifeLoadProductionGuidanceModel(
  val label: LifeLoadBetaGuidanceLabel,
  val driverKeys: List<String>,
  val actionKey: String,
  val confidence: String,
  val missingSignalIds: List<String>,
  val bridgeInputKeys: Set<String>,
)

object LifeLoadProfileCatalog {
  val forbiddenPublicTerms = setOf(
    "addiction",
    "bulimia",
    "eating disorder",
    "relapse",
    "treatment",
    "diagnosis",
    "disorder",
    "failure",
    "failed",
    "shame",
  )

  val signals: Map<String, LifeLoadSignalMetadata> = linkedMapOf(
    "core.sleep_ok" to LifeLoadSignalMetadata("core.sleep_ok", "sleep_ok", "Sleep on time", "boolean"),
    "core.nutrition_ok" to LifeLoadSignalMetadata("core.nutrition_ok", "nutrition_ok", "Nutrition clean", "boolean"),
    "mental.stress" to LifeLoadSignalMetadata("mental.stress", "stress", "Stress", "ordinal_0_10", sensitive = true),
    "energy.energy" to LifeLoadSignalMetadata("energy.energy", "energy", "Energy", "ordinal_0_10"),
    "mood.mood" to LifeLoadSignalMetadata("mood.mood", "mood", "Mood", "ordinal_0_10", sensitive = true),
    "recovery.shutdown_done" to LifeLoadSignalMetadata("recovery.shutdown_done", "shutdown_done", "Shutdown done", "boolean"),
    "recovery.decompression_done" to LifeLoadSignalMetadata("recovery.decompression_done", "decompression_done", "Decompression done", "boolean"),
    "recovery.after_work_decompression_done" to LifeLoadSignalMetadata("recovery.after_work_decompression_done", "after_work_decompression_done", "After-work decompression", "boolean"),
    "work.work_intensity" to LifeLoadSignalMetadata("work.work_intensity", "work_intensity", "Work intensity", "enum"),
    "work.home_office" to LifeLoadSignalMetadata("work.home_office", "home_office", "Home office", "boolean"),
    "work.project_overrun" to LifeLoadSignalMetadata("work.project_overrun", "project_overrun", "Project overrun", "boolean", sensitive = true),
    "training.primary_activity_type" to LifeLoadSignalMetadata("training.primary_activity_type", "primary_activity_type", "Primary activity type", "enum"),
    "training.activity_duration_min" to LifeLoadSignalMetadata("training.activity_duration_min", "activity_duration_min", "Activity duration minutes", "duration_minutes"),
    "training.rehab_done" to LifeLoadSignalMetadata("training.rehab_done", "rehab_done", "Rehab done", "boolean"),
    "body.migraine_warning" to LifeLoadSignalMetadata("body.migraine_warning", "migraine_warning", "Migraine warning", "boolean", sensitive = true),
    "body.foot_pain" to LifeLoadSignalMetadata("body.foot_pain", "foot_pain", "Foot pain", "ordinal_0_10", sensitive = true),
    "body.shoulder_pain" to LifeLoadSignalMetadata("body.shoulder_pain", "shoulder_pain", "Shoulder pain", "ordinal_0_10", sensitive = true),
    "nutrition.alcohol" to LifeLoadSignalMetadata("nutrition.alcohol", "alcohol", "Alcohol", "enum", sensitive = true),
    "nutrition.binge" to LifeLoadSignalMetadata("nutrition.binge", "binge", "Eating episode", "boolean", sensitive = true),
    "evening.phone_after_21" to LifeLoadSignalMetadata("evening.phone_after_21", "phone_after_21", "Phone after 21:00", "boolean", sensitive = true),
    "evening.evening_chain_broken" to LifeLoadSignalMetadata("evening.evening_chain_broken", "evening_chain_broken", "Evening chain broken", "boolean", sensitive = true),
    "relationship.family_stress" to LifeLoadSignalMetadata("relationship.family_stress", "family_stress", "Family stress", "ordinal_0_10", sensitive = true),
    "relationship.wife_conflict_count" to LifeLoadSignalMetadata("relationship.wife_conflict_count", "wife_conflict_count", "Relationship conflict count", "bounded_int", sensitive = true),
    "relationship.wife_conflict_school" to LifeLoadSignalMetadata("relationship.wife_conflict_school", "wife_conflict_school", "School conflict", "boolean", sensitive = true),
    "relationship.wife_conflict_chores" to LifeLoadSignalMetadata("relationship.wife_conflict_chores", "wife_conflict_chores", "Chores conflict", "boolean", sensitive = true),
    "relationship.wife_conflict_other" to LifeLoadSignalMetadata("relationship.wife_conflict_other", "wife_conflict_other", "Other relationship conflict", "boolean", sensitive = true),
    "caregiving.alone_home" to LifeLoadSignalMetadata("caregiving.alone_home", "alone_home", "Alone home", "boolean", sensitive = true),
    "caregiving.homework_done" to LifeLoadSignalMetadata("caregiving.homework_done", "homework_done", "Homework done", "boolean", sensitive = true),
    "caregiving.homework_status" to LifeLoadSignalMetadata("caregiving.homework_status", "homework_status", "Homework status", "enum", sensitive = true),
    "stimulant.coffee_cups" to LifeLoadSignalMetadata("stimulant.coffee_cups", "coffee_cups", "Coffee cups", "bounded_int"),
  )

  val optionalPacks: Map<String, LifeLoadOptionalPackMetadata> = linkedMapOf(
    "life_load_pack" to LifeLoadOptionalPackMetadata(
      id = "life_load_pack",
      name = "Life load pack",
      description = "Adds family, admin, schedule, and obligation pressure as real load.",
      signalIds = listOf("work.work_intensity", "work.project_overrun", "work.home_office", "relationship.family_stress"),
      sensitive = false,
      requiresExplicitOptIn = false,
      defaultEnabled = false,
    ),
    "pattern_awareness_pack" to LifeLoadOptionalPackMetadata(
      id = "pattern_awareness_pack",
      name = "Pattern awareness pack",
      description = "Private pattern awareness. Optional. Helps notice patterns that can make tomorrow harder.",
      signalIds = listOf("evening.phone_after_21", "evening.evening_chain_broken", "work.project_overrun"),
      sensitive = true,
      requiresExplicitOptIn = true,
      defaultEnabled = false,
    ),
  )

  val profiles: Map<String, LifeLoadProfileTemplateMetadata> = linkedMapOf(
    "personal_legacy" to LifeLoadProfileTemplateMetadata(
      id = "personal_legacy",
      name = "Personal legacy",
      publicName = "Personal Legacy",
      description = "The original fixed personal setup. For compatibility and migration review.",
      visibleSignalIds = signals.keys.toList(),
      optionalSignalIds = emptyList(),
      hiddenSignalIds = emptyList(),
      disabledSignalIds = emptyList(),
      requiredForConfidenceSignalIds = listOf("core.sleep_ok", "core.nutrition_ok", "mental.stress", "energy.energy"),
      allowedOptionalPackIds = listOf("life_load_pack", "pattern_awareness_pack"),
      maxActiveSignals = signals.size,
      publicChoice = false,
      devChoice = true,
    ),
    "general_balance" to LifeLoadProfileTemplateMetadata(
      id = "general_balance",
      name = "General balance",
      publicName = "General Balance",
      description = "Everyday balance across energy, stress, recovery, body status, and overall load.",
      visibleSignalIds = listOf("core.sleep_ok", "core.nutrition_ok", "mental.stress", "energy.energy", "mood.mood", "recovery.shutdown_done"),
      optionalSignalIds = listOf("recovery.decompression_done", "recovery.after_work_decompression_done"),
      hiddenSignalIds = emptyList(),
      disabledSignalIds = listOf(
        "body.foot_pain",
        "body.shoulder_pain",
        "relationship.wife_conflict_count",
        "relationship.wife_conflict_school",
        "relationship.wife_conflict_chores",
        "relationship.wife_conflict_other",
        "caregiving.homework_done",
        "caregiving.homework_status",
        "nutrition.alcohol",
        "nutrition.binge",
        "training.primary_activity_type",
      ),
      requiredForConfidenceSignalIds = listOf("core.sleep_ok", "core.nutrition_ok", "mental.stress", "energy.energy"),
      allowedOptionalPackIds = listOf("life_load_pack", "pattern_awareness_pack"),
      maxActiveSignals = 8,
    ),
    "work_stress" to LifeLoadProfileTemplateMetadata(
      id = "work_stress",
      name = "Work stress",
      publicName = "Work Stress",
      description = "Work pressure, focus drain, recovery breaks, and the risk of carrying work into the evening.",
      visibleSignalIds = listOf("core.sleep_ok", "core.nutrition_ok", "mental.stress", "energy.energy", "mood.mood", "work.work_intensity", "work.home_office"),
      optionalSignalIds = listOf("work.project_overrun", "evening.phone_after_21"),
      hiddenSignalIds = emptyList(),
      disabledSignalIds = listOf("body.foot_pain", "body.shoulder_pain", "relationship.wife_conflict_count", "caregiving.homework_done", "caregiving.homework_status"),
      requiredForConfidenceSignalIds = listOf("core.sleep_ok", "mental.stress", "energy.energy"),
      allowedOptionalPackIds = listOf("pattern_awareness_pack"),
      maxActiveSignals = 8,
    ),
    "training_recovery" to LifeLoadProfileTemplateMetadata(
      id = "training_recovery",
      name = "Training recovery",
      publicName = "Training Recovery",
      description = "Training load, soreness, energy, and recovery, with life stress included.",
      visibleSignalIds = listOf("core.sleep_ok", "core.nutrition_ok", "mental.stress", "energy.energy", "training.primary_activity_type", "training.activity_duration_min", "training.rehab_done"),
      optionalSignalIds = listOf("recovery.decompression_done", "body.migraine_warning"),
      hiddenSignalIds = listOf("body.foot_pain", "body.shoulder_pain"),
      disabledSignalIds = listOf("relationship.wife_conflict_count", "relationship.wife_conflict_school", "relationship.wife_conflict_chores", "relationship.wife_conflict_other", "caregiving.homework_done", "caregiving.homework_status", "nutrition.alcohol", "nutrition.binge"),
      requiredForConfidenceSignalIds = listOf("core.sleep_ok", "core.nutrition_ok", "mental.stress", "energy.energy", "training.primary_activity_type"),
      allowedOptionalPackIds = listOf("life_load_pack"),
      maxActiveSignals = 8,
    ),
    "body_signal_awareness" to LifeLoadProfileTemplateMetadata(
      id = "body_signal_awareness",
      name = "Body signal awareness",
      publicName = "Body Signal Awareness",
      description = "Track body signals like tension, soreness, discomfort, or headaches without fixed body-part assumptions.",
      visibleSignalIds = listOf("core.sleep_ok", "mental.stress", "energy.energy", "mood.mood"),
      optionalSignalIds = listOf("body.migraine_warning"),
      hiddenSignalIds = listOf("body.foot_pain", "body.shoulder_pain"),
      disabledSignalIds = listOf("relationship.wife_conflict_count", "relationship.wife_conflict_school", "relationship.wife_conflict_chores", "relationship.wife_conflict_other", "caregiving.homework_done", "caregiving.homework_status"),
      requiredForConfidenceSignalIds = listOf("core.sleep_ok", "mental.stress", "energy.energy"),
      allowedOptionalPackIds = listOf("life_load_pack"),
      maxActiveSignals = 8,
    ),
    "custom_stub" to LifeLoadProfileTemplateMetadata(
      id = "custom_stub",
      name = "Custom",
      publicName = "Custom",
      description = "Start small and choose the signals that matter most to you.",
      visibleSignalIds = listOf("core.sleep_ok", "mental.stress", "energy.energy"),
      optionalSignalIds = emptyList(),
      hiddenSignalIds = emptyList(),
      disabledSignalIds = emptyList(),
      requiredForConfidenceSignalIds = listOf("core.sleep_ok", "mental.stress", "energy.energy"),
      allowedOptionalPackIds = emptyList(),
      maxActiveSignals = 3,
    ),
  )

  fun defaultSelectedProfileConfig(): LifeLoadSelectedProfileConfig =
    buildSelectedProfileConfig("personal_legacy")

  fun buildSelectedProfileConfig(
    profileId: String,
    optionalPackIds: Set<String> = emptySet(),
    userAddedSignalIds: Set<String> = emptySet(),
  ): LifeLoadSelectedProfileConfig {
    val profile = profiles[profileId] ?: error("Unknown Life Load profile $profileId")
    val unallowedPacks = optionalPackIds - profile.allowedOptionalPackIds.toSet()
    require(unallowedPacks.isEmpty()) { "Optional pack(s) not allowed for $profileId: ${unallowedPacks.joinToString(", ")}" }
    val hiddenOrDisabled = (profile.hiddenSignalIds + profile.disabledSignalIds).toSet()
    val packSignalIds = optionalPackIds.flatMap { optionalPacks[it]?.signalIds.orEmpty() }
    val enabled = (profile.visibleSignalIds + packSignalIds + userAddedSignalIds)
      .filterNot { it in hiddenOrDisabled }
      .distinct()
      .take(profile.maxActiveSignals)
    return LifeLoadSelectedProfileConfig(
      activeProfileId = profile.id,
      templateVersion = profile.version,
      enabledSignalIds = enabled,
      optionalSignalIds = profile.optionalSignalIds,
      hiddenSignalIds = profile.hiddenSignalIds,
      disabledSignalIds = profile.disabledSignalIds,
      requiredForConfidenceSignalIds = profile.requiredForConfidenceSignalIds.filterNot { it in hiddenOrDisabled },
      optionalPackIds = optionalPackIds.sorted(),
      userAddedSignalIds = userAddedSignalIds.sorted(),
      guidanceBridgePolicyId = "${profile.id}_v0",
      defaultFormulaModifierId = null,
      maxActiveSignals = profile.maxActiveSignals,
    )
  }

  fun publicProfiles(flags: LifeLoadProfileFeatureFlags): List<LifeLoadProfileTemplateMetadata> =
    profiles.values.filter { profile ->
      profile.publicChoice || flags.devCompatibilityMode && profile.devChoice
    }

  fun devProfiles(): List<LifeLoadProfileTemplateMetadata> =
    profiles.values.filter { it.devChoice }

  fun renderableFields(config: LifeLoadSelectedProfileConfig): List<LifeLoadRenderableProfileField> {
    val inactive = (config.hiddenSignalIds + config.disabledSignalIds).toSet()
    return config.enabledSignalIds
      .filterNot { it in inactive }
      .mapNotNull { signalId ->
        signals[signalId]?.let { signal ->
          LifeLoadRenderableProfileField(
            signalId = signalId,
            legacyFieldKey = signal.legacyFieldKey,
            label = signal.label,
            scaleType = signal.scaleType,
            requiredForConfidence = signalId in config.requiredForConfidenceSignalIds,
            sensitive = signal.sensitive || config.optionalPackIds.any { packId ->
              optionalPacks[packId]?.let { pack -> pack.sensitive && signalId in pack.signalIds } == true
            },
          )
        }
      }
  }

  fun buildProductionGuidanceBridge(
    config: LifeLoadSelectedProfileConfig,
    draftState: LifeLoadProfileDraftState,
  ): LifeLoadProductionBridgeSnapshot {
    val inactiveSignalIds = (config.hiddenSignalIds + config.disabledSignalIds).toSet()
    val activeSignalIds = config.enabledSignalIds
      .filter { signalId -> signalId in signals && signalId !in inactiveSignalIds }
      .toSet()
    val presentValues = linkedMapOf<String, Any>()
    val inertUnknownSignalIds = mutableListOf<String>()
    draftState.valuesBySignalId.values.forEach { draftValue ->
      val signalId = draftValue.signalId
      if (signalId !in signals) {
        inertUnknownSignalIds += signalId
        return@forEach
      }
      if (signalId !in activeSignalIds || !draftValue.isPresent || !isPresentValue(draftValue.value)) {
        return@forEach
      }
      presentValues[signalId] = draftValue.value as Any
    }
    val requiredSignalIds = config.requiredForConfidenceSignalIds.filter { signalId ->
      signalId in signals && signalId !in inactiveSignalIds
    }
    val missingRequired = requiredSignalIds.filterNot { signalId -> signalId in presentValues }
    val confidence = if (requiredSignalIds.isEmpty()) {
      1.0
    } else {
      ((requiredSignalIds.size - missingRequired.size).toDouble() / requiredSignalIds.size).roundToTwo()
    }
    val inputs = bridgeInputsForValues(
      presentSignalValues = presentValues,
      patternPackEnabled = "pattern_awareness_pack" in config.optionalPackIds,
      personalLegacy = config.activeProfileId == "personal_legacy",
    ).toMutableMap()
    inputs["data_confidence"] = LifeLoadProductionBridgeInput(
      key = "data_confidence",
      value = confidence,
      sourceSignalIds = requiredSignalIds,
    )
    inputs["missing_required_signal_ids"] = LifeLoadProductionBridgeInput(
      key = "missing_required_signal_ids",
      value = missingRequired,
      sourceSignalIds = missingRequired,
    )
    inputs["active_profile_id"] = LifeLoadProductionBridgeInput(
      key = "active_profile_id",
      value = config.activeProfileId,
      sourceSignalIds = emptyList(),
    )
    return LifeLoadProductionBridgeSnapshot(
      activeProfileId = config.activeProfileId,
      inputs = inputs,
      presentSignalValues = presentValues,
      dataConfidence = confidence,
      missingRequiredSignalIds = missingRequired,
      inertUnknownSignalIds = inertUnknownSignalIds.distinct(),
      optionalPackIds = config.optionalPackIds,
    )
  }

  fun productionGuidanceModel(
    config: LifeLoadSelectedProfileConfig,
    draftState: LifeLoadProfileDraftState,
  ): LifeLoadProductionGuidanceModel {
    val snapshot = buildProductionGuidanceBridge(config, draftState)
    val bridgeKeys = snapshot.inputs.keys
    val presentValues = snapshot.presentSignalValues
    val confidence = if (snapshot.dataConfidence < 0.67 || presentValues.size <= 2) "limited" else "normal"
    val label = when {
      presentValues.isEmpty() -> LifeLoadBetaGuidanceLabel.MAINTAIN
      confidence == "limited" && daySeverity(presentValues) < 3 -> LifeLoadBetaGuidanceLabel.SIMPLIFY
      "private_pattern_active" in bridgeKeys && ("energy_low" in bridgeKeys || "recovery_low" in bridgeKeys) -> LifeLoadBetaGuidanceLabel.PROTECT_SLEEP
      "physical_load_high" in bridgeKeys && ("energy_low" in bridgeKeys || "recovery_low" in bridgeKeys) -> LifeLoadBetaGuidanceLabel.RECOVER
      "mental_load_high" in bridgeKeys && "energy_low" in bridgeKeys -> LifeLoadBetaGuidanceLabel.SIMPLIFY
      daySeverity(presentValues) >= 4 -> LifeLoadBetaGuidanceLabel.PROTECT_SLEEP
      daySeverity(presentValues) >= 3 -> LifeLoadBetaGuidanceLabel.SIMPLIFY
      "energy_good" in bridgeKeys && "recovery_good" in bridgeKeys -> LifeLoadBetaGuidanceLabel.PUSH
      else -> LifeLoadBetaGuidanceLabel.MAINTAIN
    }
    val drivers = driverKeysForBridge(snapshot, config.activeProfileId)
      .ifEmpty { if (confidence == "limited") listOf("missing_data") else listOf("recovery_steady") }
      .take(4)
    val actionKey = actionKeyForGuidance(label, config.activeProfileId, bridgeKeys)
    return LifeLoadProductionGuidanceModel(
      label = label,
      driverKeys = drivers,
      actionKey = if (presentValues.isEmpty()) "check_in_first" else actionKey,
      confidence = confidence,
      missingSignalIds = snapshot.missingRequiredSignalIds,
      bridgeInputKeys = bridgeKeys,
    )
  }
}

fun devProfileSelectorVisible(flags: LifeLoadProfileFeatureFlags): Boolean =
  flags.profileSetupEnabled && flags.devCompatibilityMode

fun onboardingVisibleForNewUser(flags: LifeLoadProfileFeatureFlags, hasExistingSelection: Boolean): Boolean =
  flags.onboardingEnabled && !hasExistingSelection

fun trackingSetupVisible(flags: LifeLoadProfileFeatureFlags): Boolean =
  flags.profileSetupEnabled

fun profileDrivenCheckInActive(flags: LifeLoadProfileFeatureFlags): Boolean =
  flags.profileDrivenCheckInEnabled

fun profileCopyHasForbiddenTerms(text: String): Boolean {
  val lower = text.lowercase()
  return LifeLoadProfileCatalog.forbiddenPublicTerms.any { it in lower }
}

fun profileCopyUsesInstructionLanguage(text: String): Boolean {
  val lower = text.lowercase()
  return listOf("you must", "you need to", "doctor should", "clinician should", "take medication").any { it in lower }
}

private fun JSONArray?.toStringList(): List<String> =
  if (this == null) emptyList() else List(length()) { index -> optString(index) }.filter(String::isNotBlank)

private fun JSONObject.optNullableString(key: String): String? =
  if (has(key) && !isNull(key)) optString(key) else null

private fun bridgeInputsForValues(
  presentSignalValues: Map<String, Any>,
  patternPackEnabled: Boolean,
  personalLegacy: Boolean,
): Map<String, LifeLoadProductionBridgeInput> {
  val inputs = linkedMapOf<String, LifeLoadProductionBridgeInput>()

  fun add(key: String, value: Any, signalIds: List<String>) {
    val existing = inputs[key]
    inputs[key] = LifeLoadProductionBridgeInput(
      key = key,
      value = value,
      sourceSignalIds = (existing?.sourceSignalIds.orEmpty() + signalIds).distinct(),
    )
  }

  when (presentSignalValues["core.sleep_ok"]) {
    true -> add("recovery_good", true, listOf("core.sleep_ok"))
    false -> add("recovery_low", true, listOf("core.sleep_ok"))
  }
  when (presentSignalValues["recovery.shutdown_done"]) {
    true -> {
      add("protective_behavior_present", true, listOf("recovery.shutdown_done"))
      add("recovery_good", true, listOf("recovery.shutdown_done"))
    }
    false -> {
      add("recovery_low", true, listOf("recovery.shutdown_done"))
      add("evening_boundary_broken", true, listOf("recovery.shutdown_done"))
    }
  }
  listOf("recovery.decompression_done", "recovery.after_work_decompression_done").forEach { signalId ->
    when (presentSignalValues[signalId]) {
      true -> add("protective_behavior_present", true, listOf(signalId))
      false -> add("evening_boundary_broken", true, listOf(signalId))
    }
  }

  val energy = presentSignalValues["energy.energy"].asIntOrNull()
  if (energy != null && energy <= 3) add("energy_low", true, listOf("energy.energy"))
  if (energy != null && energy >= 7) add("energy_good", true, listOf("energy.energy"))

  val stress = presentSignalValues["mental.stress"].asIntOrNull()
  val familyStress = presentSignalValues["relationship.family_stress"].asIntOrNull()
  val conflictCount = presentSignalValues["relationship.wife_conflict_count"].asIntOrNull()
  val mentalSignals = listOf(
    "mental.stress",
    "relationship.family_stress",
    "relationship.wife_conflict_count",
    "relationship.wife_conflict_school",
    "relationship.wife_conflict_chores",
    "relationship.wife_conflict_other",
    "caregiving.homework_done",
  ).filter { signalId -> signalId in presentSignalValues }
  if (
    stress != null && stress >= 7 ||
    familyStress != null && familyStress >= 7 ||
    conflictCount != null && conflictCount >= 1 ||
    presentSignalValues["relationship.wife_conflict_school"] == true ||
    presentSignalValues["relationship.wife_conflict_chores"] == true ||
    presentSignalValues["relationship.wife_conflict_other"] == true ||
    presentSignalValues["caregiving.homework_done"] == false
  ) {
    add("mental_load_high", true, mentalSignals)
  }

  val footPain = presentSignalValues["body.foot_pain"].asIntOrNull()
  val shoulderPain = presentSignalValues["body.shoulder_pain"].asIntOrNull()
  if (
    footPain != null && footPain >= 5 ||
    shoulderPain != null && shoulderPain >= 5 ||
    presentSignalValues["body.migraine_warning"] == true
  ) {
    add(
      "body_signal_high",
      true,
      listOf("body.foot_pain", "body.shoulder_pain", "body.migraine_warning").filter { signalId ->
        signalId in presentSignalValues
      },
    )
  }

  val duration = presentSignalValues["training.activity_duration_min"].asIntOrNull()
  val activityType = presentSignalValues["training.primary_activity_type"]?.toString()?.trim()?.lowercase().orEmpty()
  if (activityType in setOf("crossfit", "run") || duration != null && duration >= 45) {
    add(
      "physical_load_high",
      true,
      listOf("training.primary_activity_type", "training.activity_duration_min").filter { signalId ->
        signalId in presentSignalValues
      },
    )
  }

  val eveningSignals = listOf("evening.phone_after_21", "work.project_overrun", "evening.evening_chain_broken")
    .filter { signalId -> presentSignalValues[signalId] == true }
  if (eveningSignals.isNotEmpty()) add("evening_boundary_broken", true, eveningSignals)

  val patternSignals = listOf(
    "nutrition.alcohol",
    "nutrition.binge",
    "evening.phone_after_21",
    "work.project_overrun",
    "evening.evening_chain_broken",
  ).filter { signalId -> patternValueActive(presentSignalValues[signalId]) }
  if ((personalLegacy || patternPackEnabled) && patternSignals.isNotEmpty()) {
    add("private_pattern_active", true, patternSignals)
  }

  val highRiskKeys = setOf(
    "mental_load_high",
    "body_signal_high",
    "physical_load_high",
    "evening_boundary_broken",
    "private_pattern_active",
    "energy_low",
    "recovery_low",
  )
  val presentHighRiskKeys = highRiskKeys.intersect(inputs.keys)
  if (presentHighRiskKeys.size >= 2) {
    add("life_load_high", true, presentHighRiskKeys.flatMap { key -> inputs[key]?.sourceSignalIds.orEmpty() }.distinct())
  }
  return inputs
}

private fun driverKeysForBridge(snapshot: LifeLoadProductionBridgeSnapshot, profileId: String): List<String> {
  val keys = snapshot.inputs.keys
  val drivers = mutableListOf<String>()
  if ("mental_load_high" in keys) drivers += if (profileId == "work_stress") "work_pressure" else "stress"
  if ("energy_low" in keys) drivers += "energy"
  if ("recovery_low" in keys) drivers += "sleep"
  if ("private_pattern_active" in keys) drivers += if (profileId == "work_stress") "work_spillover" else "private_pattern"
  if ("evening_boundary_broken" in keys) drivers += "decompression"
  if ("physical_load_high" in keys) drivers += "training_load"
  if ("body_signal_high" in keys) drivers += "body_signal"
  if ("protective_behavior_present" in keys && "sleep" !in drivers && "decompression" !in drivers) {
    drivers += "protective_behavior"
  }
  if ("energy_good" in keys && drivers.size < 2) drivers += "energy"
  if ("recovery_good" in keys && drivers.size < 2) drivers += "recovery"
  return drivers.distinct()
}

private fun actionKeyForGuidance(
  label: LifeLoadBetaGuidanceLabel,
  profileId: String,
  bridgeKeys: Set<String>,
): String =
  when (label) {
    LifeLoadBetaGuidanceLabel.PROTECT_SLEEP ->
      if ("private_pattern_active" in bridgeKeys) "protect_private_pattern" else "protect_sleep"
    LifeLoadBetaGuidanceLabel.RECOVER ->
      when {
        "body_signal_high" in bridgeKeys -> "recover_body_signal"
        "physical_load_high" in bridgeKeys -> "keep_training_easy"
        else -> "take_recovery_break"
      }
    LifeLoadBetaGuidanceLabel.SIMPLIFY ->
      when {
        profileId == "work_stress" -> "reduce_optional_work"
        "evening_boundary_broken" in bridgeKeys -> "simplify_evening"
        profileId == "body_signal_awareness" -> "recover_body_signal"
        else -> "avoid_extra_commitment"
      }
    LifeLoadBetaGuidanceLabel.PUSH -> "use_good_capacity"
    LifeLoadBetaGuidanceLabel.MAINTAIN ->
      if ("recovery_good" in bridgeKeys || "protective_behavior_present" in bridgeKeys) {
        "maintain_recovery_protected"
      } else {
        "maintain_stable"
      }
  }

private fun daySeverity(presentValues: Map<String, Any>): Int {
  var severity = 0
  if (presentValues["core.sleep_ok"] == false) severity += 1
  val stress = presentValues["mental.stress"].asIntOrNull()
  val energy = presentValues["energy.energy"].asIntOrNull()
  if (stress != null && stress >= 7) severity += 1
  if (energy != null && energy <= 3) severity += 1
  if (presentValues["body.migraine_warning"] == true) severity += 1
  if (presentValues["evening.phone_after_21"] == true || presentValues["work.project_overrun"] == true) severity += 1
  return severity
}

private fun Any?.asIntOrNull(): Int? =
  when (this) {
    is Int -> this
    is Number -> toInt()
    is String -> toIntOrNull()
    else -> null
  }

private fun isPresentValue(value: Any?): Boolean =
  when (value) {
    null -> false
    is String -> value.trim().isNotEmpty() && value.trim().lowercase() != "unknown"
    is Collection<*> -> value.isNotEmpty()
    is Map<*, *> -> value.isNotEmpty()
    else -> true
  }

private fun patternValueActive(value: Any?): Boolean =
  when (value) {
    null -> false
    is Boolean -> value
    is Number -> value.toDouble() > 0.0
    is String -> value.trim().lowercase() !in setOf("", "0", "false", "no", "none", "unknown")
    else -> true
  }

private fun Double.roundToTwo(): Double =
  kotlin.math.round(this * 100.0) / 100.0
