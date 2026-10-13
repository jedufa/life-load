package com.life.lifeload

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.json.JSONArray
import org.json.JSONObject
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
class ProfileDrivenCheckInRendererTest {
  @get:Rule
  val composeRule = createComposeRule()

  @Test
  fun personal_legacy_renderable_fields_include_behavior_fields() {
    val fields = renderer().render(profileId = "personal_legacy")
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue(
      "Missing behavior fields: ${personalLegacyBehaviorFields - legacyKeys}",
      legacyKeys.containsAll(personalLegacyBehaviorFields),
    )
  }

  @Test
  fun general_balance_renderable_fields_exclude_personal_fields() {
    val fields = renderer().render(profileId = "general_balance")
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue(generalBalanceExcludedFields.intersect(legacyKeys).isEmpty())
  }

  @Test
  fun work_stress_renderable_fields_exclude_relationship_homework_body_part_pain() {
    val fields = renderer().render(profileId = "work_stress")
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue((relationshipHomeworkFields + bodyPartPainFields).intersect(legacyKeys).isEmpty())
  }

  @Test
  fun training_recovery_renderable_fields_exclude_relationship_homework() {
    val fields = renderer().render(profileId = "training_recovery")
    val legacyKeys = fields.mapNotNull { it.legacyFieldKey }.toSet()

    assertTrue(relationshipHomeworkFields.intersect(legacyKeys).isEmpty())
  }

  @Test
  fun body_signal_awareness_does_not_require_foot_or_shoulder() {
    val fields = renderer().render(profileId = "body_signal_awareness")
    val byLegacyKey = fields.mapNotNull { field ->
      field.legacyFieldKey?.let { it to field }
    }.toMap()

    assertFalse(byLegacyKey["foot_pain"]?.requiredForConfidence ?: false)
    assertFalse(byLegacyKey["shoulder_pain"]?.requiredForConfidence ?: false)
  }

  @Test
  fun hidden_disabled_fields_not_rendered_as_active() {
    val fields = renderer().render(profileId = "training_recovery")
    val signalIds = fields.map { it.signalId }.toSet()

    assertFalse("body.foot_pain" in signalIds)
    assertFalse("body.shoulder_pain" in signalIds)
    assertFalse("relationship.wife_conflict_count" in signalIds)
    assertFalse("caregiving.homework_done" in signalIds)
  }

  @Test
  fun pattern_awareness_pack_not_rendered_by_default() {
    val fields = renderer().render(profileId = "general_balance")
    val signalIds = fields.map { it.signalId }.toSet()

    assertFalse("evening.phone_after_21" in signalIds)
    assertFalse("work.project_overrun" in signalIds)
  }

  @Test
  fun pattern_awareness_pack_requires_explicit_opt_in() {
    val renderer = renderer()
    val contract = registryContractJson()
    val pack = contract.optionalPacks().first { it.getString("id") == "pattern_awareness_pack" }

    assertTrue(pack.getBoolean("requires_explicit_opt_in"))
    val withoutPack = renderer.render(profileId = "general_balance").map { it.signalId }.toSet()
    val withPack = renderer.render(
      profileId = "general_balance",
      optionalPackIds = setOf("pattern_awareness_pack"),
    ).associateBy { it.signalId }

    assertFalse("evening.phone_after_21" in withoutPack)
    assertTrue("evening.phone_after_21" in withPack)
    assertEquals("optional_pack", withPack["evening.phone_after_21"]?.visibility)
    assertTrue(withPack["evening.phone_after_21"]?.sensitive ?: false)
  }

  @Test
  fun maps_all_contract_scale_types_to_control_types() {
    val contractScaleTypes = registryContractJson()
      .getJSONArray("signals")
      .objects()
      .map { it.getString("scale_type") }
      .toSet()
    val mappedScaleTypes = contractScaleTypes.map { scaleType ->
      scaleType to RenderableControlType.fromScaleType(scaleType)
    }

    assertTrue(
      "Unsupported scale types: ${mappedScaleTypes.filter { it.second == null }.map { it.first }}",
      mappedScaleTypes.all { it.second != null },
    )
  }

