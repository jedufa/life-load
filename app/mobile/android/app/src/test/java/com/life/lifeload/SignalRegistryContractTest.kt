package com.life.lifeload

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class SignalRegistryContractTest {
  @Test
  fun registryContractJsonIsReadable() {
    val registry = registryContractJson()

    assertEquals("life_load_signal_registry_contract_v1", registry.getString("schema_version"))
    assertEquals("backend.life_load.signal_registry", registry.getString("generated_from"))
    assertTrue(registry.signals().isNotEmpty())
    assertTrue(registry.profiles().isNotEmpty())
    assertTrue(registry.optionalPacks().isNotEmpty())
    assertTrue(registry.influencePolicies().isNotEmpty())
  }

  @Test
  fun legacyFieldKeysAreRecognizedByAndroidContractGuard() {
    val unrecognized = registryContractJson()
      .signals()
      .mapNotNull { it.nullableString("legacy_field_key") }
      .filterNot { it in androidLifeLoadEntryLegacyFieldKeys }

    assertEquals(emptyList<String>(), unrecognized)
  }

  @Test
  fun knownCurrentLegacyFieldsArePresent() {
    val legacyFieldKeys = registryContractJson()
      .signals()
      .mapNotNull { it.nullableString("legacy_field_key") }
      .toSet()
    val representedExpectedKeys = expectedCurrentLegacyFields.map { legacyFieldAliases[it] ?: it }.toSet()

    assertTrue(
      "Missing expected legacy keys: ${representedExpectedKeys - legacyFieldKeys}",
      legacyFieldKeys.containsAll(representedExpectedKeys),
    )
  }

  @Test
  fun personalLegacyProfileExists() {
    val profile = registryContractJson()
      .profiles()
      .firstOrNull { it.getString("id") == "personal_legacy" }

    assertNotNull(profile)
  }

  @Test
  fun expectedProfileTemplatesExistAndAreUnique() {
    val profileIds = registryContractJson().profiles().map { it.getString("id") }

    assertEquals(profileIds.toSet().size, profileIds.size)
    assertTrue(profileIds.containsAll(expectedProfileIds))
  }

  @Test
  fun personalLegacyProfileReferencesOnlyExistingSignalIds() {
    val registry = registryContractJson()
    val signalIds = registry.signals().map { it.getString("id") }.toSet()
    val profile = registry.profiles().first { it.getString("id") == "personal_legacy" }
    val unknownProfileSignals = profile.getJSONArray("signal_ids").strings().filterNot { it in signalIds }

    assertEquals(emptyList<String>(), unknownProfileSignals)
  }

  @Test
  fun personalLegacyProfilePreservesBehaviorDrivingFields() {
    val registry = registryContractJson()
    val profile = registry.profiles().first { it.getString("id") == "personal_legacy" }
    val legacyKeysBySignalId = registry.signals().associate {
      it.getString("id") to it.nullableString("legacy_field_key")
    }
    val profileLegacyKeys = profile.getJSONArray("signal_ids")
      .strings()
      .mapNotNull { legacyKeysBySignalId[it] }
      .toSet()

    assertTrue(
      "Missing personal legacy fields: ${personalLegacyBehaviorFields - profileLegacyKeys}",
      profileLegacyKeys.containsAll(personalLegacyBehaviorFields),
    )
  }

  @Test
  fun generalBalanceDoesNotMarkPersonalFieldsVisibleOrRequired() {
    val registry = registryContractJson()
    val profile = registry.profiles().first { it.getString("id") == "general_balance" }
    val legacyKeysBySignalId = registry.signals().associate {
      it.getString("id") to it.nullableString("legacy_field_key")
    }
    val visibleOrRequiredLegacyKeys = (
      profile.getJSONArray("visible_signal_ids").strings() +
        profile.getJSONArray("required_for_confidence_signal_ids").strings()
      )
      .mapNotNull { legacyKeysBySignalId[it] }
      .toSet()

    assertTrue(generalBalancePersonalFields.intersect(visibleOrRequiredLegacyKeys).isEmpty())
  }

  @Test
  fun allProfilesReferenceOnlyExistingSignalIds() {
    val registry = registryContractJson()
    val signalIds = registry.signals().map { it.getString("id") }.toSet()
    val unknownProfileSignals = registry.profiles().flatMap { profile ->
      profile.getJSONArray("signal_ids")
        .strings()
        .filterNot { it in signalIds }
        .map { "${profile.getString("id")}:$it" }
    }

    assertEquals(emptyList<String>(), unknownProfileSignals)
  }

  @Test
  fun optionalPacksReferenceOnlyExistingSignalIds() {
    val registry = registryContractJson()
    val signalIds = registry.signals().map { it.getString("id") }.toSet()
    val unknownPackSignals = registry.optionalPacks().flatMap { pack ->
      pack.getJSONArray("signal_ids")
        .strings()
        .filterNot { it in signalIds }
        .map { "${pack.getString("id")}:$it" }
    }

    assertEquals(emptyList<String>(), unknownPackSignals)
  }

  @Test
  fun optionalPackTemplatesExistAndAreUnique() {
    val packIds = registryContractJson().optionalPacks().map { it.getString("id") }

    assertEquals(packIds.toSet().size, packIds.size)
    assertTrue(packIds.containsAll(expectedOptionalPackIds))
  }

  @Test
  fun patternAwarenessPackIsSensitiveOptInAndNotDefaultEnabled() {
    val pack = registryContractJson().optionalPacks().first { it.getString("id") == "pattern_awareness_pack" }

    assertTrue(pack.getBoolean("sensitive"))
    assertTrue(pack.getBoolean("requires_explicit_opt_in"))
    assertFalse(pack.getBoolean("default_enabled"))
  }

  @Test
  fun patternAwarenessPackAvoidsClinicalPublicLabels() {
    val pack = registryContractJson().optionalPacks().first { it.getString("id") == "pattern_awareness_pack" }
    val searchable = listOf(
      pack.getString("name"),
      pack.getString("description"),
    )
      .plus(pack.getJSONArray("placeholder_signal_ids").strings())
      .joinToString(" ")
      .lowercase()
    val forbiddenMatches = forbiddenClinicalPublicLabels.filter { it in searchable }

    assertEquals(emptyList<String>(), forbiddenMatches)
  }

  @Test
  fun influencePoliciesReferenceOnlyExistingSignalsAndProfiles() {
    val registry = registryContractJson()
    val signalIds = registry.signals().map { it.getString("id") }.toSet()
    val profileIds = registry.profiles().map { it.getString("id") }.toSet()
    val unknownPolicySignals = registry.influencePolicies()
      .map { it.getString("signal_id") }
      .filterNot { it in signalIds }
    val unknownPolicyProfiles = registry.influencePolicies().flatMap { policy ->
      policy.getJSONArray("applies_to_profile_ids")
        .strings()
        .filterNot { it in profileIds }
        .map { "${policy.getString("signal_id")}:$it" }
    }

    assertEquals(emptyList<String>(), unknownPolicySignals)
    assertEquals(emptyList<String>(), unknownPolicyProfiles)
  }

  @Test
  fun influencePolicyEnumValuesAreAllowed() {
    val invalidGuidanceEffects = registryContractJson().influencePolicies()
      .map { it.getString("guidance_effect") }
      .filterNot { it in allowedGuidanceEffects }
    val invalidSensitivities = registryContractJson().influencePolicies()
      .map { it.getString("sensitivity_class") }
      .filterNot { it in allowedSensitivityClasses }
    val invalidBoundaries = registryContractJson().influencePolicies()
      .map { it.getString("clinical_boundary") }
      .filterNot { it in allowedClinicalBoundaries }

    assertEquals(emptyList<String>(), invalidGuidanceEffects)
    assertEquals(emptyList<String>(), invalidSensitivities)
    assertEquals(emptyList<String>(), invalidBoundaries)
  }

  @Test
  fun sensitivePatternPoliciesArePrivateAndTreatmentSafe() {
    val registry = registryContractJson()
    val patternSignalIds = registry.optionalPacks()
      .first { it.getString("id") == "pattern_awareness_pack" }
      .getJSONArray("signal_ids")
      .strings()
      .toSet()
    val policiesBySignalId = registry.influencePolicies().associateBy { it.getString("signal_id") }
    val invalidSensitivity = patternSignalIds
      .mapNotNull { policiesBySignalId[it] }
      .filterNot { it.getString("sensitivity_class") in setOf("private", "private_plus") }
      .map { it.getString("signal_id") }
    val invalidBoundary = patternSignalIds
      .mapNotNull { policiesBySignalId[it] }
      .filterNot { it.getString("clinical_boundary") in setOf("never_suggest_treatment", "out_of_scope_if_urgent") }
      .map { it.getString("signal_id") }

    assertEquals(emptyList<String>(), invalidSensitivity)
    assertEquals(emptyList<String>(), invalidBoundary)
  }

  @Test
  fun contractCheckIsSnapshotOnly() {
    val contractFile = registryContractFile()

    assertTrue(contractFile.isFile)
    assertFalse(
      "Android must not consume the Phase 2A registry at runtime.",
      contractFile.path.contains("/src/main/"),
    )
  }

  @Test
  fun productionRuntimeDoesNotReferenceContractOnlyMetadata() {
    val productionFiles = productionKotlinFiles()
    val forbiddenReferences = listOf(
      "life_load_signal_registry.json",
      "optional_packs",
      "influence_policies",
      "guidance_effect",
      "clinical_boundary",
      "selected_profile_config",
    )
    val matches = productionFiles.flatMap { file ->
      val text = file.readText(Charsets.UTF_8)
      forbiddenReferences
        .filter { it in text }
        .map { "${file.relativeTo(repoRoot())}:$it" }
    }

    assertEquals(emptyList<String>(), matches)
  }

  private fun registryContractJson(): JSONObject =
    JSONObject(registryContractFile().readText(Charsets.UTF_8))

  private fun registryContractFile(): File {
    val relativePath = "app/shared/contracts/life_load_signal_registry.json"
    val userDir = System.getProperty("user.dir") ?: "."
    var current: File? = File(userDir).canonicalFile
    while (current != null) {
      val candidate = File(current, relativePath)
      if (candidate.isFile) return candidate
      current = current.parentFile
    }
    throw AssertionError("Could not find $relativePath from $userDir")
  }

  private fun repoRoot(): File {
    val contractsDir = registryContractFile().parentFile
      ?: throw AssertionError("Shared contract file has no parent directory")
    val sharedDir = contractsDir.parentFile
      ?: throw AssertionError("Shared contracts directory has no parent directory")
    val appDir = sharedDir.parentFile
      ?: throw AssertionError("Shared directory has no app parent")
    return appDir.parentFile
      ?: throw AssertionError("App directory has no repository parent")
  }

  private fun productionKotlinFiles(): List<File> {
    val sourceRoot = File(repoRoot(), "app/mobile/android/app/src/main/java")
    return sourceRoot.walkTopDown()
      .filter { it.isFile && it.extension == "kt" }
      .filterNot { it.invariantSeparatorsPath.endsWith("/data/local/LifeLoadLocalStore.kt") }
      .toList()
  }

  private fun JSONObject.signals(): List<JSONObject> = getJSONArray("signals").objects()

  private fun JSONObject.profiles(): List<JSONObject> = getJSONArray("profiles").objects()

  private fun JSONObject.optionalPacks(): List<JSONObject> = getJSONArray("optional_packs").objects()

  private fun JSONObject.influencePolicies(): List<JSONObject> = getJSONArray("influence_policies").objects()

  private fun JSONObject.nullableString(name: String): String? =
    if (isNull(name)) null else getString(name)

  private fun JSONArray.objects(): List<JSONObject> =
    (0 until length()).map { index -> getJSONObject(index) }

  private fun JSONArray.strings(): List<String> =
    (0 until length()).map { index -> getString(index) }

  companion object {
    // Test-only guard for Android's current fixed LifeLoadEntry JSON keys. This
    // is not a runtime registry mirror and should not drive UI or persistence.
    private val androidLifeLoadEntryLegacyFieldKeys = setOf(
      "date",
      "diary_text",
      "diary_summary",
      "tags",
      "sleep_ok",
      "nutrition_ok",
      "alcohol",
      "binge",
      "mood",
      "stress",
      "energy",
      "coffee_cups",
      "foot_pain",
      "shoulder_pain",
      "migraine_warning",
      "decompression_done",
      "after_work_decompression_done",
      "evening_chain_broken",
      "shutdown_done",
      "phone_after_21",
      "project_overrun",
      "primary_activity_type",
      "activity_types",
      "activity_duration_min",
      "rehab_done",
      "other_symptoms",
      "work_intensity",
      "family_stress",
      "wife_conflict_count",
      "wife_conflict_school",
      "wife_conflict_chores",
      "wife_conflict_other",
      "home_office",
      "alone_home",
      "homework_done",
      "homework_status",
    )

    private val expectedCurrentLegacyFields = setOf(
      "sleep_ok",
      "nutrition_ok",
      "alcohol",
      "binge",
      "mood",
      "stress",
      "energy",
      "coffee_cups",
      "foot_pain",
      "shoulder_pain",
      "migraine_warning",
      "decompression_done",
      "after_work_decompression",
      "shutdown_done",
      "phone_after_21",
      "project_overrun",
      "evening_chain_broken",
      "primary_activity_type",
      "activity_duration_min",
      "work_intensity",
      "home_office",
      "wife_conflict_count",
      "wife_conflict_school",
      "wife_conflict_chores",
      "wife_conflict_other",
      "alone_home",
      "homework_done",
      "homework_status",
    )

    private val legacyFieldAliases = mapOf(
      "after_work_decompression" to "after_work_decompression_done",
    )

    private val expectedProfileIds = setOf(
      "personal_legacy",
      "general_balance",
      "work_stress",
      "training_recovery",
      "body_signal_awareness",
      "custom_stub",
    )

    private val expectedOptionalPackIds = setOf(
      "life_load_pack",
      "pattern_awareness_pack",
    )

    private val personalLegacyBehaviorFields = setOf(
      "foot_pain",
      "shoulder_pain",
      "migraine_warning",
      "alcohol",
      "binge",
      "phone_after_21",
      "project_overrun",
      "primary_activity_type",
      "wife_conflict_count",
      "wife_conflict_school",
      "wife_conflict_chores",
      "wife_conflict_other",
      "alone_home",
      "homework_done",
      "homework_status",
    )

    private val generalBalancePersonalFields = setOf(
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

    private val forbiddenClinicalPublicLabels = setOf(
      "addiction",
      "bulimia",
      "eating disorder",
      "relapse",
      "treatment",
      "diagnosis",
      "disorder",
    )

    private val allowedGuidanceEffects = setOf(
      "track_only",
      "light",
      "normal",
      "strong",
      "guardrail",
    )

    private val allowedSensitivityClasses = setOf(
      "normal",
      "private",
      "private_plus",
    )

    private val allowedClinicalBoundaries = setOf(
      "wellness_only",
      "out_of_scope_if_urgent",
      "never_suggest_treatment",
    )
  }
}
