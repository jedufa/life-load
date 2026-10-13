@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package com.life.lifeload.ui.compass

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.life.lifeload.R
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadTrendPoint
import com.life.lifeload.ui.LifeLoadUiActions
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.approvedWeeklyHistoryDays
import com.life.lifeload.ui.isCheckInSaved
import com.life.lifeload.ui.visibleDashboardHistoryDays
import com.life.lifeload.ui.weeklyReviewSnapshot
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

private const val MIN_GUIDANCE_APPROVED_DAYS = 3
private const val GUIDANCE_LOOKBACK_DAYS = 10

fun LazyListScope.compassWeekItems(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  mode: CompassMode,
) {
  item {
    WeeklyHeroCard(state = state, mode = mode)
  }
  item {
    WeeklyDriversCard(state = state, mode = mode)
  }
  item {
    WeeklyTrendCard(state = state, actions = actions, mode = mode)
  }
  item {
    WeeklyWatchNextCard(state = state)
  }
  item {
    WeeklyWhyThisMattersCard()
  }
  item {
    WeeklyDataCard(state = state, mode = mode)
  }
  if (mode.showsDetails()) {
    item {
      WeeklyRecentPatternCard(state = state)
    }
    item {
      WeeklyBadgesCard()
    }
  }
  if (mode.showsDetails()) {
    item {
      RecentDaysCard(state = state, mode = mode)
    }
  }
}

@Composable
private fun WeeklyHeroCard(state: LifeLoadUiState, mode: CompassMode) {
  val approvedDayCount = recentGuidanceApprovedDayCount(state)
  val drift = state.dashboard.drift
  val rawRisk = drift?.riskLevel?.ifBlank { state.dashboard.weekly.zone }
    ?: state.dashboard.weekly.zone.ifBlank { "unknown" }
  val risk = if (approvedDayCount >= MIN_GUIDANCE_APPROVED_DAYS && rawRisk.isUnknownGuidanceRisk()) {
    "protect"
  } else {
    rawRisk
  }
  val color = compassRiskColor(risk)
  val snapshot = weeklyReviewSnapshot(state)
  val latest = state.dashboard.trendPoints.lastOrNull()
  val improving = latest?.recoveryMomentumImproving() == true
  val headline = weeklyHeadline(risk, approvedDayCount, improving = improving)
  val action = drift?.nextAction?.ifBlank { snapshot.oneCorrection }
    ?: state.dashboard.weekly.nextAction.ifBlank { snapshot.oneCorrection }
  val userAction = readableGuidanceAction(risk, approvedDayCount, action)
  val riskLabel = if (mode.showsOperatorData()) {
    risk.ifBlank { stringResource(R.string.operator_unknown) }.uppercase(Locale.ROOT)
  } else {
    userRiskLabel(risk)
  }
  val recommendationLabel = recommendationLabel(risk, approvedDayCount)
  var riskHelpOpen by remember { mutableStateOf(false) }
  var recommendationHelpOpen by remember { mutableStateOf(false) }
  var guidanceQualityHelpOpen by remember { mutableStateOf(false) }
  val notEnoughData = approvedDayCount < MIN_GUIDANCE_APPROVED_DAYS
  val highRisk = approvedDayCount >= MIN_GUIDANCE_APPROVED_DAYS && risk.lowercase() in setOf("red", "high", "stabilize")
  val guidanceReasons = weeklyGuidanceReasons(state, approvedDayCount, mode)
  val floating = LocalCompassFloatingShell.current

  CompassCard("", tag = "weekly-hero-card", accent = color) {
    Box(
      modifier = Modifier
        .fillMaxWidth()
        .then(if (highRisk) Modifier.testTag("weekly-recovery-priority-visual") else Modifier),
    ) {
      Row(
        modifier = Modifier
          .fillMaxWidth()
          .testTag("weekly-recommendation-visual"),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        RecommendationIcon(
          label = recommendationLabel,
          color = color,
          notEnoughData = notEnoughData,
          highRisk = highRisk,
        ) {
          HeroStateIcon(
            icon = recommendationIconPainter(risk, approvedDayCount),
            label = recommendationLabel,
            color = color,
            large = floating,
          )
        }
        Text(
          recommendationLabel,
          color = MaterialTheme.colorScheme.primary,
          fontWeight = FontWeight.SemiBold,
          style = MaterialTheme.typography.titleMedium,
          modifier = Modifier
            .weight(1f)
            .clickable { recommendationHelpOpen = true },
        )
        StatusPill(riskLabel, color, "weekly-risk-status", onClick = { riskHelpOpen = true }, type = riskStatusPillType(risk, approvedDayCount))
      }
    }
    Text(headline, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.headlineSmall)
    Text(
      userAction.ifBlank { stringResource(R.string.compass_guidance_body_unknown) },
      color = MaterialTheme.colorScheme.primary,
      modifier = Modifier
        .testTag("weekly-next-action")
        .clickable { recommendationHelpOpen = true },
    )
    Text(stringResource(R.string.compass_tap_guidance_for_why), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = MaterialTheme.typography.labelSmall.fontSize)
    Text(
      stringResource(R.string.guidance_quality, weeklyConfidence(approvedDayCount)),
      color = MaterialTheme.colorScheme.onSurfaceVariant,
      modifier = Modifier
        .testTag("weekly-guidance-quality")
        .clickable { guidanceQualityHelpOpen = true },
    )
  }
  if (riskHelpOpen) {
    AlertDialog(
      onDismissRequest = { riskHelpOpen = false },
      containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFBFAF6),
      title = { Text(stringResource(R.string.compass_risk_help_title, riskLabel)) },
      text = {
        SelectionContainer {
          Column(
            modifier = Modifier
              .heightIn(max = 420.dp)
              .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp),
          ) {
            Text(stringResource(R.string.risk_help))
            Text(stringResource(R.string.compass_risk_help_body), color = MaterialTheme.colorScheme.onSurfaceVariant)
          }
        }
      },
      confirmButton = {
        TextButton(onClick = { riskHelpOpen = false }, modifier = Modifier.testTag("weekly-risk-help-close")) {
          Text(stringResource(R.string.close))
        }
      },
      modifier = Modifier.testTag("weekly-risk-help-dialog"),
    )
  }
  if (recommendationHelpOpen) {
    CompassPlusGuidanceReasonDialog(
      state = state,
      reasons = guidanceReasons,
      approvedDays = approvedDayCount,
      highRisk = highRisk,
      improving = improving,
      onDismiss = { recommendationHelpOpen = false },
    )
  }
  if (guidanceQualityHelpOpen) {
    AlertDialog(
      onDismissRequest = { guidanceQualityHelpOpen = false },
      containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFBFAF6),
      title = { Text(stringResource(R.string.guidance_quality, weeklyConfidence(approvedDayCount))) },
      text = {
        SelectionContainer {
          Column(
            modifier = Modifier
              .heightIn(max = 420.dp)
              .verticalScroll(rememberScrollState()),
          ) {
            Text(stringResource(R.string.guidance_quality_help))
          }
        }
      },
      confirmButton = {
        TextButton(onClick = { guidanceQualityHelpOpen = false }, modifier = Modifier.testTag("weekly-guidance-quality-help-close")) {
          Text(stringResource(R.string.close))
        }
      },
      modifier = Modifier.testTag("weekly-guidance-quality-help-dialog"),
    )
  }
}

@Composable
private fun HeroStateIcon(
  icon: Painter,
  label: String,
  color: Color,
  large: Boolean,
  tag: String? = null,
) {
  Box(
    modifier = Modifier
      .size(if (large) 76.dp else 60.dp)
      .background(color.copy(alpha = if (large) 0.14f else 0.11f), CircleShape)
      .semantics { contentDescription = label }
      .then(if (tag != null) Modifier.testTag(tag) else Modifier),
    contentAlignment = Alignment.Center,
  ) {
    Box(
      modifier = Modifier
        .size(if (large) 58.dp else 46.dp)
        .background(if (large) compassPlusIconCircle() else color.copy(alpha = 0.10f), CircleShape),
      contentAlignment = Alignment.Center,
    ) {
      Icon(
        painter = icon,
        contentDescription = null,
        tint = color,
        modifier = Modifier.size(if (large) 34.dp else 28.dp),
      )
    }
  }
}

