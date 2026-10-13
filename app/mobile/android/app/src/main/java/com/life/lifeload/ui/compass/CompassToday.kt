package com.life.lifeload.ui.compass

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.life.lifeload.R
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.ui.LifeLoadUiActions
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.isCheckInSaved
import org.json.JSONArray
import org.json.JSONObject
import kotlinx.coroutines.delay
import java.time.DayOfWeek
import java.time.LocalDate

@OptIn(ExperimentalLayoutApi::class)
fun LazyListScope.compassTodayItems(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  mode: CompassMode,
  openDetails: () -> Unit,
  expandMissingSignals: Boolean = false,
) {
  val missing = missingFieldsForProfile(state)
  val saved = isCheckInSaved(state)
  item {
    CompassHeroCard(
      title = stringResource(R.string.nav_check_in),
      status = dailyStatus(state),
      isSaved = saved,
      dailyMeaning = localizedDailyMeaning(state, missing),
      whyItems = dailyConclusionReasons(state),
      savedStatus = localizedDailySavedStatus(state, missing),
      nextAction = localizedDailyHelpfulStep(state, missing),
      confidence = confidenceLabel(state),
      missingFields = missing,
      lastSavedText = formatLastSavedAt(state.approvedAt),
      tag = "today-hero-card",
      primaryButtonLabel = if (saved) stringResource(R.string.compass_update_checkin) else stringResource(R.string.compass_save_checkin),
      onPrimary = actions.onApprove,
      titleTrailingText = stringResource(
        when {
          state.hasUnsavedChanges -> R.string.check_in_status_unsaved
          saved -> R.string.check_in_status_done
          else -> R.string.check_in_status_open
        },
      ),
      primaryTrailingContent = {
        CheckInClipboardButtons(state = state, actions = actions, tagPrefix = "daily-hero")
      },
    )
  }

  item {
    QuickCheckInCard(state = state, actions = actions, mode = mode, highlightMissing = expandMissingSignals)
  }

  if (mode.showsDetails()) {
    item {
      DiaryCard(state = state, actions = actions)
    }
    item {
      MoreSignalsCard(state = state, actions = actions, mode = mode, expandMissingSignals = expandMissingSignals)
    }
    if (state.score.why.isNotEmpty() || mode.showsOperatorData()) item {
      FormulaCompassCard(state = state, mode = mode)
    }
    if (humanSystemStatusVisible(state, mode)) item {
      HumanSystemStatusCard(state = state, mode = mode)
    }
  } else {
    item {
      CollapsedSignalsSummary(state, onDetails = openDetails)
    }
  }
}

@Composable
private fun dailyConclusionReasons(state: LifeLoadUiState): List<String> {
  val entry = state.draftEntry
  val activeFields = activeLegacyFieldKeys(state)
  val reasons = mutableListOf<String>()
  (state.score.why + state.score.redFlags + state.score.warnings)
    .filter { supportReasonActive(it, activeFields) }
    .map { compassSupportLabel(it) }
    .filterTo(reasons) { it.isNotBlank() }
  if (state.score.lifeLoadScore >= 35.0) reasons += stringResource(R.string.daily_reason_load_threshold)
  if ("sleep_ok" in activeFields && entry.sleepOk == false) reasons += stringResource(R.string.daily_reason_sleep_late)
  if ("nutrition_ok" in activeFields && entry.nutritionOk == false) reasons += stringResource(R.string.daily_reason_food_off_track)
  if ("binge" in activeFields && entry.binge == true) reasons += stringResource(R.string.daily_reason_eating_episode)
  if ("alcohol" in activeFields) {
    when (entry.alcohol?.lowercase()) {
      "home" -> reasons += stringResource(R.string.daily_reason_alcohol_home)
      "social" -> reasons += stringResource(R.string.daily_reason_alcohol_social)
    }
  }
  if ("phone_after_21" in activeFields && entry.phoneAfter21 == true) reasons += stringResource(R.string.daily_reason_late_phone)
  if ("project_overrun" in activeFields && entry.projectOverrun == true) reasons += stringResource(R.string.daily_reason_project_overrun)
  if ("shutdown_done" in activeFields && entry.shutdownDone == false) reasons += stringResource(R.string.daily_reason_shutdown_missed)
  if (
    "after_work_decompression_done" in activeFields && entry.afterWorkDecompressionDone == false ||
    "decompression_done" in activeFields && entry.decompressionDone == false
  ) reasons += stringResource(R.string.daily_reason_decompression_missed)
  if ("stress" in activeFields && (entry.stress ?: -1) >= 6) reasons += stringResource(R.string.daily_reason_stress_high)
  if ("energy" in activeFields && (entry.energy ?: 11) <= 4) reasons += stringResource(R.string.daily_reason_energy_low)
  if (
    "foot_pain" in activeFields && (entry.footPain ?: 0) >= 5 ||
    "shoulder_pain" in activeFields && (entry.shoulderPain ?: 0) >= 5
  ) reasons += stringResource(R.string.daily_reason_pain_high)
  if ("migraine_warning" in activeFields && entry.migraineWarning == true) reasons += stringResource(R.string.daily_reason_migraine)
  if ("work_intensity" in activeFields && entry.workIntensity.lowercase() in setOf("heavy", "extreme")) reasons += stringResource(R.string.daily_reason_work_heavy)
  if (
    "family_stress" in activeFields && (entry.familyStress ?: 0) >= 2 ||
    "wife_conflict_count" in activeFields && (entry.wifeConflictCount ?: 0) > 0
  ) reasons += stringResource(R.string.daily_reason_family_stress)
  return reasons.distinct().take(8)
}

private val MovementFieldKeys = setOf("primary_activity_type", "activity_duration_min")
private val RecoveryFieldKeys = setOf("rehab_done", "decompression_done", "after_work_decompression_done", "shutdown_done", "phone_after_21", "project_overrun")
private val PainFieldKeys = setOf("foot_pain", "shoulder_pain", "migraine_warning", "other_symptoms")
private val MoodFieldKeys = setOf("mood", "stress", "energy", "coffee_cups")
private val WorkFamilyFieldKeys = setOf(
  "work_intensity",
  "home_office",
  "family_stress",
  "wife_conflict_count",
  "alone_home",
  "wife_conflict_school",
  "wife_conflict_chores",
  "wife_conflict_other",
  "homework_done",
  "homework_status",
)

private fun activeLegacyFieldKeys(state: LifeLoadUiState): Set<String> =
  LifeLoadProfileCatalog.renderableFields(state.profileSetup.selectedConfig)
    .mapNotNull { it.legacyFieldKey }
    .toSet()
    .let { keys ->
      if (state.profileSetup.selectedConfig.activeProfileId == "personal_legacy") {
        keys + "other_symptoms"
      } else {
        keys
      }
    }

private fun Set<String>.hasAny(keys: Set<String>): Boolean = any { it in keys }