  @Test
  fun boolean_signals_render_as_yes_no_controls() {
    val controls = renderer().renderInputControls(profileId = "personal_legacy").associateBy { it.signalId }

    assertEquals(RenderableControlType.YES_NO, controls["core.sleep_ok"]?.controlType)
    assertEquals(RenderableControlType.YES_NO, controls["body.migraine_warning"]?.controlType)
  }

  @Test
  fun ordinal_signals_render_as_slider_controls() {
    val controls = renderer().renderInputControls(profileId = "personal_legacy").associateBy { it.signalId }

    assertEquals(RenderableControlType.SLIDER_0_10, controls["mental.stress"]?.controlType)
    assertEquals(RenderableControlType.SLIDER_0_10, controls["energy.energy"]?.controlType)
    assertEquals(RenderableControlType.SLIDER_0_10, controls["body.foot_pain"]?.controlType)
  }

  @Test
  fun bounded_int_signals_render_as_stepper_controls() {
    val controls = renderer().renderInputControls(profileId = "personal_legacy").associateBy { it.signalId }

    assertEquals(RenderableControlType.STEPPER_INT, controls["relationship.wife_conflict_count"]?.controlType)
    assertEquals(RenderableControlType.STEPPER_INT, controls["stimulant.coffee_cups"]?.controlType)
  }

  @Test
  fun enum_signals_render_as_segmented_controls() {
    val controls = renderer().renderInputControls(profileId = "personal_legacy").associateBy { it.signalId }

    assertEquals(RenderableControlType.SEGMENTED_ENUM, controls["nutrition.alcohol"]?.controlType)
    assertEquals(RenderableControlType.SEGMENTED_ENUM, controls["training.primary_activity_type"]?.controlType)
  }

  @Test
  fun derived_signals_render_readonly_if_present() {
    val contract = registryContractJson()
    val derivedSignals = contract.getJSONArray("signals")
      .objects()
      .filter { it.getString("scale_type") == "derived" }

    if (derivedSignals.isEmpty()) {
      val unsupportedScaleTypes = contract.getJSONArray("signals")
        .objects()
        .map { it.getString("scale_type") }
        .filter { RenderableControlType.fromScaleType(it) == null }
        .toSet()

      assertEquals(emptySet<String>(), unsupportedScaleTypes)
      return
    }

    val controls = renderer().renderInputControls(profileId = "personal_legacy").associateBy { it.signalId }
    derivedSignals.forEach { signal ->
      val control = controls[signal.getString("id")]
      assertEquals(RenderableControlType.READONLY_DERIVED, control?.controlType)
      assertTrue(control?.readOnly ?: false)
    }
  }

  @Test
  fun hidden_disabled_fields_do_not_create_active_input_controls() {
    listOf(
      "general_balance",
      "work_stress",
      "training_recovery",
      "body_signal_awareness",
    ).forEach { profileId ->
      val controls = renderer().renderInputControls(profileId = profileId)
      val activeSignalIds = controls.map { it.signalId }.toSet()
      val profile = registryContractJson().profiles().first { it.getString("id") == profileId }
      val inactiveSignalIds = (
        profile.getJSONArray("hidden_signal_ids").strings() +
          profile.getJSONArray("disabled_signal_ids").strings()
        ).toSet()

      assertTrue(
        "$profileId rendered hidden/disabled controls: ${inactiveSignalIds.intersect(activeSignalIds)}",
        inactiveSignalIds.intersect(activeSignalIds).isEmpty(),
      )
    }
  }

  @Test
  fun pattern_awareness_controls_not_created_by_default() {
    val patternSignalIds = registryContractJson().optionalPacks()
      .first { it.getString("id") == "pattern_awareness_pack" }
      .getJSONArray("signal_ids")
      .strings()
      .toSet()
    val controls = renderer().renderInputControls(profileId = "general_balance")
    val controlSignalIds = controls.map { it.signalId }.toSet()

    assertTrue(patternSignalIds.intersect(controlSignalIds).isEmpty())
  }