@Composable
private fun CompassPlusGuidanceReasonDialog(
  state: LifeLoadUiState,
  reasons: List<String>,
  approvedDays: Int,
  highRisk: Boolean,
  improving: Boolean,
  onDismiss: () -> Unit,
) {
  var selectedReason by remember { mutableStateOf<String?>(null) }
  selectedReason?.let { reason ->
    AlertDialog(
      onDismissRequest = { selectedReason = null },
      containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFFFDF7),
      title = { Text(reason) },
      text = { Text(guidanceReasonDateText(reason, state), color = MaterialTheme.colorScheme.onSurfaceVariant) },
      confirmButton = {
        TextButton(onClick = { selectedReason = null }, modifier = Modifier.testTag("weekly-guidance-reason-date-close")) {
          Text(stringResource(R.string.close))
        }
      },
      modifier = Modifier.testTag("weekly-guidance-reason-date-dialog"),
    )
  }
  Dialog(onDismissRequest = onDismiss) {
    Card(
      modifier = Modifier
        .fillMaxWidth()
        .heightIn(max = 560.dp)
        .testTag("weekly-guidance-reason-dialog"),
      shape = RoundedCornerShape(28.dp),
      colors = CardDefaults.cardColors(containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFFFDF7)),
      elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
    ) {
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .verticalScroll(rememberScrollState())
          .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
      ) {
        Text(
          stringResource(R.string.compass_why_this_conclusion),
          style = MaterialTheme.typography.titleLarge,
          fontWeight = FontWeight.SemiBold,
        )
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
          GuidanceReasonGroup(
            title = stringResource(R.string.compass_guidance_reason_active),
            lines = guidanceReasonPrimaryLines(reasons, approvedDays, highRisk, improving),
            state = state,
            selectedReason = selectedReason,
            onSelectReason = { selectedReason = if (selectedReason == it) null else it },
          )
          GuidanceReasonGroup(
            title = stringResource(R.string.compass_guidance_reason_not_higher),
            lines = guidanceReasonWhyNotHigher(approvedDays, highRisk, improving),
            state = state,
            selectedReason = selectedReason,
            onSelectReason = { selectedReason = if (selectedReason == it) null else it },
          )
          GuidanceReasonGroup(
            title = stringResource(R.string.compass_guidance_reason_not_lower),
            lines = guidanceReasonWhyNotLower(approvedDays, highRisk, improving),
            state = state,
            selectedReason = selectedReason,
            onSelectReason = { selectedReason = if (selectedReason == it) null else it },
          )
          GuidanceReasonGroup(
            title = stringResource(R.string.compass_guidance_reason_ease),
            lines = guidanceReasonEaseLines(highRisk, improving),
            state = state,
            selectedReason = selectedReason,
            onSelectReason = { selectedReason = if (selectedReason == it) null else it },
          )
          if (reasons.isNotEmpty()) {
            GuidanceReasonGroup(
              title = stringResource(R.string.compass_guidance_reason_signals),
              lines = reasons.take(6),
              state = state,
              selectedReason = selectedReason,
              onSelectReason = { selectedReason = if (selectedReason == it) null else it },
            )
          }
        }
        TextButton(
          onClick = onDismiss,
          modifier = Modifier
            .align(Alignment.End)
            .testTag("weekly-guidance-reason-close"),
        ) {
          Text(stringResource(R.string.close), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
        }
      }
    }
  }
}

@Composable
private fun GuidanceReasonGroup(title: String, lines: List<String>) {
  GuidanceReasonGroup(title = title, lines = lines, state = null, selectedReason = null, onSelectReason = {})
}

@Composable
private fun GuidanceReasonGroup(
  title: String,
  lines: List<String>,
  state: LifeLoadUiState?,
  selectedReason: String?,
  onSelectReason: (String) -> Unit,
) {
  if (lines.isEmpty()) return
  Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
    Text(title, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
    lines.forEach { line ->
      Text(
        line,
        color = if (state == null) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary,
        modifier = if (state == null) Modifier else Modifier.clickable { onSelectReason(line) },
      )
      if (state != null && selectedReason == line) {
        Text(
          guidanceReasonDateText(line, state),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
          style = MaterialTheme.typography.bodySmall,
          modifier = Modifier.testTag("weekly-guidance-reason-dates"),
        )
      }
    }
  }
}

@Composable
private fun guidanceReasonDateText(reason: String, state: LifeLoadUiState): String {
  val dates = guidanceReasonDates(reason, state).distinct().takeLast(10)
  return if (dates.isEmpty()) {
    stringResource(R.string.compass_guidance_relevant_dates_window)
  } else {
    stringResource(R.string.compass_guidance_relevant_dates, dates.joinToString(", "))
  }
}

private fun guidanceReasonDates(reason: String, state: LifeLoadUiState): List<String> {
  val lower = reason.lowercase(Locale.ROOT)
  val trends = state.dashboard.trendPoints
  return when {
    "phone" in lower -> trends.filter { it.phoneAfter21Count7d > 0 }.map { it.date }
    "project" in lower || "spillover" in lower -> trends.filter { it.projectOverrunCount7d > 0 }.map { it.date }
    "pain" in lower -> trends.filter { it.painAvg7d >= 4.0 }.map { it.date }
    "recovery" in lower && ("improving" in lower || "easing" in lower) -> trends.filter { it.recoveryMomentumImproving() }.map { it.date }
    "recovery" in lower || "load" in lower || "margin" in lower -> trends.filter { it.lifeMargin7d < 0.0 || it.lifeLoadRollingAvg7d >= 4.0 }.map { it.date }
    "risk" in lower || "warning" in lower || "watch" in lower || "protect" in lower -> trends.filter { it.driftRiskScore >= 35.0 }.map { it.date }
    "stable" in lower -> trends.filter { it.driftRiskScore >= 0.0 && it.driftRiskScore < 35.0 }.map { it.date }
    "check-in" in lower || "data" in lower -> recentGuidanceApprovedDates(state).map { it.toString() }
    else -> state.dashboard.historyDays
      .filter { day ->
        val text = "${day.zone} ${day.nextAction} ${day.diarySummary}".lowercase(Locale.ROOT)
        lower.split(Regex("\\s+")).filter { it.length >= 5 }.any { token -> token in text }
      }
      .map { it.date }
  }
}

@Composable
private fun guidanceReasonPrimaryLines(
  reasons: List<String>,
  approvedDays: Int,
  highRisk: Boolean,
  improving: Boolean,
): List<String> = when {
  approvedDays < MIN_GUIDANCE_APPROVED_DAYS -> listOf(missingGuidanceRequirement(approvedDays))
  highRisk && improving -> listOf(stringResource(R.string.compass_guidance_recent_recovery_still_high))
  highRisk -> listOf(stringResource(R.string.compass_guidance_recent_signals_need_protection))
  improving -> listOf(stringResource(R.string.compass_guidance_recovery_improving_line), stringResource(R.string.compass_guidance_earlier_week_still_counts))
  else -> reasons.take(2)
}

@Composable
private fun guidanceReasonWhyNotHigher(
  approvedDays: Int,
  highRisk: Boolean,
  improving: Boolean,
): List<String> = when {
  approvedDays < MIN_GUIDANCE_APPROVED_DAYS -> listOf(stringResource(R.string.compass_guidance_waits_for_data))
  highRisk && improving -> listOf(stringResource(R.string.compass_guidance_improvement_protection))
  highRisk -> listOf(stringResource(R.string.compass_guidance_no_extra_severity))
  else -> listOf(stringResource(R.string.compass_guidance_no_severe_signal))
}

@Composable
private fun guidanceReasonWhyNotLower(
  approvedDays: Int,
  highRisk: Boolean,
  improving: Boolean,
): List<String> = when {
  approvedDays < MIN_GUIDANCE_APPROVED_DAYS -> listOf(stringResource(R.string.compass_guidance_not_enough_to_change))
  highRisk -> listOf(stringResource(R.string.compass_guidance_recent_recovery_priority))
  improving -> listOf(stringResource(R.string.compass_guidance_steady_days_needed))
  else -> listOf(stringResource(R.string.compass_guidance_no_stronger_warning))
}

@Composable
private fun guidanceReasonEaseLines(highRisk: Boolean, improving: Boolean): List<String> = when {
  highRisk && improving -> listOf(stringResource(R.string.compass_guidance_keep_sleep_protected))
  highRisk -> listOf(stringResource(R.string.compass_guidance_stable_evenings_ease))
  improving -> listOf(stringResource(R.string.compass_guidance_keep_recovery_margin))
  else -> listOf(stringResource(R.string.compass_guidance_more_steady_days))
}

@Composable
private fun WeeklyDriversCard(state: LifeLoadUiState, mode: CompassMode) {
  val driftSignals = state.dashboard.drift?.contributingSignals.orEmpty()
  val latest = state.dashboard.trendPoints.lastOrNull()
  val hasPhoneCount = (latest?.phoneAfter21Count7d ?: 0) > 0
  val hasProjectCount = (latest?.projectOverrunCount7d ?: 0) > 0
  val latePhoneDriver = latest?.let { latePhoneDriverCopy(it, mode) }
  val projectDriver = latest?.let { projectDriverCopy(it, mode) }
  val drivers = buildList {
    if (hasPhoneCount && latePhoneDriver != null) add(latePhoneDriver)
    if (hasProjectCount && projectDriver != null) add(projectDriver)
    driftSignals
      .filterNot { hasPhoneCount && it.contains("phone", ignoreCase = true) }
      .filterNot { hasProjectCount && it.contains("project", ignoreCase = true) }
      .take(4)
      .forEach { add(readableDriver(it)) }
    if ((latest?.painAvg7d ?: 0.0) >= 4.0) add("Pain average: ${oneDecimal(latest?.painAvg7d)}")
    if ((latest?.lifeMargin7d ?: 0.0) < 0.0) add("Recovery lower than load")
  }.distinct().take(5)

  if (LocalCompassFloatingShell.current && !mode.showsDetails()) {
    FloatingExplanationCard(
      title = stringResource(R.string.compass_main_drivers),
      body = if (drivers.isEmpty()) {
        stringResource(R.string.compass_no_weekly_drivers)
      } else {
        simpleGuidanceSummary(drivers, latest)
      },
      tag = "weekly-driver-list",
      icon = painterResource(R.drawable.ll_ic_signal_bars),
      showChevron = false,
    )
    return
  }

  CompassCard(stringResource(R.string.compass_main_drivers), tag = "weekly-driver-list") {
    if (drivers.isEmpty()) {
      Text(stringResource(R.string.compass_no_weekly_drivers), color = MaterialTheme.colorScheme.onSurfaceVariant)
    } else {
      drivers.forEach { Text("• $it") }
    }
  }
}