private fun missingFieldsForProfile(state: LifeLoadUiState): List<String> {
  val entry = state.draftEntry
  val activeFields = activeLegacyFieldKeys(state)
  return buildList {
    if ("sleep_ok" in activeFields && entry.sleepOk == null) add("sleep")
    if ("nutrition_ok" in activeFields && entry.nutritionOk == null) add("food")
    if ("alcohol" in activeFields && entry.alcohol == null) add("alcohol")
    if ("binge" in activeFields && entry.binge == null) add("eating")
    if ("primary_activity_type" in activeFields && entry.primaryActivityType.isBlank()) add("movement")
    if ("stress" in activeFields && entry.stress == null) add("stress")
    if ("energy" in activeFields && entry.energy == null) add("energy")
    if (
      ("foot_pain" in activeFields || "shoulder_pain" in activeFields) &&
      ("foot_pain" !in activeFields || entry.footPain == null) &&
      ("shoulder_pain" !in activeFields || entry.shoulderPain == null)
    ) add("pain")
  }
}

private fun supportReasonActive(reason: String, activeFields: Set<String>): Boolean =
  when (reason.trim()) {
    "alcohol" -> "alcohol" in activeFields
    "binge" -> "binge" in activeFields
    "sleep drift", "garmin short sleep" -> "sleep_ok" in activeFields
    "nutrition drift" -> "nutrition_ok" in activeFields
    "relationship conflict", "repeated relationship conflict", "school conflict" -> activeFields.hasAny(WorkFamilyFieldKeys)
    "training spike from low base", "acute training spike", "training load rising fast", "chronic load ramp", "multiple hard sessions" -> activeFields.hasAny(MovementFieldKeys)
    "garmin high stress", "garmin elevated stress", "emotional overload", "accumulated emotional load" -> "stress" in activeFields
    "migraine warning" -> "migraine_warning" in activeFields
    "pain flare" -> activeFields.hasAny(PainFieldKeys)
    "shutdown missed" -> "shutdown_done" in activeFields
    "decompression missed", "after-work decompression missed" -> activeFields.hasAny(setOf("decompression_done", "after_work_decompression_done"))
    "late phone" -> "phone_after_21" in activeFields
    "project spillover" -> "project_overrun" in activeFields
    "evening chain broken" -> "evening_chain_broken" in activeFields
    "alone at home trigger", "alone home food risk" -> "alone_home" in activeFields
    else -> true
  }

@Composable
private fun compassSupportLabel(value: String): String = when (value.trim()) {
  "alcohol" -> stringResource(R.string.daily_reason_alcohol_logged)
  "binge" -> stringResource(R.string.daily_reason_eating_episode)
  "sleep drift" -> stringResource(R.string.daily_reason_sleep_late)
  "garmin short sleep" -> stringResource(R.string.daily_reason_garmin_short_sleep)
  "nutrition drift" -> stringResource(R.string.daily_reason_food_off_track)
  "recovery compliance falling", "recovery consistency falling" -> stringResource(R.string.daily_reason_recovery_slipping)
  "historical risk score high", "risk score high" -> stringResource(R.string.daily_reason_recent_risk_high)
  "relationship conflict", "repeated relationship conflict" -> stringResource(R.string.daily_reason_family_stress)
  "school conflict" -> stringResource(R.string.daily_reason_school_conflict)
  "training spike from low base", "acute training spike", "training load rising fast", "chronic load ramp" -> stringResource(R.string.daily_reason_training_load)
  "garmin high stress", "garmin elevated stress" -> stringResource(R.string.daily_reason_stress_high)
  "multiple hard sessions" -> stringResource(R.string.daily_reason_hard_sessions)
  "migraine warning" -> stringResource(R.string.daily_reason_migraine)
  "pain flare" -> stringResource(R.string.daily_reason_pain_high)
  "shutdown missed" -> stringResource(R.string.daily_reason_shutdown_missed)
  "decompression missed", "after-work decompression missed" -> stringResource(R.string.daily_reason_decompression_missed)
  "late phone" -> stringResource(R.string.daily_reason_late_phone)
  "project spillover" -> stringResource(R.string.daily_reason_project_overrun)
  "evening chain broken" -> stringResource(R.string.daily_reason_evening_chain)
  "emotional overload", "accumulated emotional load" -> stringResource(R.string.daily_reason_emotional_load)
  "alone at home trigger", "alone home food risk" -> stringResource(R.string.daily_reason_alone_home)
  "missing structured data" -> stringResource(R.string.daily_reason_missing_data)
  else -> value
}

@Composable
private fun QuickCheckInCard(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  mode: CompassMode,
  highlightMissing: Boolean = false,
) {
  val missing = missingFieldsForProfile(state)
  val activeFields = activeLegacyFieldKeys(state)
  CompassCard(stringResource(R.string.compass_quick_checkin), tag = "quick-checkin-card") {
    Text(stringResource(R.string.compass_quick_checkin_helper), color = MaterialTheme.colorScheme.onSurfaceVariant)
    if ("sleep_ok" in activeFields) {
      SegmentedField(
        label = stringResource(R.string.field_sleep_label),
        selected = booleanChoice(state.draftEntry.sleepOk),
        options = yesNoUnknownOptions(),
        tagPrefix = "daily-core-sleep",
        mode = mode,
        riskValues = setOf("no"),
        help = SleepHelp,
        highlightMissing = highlightMissing && "sleep" in missing,
      ) { actions.onBooleanField("sleep_ok", yesNoUnknownValue(it)) }
    }
    if ("nutrition_ok" in activeFields) {
      SegmentedField(
        label = stringResource(R.string.field_food_label),
        selected = booleanChoice(state.draftEntry.nutritionOk),
        options = yesNoUnknownOptions(),
        tagPrefix = "daily-core-nutrition",
        mode = mode,
        riskValues = setOf("no"),
        help = FoodHelp,
        highlightMissing = highlightMissing && "food" in missing,
      ) { actions.onBooleanField("nutrition_ok", yesNoUnknownValue(it)) }
    }
    if ("alcohol" in activeFields) {
      SegmentedField(
        label = stringResource(R.string.field_alcohol_label),
        selected = alcoholChoice(state.draftEntry.alcohol),
        options = listOf("none" to stringResource(R.string.none), "social" to stringResource(R.string.social), "home" to stringResource(R.string.at_home), "unknown" to stringResource(R.string.unknown)),
        tagPrefix = "daily-core-alcohol",
        mode = mode,
        riskValues = setOf("home"),
        cautionValues = setOf("social"),
        positiveValues = setOf("none"),
        help = AlcoholHelp,
        highlightMissing = highlightMissing && "alcohol" in missing,
      ) { actions.onStringField("alcohol", if (it == "unknown") "" else it) }
    }
    if ("binge" in activeFields) {
      SegmentedField(
        label = stringResource(R.string.field_eating_episode_label),
        selected = booleanChoice(state.draftEntry.binge),
        options = yesNoUnknownOptions(),
        tagPrefix = "daily-core-binge",
        mode = mode,
        riskValues = setOf("yes"),
        positiveValues = setOf("no"),
        help = EatingEpisodeHelp,
        highlightMissing = highlightMissing && "eating" in missing,
      ) { actions.onBooleanField("binge", yesNoUnknownValue(it)) }
    }
    if (mode == CompassMode.Simple) {
      CompassTextField(
        label = stringResource(R.string.field_optional_diary_label),
        value = state.draftEntry.diaryText,
        tag = "daily-diary-input",
        minLines = 3,
        onValueChange = actions.onDiaryChanged,
      )
    }
  }
}