  @Test
  fun pattern_awareness_controls_carry_sensitive_metadata_when_enabled() {
    val contract = registryContractJson()
    val patternSignalIds = contract.optionalPacks()
      .first { it.getString("id") == "pattern_awareness_pack" }
      .getJSONArray("signal_ids")
      .strings()
      .toSet()
    val controls = renderer().renderInputControls(
      profileId = "general_balance",
      optionalPackIds = setOf("pattern_awareness_pack"),
    ).filter { it.signalId in patternSignalIds }

    assertTrue(controls.isNotEmpty())
    assertTrue(controls.all { it.sensitive })
  }

  @Test
  fun general_balance_controls_exclude_personal_fields() {
    val controls = renderer().renderInputControls(profileId = "general_balance")
    val legacyKeys = controls.mapNotNull { control ->
      renderer().legacyFieldKeyFor(control.signalId)
    }.toSet()

    assertTrue(generalBalanceExcludedFields.intersect(legacyKeys).isEmpty())
  }

  @Test
  fun production_compass_today_still_does_not_consume_renderer() {
    val compassToday = File(repoRoot(), "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt")
      .readText(Charsets.UTF_8)
    val forbiddenReferences = listOf(
      "ProfileDrivenCheckInRenderer",
      "RenderableSignalField",
      "life_load_signal_registry.json",
      "optional_packs",
      "influence_policies",
    )
    val matches = forbiddenReferences.filter { it in compassToday }

    assertEquals(emptyList<String>(), matches)
  }

  @Test
  fun production_source_does_not_reference_test_only_input_controls() {
    val productionFiles = File(repoRoot(), "app/mobile/android/app/src/main/java")
      .walkTopDown()
      .filter { it.isFile && it.extension in setOf("kt", "java") }
      .toList()
    val forbiddenReferences = listOf(
      "RenderableInputControl",
      "RenderableControlType",
      "TestOnlyProfileDrivenCheckInRenderer",
      "ProfileDrivenCheckInRenderer",
    )
    val matches = productionFiles.flatMap { file ->
      val text = file.readText(Charsets.UTF_8)
      forbiddenReferences
        .filter { it in text }
        .map { "${file.relativeTo(repoRoot())}:$it" }
    }

    assertEquals(emptyList<String>(), matches)
  }

  @Test
  fun yes_no_control_encodes_true_false_and_absent_distinctly() {
    val draft = draftFor("personal_legacy")
    val withTrue = draft.updateValue("evening.phone_after_21", TestDraftEncodedValue.BooleanValue(true))
    val withFalse = draft.updateValue("evening.phone_after_21", TestDraftEncodedValue.BooleanValue(false))

    assertFalse(draft.valuesBySignalId.containsKey("evening.phone_after_21"))
    assertEquals(TestDraftEncodedValue.BooleanValue(true), withTrue.valuesBySignalId["evening.phone_after_21"]?.value)
    assertEquals(TestDraftEncodedValue.BooleanValue(false), withFalse.valuesBySignalId["evening.phone_after_21"]?.value)
    assertTrue(withFalse.valuesBySignalId["evening.phone_after_21"]?.isPresent ?: false)
  }

  @Test
  fun slider_control_encodes_zero_and_nonzero_distinctly() {
    val draft = draftFor("personal_legacy")
    val zero = draft.updateValue("body.foot_pain", TestDraftEncodedValue.OrdinalNumber(0))
    val nonzero = draft.updateValue("body.foot_pain", TestDraftEncodedValue.OrdinalNumber(4))

    assertFalse(draft.valuesBySignalId.containsKey("body.foot_pain"))
    assertEquals(TestDraftEncodedValue.OrdinalNumber(0), zero.valuesBySignalId["body.foot_pain"]?.value)
    assertEquals(TestDraftEncodedValue.OrdinalNumber(4), nonzero.valuesBySignalId["body.foot_pain"]?.value)
  }

  @Test
  fun enum_control_accepts_only_allowed_values() {
    val draft = draftFor("personal_legacy")
    val updated = draft.updateValue("training.primary_activity_type", TestDraftEncodedValue.EnumSelected("crossfit"))

    assertEquals(
      TestDraftEncodedValue.EnumSelected("crossfit"),
      updated.valuesBySignalId["training.primary_activity_type"]?.value,
    )

    try {
      draft.updateValue("training.primary_activity_type", TestDraftEncodedValue.EnumSelected("not_allowed"))
      throw AssertionError("Expected invalid enum value to fail")
    } catch (expected: IllegalArgumentException) {
      assertTrue(expected.message.orEmpty().contains("not allowed"))
    }
  }