@Composable
private fun WeeklyWhyThisMattersCard() {
  if (LocalCompassFloatingShell.current) {
    FloatingExplanationCard(
      title = stringResource(R.string.science_note_patterns_title),
      body = stringResource(R.string.science_note_patterns_short),
      tag = "weekly-why-this-matters",
      icon = painterResource(R.drawable.ll_ic_pattern_wave),
      showChevron = false,
    )
    return
  }
  CompassCard(stringResource(R.string.science_note_patterns_title), tag = "weekly-why-this-matters") {
    Text(stringResource(R.string.science_note_patterns_short), color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun WeeklyWatchNextCard(state: LifeLoadUiState) {
  val approvedDays = recentGuidanceApprovedDayCount(state)
  val latest = state.dashboard.trendPoints.lastOrNull()
  val risk = riskQuality(latest?.driftRiskScore)
  val hasEveningRisk = (latest?.phoneAfter21Count7d ?: 0) > 0 || (latest?.projectOverrunCount7d ?: 0) > 0
  val body = when {
    approvedDays < MIN_GUIDANCE_APPROVED_DAYS -> stringResource(R.string.what_to_watch_next_body_empty)
    risk == "high" && hasEveningRisk -> stringResource(R.string.what_to_watch_next_body_high_evening)
    risk == "high" -> stringResource(R.string.what_to_watch_next_body_high_generic)
    risk == "medium" -> stringResource(R.string.what_to_watch_next_body_caution)
    else -> stringResource(R.string.what_to_watch_next_body_stable)
  }
  if (LocalCompassFloatingShell.current) {
    FloatingExplanationCard(
      title = stringResource(R.string.what_to_watch_next),
      body = body,
      tag = "weekly-watch-next",
      icon = painterResource(R.drawable.ll_ic_watch_eye),
      showChevron = false,
    )
    return
  }
  CompassCard(stringResource(R.string.what_to_watch_next), tag = "weekly-watch-next") {
    Text(body)
  }
}

@Composable
private fun WeeklyRecentPatternCard(state: LifeLoadUiState) {
  val latest = state.dashboard.trendPoints.lastOrNull()
  val phone = latest?.phoneAfter21Count7d ?: 0
  val projects = latest?.projectOverrunCount7d ?: 0
  val latePhoneDriver = latest?.let { latePhoneDriverCopy(it, CompassMode.Simple) }
  val projectDriver = latest?.let { projectDriverCopy(it, CompassMode.Simple) }
  val savedText = guidanceApprovedText(recentGuidanceApprovedDayCount(state), state.dashboard.historyDays.size)
  val items = buildList {
    if (phone > 0 && latePhoneDriver != null) add(latePhoneDriver)
    if (projects > 0 && projectDriver != null) add(projectDriver)
    add(savedText)
  }.take(5)
  CompassCard(stringResource(R.string.what_changed_recently), tag = "weekly-recent-pattern") {
    items.forEach { Text("• $it") }
  }
}

@Composable
private fun WeeklyDataCard(state: LifeLoadUiState, mode: CompassMode) {
  val approvedDayCount = recentGuidanceApprovedDayCount(state)
  if (LocalCompassFloatingShell.current && !mode.showsOperatorData()) {
    FloatingExplanationCard(
      title = stringResource(R.string.compass_data_availability),
      body = listOf(
        guidanceApprovedText(approvedDayCount, state.dashboard.historyDays.size),
        stringResource(R.string.compass_data_available_entries, state.dashboard.historyDays.size),
        reviewNeededText(state.localDebug.conflictCount),
      ).joinToString("\n"),
      tag = "weekly-data-card",
      icon = painterResource(R.drawable.ll_ic_compass_mark),
      showChevron = false,
    )
    return
  }
  CompassCard(stringResource(R.string.compass_data_availability), tag = "weekly-data-card") {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      StatusPill(guidanceApprovedText(approvedDayCount, state.dashboard.historyDays.size), if (approvedDayCount >= 5) compassGreen() else compassAmber(), type = if (approvedDayCount >= 5) StatusPillType.Positive else StatusPillType.Warning)
      StatusPill(stringResource(R.string.compass_data_available_entries, state.dashboard.historyDays.size), compassBlue(), type = StatusPillType.Info)
      StatusPill(reviewNeededText(state.localDebug.conflictCount), if (state.localDebug.conflictCount > 0) compassRed() else compassGreen(), type = if (state.localDebug.conflictCount > 0) StatusPillType.Danger else StatusPillType.Positive)
    }
    if (mode.showsOperatorData()) {
      Text(stringResource(R.string.compass_week_state, state.weeklyContext.zone.ifBlank { "unknown" }, state.weeklyContext.weekStart, state.weeklyContext.weekEnd))
      Text(stringResource(R.string.compass_backend_sync, state.statusLights.backend.name, state.statusLights.sync.name))
    }
  }
}

@Composable
private fun WeeklyBadgesCard() {
  CompassCard(stringResource(R.string.badges_title), tag = "weekly-badges-card") {
    BadgeLine(stringResource(R.string.badge_pattern_spotter), stringResource(R.string.badge_pattern_spotter_body))
    BadgeLine(stringResource(R.string.badge_no_reset), stringResource(R.string.badge_no_reset_body))
  }
}

@Composable
private fun BadgeLine(title: String, body: String) {
  Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
    Text(title, fontWeight = FontWeight.SemiBold)
    Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun FloatingExplanationCard(
  title: String,
  body: String,
  tag: String,
  icon: Painter,
  showChevron: Boolean,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag),
    shape = RoundedCornerShape(24.dp),
    colors = CardDefaults.cardColors(containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFFFDF7)),
    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
  ) {
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .padding(18.dp),
      horizontalArrangement = Arrangement.spacedBy(14.dp),
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Box(
        modifier = Modifier
          .size(56.dp)
          .background(compassPlusIconCircle(), CircleShape),
        contentAlignment = Alignment.Center,
      ) {
        Icon(painter = icon, contentDescription = null, tint = compassPlusIconTint(), modifier = Modifier.size(26.dp))
      }
      Column(
        modifier = Modifier.weight(1f),
        verticalArrangement = Arrangement.spacedBy(4.dp),
      ) {
        SelectionContainer {
          Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
            Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
          }
        }
      }
      if (showChevron) {
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
  }
}