@Composable
private fun DiaryCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val saved = isCheckInSaved(state)
  var expanded by rememberSaveable(state.selectedDate, state.approvedAt, state.entryState) { mutableStateOf(!saved) }
  CompassCard(stringResource(R.string.compass_diary), tag = "daily-diary-card") {
    if (expanded) {
      CompassTextField(
        label = stringResource(R.string.field_diary_label),
        value = state.draftEntry.diaryText,
        tag = "daily-diary-input",
        minLines = 6,
        onValueChange = actions.onDiaryChanged,
      )
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Button(onClick = actions.onAnalyzeDiary, modifier = Modifier.testTag("daily-analyze-button")) {
          Text(if (state.analysisLocked) stringResource(R.string.compass_analyzing) else stringResource(R.string.compass_analyze_diary))
        }
        Spacer(Modifier.weight(1f))
        Button(onClick = actions.onApprove, modifier = Modifier.testTag("daily-approve-button")) {
          Text(if (saved) stringResource(R.string.compass_update_checkin) else stringResource(R.string.compass_save_checkin))
        }
        Spacer(Modifier.width(10.dp))
        CheckInClipboardButtons(state = state, actions = actions, tagPrefix = "daily-diary")
      }
    } else {
      Text(
        state.draftEntry.diaryText.ifBlank { stringResource(R.string.compass_no_diary_note) },
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
      )
      TextButton(onClick = { expanded = true }, modifier = Modifier.testTag("daily-diary-expand")) {
        Text(stringResource(R.string.compass_edit_diary))
      }
    }
  }
}

@Composable
private fun CheckInClipboardButtons(state: LifeLoadUiState, actions: LifeLoadUiActions, tagPrefix: String) {
  val clipboardManager = LocalClipboardManager.current
  val copiedText = stringResource(R.string.compass_clipboard_copied)
  val pastedText = stringResource(R.string.compass_clipboard_pasted)
  val emptyText = stringResource(R.string.compass_clipboard_empty)
  var feedback by rememberSaveable { mutableStateOf("") }
  LaunchedEffect(feedback) {
    if (feedback.isNotBlank()) {
      delay(2000)
      feedback = ""
    }
  }
  Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 8.dp)) {
    Row(horizontalArrangement = Arrangement.spacedBy(0.dp), verticalAlignment = Alignment.CenterVertically) {
      IconButton(
        onClick = {
          clipboardManager.setText(AnnotatedString(state.draftEntry.toClipboardJson()))
          feedback = copiedText
        },
        modifier = Modifier
          .size(32.dp)
          .testTag("$tagPrefix-copy-checkin"),
      ) {
        Icon(
          Icons.Filled.ContentCopy,
          contentDescription = stringResource(R.string.copy_checkin_content_description),
          tint = compassGreen(),
          modifier = Modifier.size(17.dp),
        )
      }
      IconButton(
        onClick = {
          val pasted = clipboardManager.getText()?.text?.toLifeLoadEntryForDate(state.selectedDate)
          if (pasted != null) {
            pasted.applyTo(actions)
            feedback = pastedText
          } else {
            feedback = emptyText
          }
        },
        modifier = Modifier
          .size(32.dp)
          .testTag("$tagPrefix-paste-checkin"),
      ) {
        Icon(
          Icons.Filled.ContentPaste,
          contentDescription = stringResource(R.string.paste_checkin_content_description),
          tint = compassGreen(),
          modifier = Modifier.size(17.dp),
        )
      }
    }
    if (feedback.isNotBlank()) {
      Text(
        feedback,
        color = MaterialTheme.colorScheme.primary,
        style = MaterialTheme.typography.labelSmall,
        modifier = Modifier.testTag("$tagPrefix-clipboard-feedback"),
      )
    }
  }
}

private fun LifeLoadEntry.toClipboardJson(): String =
  JSONObject()
    .put("kind", "life-load-check-in")
    .put("version", 1)
    .put("date", date)
    .put("diary_text", diaryText)
    .put("diary_summary", diarySummary)
    .put("tags", JSONArray(tags))
    .putNullable("sleep_ok", sleepOk)
    .putNullable("nutrition_ok", nutritionOk)
    .putNullable("alcohol", alcohol)
    .putNullable("binge", binge)
    .putNullable("mood", mood)
    .putNullable("stress", stress)
    .putNullable("energy", energy)
    .putNullable("coffee_cups", coffeeCups)
    .putNullable("foot_pain", footPain)
    .putNullable("shoulder_pain", shoulderPain)
    .putNullable("migraine_warning", migraineWarning)
    .putNullable("decompression_done", decompressionDone)
    .putNullable("after_work_decompression_done", afterWorkDecompressionDone)
    .putNullable("evening_chain_broken", eveningChainBroken)
    .putNullable("shutdown_done", shutdownDone)
    .putNullable("phone_after_21", phoneAfter21)
    .putNullable("project_overrun", projectOverrun)
    .put("primary_activity_type", primaryActivityType)
    .put("activity_types", JSONArray(activityTypes))
    .putNullable("activity_duration_min", activityDurationMin)
    .putNullable("rehab_done", rehabDone)
    .put("other_symptoms", otherSymptoms)
    .put("work_intensity", workIntensity)
    .putNullable("family_stress", familyStress)
    .putNullable("wife_conflict_count", wifeConflictCount)
    .putNullable("wife_conflict_school", wifeConflictSchool)
    .putNullable("wife_conflict_chores", wifeConflictChores)
    .putNullable("wife_conflict_other", wifeConflictOther)
    .putNullable("home_office", homeOffice)
    .putNullable("alone_home", aloneHome)
    .putNullable("homework_done", homeworkDone)
    .putNullable("homework_status", homeworkStatus)
    .toString()

private fun JSONObject.putNullable(name: String, value: Any?): JSONObject = put(name, value ?: JSONObject.NULL)