  @Test
  fun duration_control_encodes_minutes() {
    val draft = draftFor("personal_legacy")
    val updated = draft.updateValue("training.activity_duration_min", TestDraftEncodedValue.DurationMinutes(45))

    assertEquals(
      TestDraftEncodedValue.DurationMinutes(45),
      updated.valuesBySignalId["training.activity_duration_min"]?.value,
    )
  }

  @Test
  fun text_control_encodes_text_without_persistence() {
    val draft = TestCheckInDraftState(
      profileId = "test_text_control",
      activeSignalIds = setOf("metadata.diary_text"),
    )
    val emptyText = draft.updateValue("metadata.diary_text", TestDraftEncodedValue.TextValue(""))
    val text = draft.updateValue("metadata.diary_text", TestDraftEncodedValue.TextValue("test-only note"))

    assertEquals(TestDraftEncodedValue.TextValue(""), emptyText.valuesBySignalId["metadata.diary_text"]?.value)
    assertEquals(TestDraftEncodedValue.TextValue("test-only note"), text.valuesBySignalId["metadata.diary_text"]?.value)
    assertFalse(draft.valuesBySignalId.containsKey("metadata.diary_text"))
  }

  @Test
  fun hidden_disabled_fields_cannot_update_active_draft_state() {
    val draft = draftFor("training_recovery")
    val updatedHidden = draft.updateValue("body.foot_pain", TestDraftEncodedValue.OrdinalNumber(5))
    val updatedDisabled = draft.updateValue("relationship.wife_conflict_count", TestDraftEncodedValue.IntNumber(1))

    assertFalse(updatedHidden.valuesBySignalId.containsKey("body.foot_pain"))
    assertFalse(updatedDisabled.valuesBySignalId.containsKey("relationship.wife_conflict_count"))
  }

  @Test
  fun general_balance_draft_excludes_personal_fields() {
    val draft = draftFor("general_balance")
    val legacyKeys = draft.activeSignalIds.mapNotNull { renderer().legacyFieldKeyFor(it) }.toSet()

    assertTrue(generalBalanceExcludedFields.intersect(legacyKeys).isEmpty())
  }

  @Test
  fun pattern_awareness_draft_values_absent_without_explicit_pack() {
    val draft = draftFor("general_balance")
    val updated = draft.updateValue("evening.phone_after_21", TestDraftEncodedValue.BooleanValue(true))

    assertFalse("evening.phone_after_21" in draft.activeSignalIds)
    assertFalse(updated.valuesBySignalId.containsKey("evening.phone_after_21"))
  }

  @Test
  fun pattern_awareness_draft_values_supported_when_pack_enabled_in_test_path() {
    val draft = draftFor("general_balance", optionalPackIds = setOf("pattern_awareness_pack"))
    val updated = draft.updateValue("evening.phone_after_21", TestDraftEncodedValue.BooleanValue(true))

    assertTrue("evening.phone_after_21" in draft.activeSignalIds)
    assertEquals(
      TestDraftEncodedValue.BooleanValue(true),
      updated.valuesBySignalId["evening.phone_after_21"]?.value,
    )
  }

  @Test
  fun draft_state_does_not_create_LifeLoadEntry_or_entry_json() {
    val draft = draftFor("personal_legacy")
      .updateValue("core.sleep_ok", TestDraftEncodedValue.BooleanValue(true))

    assertEquals("test_renderer", draft.valuesBySignalId["core.sleep_ok"]?.source)
    assertFalse(draft.toString().contains("LifeLoadEntry"))
    assertFalse(draft.toString().contains("entry_json"))
    assertProductionSourceDoesNotReference(
      "TestCheckInDraftState",
      "TestCheckInDraftValue",
      "TestDraftEncodedValue",
    )
  }

