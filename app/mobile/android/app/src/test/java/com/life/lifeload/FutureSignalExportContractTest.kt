package com.life.lifeload

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class FutureSignalExportContractTest {
  @Test
  fun future_bundle_shape_parses_in_android_test_only() {
    val bundle = parseFutureBundle()

    assertEquals("life_load_export_v_next", bundle.version)
    assertEquals("personal_legacy", bundle.profileTemplate.getString("id"))
    assertTrue(bundle.signalDefinitions.isNotEmpty())
    assertTrue(bundle.signalEntries.isNotEmpty())
    assertTrue(bundle.optionalPacks.isNotEmpty())
    assertTrue(bundle.influencePolicies.isNotEmpty())
  }

  @Test
  fun fixed_entries_remain_present_as_compatibility_truth() {
    val bundle = parseFutureBundle()

    assertTrue(bundle.entries.isNotEmpty())
    assertEquals("2026-05-17", bundle.entries.single().getString("date"))
    assertEquals(true, bundle.entries.single().getBoolean("sleep_ok"))
    assertEquals(false, bundle.entries.single().getBoolean("phone_after_21"))
    assertEquals(0, bundle.entries.single().getInt("foot_pain"))
    assertTrue(bundle.contractNotes.getBoolean("fixed_entries_are_compatibility_truth"))
  }

  @Test
  fun selected_profile_config_section_is_preserved_as_data_only() {
    val bundle = parseFutureBundle()
    val selectedConfig = bundle.selectedProfileConfig

    assertEquals("personal_legacy", selectedConfig.getString("active_profile_id"))
    assertTrue(selectedConfig.getJSONArray("enabled_signal_ids").strings().contains("core.sleep_ok"))
    assertProductionSourceDoesNotReference(
      "FutureSignalExportBundle",
      "selected_profile_config",
    )
  }

  @Test
  fun signal_definitions_section_is_preserved_as_data_only() {
    val bundle = parseFutureBundle()
    val definitionsById = bundle.signalDefinitions.associateBy { it.getString("id") }

    assertEquals("Sleep on time", definitionsById["core.sleep_ok"]?.getString("label"))
    assertEquals("Custom future signal", definitionsById["custom.future_signal"]?.getString("label"))
    assertProductionSourceDoesNotReference(
      "FutureSignalExportBundleParser",
      "signal_definitions",
    )
  }

  @Test
  fun signal_entries_preserve_absent_false_zero_distinctions() {
    val bundle = parseFutureBundle()

    assertEquals(false, bundle.signalEntryValue("evening.phone_after_21"))
    assertEquals(0, bundle.signalEntryValue("body.foot_pain"))
    assertFalse(bundle.hasSignalEntry("body.shoulder_pain"))
  }

  @Test
  fun optional_packs_and_influence_policies_parse_without_runtime_effect() {
    val bundle = parseFutureBundle()
    val patternPack = bundle.optionalPacks.first { it.getString("id") == "pattern_awareness_pack" }
    val sleepPolicy = bundle.influencePolicies.first { it.getString("signal_id") == "core.sleep_ok" }

    assertTrue(patternPack.getBoolean("sensitive"))
    assertTrue(patternPack.getBoolean("requires_explicit_opt_in"))
    assertEquals("normal", sleepPolicy.getString("guidance_effect"))
    assertProductionSourceDoesNotReference(
      "optional_packs",
      "influence_policies",
      "guidance_effect",
      "clinical_boundary",
    )
  }

  @Test
  fun unknown_future_sections_are_ignored_or_preserved_inertly() {
    val bundle = parseFutureBundle(fixtureJson = futureBundleFixtureWithUnknownTopLevelSection())

    assertEquals("preserved but not applied", bundle.unknownTopLevelSections["future_client_only_section"])
    assertEquals("custom.future_signal", bundle.signalDefinitions.last().getString("id"))
    assertEquals(9, bundle.signalEntryValue("custom.future_signal"))
  }

  @Test
  fun production_local_store_not_changed() {
    val localStore = File(
      repoRoot(),
      "app/mobile/android/app/src/main/java/com/life/lifeload/data/local/LifeLoadLocalStore.kt",
    ).readText(Charsets.UTF_8)

    assertTrue("Phase 5C-E local store owns additive future bundle sections.", "selected_profile_config" in localStore)
    assertFalse("Future bundle must not change local entry_json semantics.", "entry_json\".put(\"signal_entries" in localStore)
    assertProductionSourceDoesNotReference(
      "FutureSignalExportContractTest",
      "FutureSignalExportBundleParser",
      "FutureSignalExportBundle",
    )
  }

  private fun parseFutureBundle(fixtureJson: String = futureBundleFixture()): FutureSignalExportBundle =
    FutureSignalExportBundleParser.parse(fixtureJson)

  private fun assertProductionSourceDoesNotReference(vararg forbiddenReferences: String) {
    val productionFiles = File(repoRoot(), "app/mobile/android/app/src/main/java")
      .walkTopDown()
      .filter { it.isFile && it.extension in setOf("kt", "java") }
      .filterNot { it.invariantSeparatorsPath.endsWith("/data/local/LifeLoadLocalStore.kt") }
      .toList()
    val matches = productionFiles.flatMap { file ->
      val text = file.readText(Charsets.UTF_8)
      forbiddenReferences
        .filter { it in text }
        .map { "${file.relativeTo(repoRoot())}:$it" }
    }

    assertEquals(emptyList<String>(), matches)
  }

  private fun repoRoot(): File {
    val userDir = System.getProperty("user.dir") ?: "."
    var current: File? = File(userDir).canonicalFile
    while (current != null) {
      if (File(current, "app/mobile/android").isDirectory && File(current, "app/backend/life_load").isDirectory) {
        return current
      }
      current = current.parentFile
    }
    throw AssertionError("Could not find repo root from $userDir")
  }
}