private fun String.toLifeLoadEntryForDate(date: String): LifeLoadEntry? = runCatching {
  val json = JSONObject(this)
  if (json.optString("kind") != "life-load-check-in") return null
  LifeLoadEntry(
    date = date,
    diaryText = json.optString("diary_text"),
    diarySummary = json.optString("diary_summary"),
    tags = json.optStringList("tags"),
    sleepOk = json.optNullableBoolean("sleep_ok"),
    nutritionOk = json.optNullableBoolean("nutrition_ok"),
    alcohol = json.optNullableString("alcohol"),
    binge = json.optNullableBoolean("binge"),
    mood = json.optNullableInt("mood"),
    stress = json.optNullableInt("stress"),
    energy = json.optNullableInt("energy"),
    coffeeCups = json.optNullableInt("coffee_cups"),
    footPain = json.optNullableInt("foot_pain"),
    shoulderPain = json.optNullableInt("shoulder_pain"),
    migraineWarning = json.optNullableBoolean("migraine_warning"),
    decompressionDone = json.optNullableBoolean("decompression_done"),
    afterWorkDecompressionDone = json.optNullableBoolean("after_work_decompression_done"),
    eveningChainBroken = json.optNullableBoolean("evening_chain_broken"),
    shutdownDone = json.optNullableBoolean("shutdown_done"),
    phoneAfter21 = json.optNullableBoolean("phone_after_21"),
    projectOverrun = json.optNullableBoolean("project_overrun"),
    primaryActivityType = json.optString("primary_activity_type"),
    activityTypes = json.optStringList("activity_types"),
    activityDurationMin = json.optNullableInt("activity_duration_min"),
    rehabDone = json.optNullableBoolean("rehab_done"),
    otherSymptoms = json.optString("other_symptoms"),
    workIntensity = json.optString("work_intensity"),
    familyStress = json.optNullableInt("family_stress"),
    wifeConflictCount = json.optNullableInt("wife_conflict_count"),
    wifeConflictSchool = json.optNullableBoolean("wife_conflict_school"),
    wifeConflictChores = json.optNullableBoolean("wife_conflict_chores"),
    wifeConflictOther = json.optNullableBoolean("wife_conflict_other"),
    homeOffice = json.optNullableBoolean("home_office"),
    aloneHome = json.optNullableBoolean("alone_home"),
    homeworkDone = json.optNullableBoolean("homework_done"),
    homeworkStatus = json.optNullableString("homework_status"),
  )
}.getOrNull()

private fun JSONObject.optNullableString(name: String): String? =
  if (isNull(name)) null else optString(name)

private fun JSONObject.optNullableBoolean(name: String): Boolean? =
  if (isNull(name)) null else optBoolean(name)

private fun JSONObject.optNullableInt(name: String): Int? =
  if (isNull(name)) null else optInt(name)

private fun JSONObject.optStringList(name: String): List<String> {
  val array = optJSONArray(name) ?: return emptyList()
  return (0 until array.length()).mapNotNull { index -> array.optString(index).takeIf(String::isNotBlank) }
}