  @Test
  fun preview_renders_general_balance_without_personal_fields() {
    setPreviewContent(profileId = "general_balance")

    listOf(
      "Foot pain",
      "Shoulder pain",
      "Relationship conflict count",
      "Homework done",
      "Alcohol",
      "Eating episode",
      "Primary activity type",
    ).forEach { label ->
      composeRule.onNodeWithText(label).assertDoesNotExist()
    }
  }

  @Test
  fun preview_renders_personal_legacy_behavior_fields_in_test_path() {
    setPreviewContent(profileId = "personal_legacy")

    listOf(
      "Foot pain",
      "Shoulder pain",
      "Phone after 21:00",
      "Project overrun",
      "Primary activity type",
      "Homework done",
    ).forEach { label ->
      composeRule.onNodeWithText(label).assertExists()
    }
  }

  @Test
  fun preview_does_not_render_pattern_awareness_by_default() {
    setPreviewContent(profileId = "general_balance")

    composeRule.onNodeWithText("Phone after 21:00").assertDoesNotExist()
    composeRule.onNodeWithText("Project overrun").assertDoesNotExist()
  }

  @Test
  fun preview_renders_pattern_awareness_when_explicitly_enabled_and_marks_sensitive() {
    setPreviewContent(profileId = "general_balance", optionalPackIds = setOf("pattern_awareness_pack"))

    composeRule.onNodeWithText("Phone after 21:00").assertExists()
    composeRule.onNodeWithText("Sensitive: Phone after 21:00").assertExists()
  }

  @Test
  fun interacting_with_control_updates_test_draft_state_only() {
    val controls = renderer().renderInputControls(profileId = "general_balance")
    val draftState = mutableStateOf(draftForControls(profileId = "general_balance", controls = controls))

    composeRule.setContent {
      TestProfileDrivenCheckInPreview(
        profileId = "general_balance",
        renderableControls = controls,
        draftState = draftState.value,
        onDraftChange = { signalId, value ->
          draftState.value = draftState.value.updateValue(signalId, value)
        },
      )
    }

    composeRule.onNodeWithText("Yes: Sleep on time").performClick()

    assertEquals(
      TestDraftEncodedValue.BooleanValue(true),
      draftState.value.valuesBySignalId["core.sleep_ok"]?.value,
    )
    assertEquals("test_renderer", draftState.value.valuesBySignalId["core.sleep_ok"]?.source)
  }

  @Test
  fun production_compass_today_does_not_reference_test_preview() {
    val compassToday = File(repoRoot(), "app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt")
      .readText(Charsets.UTF_8)
    val forbiddenReferences = listOf(
      "TestProfileDrivenCheckInPreview",
      "TestCheckInDraftState",
      "TestCheckInDraftValue",
      "RenderableInputControl",
    )
    val matches = forbiddenReferences.filter { it in compassToday }

    assertEquals(emptyList<String>(), matches)
  }

  @Test
  fun production_navigation_does_not_reference_test_preview() {
    assertProductionSourceDoesNotReference(
      "TestProfileDrivenCheckInPreview",
      "TestCheckInDraftState",
      "TestCheckInDraftValue",
      "RenderableInputControl",
      "life_load_signal_registry.json",
    )
  }

  private fun renderer(): TestOnlyProfileDrivenCheckInRenderer =
    TestOnlyProfileDrivenCheckInRenderer(registryContractJson())

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

  private fun JSONObject.optionalPacks(): List<JSONObject> = getJSONArray("optional_packs").objects()

  private fun JSONObject.profiles(): List<JSONObject> = getJSONArray("profiles").objects()

  private fun JSONArray.objects(): List<JSONObject> =
    (0 until length()).map { index -> getJSONObject(index) }

  private fun draftFor(
    profileId: String,
    optionalPackIds: Set<String> = emptySet(),
  ): TestCheckInDraftState {
    val controls = renderer().renderInputControls(profileId = profileId, optionalPackIds = optionalPackIds)
    return draftForControls(profileId = profileId, controls = controls)
  }

  private fun draftForControls(
    profileId: String,
    controls: List<RenderableInputControl>,
  ): TestCheckInDraftState =
    TestCheckInDraftState(
      profileId = profileId,
      activeSignalIds = controls.map { it.signalId }.toSet(),
      allowedEnumValuesBySignalId = controls
        .filter { it.controlType == RenderableControlType.SEGMENTED_ENUM }
        .associate { it.signalId to it.allowedValues.toSet() },
    )