private data class FutureSignalExportBundle(
  val version: String,
  val entries: List<JSONObject>,
  val profileTemplate: JSONObject,
  val selectedProfileConfig: JSONObject,
  val signalDefinitions: List<JSONObject>,
  val signalEntries: List<JSONObject>,
  val optionalPacks: List<JSONObject>,
  val influencePolicies: List<JSONObject>,
  val contractNotes: JSONObject,
  val unknownTopLevelSections: Map<String, Any?>,
) {
  fun hasSignalEntry(signalId: String): Boolean =
    signalEntries.any { it.getString("signal_id") == signalId }

  fun signalEntryValue(signalId: String): Any? =
    signalEntries.firstOrNull { it.getString("signal_id") == signalId }?.get("value")
}

private object FutureSignalExportBundleParser {
  private val knownTopLevelKeys = setOf(
    "version",
    "entries",
    "profile_template",
    "selected_profile_config",
    "signal_definitions",
    "signal_entries",
    "optional_packs",
    "influence_policies",
    "contract_notes",
  )

  fun parse(jsonText: String): FutureSignalExportBundle {
    val root = JSONObject(jsonText)
    val unknownTopLevelSections = root.keys().asSequence()
      .filterNot { it in knownTopLevelKeys }
      .associateWith { key -> root.get(key) }

    return FutureSignalExportBundle(
      version = root.getString("version"),
      entries = root.getJSONArray("entries").objects(),
      profileTemplate = root.getJSONObject("profile_template"),
      selectedProfileConfig = root.getJSONObject("selected_profile_config"),
      signalDefinitions = root.getJSONArray("signal_definitions").objects(),
      signalEntries = root.getJSONArray("signal_entries").objects(),
      optionalPacks = root.getJSONArray("optional_packs").objects(),
      influencePolicies = root.getJSONArray("influence_policies").objects(),
      contractNotes = root.getJSONObject("contract_notes"),
      unknownTopLevelSections = unknownTopLevelSections,
    )
  }
}