private fun LifeLoadEntry.applyTo(actions: LifeLoadUiActions) {
  actions.onDiaryChanged(diaryText)
  actions.onTagsChanged(tags.joinToString(","))
  actions.onBooleanField("sleep_ok", sleepOk)
  actions.onBooleanField("nutrition_ok", nutritionOk)
  actions.onStringField("alcohol", alcohol.orEmpty())
  actions.onBooleanField("binge", binge)
  actions.onIntField("mood", mood)
  actions.onIntField("stress", stress)
  actions.onIntField("energy", energy)
  actions.onIntField("coffee_cups", coffeeCups)
  actions.onIntField("foot_pain", footPain)
  actions.onIntField("shoulder_pain", shoulderPain)
  actions.onBooleanField("migraine_warning", migraineWarning)
  actions.onBooleanField("decompression_done", decompressionDone)
  actions.onBooleanField("after_work_decompression_done", afterWorkDecompressionDone)
  actions.onBooleanField("evening_chain_broken", eveningChainBroken)
  actions.onBooleanField("shutdown_done", shutdownDone)
  actions.onBooleanField("phone_after_21", phoneAfter21)
  actions.onBooleanField("project_overrun", projectOverrun)
  actions.onStringField("activity_types", activityTypes.ifEmpty { listOf(primaryActivityType) }.filter(String::isNotBlank).joinToString(","))
  actions.onIntField("activity_duration_min", activityDurationMin)
  actions.onBooleanField("rehab_done", rehabDone)
  actions.onStringField("other_symptoms", otherSymptoms)
  actions.onStringField("work_intensity", workIntensity)
  actions.onIntField("family_stress", familyStress)
  actions.onIntField("wife_conflict_count", wifeConflictCount)
  actions.onBooleanField("wife_conflict_school", wifeConflictSchool)
  actions.onBooleanField("wife_conflict_chores", wifeConflictChores)
  actions.onBooleanField("wife_conflict_other", wifeConflictOther)
  actions.onBooleanField("home_office", homeOffice)
  actions.onBooleanField("alone_home", aloneHome)
  actions.onStringField("homework_done", homeworkStatus ?: when (homeworkDone) {
    true -> "yes"
    false -> "no"
    null -> ""
  })
  actions.onStringField("diary_summary", diarySummary)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MoreSignalsCard(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  mode: CompassMode,
  expandMissingSignals: Boolean = false,
) {
  val entry = state.draftEntry
  val missing = missingFieldsForProfile(state)
  val activeFields = activeLegacyFieldKeys(state)
  val weekend = isWeekendDate(state.selectedDate)
  var movement by rememberSaveable { mutableStateOf(false) }
  var recovery by rememberSaveable { mutableStateOf(false) }
  var pain by rememberSaveable { mutableStateOf(false) }
  var mood by rememberSaveable { mutableStateOf(false) }
  var work by rememberSaveable { mutableStateOf(false) }
  var tags by rememberSaveable { mutableStateOf(false) }
  LaunchedEffect(expandMissingSignals, state.selectedDate) {
    if (expandMissingSignals) {
      movement = "movement" in missing
      pain = "pain" in missing
      mood = "stress" in missing || "energy" in missing
      recovery = false
      work = false
      tags = false
    }
  }

  Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("daily-more-signals")) {
    if (activeFields.hasAny(MovementFieldKeys)) {
      ExpandableCompassSection(stringResource(R.string.compass_movement), movementSummary(entry), movement, "daily-more-movement-summary", { movement = !movement }, summaryColor = movementSummaryColor(entry)) {
        if ("primary_activity_type" in activeFields) {
          ActivityTypesField(entry = entry, actions = actions, highlightMissing = expandMissingSignals && "movement" in missing)
        }
        if ("activity_duration_min" in activeFields) {
          SegmentedField(
            label = stringResource(R.string.field_movement_minutes_label),
            selected = entry.activityDurationMin?.toString() ?: "unknown",
            options = listOf("unknown", "0", "10", "20", "30", "45", "60").map { it to if (it == "unknown") stringResource(R.string.unknown) else it },
            tagPrefix = "daily-activity-minutes",
            mode = mode,
            help = MovementMinutesHelp,
            highlightMissing = expandMissingSignals && "movement" in missing && entry.activityDurationMin == null,
          ) { actions.onIntField("activity_duration_min", it.toIntOrNull()) }
        }
      }
    }

    if (activeFields.hasAny(RecoveryFieldKeys)) {
      ExpandableCompassSection(stringResource(R.string.compass_evening_risk), recoverySummary(entry), recovery, "daily-more-recovery-summary", { recovery = !recovery }, summaryColor = recoverySummaryColor(entry)) {
        if ("rehab_done" in activeFields) {
          ternary(RehabHelp, stringResource(R.string.field_rehab_label), entry.rehabDone, "daily-rehab-done", "rehab_done", actions, mode)
        }
        if ("decompression_done" in activeFields) {
          ternary(DecompressionHelp, stringResource(R.string.field_decompression_label), entry.decompressionDone, "daily-decompression-done", "decompression_done", actions, mode)
        }
        if ("shutdown_done" in activeFields) {
          ternary(ShutdownHelp, stringResource(R.string.field_shutdown_label), entry.shutdownDone, "daily-shutdown-done", "shutdown_done", actions, mode)
        }
        if ("phone_after_21" in activeFields) {
          ternary(PhoneHelp, stringResource(R.string.field_phone_after_21_label), entry.phoneAfter21, "daily-phone-after-21", "phone_after_21", actions, mode, riskYes = true)
        }
        if ("project_overrun" in activeFields) {
          ternary(ProjectOverrunHelp, stringResource(R.string.field_project_overrun_label), entry.projectOverrun, "daily-project-overrun", "project_overrun", actions, mode, riskYes = true)
        }
      }
    }

    if (activeFields.hasAny(PainFieldKeys)) {
      ExpandableCompassSection(stringResource(R.string.compass_pain), painSummary(entry), pain, "daily-more-pain-summary", { pain = !pain }, summaryColor = painSummaryColor(entry)) {
        if ("foot_pain" in activeFields) {
          IntensitySliderField(stringResource(R.string.field_foot_pain_label), entry.footPain, "daily-pain-foot-slider", mode = mode, help = FootPainHelp, highlightMissing = expandMissingSignals && "pain" in missing && entry.footPain == null) { actions.onIntField("foot_pain", it) }
        }
        if ("shoulder_pain" in activeFields) {
          IntensitySliderField(stringResource(R.string.field_shoulder_pain_label), entry.shoulderPain, "daily-pain-shoulder-slider", mode = mode, help = ShoulderPainHelp, highlightMissing = expandMissingSignals && "pain" in missing && entry.shoulderPain == null) { actions.onIntField("shoulder_pain", it) }
        }
        if ("migraine_warning" in activeFields) {
          ternary(MigraineHelp, stringResource(R.string.field_migraine_label), entry.migraineWarning, "daily-migraine", "migraine_warning", actions, mode, riskYes = true)
        }
        if ("other_symptoms" in activeFields) {
          CompassTextField(stringResource(R.string.field_other_symptoms_label), entry.otherSymptoms, "daily-other-symptoms") { actions.onStringField("other_symptoms", it) }
        }
      }
    }

    if (activeFields.hasAny(MoodFieldKeys)) {
      ExpandableCompassSection(stringResource(R.string.compass_mood_stress), moodSummary(entry), mood, "daily-more-mood-summary", { mood = !mood }, summaryColor = moodSummaryColor(entry)) {
        if ("mood" in activeFields) {
          IntensitySliderField(stringResource(R.string.field_mood_label), entry.mood, "daily-mood-slider", mode = mode, help = MoodHelp, highlightMissing = expandMissingSignals && entry.mood == null) { actions.onIntField("mood", it) }
        }
        if ("stress" in activeFields) {
          IntensitySliderField(stringResource(R.string.field_stress_label), entry.stress, "daily-stress-slider", mode = mode, help = StressHelp, highlightMissing = expandMissingSignals && "stress" in missing) { actions.onIntField("stress", it) }
        }
        if ("energy" in activeFields) {
          IntensitySliderField(stringResource(R.string.field_energy_label), entry.energy, "daily-energy-slider", mode = mode, help = EnergyHelp, highlightMissing = expandMissingSignals && "energy" in missing) { actions.onIntField("energy", it) }
        }
        if ("coffee_cups" in activeFields) {
          CountStepper(stringResource(R.string.field_coffee_label), entry.coffeeCups, "daily-coffee-stepper", mode = mode, help = CoffeeHelp) { actions.onIntField("coffee_cups", it) }
        }
      }
    }

    if (activeFields.hasAny(WorkFamilyFieldKeys)) {
      ExpandableCompassSection(stringResource(R.string.compass_work_family), workSummary(entry, weekend), work, "daily-more-work-summary", { work = !work }, summaryColor = workSummaryColor(entry, weekend)) {
        if ("work_intensity" in activeFields) {
          SegmentedField(
            label = stringResource(R.string.field_work_intensity_label),
            selected = entry.workIntensity.ifBlank { "unknown" },
            options = listOf(
              "unknown" to stringResource(R.string.unknown),
              "low" to stringResource(R.string.low),
              "normal" to stringResource(R.string.normal),
              "heavy" to stringResource(R.string.heavy),
            ),
            tagPrefix = "daily-work-intensity",
            mode = mode,
            riskValues = setOf("heavy"),
            help = WorkIntensityHelp,
          ) { actions.onStringField("work_intensity", if (it == "unknown") "" else it) }
        }
        if ("home_office" in activeFields) {
          ternary(HomeOfficeHelp, stringResource(R.string.field_home_office_label), entry.homeOffice, "daily-home-office", "home_office", actions, mode)
        }
        if ("family_stress" in activeFields) {
          SegmentedField(
            label = stringResource(R.string.field_family_stress_label),
            selected = familyStressChoice(entry.familyStress),
            options = listOf("unknown" to stringResource(R.string.unknown), "low" to stringResource(R.string.low), "normal" to stringResource(R.string.normal), "high" to stringResource(R.string.high)),
            tagPrefix = "daily-family-stress",
            mode = mode,
            riskValues = setOf("high"),
            help = FamilyStressHelp,
          ) { actions.onIntField("family_stress", familyStressValue(it)) }
        }
        if ("wife_conflict_count" in activeFields) {
          SegmentedField(
            label = stringResource(R.string.field_relationship_tension_label),
            selected = wifeConflictChoice(entry.wifeConflictCount),
            options = listOf("0", "1", "2", "3", "4+").map { it to it },
            tagPrefix = "daily-relationship-stress",
            mode = mode,
            riskValues = setOf("2", "3", "4+"),
            help = RelationshipTensionHelp,
          ) { actions.onIntField("wife_conflict_count", if (it == "4+") 4 else it.toIntOrNull()) }
        }
        if ("alone_home" in activeFields) {
          ternary(AloneHomeHelp, stringResource(R.string.field_alone_home_label), entry.aloneHome, "daily-alone-home", "alone_home", actions, mode, riskYes = true)
        }
        if ("wife_conflict_school" in activeFields) {
          ternary(SchoolConflictHelp, stringResource(R.string.field_school_conflict_label), entry.wifeConflictSchool, "daily-school-conflict", "wife_conflict_school", actions, mode, riskYes = true)
        }
        if ("wife_conflict_chores" in activeFields) {
          ternary(ChoresConflictHelp, stringResource(R.string.field_chores_conflict_label), entry.wifeConflictChores, "daily-chores-conflict", "wife_conflict_chores", actions, mode, riskYes = true)
        }
        if ("homework_done" in activeFields || "homework_status" in activeFields) {
          SegmentedField(
            label = stringResource(R.string.field_homework_label),
            selected = homeworkChoice(entry.homeworkDone, entry.homeworkStatus),
            options = listOf("unknown" to stringResource(R.string.unknown), "yes" to stringResource(R.string.yes), "no" to stringResource(R.string.no), "na" to stringResource(R.string.na)),
            tagPrefix = "daily-homework",
            mode = mode,
            help = HomeworkHelp,
          ) { actions.onStringField("homework_done", if (it == "na") "na" else it) }
        }
        if (weekend) {
          Text(
            stringResource(R.string.weekend_context_optional),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
          )
        }
      }
    }

    ExpandableCompassSection(stringResource(R.string.compass_tags), tagsSummary(entry), tags, "daily-more-tags-summary", { tags = !tags }, summaryColor = tagsSummaryColor(entry)) {
      CompassTextField(stringResource(R.string.compass_tags), entry.tags.joinToString(", "), "daily-tags-input") { actions.onTagsChanged(it) }
      if (entry.tags.isEmpty()) Text(stringResource(R.string.compass_no_tags), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ActivityTypesField(entry: LifeLoadEntry, actions: LifeLoadUiActions, highlightMissing: Boolean) {
  val selectedTypes = entry.activityTypes.ifEmpty { listOfNotNull(entry.primaryActivityType.takeIf(String::isNotBlank)) }
  val options = listOf(
    "walk" to stringResource(R.string.option_walk),
    "bike" to stringResource(R.string.option_bike),
    "run" to stringResource(R.string.option_run),
    "crossfit" to stringResource(R.string.option_crossfit),
    "rehab" to stringResource(R.string.option_rehab),
    "meditation" to stringResource(R.string.option_meditation),
    "other" to stringResource(R.string.option_other),
  )
  Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.testTag("daily-activity-types")) {
    Text(stringResource(R.string.field_activity_type_label), color = if (highlightMissing) compassAmber() else MaterialTheme.colorScheme.onSurface)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      options.forEach { (value, label) ->
        val selected = value in selectedTypes
        FilterChip(
          selected = selected,
          onClick = {
            val activeTypes = selectedTypes.filterNot { it == "none" }
            val next = if (selected) activeTypes - value else activeTypes + value
            actions.onStringField("activity_types", next.joinToString(","))
          },
          label = { Text(label) },
          modifier = Modifier.testTag("daily-activity-type-$value"),
        )
      }
      FilterChip(
        selected = "none" in selectedTypes,
        onClick = { actions.onStringField("activity_types", "none") },
        label = { Text(stringResource(R.string.none)) },
        modifier = Modifier.testTag("daily-activity-type-none"),
      )
    }
  }
}

@Composable
private fun FormulaCompassCard(state: LifeLoadUiState, mode: CompassMode) {
  val visibleWhy = state.score.why.filter { supportReasonActive(it, activeLegacyFieldKeys(state)) }
  CompassCard(stringResource(R.string.compass_why_this_suggestion), tag = "formula-card") {
    if (mode.showsOperatorData()) {
      val riskLevel = state.score.zone.ifBlank { stringResource(R.string.operator_unknown) }
      Text(stringResource(R.string.compass_risk_level_mode, riskLevel, state.score.mode.ifBlank { "unknown" }))
    }
    if (visibleWhy.isEmpty()) {
      Text(stringResource(R.string.compass_add_details_for_guidance), color = MaterialTheme.colorScheme.onSurfaceVariant)
    } else {
      visibleWhy.take(if (mode.showsOperatorData()) 8 else 3).forEach {
        Text("• $it")
      }
    }
    if (state.score.profileEffects.isNotEmpty()) {
      Text(stringResource(R.string.profile_effects), fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
      state.score.profileEffects.take(if (mode.showsOperatorData()) 8 else 3).forEach {
        Text("• $it", color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
      if (mode.showsOperatorData()) {
        Text(
          stringResource(
            R.string.profile_score_provenance,
            state.score.baseScore,
            state.score.profileAdjustedScore,
            state.score.guidanceMediumThreshold,
            state.score.guidanceHighThreshold,
          ),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
      }
    }
    if (mode.showsOperatorData()) {
      Text(stringResource(R.string.compass_operator_formula_version, state.formulaContract.scoringContractVersion.ifBlank { stringResource(R.string.operator_unknown) }), color = MaterialTheme.colorScheme.onSurfaceVariant)
      state.formulaContract.sections.take(4).forEach { section ->
        Text(section.title, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
        section.items.take(5).forEach { Text("${it.input}: ${it.effect}", color = MaterialTheme.colorScheme.onSurfaceVariant) }
      }
    }
  }
}

@Composable
private fun HumanSystemStatusCard(state: LifeLoadUiState, mode: CompassMode) {
  CompassCard(stringResource(R.string.legacy_system_status), tag = "system-status-card", debug = mode.showsOperatorData()) {
    val status = dailyStatus(state)
    Text(if (mode.showsOperatorData()) status.technical.ifBlank { status.label } else status.label)
    Text(status.detail, color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (mode.showsOperatorData()) {
      Text(stringResource(R.string.compass_operator_backend, state.statusLights.backend.name))
      Text(stringResource(R.string.compass_operator_database, state.statusLights.db.name))
      Text(stringResource(R.string.compass_operator_sync, state.statusLights.sync.name))
      Text(stringResource(R.string.compass_operator_local_counts, state.localDebug.entryCount, state.localDebug.outboxCount, state.localDebug.conflictCount))
    }
  }
}

private fun humanSystemStatusVisible(state: LifeLoadUiState, mode: CompassMode): Boolean {
  if (mode.showsOperatorData()) return true
  return state.error.isNotBlank() ||
    state.localDebug.pendingApprovalCount > 0 ||
    state.localDebug.outboxCount > 0 ||
    state.localDebug.conflictCount > 0
}

@Composable
private fun CollapsedSignalsSummary(state: LifeLoadUiState, onDetails: () -> Unit) {
  val entry = state.draftEntry
  val activeFields = activeLegacyFieldKeys(state)
  CompassCard(stringResource(R.string.compass_detailed_signals), tag = "daily-detailed-signals-summary") {
    Text(stringResource(R.string.compass_detailed_signals_helper), color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (activeFields.hasAny(MovementFieldKeys)) {
      Text(stringResource(R.string.compass_movement_summary, movementSummary(entry)))
    }
    if (activeFields.hasAny(RecoveryFieldKeys)) {
      Text(stringResource(R.string.compass_evening_risk_summary, recoverySummary(entry)))
    }
    if (activeFields.hasAny(MoodFieldKeys)) {
      Text(stringResource(R.string.compass_mood_stress_summary, moodSummary(entry)))
    }
    TextButton(onClick = onDetails, modifier = Modifier.testTag("daily-quick-checkin-button")) {
      Text(stringResource(R.string.compass_open_details))
    }
  }
}

@Composable
private fun ternary(help: FieldHelpSpec, label: String, value: Boolean?, tagPrefix: String, field: String, actions: LifeLoadUiActions, mode: CompassMode, riskYes: Boolean = false) {
  SegmentedField(
    label = label,
    selected = booleanChoice(value),
    options = yesNoUnknownOptions(),
    tagPrefix = tagPrefix,
    mode = mode,
    riskValues = if (riskYes) setOf("yes") else emptySet(),
    positiveValues = setOf("yes"),
    cautionValues = if (!riskYes) setOf("no") else emptySet(),
    help = help,
  ) { actions.onBooleanField(field, yesNoUnknownValue(it)) }
}

@Composable
private fun yesNoUnknownOptions(): List<Pair<String, String>> =
  listOf("unknown" to stringResource(R.string.unknown), "yes" to stringResource(R.string.yes), "no" to stringResource(R.string.no))

private val SleepHelp = FieldHelpSpec(
  fieldKey = "sleep_on_time",
  label = "Did you sleep on time?",
  shortHelper = "Close enough to your intended bedtime.",
  longHelper = "Choose Yes if you went to sleep close enough to your intended bedtime. Choose No if bedtime was clearly late or disrupted.",
  yesMeaning = "Bedtime was close enough to the plan.",
  noMeaning = "Bedtime was clearly late, disrupted, or recovery-relevant.",
  internalFieldName = "sleep_ok",
)

private val FoodHelp = FieldHelpSpec(
  fieldKey = "food_on_track",
  label = "Did food stay on track?",
  shortHelper = "Close enough to the way you intended to eat today.",
  longHelper = "Choose Yes if food was broadly aligned with the way you intended to eat today. Choose No if eating felt clearly off-track or recovery-relevant.",
  yesMeaning = "Food broadly matched your intended eating pattern.",
  noMeaning = "Food was clearly off-track or relevant for recovery/load.",
  internalFieldName = "nutrition_ok",
)

private val AlcoholHelp = FieldHelpSpec(
  fieldKey = "alcohol_today",
  label = "Alcohol today?",
  shortHelper = "Use At home for drinking outside a social setting.",
  longHelper = "Choose None for no alcohol, Social for alcohol in a social setting, and At home for drinking outside a social setting.",
  internalFieldName = "alcohol",
)

private val EatingEpisodeHelp = FieldHelpSpec(
  fieldKey = "eating_episode",
  label = "Any eating episode to flag?",
  shortHelper = "Only mark this if it feels relevant for recovery or load.",
  longHelper = "Use this for a loss-of-control, overeating, or recovery-relevant eating event. Choose No if nothing like that happened.",
  yesMeaning = "A recovery-relevant eating event happened.",
  noMeaning = "Nothing like that happened.",
  internalFieldName = "binge",
)

private val MovementTypeHelp = FieldHelpSpec(
  fieldKey = "movement_type",
  label = "What kind of movement?",
  shortHelper = "Pick the main movement signal for today.",
  longHelper = "Choose the movement that best represents the day. Use None if there was no meaningful movement.",
  internalFieldName = "primary_activity_type",
)

private val MovementMinutesHelp = FieldHelpSpec(
  fieldKey = "movement_minutes",
  label = "Roughly how long?",
  shortHelper = "Approximate is fine.",
  longHelper = "Choose the closest duration. Pick Not sure if you do not know.",
  internalFieldName = "activity_duration_min",
)

private val RehabHelp = FieldHelpSpec(
  fieldKey = "rehab_done",
  label = "Did you do rehab/prehab?",
  shortHelper = "Any planned body maintenance counts.",
  longHelper = "Choose Yes if you did rehab, prehab, mobility, or body-maintenance work. Choose No if it was planned or useful but did not happen.",
  yesMeaning = "Rehab or prehab happened.",
  noMeaning = "It did not happen.",
  internalFieldName = "rehab_done",
)

private val DecompressionHelp = FieldHelpSpec(
  fieldKey = "decompression_done",
  label = "Did you decompress after work?",
  shortHelper = "A short transition before family/evening mode.",
  longHelper = "Choose Yes if you had a short transition before family or evening mode. Choose No if work/load carried straight into the evening.",
  yesMeaning = "You had a real transition.",
  noMeaning = "There was no useful transition.",
  internalFieldName = "decompression_done",
)

private val ShutdownHelp = FieldHelpSpec(
  fieldKey = "shutdown",
  label = "Did you intentionally end the day?",
  shortHelper = "A clear stop point for work, projects, or screens.",
  longHelper = "Choose Yes if you deliberately stopped work, projects, or screen activity and shifted into recovery. Choose No if the evening drifted without a clear stop.",
  yesMeaning = "There was a clear stop point.",
  noMeaning = "The evening drifted without a clear stop.",
  internalFieldName = "shutdown_done",
)

private val PhoneHelp = FieldHelpSpec(
  fieldKey = "phone_after_21",
  label = "Phone after 21:00?",
  shortHelper = "Only count non-essential scrolling or browsing.",
  longHelper = "Choose Yes for non-essential scrolling or browsing after 21:00. Choose No if phone use was avoided or only essential.",
  yesMeaning = "Non-essential phone use happened after 21:00.",
  noMeaning = "No recovery-relevant phone use after 21:00.",
  internalFieldName = "phone_after_21",
)

private val ProjectOverrunHelp = FieldHelpSpec(
  fieldKey = "project_overrun",
  label = "Did a project run too late?",
  shortHelper = "Personal or work project spilling into recovery time.",
  longHelper = "Choose Yes if a work or personal project extended into time you meant to keep for recovery, sleep, or family. Choose No if it stayed within reasonable bounds.",
  yesMeaning = "A project spilled into recovery time.",
  noMeaning = "Projects stayed within reasonable bounds.",
  internalFieldName = "project_overrun",
)

private val FootPainHelp = FieldHelpSpec("foot_pain", "Foot pain today", "None -> severe. 5+ means reduce impact/load.", internalFieldName = "foot_pain")
private val ShoulderPainHelp = FieldHelpSpec("shoulder_pain", "Shoulder pain today", "None -> severe.", internalFieldName = "shoulder_pain")
private val MigraineHelp = FieldHelpSpec("migraine", "Migraine signal today?", "Any migraine warning or active migraine signal.", yesMeaning = "Migraine warning or symptoms were present.", noMeaning = "No migraine signal.", internalFieldName = "migraine_warning")
private val MoodHelp = FieldHelpSpec("mood", "How was your mood?", "Very low -> very good", internalFieldName = "mood")
private val StressHelp = FieldHelpSpec("stress", "How stressed did you feel?", "Calm -> extreme", internalFieldName = "stress")
private val EnergyHelp = FieldHelpSpec("energy", "How much energy did you have?", "Empty -> strong", internalFieldName = "energy")
private val CoffeeHelp = FieldHelpSpec("coffee", "How many coffees?", "Approximate is fine.", internalFieldName = "coffee_cups")
private val WorkIntensityHelp = FieldHelpSpec("work_intensity", "How intense was work?", "Use the closest overall work-load level.", internalFieldName = "work_intensity")
private val HomeOfficeHelp = FieldHelpSpec("home_office", "Did you work from home?", internalFieldName = "home_office")
private val FamilyStressHelp = FieldHelpSpec("family_stress", "Home/family stress", "Choose the closest level for the day.", internalFieldName = "family_stress")
private val RelationshipTensionHelp = FieldHelpSpec("relationship_tension", "Relationship tension moments", "Small or large moments that affected your load.", internalFieldName = "wife_conflict_count")
private val AloneHomeHelp = FieldHelpSpec("alone_home", "Were you alone at home for a meaningful stretch?", internalFieldName = "alone_home")
private val SchoolConflictHelp = FieldHelpSpec("school_conflict", "Conflict about school/homework?", internalFieldName = "wife_conflict_school")
private val ChoresConflictHelp = FieldHelpSpec("chores_conflict", "Conflict about chores?", internalFieldName = "wife_conflict_chores")
private val HomeworkHelp = FieldHelpSpec(
  fieldKey = "homework_handled",
  label = "Homework handled?",
  shortHelper = "Whether homework was handled enough for the day.",
  longHelper = "Choose Yes if homework was handled enough. Choose No if it remained unresolved or created load. Choose N/A if homework was not relevant today.",
  yesMeaning = "Homework was handled enough.",
  noMeaning = "Homework was unresolved or created load.",
  unknownMeaning = "Choose Not sure if you do not know or do not want to decide.",
  internalFieldName = "homework_done",
)

private fun yesNoUnknownValue(value: String): Boolean? = when (value) {
  "yes" -> true
  "no" -> false
  else -> null
}

private fun movementSummary(entry: LifeLoadEntry): String = when {
  entry.activityTypes.isEmpty() && entry.primaryActivityType.isBlank() -> "Not set"
  entry.activityDurationMin == null -> "${movementTypesLabel(entry)} · minutes unknown"
  else -> "${movementTypesLabel(entry)} · ${entry.activityDurationMin} min"
}

private fun movementTypesLabel(entry: LifeLoadEntry): String =
  entry.activityTypes.ifEmpty { listOfNotNull(entry.primaryActivityType.takeIf(String::isNotBlank)) }.joinToString(" + ")

private fun recoverySummary(entry: LifeLoadEntry): String {
  val risks = buildList {
    if (entry.phoneAfter21 == true) add("phone late")
    if (entry.projectOverrun == true) add("project overrun")
    if (entry.shutdownDone == false) add("shutdown missed")
  }
  if (risks.isNotEmpty()) return risks.joinToString(" · ")
  val known = listOf(entry.rehabDone, entry.decompressionDone, entry.shutdownDone, entry.phoneAfter21, entry.projectOverrun).count { it != null }
  return if (known == 0) "Evening risk not set" else "No evening risk marked"
}

private fun painSummary(entry: LifeLoadEntry): String = when {
  (entry.footPain ?: 0) >= 5 || (entry.shoulderPain ?: 0) >= 5 -> "High pain marked"
  entry.footPain == null && entry.shoulderPain == null -> "Pain not set"
  entry.footPain == null || entry.shoulderPain == null -> "Pain details incomplete"
  else -> "No high pain marked"
}

private fun moodSummary(entry: LifeLoadEntry): String =
  when {
    entry.mood == null && entry.stress == null && entry.energy == null -> "Not set"
    entry.stress == null && entry.energy == null -> "Stress not set · energy not set"
    else -> "Stress ${entry.stress?.toString() ?: "not set"} · energy ${entry.energy?.toString() ?: "not set"}"
  }

@Composable
private fun workSummary(entry: LifeLoadEntry, weekend: Boolean): String {
  if (weekend && weekendWorkFamilyUnset(entry)) {
    return stringResource(R.string.weekend_context_summary)
  }
  val parts = buildList {
    add(if (entry.workIntensity.isBlank()) "Work unknown" else "${entry.workIntensity} work")
    if (entry.homeOffice == true) add("home office yes")
    if ((entry.familyStress ?: 0) >= 7) add("family stress high")
    if ((entry.wifeConflictCount ?: 0) > 0) add("relationship stress ${entry.wifeConflictCount}")
  }
  return parts.joinToString(" · ")
}

private fun tagsSummary(entry: LifeLoadEntry): String =
  if (entry.tags.isEmpty()) "Empty" else "${entry.tags.size} tags"

@Composable
private fun movementSummaryColor(entry: LifeLoadEntry) =
  if (entry.primaryActivityType.isBlank()) compassGray() else compassBlue()

@Composable
private fun recoverySummaryColor(entry: LifeLoadEntry) =
  if (entry.phoneAfter21 == true || entry.projectOverrun == true || entry.shutdownDone == false) compassAmber()
  else if (listOf(entry.rehabDone, entry.decompressionDone, entry.shutdownDone, entry.phoneAfter21, entry.projectOverrun).all { it == null }) compassGray()
  else compassGreen()

@Composable
private fun painSummaryColor(entry: LifeLoadEntry) =
  if ((entry.footPain ?: 0) >= 5 || (entry.shoulderPain ?: 0) >= 5) compassAmber()
  else if (entry.footPain == null || entry.shoulderPain == null) compassGray()
  else compassGreen()

@Composable
private fun moodSummaryColor(entry: LifeLoadEntry) =
  if ((entry.stress ?: 0) >= 7 || (entry.energy ?: 10) <= 3) compassAmber()
  else if (entry.mood == null && entry.stress == null && entry.energy == null) compassGray()
  else compassBlue()

@Composable
private fun workSummaryColor(entry: LifeLoadEntry, weekend: Boolean) =
  if (entry.workIntensity in setOf("heavy", "extreme") || (entry.familyStress ?: 0) >= 7 || (entry.wifeConflictCount ?: 0) > 0) compassAmber()
  else if (weekend && weekendWorkFamilyUnset(entry)) compassGray()
  else if (entry.workIntensity.isBlank()) compassGray()
  else compassBlue()

private fun weekendWorkFamilyUnset(entry: LifeLoadEntry): Boolean =
  (entry.workIntensity.isBlank() || entry.workIntensity == "normal") &&
    entry.homeOffice == null &&
    entry.familyStress == null &&
    entry.wifeConflictCount == null &&
    entry.wifeConflictSchool == null &&
    entry.wifeConflictChores == null &&
    entry.wifeConflictOther == null &&
    entry.aloneHome == null &&
    (entry.homeworkStatus == null || entry.homeworkStatus == "na") &&
    entry.homeworkDone == null

private fun isWeekendDate(date: String): Boolean {
  val day = runCatching { LocalDate.parse(date) }.getOrNull() ?: return false
  return day.dayOfWeek == DayOfWeek.SATURDAY || day.dayOfWeek == DayOfWeek.SUNDAY
}

@Composable
private fun tagsSummaryColor(entry: LifeLoadEntry) =
  if (entry.tags.isEmpty()) compassGray() else compassBlue()

private fun familyStressChoice(value: Int?): String = when {
  value == null -> "unknown"
  value <= 3 -> "low"
  value <= 6 -> "normal"
  else -> "high"
}

private fun familyStressValue(value: String): Int? = when (value) {
  "low" -> 2
  "normal" -> 5
  "high" -> 8
  else -> null
}

private fun wifeConflictChoice(value: Int?): String = when {
  value == null || value <= 0 -> "0"
  value >= 4 -> "4+"
  else -> value.toString()
}