  private fun setPreviewContent(
    profileId: String,
    optionalPackIds: Set<String> = emptySet(),
  ): MutableState<TestCheckInDraftState> {
    val controls = renderer().renderInputControls(profileId = profileId, optionalPackIds = optionalPackIds)
    val draftState = mutableStateOf(draftForControls(profileId = profileId, controls = controls))

    composeRule.setContent {
      TestProfileDrivenCheckInPreview(
        profileId = profileId,
        renderableControls = controls,
        draftState = draftState.value,
        onDraftChange = { signalId, value ->
          draftState.value = draftState.value.updateValue(signalId, value)
        },
      )
    }

    return draftState
  }

  private fun assertProductionSourceDoesNotReference(vararg forbiddenReferences: String) {
    val productionFiles = File(repoRoot(), "app/mobile/android/app/src/main/java")
      .walkTopDown()
      .filter { it.isFile && it.extension in setOf("kt", "java") }
      .toList()
    val matches = productionFiles.flatMap { file ->
      val text = file.readText(Charsets.UTF_8)
      forbiddenReferences
        .filter { it in text }
        .map { "${file.relativeTo(repoRoot())}:$it" }
    }

    assertEquals(emptyList<String>(), matches)
  }

  companion object {
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

    private val generalBalanceExcludedFields = setOf(
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

    private val relationshipHomeworkFields = setOf(
      "wife_conflict_count",
      "wife_conflict_school",
      "wife_conflict_chores",
      "wife_conflict_other",
      "homework_done",
      "homework_status",
    )

    private val bodyPartPainFields = setOf("foot_pain", "shoulder_pain")
  }
}

private data class RenderableSignalField(
  val signalId: String,
  val legacyFieldKey: String?,
  val label: String,
  val category: String,
  val scaleType: String,
  val visibility: String,
  val requiredForConfidence: Boolean,
  val sensitive: Boolean,
)

private data class RenderableInputControl(
  val signalId: String,
  val label: String,
  val controlType: RenderableControlType,
  val allowedValues: List<String>,
  val requiredForConfidence: Boolean,
  val sensitive: Boolean,
  val readOnly: Boolean,
)

private data class TestCheckInDraftValue(
  val signalId: String,
  val value: TestDraftEncodedValue,
  val source: String = "test_renderer",
  val isPresent: Boolean = value != TestDraftEncodedValue.Absent,
)

private data class TestCheckInDraftState(
  val profileId: String,
  val activeSignalIds: Set<String>,
  val valuesBySignalId: Map<String, TestCheckInDraftValue> = emptyMap(),
  val allowedEnumValuesBySignalId: Map<String, Set<String>> = emptyMap(),
) {
  fun updateValue(
    signalId: String,
    value: TestDraftEncodedValue,
  ): TestCheckInDraftState {
    if (signalId !in activeSignalIds) return this
    if (value == TestDraftEncodedValue.Absent) return clearValue(signalId)
    validateValue(signalId = signalId, value = value)

    return copy(
      valuesBySignalId = valuesBySignalId + (
        signalId to TestCheckInDraftValue(
          signalId = signalId,
          value = value,
        )
        ),
    )
  }

  fun clearValue(signalId: String): TestCheckInDraftState =
    copy(valuesBySignalId = valuesBySignalId - signalId)

  private fun validateValue(
    signalId: String,
    value: TestDraftEncodedValue,
  ) {
    if (value is TestDraftEncodedValue.EnumSelected) {
      val allowedValues = allowedEnumValuesBySignalId[signalId].orEmpty()
      require(value.value in allowedValues) {
        "Enum value ${value.value} is not allowed for $signalId"
      }
    }
  }
}

private sealed class TestDraftEncodedValue {
  data object Absent : TestDraftEncodedValue()
  data class BooleanValue(val value: Boolean) : TestDraftEncodedValue()
  data class OrdinalNumber(val value: Int) : TestDraftEncodedValue()
  data class IntNumber(val value: Int) : TestDraftEncodedValue()
  data class EnumSelected(val value: String) : TestDraftEncodedValue()
  data class DurationMinutes(val minutes: Int) : TestDraftEncodedValue()
  data class TextValue(val value: String) : TestDraftEncodedValue()
}

private enum class RenderableControlType {
  YES_NO,
  TERNARY,
  SLIDER_0_10,
  STEPPER_INT,
  SEGMENTED_ENUM,
  DURATION_MINUTES,
  TEXT_NOTE,
  READONLY_DERIVED,
  ;