@Composable
private fun WeeklyTrendCard(state: LifeLoadUiState, actions: LifeLoadUiActions, mode: CompassMode) {
  val latest = state.dashboard.trendPoints.lastOrNull()
  val previous = state.dashboard.trendPoints.dropLast(1).lastOrNull()
  if (!mode.showsDetails()) {
    RecentPathCard(state = state, actions = actions)
    return
  }
  val committedAnchor = recentPathAnchorDate(state)
  var previewAnchorText by rememberSaveable(committedAnchor.toString()) { mutableStateOf(committedAnchor.toString()) }
  val previewAnchor = runCatching { LocalDate.parse(previewAnchorText) }.getOrNull() ?: committedAnchor
  val pathPoints = recentPathPoints(state, previewAnchor)
  val selectedPoint = remember(pathPoints) { mutableStateOf<RecentPathPoint?>(null) }
  CompassCard(stringResource(R.string.compass_trend), tag = "weekly-trend-card") {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
      RecentPathActiveDateLabel(previewAnchor)
    }
    SelectionContainer {
      Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(weeklyTrendSentence(latest), fontWeight = FontWeight.SemiBold)
        Text(weeklyTrendExplanation(latest), color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
    RecentPathCurve(
      points = pathPoints,
      activeAnchor = previewAnchor,
      selectedPoint = selectedPoint.value,
      onSelect = { selectedPoint.value = it },
      onPreviewAnchorChanged = { previewAnchorText = it.toString() },
      onCommitShift = { days ->
        if (days != 0L) actions.onShiftDate(days)
      },
    )
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
      Text(pathPoints.firstNotNullOfOrNull { it?.dateLabel }.orEmpty(), color = MaterialTheme.colorScheme.onSurfaceVariant)
      Text(pathPoints.asReversed().firstNotNullOfOrNull { it?.dateLabel }.orEmpty(), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    RecentPathReferenceLegend()
    selectedPoint.value?.let { point ->
      SelectionContainer {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
          Text("${point.dateLabel} · ${localizedRecentPathStateLabel(point.stateLabel)}", fontWeight = FontWeight.SemiBold)
          if (point.summary.isNotBlank()) {
            Text(point.summary, color = MaterialTheme.colorScheme.onSurfaceVariant)
          }
        }
      }
    }
    if (mode.showsDetails()) {
      SelectionContainer {
        Text(stringResource(R.string.risk_help), color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      TrendStatus("Load:", trendQuality(latest?.lifeLoadRollingAvg7d, positiveGood = false), latest?.lifeLoadRollingAvg7d, previous?.lifeLoadRollingAvg7d, lowerIsBetter = true)
      TrendStatus("Recovery:", recoveryQuality(latest?.recoveryProxy()), latest?.recoveryProxy(), previous?.recoveryProxy(), lowerIsBetter = false)
      TrendStatus("Recovery margin:", recoveryMarginQuality(latest?.lifeMargin7d, simple = !mode.showsDetails()), latest?.lifeMargin7d, previous?.lifeMargin7d, lowerIsBetter = false)
      TrendStatus("Risk:", riskQuality(latest?.driftRiskScore), latest?.driftRiskScore, previous?.driftRiskScore, lowerIsBetter = true, absoluteRisk = true)
    }
    if (mode.showsDetails()) {
      SelectionContainer {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
          Text("Details: load ${oneDecimal(latest?.lifeLoadRollingAvg7d)} · recovery ${oneDecimal(latest?.recoveryProxy())} · recovery margin ${oneDecimal(latest?.lifeMargin7d)} · risk ${oneDecimal(latest?.driftRiskScore)}/100")
          Text("Sleep ${percent(latest?.sleepCompliance7d)} · Food ${percent(latest?.nutritionCompliance7d)} · Pain ${oneDecimal(latest?.painAvg7d)}")
        }
      }
    }
    if (mode.showsOperatorData()) {
      SelectionContainer {
        Text("Trend points: ${state.dashboard.trendPoints.size} · dashboard date ${state.dashboard.date}")
      }
    }
  }
}

@Composable
private fun RecentPathCard(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val committedAnchor = recentPathAnchorDate(state)
  var previewAnchorText by rememberSaveable(committedAnchor.toString()) { mutableStateOf(committedAnchor.toString()) }
  val previewAnchor = runCatching { LocalDate.parse(previewAnchorText) }.getOrNull() ?: committedAnchor
  val pathPoints = recentPathPoints(state, previewAnchor)
  val selectedPoint = remember(pathPoints) { mutableStateOf<RecentPathPoint?>(null) }
  val floating = LocalCompassFloatingShell.current
  val plottedCount = pathPoints.count { it != null }
  if (floating && plottedCount == 0) {
    RecentPathEmptyFloatingCard()
    return
  }
  if (floating) {
    Card(
      modifier = Modifier
        .fillMaxWidth()
        .testTag("weekly-trend-card"),
      shape = RoundedCornerShape(24.dp),
      colors = CardDefaults.cardColors(containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFFFDF7)),
      elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
    ) {
      Column(
        modifier = Modifier
          .fillMaxWidth()
        .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.spacedBy(12.dp),
          verticalAlignment = Alignment.CenterVertically,
        ) {
          FloatingCardIcon(painterResource(R.drawable.ll_ic_recent_path), size = 48.dp, iconSize = 24.dp)
          Text(stringResource(R.string.compass_recent_path), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
          RecentPathActiveDateLabel(previewAnchor)
        }
        SelectionContainer {
          Text(recentPathSentence(pathPoints), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        RecentPathCurve(
          points = pathPoints,
          activeAnchor = previewAnchor,
          selectedPoint = selectedPoint.value,
          onSelect = { selectedPoint.value = it },
          onPreviewAnchorChanged = { previewAnchorText = it.toString() },
          onCommitShift = { days ->
            if (days != 0L) actions.onShiftDate(days)
          },
        )
        selectedPoint.value?.let { point ->
          SelectionContainer {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
              Text("${point.dateLabel} · ${localizedRecentPathStateLabel(point.stateLabel)}", fontWeight = FontWeight.SemiBold)
              if (point.summary.isNotBlank()) {
                Text(point.summary, color = MaterialTheme.colorScheme.onSurfaceVariant)
              }
            }
          }
        }
      }
    }
    return
  }
  CompassCard(stringResource(R.string.compass_recent_path), tag = "weekly-trend-card") {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
      RecentPathActiveDateLabel(previewAnchor)
    }
    SelectionContainer {
      Text(recentPathSentence(pathPoints), fontWeight = FontWeight.SemiBold)
    }
    RecentPathCurve(
      points = pathPoints,
      activeAnchor = previewAnchor,
      selectedPoint = selectedPoint.value,
      onSelect = { selectedPoint.value = it },
      onPreviewAnchorChanged = { previewAnchorText = it.toString() },
      onCommitShift = { days ->
        if (days != 0L) actions.onShiftDate(days)
      },
    )
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
      Text(pathPoints.firstNotNullOfOrNull { it?.dateLabel }.orEmpty(), color = MaterialTheme.colorScheme.onSurfaceVariant)
      Text(pathPoints.asReversed().firstNotNullOfOrNull { it?.dateLabel }.orEmpty(), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    RecentPathReferenceLegend()
    selectedPoint.value?.let { point ->
      SelectionContainer {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
          Text("${point.dateLabel} · ${localizedRecentPathStateLabel(point.stateLabel)}", fontWeight = FontWeight.SemiBold)
          if (point.summary.isNotBlank()) {
            Text(point.summary, color = MaterialTheme.colorScheme.onSurfaceVariant)
          }
        }
      }
    }
  }
}

@Composable
private fun RecentPathActiveDateLabel(anchor: LocalDate) {
  Text(
    stringResource(R.string.compass_recent_path_through, shortDateLabel(anchor.toString())),
    color = MaterialTheme.colorScheme.onSurfaceVariant,
    style = MaterialTheme.typography.labelMedium,
    fontWeight = FontWeight.SemiBold,
    modifier = Modifier.testTag("weekly-recent-path-active-date"),
  )
}

@Composable
private fun RecentPathEmptyFloatingCard() {
  val pathAccessibility = stringResource(R.string.compass_recent_path_accessibility_empty)
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("weekly-trend-card"),
    shape = RoundedCornerShape(24.dp),
    colors = CardDefaults.cardColors(containerColor = if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFFFDF7)),
    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
  ) {
    Box(
      modifier = Modifier
        .fillMaxWidth()
        .height(230.dp)
        .padding(18.dp),
    ) {
      Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
          FloatingCardIcon(painterResource(R.drawable.ll_ic_recent_path), size = 48.dp, iconSize = 24.dp)
          Text(stringResource(R.string.compass_recent_path), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
        }
        SelectionContainer {
          Text(stringResource(R.string.compass_recent_path_empty), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Box(
          modifier = Modifier
            .fillMaxWidth()
            .height(118.dp)
            .background(if (androidx.compose.foundation.isSystemInDarkTheme()) MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.28f) else Color(0xFFFFF2E8), RoundedCornerShape(20.dp))
            .semantics { contentDescription = pathAccessibility },
          contentAlignment = Alignment.Center,
        ) {
          Text(stringResource(R.string.compass_recent_path_placeholder), color = MaterialTheme.colorScheme.onSurfaceVariant)
          Icon(
            painter = painterResource(R.drawable.ll_illustration_branch_empty),
            contentDescription = null,
            tint = compassPlusDecorativeLeaf(),
            modifier = Modifier
              .align(Alignment.BottomEnd)
              .size(88.dp),
          )
        }
      }
    }
  }
}

@Composable
private fun FloatingCardIcon(
  painter: Painter,
  size: androidx.compose.ui.unit.Dp,
  iconSize: androidx.compose.ui.unit.Dp,
) {
  Box(
    modifier = Modifier
      .size(size)
      .background(compassPlusIconCircle(), CircleShape),
    contentAlignment = Alignment.Center,
  ) {
    Icon(painter = painter, contentDescription = null, tint = compassPlusIconTint(), modifier = Modifier.size(iconSize))
  }
}

@Composable
private fun RecentPathReferenceLegend() {
  Row(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.spacedBy(12.dp),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    PathReferenceLabel(color = compassGreen(), label = stringResource(R.string.compass_recent_path_balance_line))
    PathReferenceLabel(color = compassAmber(), label = stringResource(R.string.compass_recent_path_risk_line))
  }
}