private fun futureBundleFixtureWithUnknownTopLevelSection(): String =
  JSONObject(futureBundleFixture())
    .put("future_client_only_section", "preserved but not applied")
    .toString()

private fun futureBundleFixture(): String =
  """
  {
    "version": "life_load_export_v_next",
    "entries": [
      {
        "date": "2026-05-17",
        "source": "android_phase_5b_fixture",
        "sleep_ok": true,
        "energy": 7,
        "stress": 3,
        "phone_after_21": false,
        "foot_pain": 0
      }
    ],
    "profile_template": {
      "id": "personal_legacy",
      "name": "Personal legacy",
      "version": 1,
      "signal_ids": ["core.sleep_ok", "evening.phone_after_21", "body.foot_pain"]
    },
    "selected_profile_config": {
      "active_profile_id": "personal_legacy",
      "template_version": 1,
      "enabled_signal_ids": ["core.sleep_ok", "evening.phone_after_21", "body.foot_pain"],
      "optional_signal_ids": [],
      "hidden_signal_ids": [],
      "disabled_signal_ids": [],
      "required_for_confidence_signal_ids": ["core.sleep_ok"],
      "optional_pack_ids": [],
      "user_added_signal_ids": [],
      "user_overridden_signal_ids": [],
      "guidance_bridge_policy_id": "fixed_field_legacy",
      "default_formula_modifier_id": null,
      "max_active_signals": 32
    },
    "signal_definitions": [
      {
        "id": "core.sleep_ok",
        "legacy_field_key": "sleep_ok",
        "label": "Sleep on time",
        "category": "core_recovery",
        "scale_type": "boolean",
        "version": 1
      },
      {
        "id": "custom.future_signal",
        "legacy_field_key": null,
        "label": "Custom future signal",
        "category": "body_signal",
        "scale_type": "ordinal_0_10",
        "version": 99
      }
    ],
    "signal_entries": [
      {
        "date": "2026-05-17",
        "signal_id": "core.sleep_ok",
        "value": true,
        "is_present": true,
        "source": "fixed_entry_projection"
      },
      {
        "date": "2026-05-17",
        "signal_id": "evening.phone_after_21",
        "value": false,
        "is_present": true,
        "source": "fixed_entry_projection"
      },
      {
        "date": "2026-05-17",
        "signal_id": "body.foot_pain",
        "value": 0,
        "is_present": true,
        "source": "fixed_entry_projection"
      },
      {
        "date": "2026-05-17",
        "signal_id": "custom.future_signal",
        "value": 9,
        "is_present": true,
        "source": "future_client"
      }
    ],
    "optional_packs": [
      {
        "id": "pattern_awareness_pack",
        "name": "Pattern awareness pack",
        "signal_ids": ["evening.phone_after_21"],
        "placeholder_signal_ids": [],
        "default_enabled": false,
        "sensitive": true,
        "requires_explicit_opt_in": true,
        "version": 1
      }
    ],
    "influence_policies": [
      {
        "signal_id": "core.sleep_ok",
        "guidance_effect": "normal",
        "polarity": "capacity_positive",
        "sensitivity_class": "normal",
        "clinical_boundary": "wellness_only",
        "applied_to_scoring": false,
        "version": 1
      }
    ],
    "contract_notes": {
      "fixed_entries_are_compatibility_truth": true,
      "signal_sections_are_additive_future_data": true,
      "unknown_signal_definitions_import_mode": "preserve_inert",
      "unknown_signal_entries_import_mode": "preserve_inert",
      "delete_reset_must_clear": [
        "selected_profile_config",
        "signal_definitions",
        "signal_entries",
        "optional_pack_selections",
        "influence_overrides"
      ],
      "sensitive_labels_must_not_be_logged": true
    }
  }
  """.trimIndent()

private fun JSONArray.objects(): List<JSONObject> =
  (0 until length()).map { index -> getJSONObject(index) }

private fun JSONArray.strings(): List<String> =
  (0 until length()).map { index -> getString(index) }