  companion object {
    fun fromScaleType(scaleType: String): RenderableControlType? =
      when (scaleType) {
        "boolean" -> YES_NO
        "ternary" -> TERNARY
        "ordinal_0_10" -> SLIDER_0_10
        "bounded_int" -> STEPPER_INT
        "enum" -> SEGMENTED_ENUM
        "duration_minutes" -> DURATION_MINUTES
        "text" -> TEXT_NOTE
        "derived" -> READONLY_DERIVED
        else -> null
      }
  }
}

@Composable
private fun TestProfileDrivenCheckInPreview(
  profileId: String,
  renderableControls: List<RenderableInputControl>,
  draftState: TestCheckInDraftState,
  onDraftChange: (String, TestDraftEncodedValue) -> Unit,
) {
  Column {
    Text("Test profile: $profileId")
    renderableControls.forEach { control ->
      Column {
        Text(control.label)
        if (control.sensitive) {
          Text("Sensitive: ${control.label}")
        }
        when (control.controlType) {
          RenderableControlType.YES_NO -> {
            Row {
              Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.BooleanValue(true)) }) {
                Text("Yes: ${control.label}")
              }
              Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.BooleanValue(false)) }) {
                Text("No: ${control.label}")
              }
            }
          }

          RenderableControlType.TERNARY -> {
            Row {
              listOf("yes", "no", "unknown").forEach { value ->
                Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.EnumSelected(value)) }) {
                  Text("${control.label}: $value")
                }
              }
            }
          }

          RenderableControlType.SLIDER_0_10 -> {
            Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.OrdinalNumber(1)) }) {
              Text("Set ${control.label} to 1")
            }
          }

          RenderableControlType.STEPPER_INT -> {
            Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.IntNumber(1)) }) {
              Text("Increase ${control.label}")
            }
          }

          RenderableControlType.SEGMENTED_ENUM -> {
            Row {
              control.allowedValues.forEach { value ->
                Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.EnumSelected(value)) }) {
                  Text("${control.label}: $value")
                }
              }
            }
          }

          RenderableControlType.DURATION_MINUTES -> {
            Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.DurationMinutes(15)) }) {
              Text("Set ${control.label} to 15 min")
            }
          }

          RenderableControlType.TEXT_NOTE -> {
            Button(onClick = { onDraftChange(control.signalId, TestDraftEncodedValue.TextValue("test note")) }) {
              Text("Add note: ${control.label}")
            }
          }

          RenderableControlType.READONLY_DERIVED -> {
            val value = draftState.valuesBySignalId[control.signalId]?.value ?: TestDraftEncodedValue.Absent
            Text("Read only ${control.label}: $value")
          }
        }
      }
    }
  }
}