@Composable
private fun PathReferenceLabel(color: androidx.compose.ui.graphics.Color, label: String) {
  Row(
    horizontalArrangement = Arrangement.spacedBy(6.dp),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Canvas(modifier = Modifier.height(10.dp).width(26.dp)) {
      drawLine(
        color = color.copy(alpha = 0.62f),
        start = Offset(0f, size.height / 2f),
        end = Offset(size.width, size.height / 2f),
        strokeWidth = 2.2f,
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 6f), 0f),
      )
    }
    Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun RecentPathCurve(
  points: List<RecentPathPoint?>,
  activeAnchor: LocalDate,
  selectedPoint: RecentPathPoint?,
  onSelect: (RecentPathPoint) -> Unit,
  onPreviewAnchorChanged: (LocalDate) -> Unit,
  onCommitShift: (Long) -> Unit,
) {
  val floating = LocalCompassFloatingShell.current
  val stableColor = compassGreen()
  val watchColor = compassAmber()
  val priorityColor = compassRed()
  val lineColor = MaterialTheme.colorScheme.primary
  val missingColor = MaterialTheme.colorScheme.outline
  val incompleteColor = compassRed()
  val surfaceColor = MaterialTheme.colorScheme.surface
  val floatingPlotColor = Color(0xFFFFEFE2).copy(alpha = if (androidx.compose.foundation.isSystemInDarkTheme()) 0.10f else 0.70f)
  val balanceThreshold = 30.0
  val riskThreshold = 70.0
  val latestAnchor = rememberUpdatedState(activeAnchor)
  val latestPreviewChange = rememberUpdatedState(onPreviewAnchorChanged)
  val latestCommitShift = rememberUpdatedState(onCommitShift)
  var dragOffsetPx by remember { mutableFloatStateOf(0f) }
  val pathDescription = recentPathAccessibility(points)
  Canvas(
    modifier = Modifier
      .fillMaxWidth()
      .height(if (floating) 174.dp else 152.dp)
      .testTag("weekly-recent-path-curve")
      .semantics { contentDescription = pathDescription }
      .pointerInput(Unit) {
        var dragStartAnchor = latestAnchor.value
        var dragAnchor = latestAnchor.value
        var dragRemainder = 0f
        detectHorizontalDragGestures(
          onDragStart = {
            dragStartAnchor = latestAnchor.value
            dragAnchor = dragStartAnchor
            dragRemainder = dragOffsetPx
          },
          onHorizontalDrag = { change, dragAmount ->
            val dayWidth = (size.width / 9f).coerceAtLeast(24f)
            dragRemainder += dragAmount
            dragOffsetPx = dragRemainder
            val steps = (dragRemainder / dayWidth).toInt()
            if (steps != 0) {
              val today = LocalDate.now()
              val nextAnchor = dragAnchor.minusDays(steps.toLong()).let { if (it.isAfter(today)) today else it }
              if (nextAnchor != dragAnchor) {
                dragAnchor = nextAnchor
                latestPreviewChange.value(nextAnchor)
                dragRemainder -= steps * dayWidth
                dragOffsetPx = dragRemainder
              } else {
                dragRemainder = 0f
                dragOffsetPx = 0f
              }
            }
            change.consume()
          },
          onDragEnd = {
            val delta = ChronoUnit.DAYS.between(dragStartAnchor, dragAnchor)
            dragOffsetPx = 0f
            if (delta != 0L) {
              latestCommitShift.value(delta)
            }
          },
          onDragCancel = {
            dragOffsetPx = 0f
            latestPreviewChange.value(dragStartAnchor)
          },
        )
      }
      .pointerInput(points) {
        detectTapGestures { offset ->
          val plotted = points.mapIndexedNotNull { index, point ->
            point?.let { index to it }
          }
          if (plotted.isEmpty()) return@detectTapGestures
          val nearest = plotted.minBy { (index, _) ->
            abs(offset.x - (size.width * (index / 6f) + dragOffsetPx))
          }.second
          onSelect(nearest)
        }
      },
  ) {
    val top = if (floating) 18f else 10f
    val bottom = size.height - if (floating) 24f else 18f
    val chartHeight = bottom - top
    val bandHeight = chartHeight / 3f
    if (floating) {
      drawRoundRect(
        color = floatingPlotColor,
        topLeft = Offset(0f, 0f),
        size = androidx.compose.ui.geometry.Size(size.width, size.height),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(28f, 28f),
      )
    }
    drawRoundRect(
      color = stableColor.copy(alpha = if (floating) 0.045f else 0.07f),
      topLeft = Offset(0f, top + bandHeight * 2f),
      size = androidx.compose.ui.geometry.Size(size.width, bandHeight),
      cornerRadius = androidx.compose.ui.geometry.CornerRadius(18f, 18f),
    )
    drawRoundRect(
      color = watchColor.copy(alpha = if (floating) 0.045f else 0.07f),
      topLeft = Offset(0f, top + bandHeight),
      size = androidx.compose.ui.geometry.Size(size.width, bandHeight),
      cornerRadius = androidx.compose.ui.geometry.CornerRadius(18f, 18f),
    )
    drawRoundRect(
      color = priorityColor.copy(alpha = if (floating) 0.04f else 0.06f),
      topLeft = Offset(0f, top),
      size = androidx.compose.ui.geometry.Size(size.width, bandHeight),
      cornerRadius = androidx.compose.ui.geometry.CornerRadius(18f, 18f),
    )
    if (!floating) {
      val balanceY = bottom - ((balanceThreshold / 100.0).toFloat() * chartHeight)
      drawLine(
        color = stableColor.copy(alpha = 0.42f),
        start = Offset(0f, balanceY),
        end = Offset(size.width, balanceY),
        strokeWidth = 2.2f,
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f), 0f),
      )
      val riskY = bottom - ((riskThreshold / 100.0).toFloat() * chartHeight)
      drawLine(
        color = watchColor.copy(alpha = 0.58f),
        start = Offset(0f, riskY),
        end = Offset(size.width, riskY),
        strokeWidth = 2.6f,
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f), 0f),
      )
    }
    val missingBandWidth = size.width / 13f
    points.forEachIndexed { index, point ->
      if (point == null) {
        val x = size.width * (index / 6f) + dragOffsetPx
        val bandLeft = (x - missingBandWidth / 2f).coerceIn(0f, size.width)
        drawRoundRect(
          color = incompleteColor.copy(alpha = if (floating) 0.055f else 0.075f),
          topLeft = Offset(bandLeft, top),
          size = androidx.compose.ui.geometry.Size(
            width = missingBandWidth.coerceAtMost(size.width - bandLeft).coerceAtLeast(0f),
            height = chartHeight,
          ),
          cornerRadius = androidx.compose.ui.geometry.CornerRadius(14f, 14f),
        )
      }
    }

    fun drawSegment(segment: List<Pair<RecentPathPoint, Offset>>) {
      if (segment.size <= 1) return
      val path = Path()
      segment.forEachIndexed { index, (_, offset) ->
        if (index == 0) {
          path.moveTo(offset.x, offset.y)
        } else {
          val previous = segment[index - 1].second
          val midX = (previous.x + offset.x) / 2f
          path.cubicTo(midX, previous.y, midX, offset.y, offset.x, offset.y)
        }
      }
      drawPath(path, color = lineColor.copy(alpha = if (floating) 0.78f else 0.82f), style = Stroke(width = if (floating) 5.8f else 5.2f, cap = androidx.compose.ui.graphics.StrokeCap.Round))
    }

    val segment = mutableListOf<Pair<RecentPathPoint, Offset>>()
    points.forEachIndexed { index, point ->
      if (point == null) {
        drawSegment(segment)
        segment.clear()
      } else {
        val x = size.width * (index / 6f) + dragOffsetPx
        val y = bottom - ((point.pathScore.coerceIn(0.0, 100.0) / 100.0).toFloat() * chartHeight)
        segment += point to Offset(x, y)
      }
    }
    drawSegment(segment)

    points.forEachIndexed { index, point ->
      val x = size.width * (index / 6f) + dragOffsetPx
      if (point == null) {
        drawCircle(color = missingColor.copy(alpha = if (floating) 0.16f else 0.22f), radius = if (floating) 4f else 5f, center = Offset(x, bottom))
        drawCircle(color = incompleteColor.copy(alpha = if (floating) 0.62f else 0.72f), radius = if (floating) 2.6f else 3.2f, center = Offset(x, bottom))
      } else {
        val y = bottom - ((point.pathScore.coerceIn(0.0, 100.0) / 100.0).toFloat() * chartHeight)
        val center = Offset(x, y)
        val selected = selectedPoint?.date == point.date
        val radius = if (selected) 7.5f else if (floating) 5.4f else 6f
        if (point.complete) {
          drawCircle(color = lineColor, radius = radius, center = center)
        } else {
          drawCircle(color = surfaceColor, radius = radius, center = center)
          drawCircle(color = lineColor.copy(alpha = 0.72f), radius = radius, center = center, style = Stroke(width = 2.4f))
        }
      }
    }
  }
}

@Composable
private fun TrendStatus(
  label: String,
  value: String,
  current: Double?,
  previous: Double?,
  lowerIsBetter: Boolean,
  absoluteRisk: Boolean = false,
) {
  val delta = if (current != null && previous != null) current - previous else null
  val better = delta?.let { if (lowerIsBetter) it <= 0.0 else it >= 0.0 }
  val color = if (absoluteRisk && current != null) {
    trendRiskColor(current)
  } else {
    when (better) {
      true -> compassGreen()
      false -> compassAmber()
      null -> compassGray()
    }
  }
  StatusPill(
    "$label $value",
    color,
    type = if (absoluteRisk && current != null) {
      when {
        current >= 70.0 -> StatusPillType.Danger
        current >= 35.0 -> StatusPillType.Warning
        else -> StatusPillType.Positive
      }
    } else {
      when (better) {
        true -> StatusPillType.Positive
        false -> StatusPillType.Warning
        null -> StatusPillType.Info
      }
    },
  )
}

@Composable
private fun trendRiskColor(value: Double) = when {
    value >= 70.0 -> compassRed()
    value >= 35.0 -> compassAmber()
    else -> compassGreen()
}