private class TestOnlyProfileDrivenCheckInRenderer(
  contract: JSONObject,
) {
  private val signalsById = contract.getJSONArray("signals")
    .objects()
    .associateBy { it.getString("id") }
  private val profilesById = contract.getJSONArray("profiles")
    .objects()
    .associateBy { it.getString("id") }
  private val packsById = contract.getJSONArray("optional_packs")
    .objects()
    .associateBy { it.getString("id") }

  fun render(
    profileId: String,
    optionalPackIds: Set<String> = emptySet(),
  ): List<RenderableSignalField> {
    val profile = profilesById[profileId] ?: throw IllegalArgumentException("Unknown profile $profileId")
    val hiddenOrDisabled = (
      profile.getJSONArray("hidden_signal_ids").strings() +
        profile.getJSONArray("disabled_signal_ids").strings()
      ).toSet()
    val required = profile.getJSONArray("required_for_confidence_signal_ids").strings().toSet()
    val fields = linkedMapOf<String, RenderableSignalField>()

    profile.getJSONArray("visible_signal_ids").strings().forEach { signalId ->
      addRenderableField(fields, signalId, "visible", required, sensitiveOverride = false)
    }
    profile.getJSONArray("optional_signal_ids").strings().forEach { signalId ->
      addRenderableField(fields, signalId, "optional", required, sensitiveOverride = false)
    }
    optionalPackIds.forEach { packId ->
      val pack = packsById[packId] ?: throw IllegalArgumentException("Unknown optional pack $packId")
      val allowedPacks = profile.getJSONArray("allowed_optional_pack_ids").strings().toSet()
      require(packId in allowedPacks) { "Optional pack $packId is not allowed for profile $profileId" }
      pack.getJSONArray("signal_ids").strings()
        .filterNot { it in hiddenOrDisabled }
        .forEach { signalId ->
          addRenderableField(fields, signalId, "optional_pack", required, sensitiveOverride = pack.getBoolean("sensitive"))
        }
    }

    return fields.values
      .filterNot { it.signalId in hiddenOrDisabled }
      .toList()
  }

  fun renderInputControls(
    profileId: String,
    optionalPackIds: Set<String> = emptySet(),
  ): List<RenderableInputControl> =
    render(profileId = profileId, optionalPackIds = optionalPackIds)
      .map { field ->
        val signal = signalsById[field.signalId]
          ?: throw IllegalArgumentException("Unknown signal ${field.signalId}")
        val controlType = RenderableControlType.fromScaleType(field.scaleType)
          ?: throw IllegalArgumentException("Unsupported scale type ${field.scaleType} for ${field.signalId}")

        RenderableInputControl(
          signalId = field.signalId,
          label = field.label,
          controlType = controlType,
          allowedValues = signal.optionalStringArray("allowed_values").ifEmpty {
            fallbackAllowedValuesFor(signalId = field.signalId, controlType = controlType)
          },
          requiredForConfidence = field.requiredForConfidence,
          sensitive = field.sensitive,
          readOnly = controlType == RenderableControlType.READONLY_DERIVED,
        )
      }

  fun legacyFieldKeyFor(signalId: String): String? =
    signalsById[signalId]?.nullableString("legacy_field_key")

  private fun fallbackAllowedValuesFor(
    signalId: String,
    controlType: RenderableControlType,
  ): List<String> =
    when {
      controlType == RenderableControlType.TERNARY -> listOf("yes", "no", "unknown")
      controlType != RenderableControlType.SEGMENTED_ENUM -> emptyList()
      signalId == "training.primary_activity_type" -> listOf("none", "crossfit", "run", "bike", "rehab")
      signalId == "training.activity_types" -> listOf("crossfit", "run", "bike", "rehab")
      signalId == "nutrition.alcohol" -> listOf("none", "some")
      signalId == "caregiving.homework_status" -> listOf("done", "missed", "not_applicable")
      signalId == "work.work_intensity" -> listOf("low", "moderate", "high")
      else -> emptyList()
    }

  private fun addRenderableField(
    fields: MutableMap<String, RenderableSignalField>,
    signalId: String,
    visibility: String,
    required: Set<String>,
    sensitiveOverride: Boolean,
  ) {
    val signal = signalsById[signalId] ?: return
    fields.putIfAbsent(
      signalId,
      RenderableSignalField(
        signalId = signalId,
        legacyFieldKey = signal.nullableString("legacy_field_key"),
        label = signal.getString("label"),
        category = signal.getString("category"),
        scaleType = signal.getString("scale_type"),
        visibility = visibility,
        requiredForConfidence = signalId in required,
        sensitive = sensitiveOverride || signal.getString("privacy_class") == "sensitive_label",
      ),
    )
  }
}

private fun JSONObject.nullableString(name: String): String? =
  if (isNull(name)) null else getString(name)

private fun JSONObject.optionalStringArray(name: String): List<String> =
  if (has(name) && !isNull(name)) getJSONArray(name).strings() else emptyList()

private fun JSONArray.objects(): List<JSONObject> =
  (0 until length()).map { index -> getJSONObject(index) }

private fun JSONArray.strings(): List<String> =
  (0 until length()).map { index -> getString(index) }