@Composable
private fun RecentDaysCard(state: LifeLoadUiState, mode: CompassMode) {
  val days = recentGuidanceApprovedHistoryDays(state).take(10)
  CompassCard(stringResource(R.string.compass_recent_saved_checkins), tag = "weekly-recent-days") {
    if (days.isEmpty()) {
      Text(stringResource(R.string.compass_save_checkins_for_guidance), color = MaterialTheme.colorScheme.onSurfaceVariant)
    } else {
      days.forEach { day ->
        RecentDayRow(day = day, showOperator = mode.showsOperatorData())
      }
    }
  }
}

@Composable
private fun RecentDayRow(day: LifeLoadHistoryDay, showOperator: Boolean) {
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("weekly-recent-day-${day.date}"),
    verticalArrangement = Arrangement.spacedBy(3.dp),
  ) {
    val risk = day.zone.ifBlank { "unknown" }
    val riskLabel = if (risk == "unknown") stringResource(R.string.not_sure) else risk.uppercase(Locale.ROOT)
    StatusPill("${day.date} · $riskLabel", compassRiskColor(risk), type = riskStatusPillType(risk, approvedDays = if (risk == "unknown") 0 else 7))
    Text(readableRecentDayCopy(day.nextAction.ifBlank { day.diarySummary.ifBlank { stringResource(R.string.compass_no_short_summary) } }), maxLines = 2)
    if (showOperator) {
      Text("state=${day.state} score=${oneDecimal(day.lifeLoadScore)} approved=${day.approvedAt}", color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun weeklyHeadline(risk: String, approvedDays: Int, improving: Boolean = false): String {
  if (approvedDays < MIN_GUIDANCE_APPROVED_DAYS) {
    return stringResource(R.string.compass_guidance_headline_need_checkins, approvedDays.coerceAtLeast(0), MIN_GUIDANCE_APPROVED_DAYS)
  }
  return when (risk.lowercase()) {
    "green", "stable", "continue" -> stringResource(R.string.compass_guidance_headline_stable)
    "red", "high", "stabilize" -> if (improving) stringResource(R.string.compass_guidance_headline_improving_high) else stringResource(R.string.compass_guidance_recovery_protected)
    "yellow", "orange", "amber", "protect", "hold" -> stringResource(R.string.compass_guidance_pattern_watching)
    else -> stringResource(R.string.compass_guidance_headline_unknown)
  }
}

private fun String.isUnknownGuidanceRisk(): Boolean =
  isBlank() || lowercase(Locale.ROOT) in setOf("unknown", "none", "not_sure")

@Composable
private fun weeklyConfidence(approvedDays: Int): String = when {
  approvedDays >= 6 -> stringResource(R.string.confidence_quality_high)
  approvedDays >= 4 -> stringResource(R.string.confidence_quality_medium)
  approvedDays > 0 -> stringResource(R.string.confidence_quality_partial)
  else -> stringResource(R.string.confidence_quality_not_enough)
}

@Composable
private fun weeklyDataQualityText(approvedDays: Int, entries: Int): String = when {
  approvedDays >= 7 -> stringResource(R.string.compass_data_quality_complete)
  approvedDays > 0 -> stringResource(R.string.compass_data_quality_partial, approvedDays.coerceAtMost(7))
  entries > 0 -> stringResource(R.string.compass_data_quality_entries, entries)
  else -> stringResource(R.string.compass_data_quality_empty)
}

@Composable
private fun draftsConflictText(drafts: Int, conflicts: Int): String =
  if (drafts == 0 && conflicts == 0) {
    stringResource(R.string.compass_no_drafts_conflicts)
  } else {
    stringResource(R.string.compass_drafts_conflicts, drafts, reviewNeededText(conflicts))
  }

@Composable
private fun reviewNeededText(conflicts: Int): String =
  if (conflicts == 0) {
    stringResource(R.string.compass_none_need_review)
  } else {
    stringResource(R.string.compass_review_needed_count, conflicts)
  }

@Composable
private fun weeklyApprovedText(approvedDays: Int, entries: Int): String = when {
  approvedDays >= 7 -> stringResource(R.string.compass_data_quality_complete)
  approvedDays > 0 -> stringResource(R.string.compass_data_quality_partial, approvedDays.coerceAtMost(7))
  entries > 0 -> stringResource(R.string.compass_data_quality_entries, entries)
  else -> stringResource(R.string.compass_data_quality_empty)
}

internal fun recentGuidanceApprovedDayCount(state: LifeLoadUiState, lookbackDays: Int = GUIDANCE_LOOKBACK_DAYS): Int {
  return recentGuidanceApprovedDates(state, lookbackDays).size
}

internal fun recentGuidanceApprovedDates(state: LifeLoadUiState, lookbackDays: Int = GUIDANCE_LOOKBACK_DAYS): List<LocalDate> {
  val anchor = runCatching { LocalDate.parse(state.dashboard.date) }.getOrNull()
    ?: state.dashboard.historyDays.mapNotNull { runCatching { LocalDate.parse(it.date) }.getOrNull() }.maxOrNull()
    ?: runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
    ?: return emptyList()
  val start = anchor.minusDays((lookbackDays - 1).coerceAtLeast(0).toLong())
  val approvedDates = approvedWeeklyHistoryDays(state.dashboard.historyDays)
    .mapNotNull { day -> runCatching { LocalDate.parse(day.date) }.getOrNull() }
    .filter { !it.isBefore(start) && !it.isAfter(anchor) }
    .toMutableSet()
  val selectedDate = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val selectedScoreAvailable = state.scoreAvailable ?: (state.score.zone.isNotBlank() || state.score.mode.isNotBlank() || state.score.nextAction.isNotBlank() || state.score.why.isNotEmpty() || state.score.lifeLoadScore != 0.0 || state.score.confidence != null)
  if (isCheckInSaved(state) && selectedScoreAvailable && selectedDate != null && !selectedDate.isBefore(start) && !selectedDate.isAfter(anchor)) {
    approvedDates += selectedDate
  }
  return approvedDates.sortedDescending()
}

private fun recentGuidanceApprovedHistoryDays(state: LifeLoadUiState): List<LifeLoadHistoryDay> {
  val byDate = approvedWeeklyHistoryDays(visibleDashboardHistoryDays(state))
    .associateBy { it.date }
    .toMutableMap()
  selectedSavedHistoryDay(state)?.let { selected ->
    byDate.putIfAbsent(selected.date, selected)
  }
  return byDate.values
    .sortedByDescending { day -> runCatching { LocalDate.parse(day.date) }.getOrNull() ?: LocalDate.MIN }
}

private fun selectedSavedHistoryDay(state: LifeLoadUiState): LifeLoadHistoryDay? {
  if (!isCheckInSaved(state)) return null
  val selectedDate = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull() ?: return null
  val dashboardDate = runCatching { LocalDate.parse(state.dashboard.date) }.getOrNull()
  if (dashboardDate != null && selectedDate.isAfter(dashboardDate)) return null
  val selectedScoreAvailable = state.scoreAvailable ?: (state.score.zone.isNotBlank() || state.score.mode.isNotBlank() || state.score.nextAction.isNotBlank() || state.score.why.isNotEmpty() || state.score.lifeLoadScore != 0.0 || state.score.confidence != null)
  return LifeLoadHistoryDay(
    date = state.selectedDate,
    state = state.entryState,
    approvedAt = state.approvedAt,
    canonicalCompleted = true,
    zone = state.score.zone.ifBlank { state.score.mode },
    nextAction = state.score.nextAction,
    lifeLoadScore = state.score.lifeLoadScore,
    diarySummary = state.draftEntry.diarySummary.ifBlank { state.draftEntry.diaryText },
    mood = state.draftEntry.mood,
    stress = state.draftEntry.stress,
    energy = state.draftEntry.energy,
    scoreAvailable = selectedScoreAvailable,
  )
}

@Composable
private fun guidanceApprovedText(approvedDays: Int, entries: Int): String = when {
  approvedDays >= GUIDANCE_LOOKBACK_DAYS -> stringResource(R.string.compass_guidance_complete_window, GUIDANCE_LOOKBACK_DAYS)
  approvedDays > 0 -> stringResource(R.string.compass_guidance_saved_in_window, approvedDays, GUIDANCE_LOOKBACK_DAYS)
  entries > 0 -> stringResource(R.string.compass_data_available_entries, entries)
  else -> stringResource(R.string.compass_no_saved_checkins)
}

@Composable
private fun weeklyTrendSentence(latest: LifeLoadTrendPoint?): String {
  if (latest == null) return stringResource(R.string.compass_trend_empty)
  val recovery = recoveryQuality(latest.recoveryProxy())
  val risk = riskQuality(latest.driftRiskScore)
  return if (risk == "low") {
    stringResource(R.string.compass_trend_recovery_risk_ok)
  } else if (recovery == "strong") {
    stringResource(R.string.compass_trend_recovery_strong_risk_high)
  } else {
    stringResource(R.string.compass_trend_explanation_high)
  }
}

@Composable
private fun weeklyTrendExplanation(latest: LifeLoadTrendPoint?): String {
  if (latest == null) return stringResource(R.string.compass_trend_explanation_empty)
  return if (riskQuality(latest.driftRiskScore) == "low") {
    stringResource(R.string.compass_trend_explanation_low)
  } else {
    stringResource(R.string.compass_trend_explanation_high)
  }
}

private fun readableGuidanceAction(value: String): String {
  val normalized = value.trim()
  if (normalized.isBlank()) return ""
  val internalPlanName = "stabilization " + "block"
  if (normalized.contains(internalPlanName, ignoreCase = true)) {
    return "Take the next 48 hours easier: protect sleep, reduce optional commitments, and keep evenings simple."
  }
  return normalized
}

@Composable
private fun readableGuidanceAction(risk: String, approvedDays: Int, fallback: String): String {
  if (approvedDays < MIN_GUIDANCE_APPROVED_DAYS) return missingGuidanceRequirement(approvedDays)
  return when (risk.lowercase()) {
    "red", "high", "stabilize" -> stringResource(R.string.compass_guidance_action_recovery)
    "yellow", "orange", "amber", "protect", "hold" -> stringResource(R.string.compass_guidance_action_caution)
    "green", "stable", "continue" -> stringResource(R.string.compass_guidance_action_keep_rhythm)
    else -> if (Locale.getDefault().language == "de") stringResource(R.string.compass_guidance_body_unknown) else readableGuidanceAction(fallback)
  }
}

@Composable
private fun missingGuidanceRequirement(approvedDays: Int): String {
  val saved = approvedDays.coerceIn(0, MIN_GUIDANCE_APPROVED_DAYS)
  val remaining = (MIN_GUIDANCE_APPROVED_DAYS - saved).coerceAtLeast(1)
  val checkInWord = stringResource(
    if (remaining == 1) R.string.compass_guidance_checkin_singular else R.string.compass_guidance_checkin_plural,
  )
  return stringResource(R.string.compass_guidance_requirement, saved, MIN_GUIDANCE_APPROVED_DAYS, GUIDANCE_LOOKBACK_DAYS, remaining, checkInWord)
}

private fun recoveryMarginQuality(value: Double?, simple: Boolean): String {
  if (value == null) return "not enough data"
  return if (simple) {
    when {
      value >= 2.0 -> "enough"
      value >= 0.0 -> "narrow"
      else -> "low"
    }
  } else {
    trendQuality(value, positiveGood = true)
  }
}

internal data class RecentPathPoint(
  val date: String,
  val dateLabel: String,
  val pathScore: Double,
  val complete: Boolean,
  val stateLabel: String,
  val summary: String,
)

internal fun recentPathPointsForTest(state: LifeLoadUiState): List<RecentPathPoint?> =
  recentPathPoints(state)

internal fun recentPathPointsForTest(state: LifeLoadUiState, anchor: LocalDate): List<RecentPathPoint?> =
  recentPathPoints(state, anchor)

private fun recentPathAnchorDate(state: LifeLoadUiState): LocalDate {
  val dashboardDate = runCatching { LocalDate.parse(state.dashboard.date) }.getOrNull()
  val visibleHistory = visibleDashboardHistoryDays(state)
  val visibleTrendPoints = state.dashboard.trendPoints.filter { point ->
    val date = runCatching { LocalDate.parse(point.date) }.getOrNull() ?: return@filter false
    dashboardDate == null || !date.isAfter(dashboardDate)
  }
  val latestTrendDate = visibleTrendPoints
    .mapNotNull { runCatching { LocalDate.parse(it.date) }.getOrNull() }
    .maxOrNull()
  val latestHistoryDate = visibleHistory
    .mapNotNull { runCatching { LocalDate.parse(it.date) }.getOrNull() }
    .maxOrNull()
  return when {
    dashboardDate != null -> dashboardDate
    latestTrendDate != null -> latestTrendDate
    latestHistoryDate != null -> latestHistoryDate
    else -> LocalDate.now()
  }
}

private fun recentPathPoints(state: LifeLoadUiState, anchorOverride: LocalDate? = null): List<RecentPathPoint?> {
  val anchor = anchorOverride ?: recentPathAnchorDate(state)
  val visibleHistory = visibleDashboardHistoryDays(state)
  val historyByDate = visibleHistory.associateBy { it.date }
  val visibleTrendPoints = state.dashboard.trendPoints.filter { point ->
    val date = runCatching { LocalDate.parse(point.date) }.getOrNull() ?: return@filter false
    !date.isAfter(anchor)
  }
  val trendByDate = visibleTrendPoints.associateBy { it.date }
  return (6 downTo 0).map { daysAgo ->
    val date = anchor.minusDays(daysAgo.toLong()).toString()
    val history = historyByDate[date]
    if (history?.scoreAvailable == false) return@map null
    val point = trendByDate[date] ?: history?.let { localHistoryPathPoint(it) } ?: return@map null
    val complete = history?.approvedAt?.isNotBlank() == true || history?.canonicalCompleted == true
    val pathScore = recentPathScore(point, history)
    RecentPathPoint(
      date = point.date,
      dateLabel = shortDateLabel(point.date),
      pathScore = pathScore,
      complete = complete,
      stateLabel = recentPathStateLabel(pathScore),
      summary = recentPathSummary(point, history),
    )
  }
}

private fun localHistoryPathPoint(history: LifeLoadHistoryDay): LifeLoadTrendPoint =
  LifeLoadTrendPoint(
    date = history.date,
    driftRiskScore = when (history.zone.lowercase(Locale.ROOT)) {
      "red", "stabilize" -> 85.0
      "orange", "hold" -> 65.0
      "yellow", "amber", "protect", "caution" -> 45.0
      "green", "continue", "stable" -> 20.0
      else -> history.lifeLoadScore.takeIf { it > 0.0 }?.coerceIn(0.0, 100.0) ?: 45.0
    },
  )

@Composable
private fun recentPathSentence(points: List<RecentPathPoint?>): String {
  val plotted = points.filterNotNull()
  if (plotted.size < 3) return stringResource(R.string.compass_recent_path_empty)
  val latest = plotted.last()
  val previous = plotted.dropLast(1).lastOrNull()
  return when {
    latest.pathScore >= 70.0 -> stringResource(R.string.compass_recent_path_recovery_priority)
    previous != null && latest.pathScore < previous.pathScore - 8.0 -> stringResource(R.string.compass_recent_path_easing)
    else -> stringResource(R.string.compass_recent_path_steady)
  }
}

private fun recentPathScore(point: LifeLoadTrendPoint, history: LifeLoadHistoryDay?): Double {
  val zone = history?.zone?.lowercase(Locale.ROOT).orEmpty()
  return when (zone) {
    "red", "stabilize" -> 85.0
    "orange", "hold" -> 65.0
    "yellow", "amber", "protect", "caution" -> 45.0
    "green", "continue", "stable" -> 20.0
    else -> point.driftRiskScore
  }
}

private fun recentPathStateLabel(pathScore: Double): String = when {
  pathScore >= 70.0 -> "Recovery priority"
  pathScore >= 35.0 -> "Watch"
  else -> "Stable"
}

@Composable
private fun localizedRecentPathStateLabel(value: String): String = when (value) {
  "Recovery priority" -> stringResource(R.string.compass_recent_path_state_recovery)
  "Watch" -> stringResource(R.string.compass_recent_path_state_watch)
  "Stable" -> stringResource(R.string.compass_recent_path_state_stable)
  else -> value
}

private fun recentPathSummary(point: LifeLoadTrendPoint, history: LifeLoadHistoryDay?): String {
  val items = buildList {
    if (history?.nextAction?.isNotBlank() == true) add(readableGuidanceAction(history.nextAction))
    if (point.phoneAfter21Count7d > 0) {
      add(if (point.phoneAfter21RecentCount3d == 0 && point.phoneAfter21OlderCount4To7d > 0) "late phone improved recently" else "recent window includes late phone")
    }
    if (point.projectOverrunCount7d > 0) {
      add(if (point.projectOverrunRecentCount3d == 0 && point.projectOverrunOlderCount4To7d > 0) "project spillover improved recently" else "recent window includes project spillover")
    }
    if (point.painAvg7d >= 4.0) add("pain")
    if (history?.diarySummary?.isNotBlank() == true) add(history.diarySummary)
  }
  return items.take(2).joinToString(" and ").replaceFirstChar { it.uppercase() }
}

@Composable
private fun simpleGuidanceSummary(drivers: List<String>, latest: LifeLoadTrendPoint?): String {
  val activeLatePhone = (latest?.phoneAfter21RecentCount3d ?: 0) > 0
  val activeProject = (latest?.projectOverrunRecentCount3d ?: 0) > 0
  val improving = latest?.recoveryMomentumImproving() == true
  return when {
    improving && (activeLatePhone || activeProject) ->
      stringResource(R.string.compass_recent_risk_improving_active, simpleActiveSignalLine(activeLatePhone, activeProject))
    improving ->
      stringResource(R.string.compass_recent_risk_improving)
    activeLatePhone || activeProject ->
      stringResource(R.string.compass_recent_risk_active, simpleActiveSignalLine(activeLatePhone, activeProject))
    else -> drivers.take(2).joinToString("\n")
  }
}

@Composable
private fun simpleActiveSignalLine(activeLatePhone: Boolean, activeProject: Boolean): String = when {
  activeLatePhone && activeProject -> stringResource(R.string.compass_recent_signal_late_phone_project)
  activeLatePhone -> stringResource(R.string.compass_recent_signal_late_phone)
  activeProject -> stringResource(R.string.compass_recent_signal_project)
  else -> stringResource(R.string.compass_recent_signal_recovery_margin)
}

@Composable
private fun recentPathAccessibility(points: List<RecentPathPoint?>): String {
  val descriptions = points.mapIndexed { index, point ->
    if (point == null) {
      stringResource(R.string.compass_recent_path_accessibility_missing, index + 1)
    } else {
      val completeness = if (point.complete) stringResource(R.string.compass_recent_path_complete) else stringResource(R.string.compass_recent_path_partial)
      stringResource(R.string.compass_recent_path_accessibility_point, point.dateLabel, point.stateLabel.lowercase(Locale.getDefault()), completeness)
    }
  }
  return stringResource(R.string.compass_recent_path_accessibility_summary, descriptions.joinToString(". "))
}

private fun shortDateLabel(date: String): String =
  runCatching {
    LocalDate.parse(date).format(DateTimeFormatter.ofPattern("MMM d", Locale.getDefault()))
  }.getOrDefault(date.takeLast(5))

@Composable
private fun userRiskLabel(risk: String): String = when (risk.lowercase()) {
  "red", "high", "stabilize" -> stringResource(R.string.compass_risk_high)
  "yellow", "orange", "amber", "protect", "hold" -> stringResource(R.string.compass_risk_caution)
  "green", "stable", "continue" -> stringResource(R.string.compass_risk_stable)
  else -> stringResource(R.string.compass_risk_unknown)
}

@Composable
private fun latePhoneDriverCopy(point: LifeLoadTrendPoint, mode: CompassMode): String {
  if (mode.showsOperatorData()) {
    return stringResource(R.string.late_phone_driver_operator, point.phoneAfter21Count7d, point.phoneAfter21Weighted7d)
  }
  return when {
    point.phoneAfter21RecentCount3d > 0 -> stringResource(R.string.late_phone_driver_recent)
    point.phoneAfter21OlderCount4To7d > 0 -> stringResource(R.string.late_phone_driver_fading)
    else -> stringResource(R.string.late_phone_driver_window)
  }
}

@Composable
private fun projectDriverCopy(point: LifeLoadTrendPoint, mode: CompassMode): String {
  if (mode.showsOperatorData()) {
    return stringResource(R.string.project_spillover_driver_operator, point.projectOverrunCount7d, point.projectOverrunWeighted7d)
  }
  return when {
    point.projectOverrunRecentCount3d > 0 -> stringResource(R.string.project_spillover_driver_recent)
    point.projectOverrunOlderCount4To7d > 0 -> stringResource(R.string.project_spillover_driver_fading)
    else -> stringResource(R.string.project_spillover_driver_window)
  }
}

private fun LifeLoadTrendPoint.recoveryMomentumImproving(): Boolean =
  (phoneAfter21RecentCount3d == 0 && phoneAfter21OlderCount4To7d > 0) ||
    (projectOverrunRecentCount3d == 0 && projectOverrunOlderCount4To7d > 0)

@Composable
private fun recommendationLabel(risk: String, approvedDays: Int): String {
  if (approvedDays < MIN_GUIDANCE_APPROVED_DAYS) return stringResource(R.string.compass_guidance_need_recent_checkins, MIN_GUIDANCE_APPROVED_DAYS)
  return when (risk.lowercase()) {
    "red", "high", "stabilize" -> stringResource(R.string.recommendation_recovery_priority)
    "yellow", "orange", "amber", "protect", "hold" -> stringResource(R.string.recommendation_watch)
    "green", "stable", "continue" -> stringResource(R.string.recommendation_stable)
    else -> stringResource(R.string.recommendation_not_enough_data)
  }
}

@Composable
private fun recommendationIconPainter(risk: String, approvedDays: Int): Painter {
  if (approvedDays < MIN_GUIDANCE_APPROVED_DAYS) return painterResource(R.drawable.ll_ic_compass_mark)
  return when (risk.lowercase()) {
    "red", "high", "stabilize" -> painterResource(R.drawable.ll_ic_recovery_shield_moon)
    "yellow", "orange", "amber", "protect", "hold" -> painterResource(R.drawable.ll_ic_signal_bars)
    "green", "stable", "continue" -> painterResource(R.drawable.ll_ic_recent_path)
    else -> painterResource(R.drawable.ll_ic_compass_mark)
  }
}

private fun trendQuality(value: Double?, positiveGood: Boolean): String {
  if (value == null) return "not enough data"
  return if (positiveGood) {
    when {
      value >= 2.0 -> "positive"
      value >= 0.0 -> "narrow"
      else -> "negative"
    }
  } else {
    when {
      value >= 7.0 -> "high"
      value >= 4.0 -> "moderate"
      else -> "low"
    }
  }
}

private fun riskQuality(value: Double?): String = when {
  value == null -> "not enough data"
  value >= 70.0 -> "high"
  value >= 35.0 -> "medium"
  else -> "low"
}

private fun riskStatusPillType(risk: String, approvedDays: Int): StatusPillType = when {
  approvedDays < MIN_GUIDANCE_APPROVED_DAYS -> StatusPillType.Info
  risk.lowercase(Locale.ROOT) in setOf("red", "high", "stabilize") -> StatusPillType.Danger
  risk.lowercase(Locale.ROOT) in setOf("yellow", "orange", "amber", "protect", "hold") -> StatusPillType.Warning
  risk.lowercase(Locale.ROOT) in setOf("green", "stable", "continue") -> StatusPillType.Positive
  else -> StatusPillType.Info
}

@Composable
private fun weeklyGuidanceReasons(state: LifeLoadUiState, approvedDays: Int, mode: CompassMode): List<String> {
  val latest = state.dashboard.trendPoints.lastOrNull()
  val drift = state.dashboard.drift
  val risk = drift?.riskLevel?.ifBlank { state.dashboard.weekly.zone } ?: state.dashboard.weekly.zone
  val reasons = buildList {
    if (approvedDays < MIN_GUIDANCE_APPROVED_DAYS) add(stringResource(R.string.what_to_watch_next_body_empty))
    if (risk.lowercase(Locale.ROOT) in setOf("red", "high", "stabilize")) {
      add(stringResource(R.string.what_to_watch_next_body_high_generic))
    }
    if (risk.lowercase(Locale.ROOT) in setOf("yellow", "orange", "amber", "protect", "hold")) {
      add(stringResource(R.string.what_to_watch_next_body_caution))
    }
    if (latest != null && latest.recoveryMomentumImproving()) {
      add(stringResource(R.string.recent_recovery_improving))
      add(stringResource(R.string.recent_recovery_caution_easing))
    }
    if ((latest?.phoneAfter21Count7d ?: 0) > 0) {
      latest?.let { add(latePhoneDriverCopy(it, mode)) }
    }
    if ((latest?.projectOverrunCount7d ?: 0) > 0) {
      latest?.let { add(projectDriverCopy(it, mode)) }
    }
    drift?.contributingSignals.orEmpty().take(4).forEach { add(readableDriver(it)) }
    if ((latest?.painAvg7d ?: 0.0) >= 4.0) add("Pain average: ${oneDecimal(latest?.painAvg7d)}")
    if ((latest?.lifeMargin7d ?: 0.0) < 0.0) add("Recovery lower than load")
    if (isEmpty()) add(stringResource(R.string.compass_guidance_body_stable))
  }
  return reasons.distinct().take(8)
}

private fun recoveryQuality(value: Double?): String = when {
  value == null -> "not enough data"
  value >= 7.0 -> "strong"
  value >= 4.0 -> "usable"
  else -> "weak"
}

private fun readableRecentDayCopy(value: String): String =
  if (value.contains("A few fields are missing", ignoreCase = true)) {
    "Saved with partial confidence. Add missing details for a more reliable score."
  } else {
    readableGuidanceAction(value)
  }

private fun LifeLoadTrendPoint.recoveryProxy(): Double =
  ((sleepCompliance7d + nutritionCompliance7d) * 5.0 - painAvg7d / 2.0).coerceIn(0.0, 10.0)

private fun readableDriver(value: String): String = when (value.trim()) {
  "alcohol" -> "Alcohol exposure logged"
  "binge" -> "Eating episode flagged recently"
  "sleep drift" -> "Sleep support needed"
  "garmin short sleep" -> "Garmin sleep suggests extra recovery"
  "nutrition drift" -> "Food plan support needed"
  "recovery compliance falling" -> "Recovery habits slipping"
  "recovery consistency falling" -> "Recovery consistency falling"
  "historical risk score high" -> "Recent pattern suggests higher risk"
  "risk score high" -> "Risk trend remains high"
  "relationship conflict" -> "Relationship stress logged"
  "repeated relationship conflict" -> "Relationship stress repeated"
  "school conflict" -> "School-related conflict added load"
  "training spike from low base" -> "Training increased from a low base"
  "acute training spike" -> "Recent training load is elevated"
  "training load rising fast" -> "Training load is rising quickly"
  "project overrun" -> "Projects cut into recovery"
  "late phone" -> "Late phone"
  else -> value.replace('_', ' ').replaceFirstChar { it.uppercase() }
}

private fun oneDecimal(value: Double?): String =
  if (value == null) "-" else ((value * 10.0).roundToInt() / 10.0).toString()

private fun percent(value: Double?): String =
  if (value == null) "-" else "${(value * 100.0).roundToInt()}%"
