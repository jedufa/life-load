@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package com.life.lifeload.ui.compass

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringArrayResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.life.lifeload.R
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.isCheckInSaved
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

enum class CompassScreen {
  Today,
  Week,
  Settings,
}

enum class CompassMode(val label: String) {
  Simple("Simple"),
  Detailed("Detailed"),
  Operator("Operator"),
}

data class CompassStatus(
  val label: String,
  val detail: String,
  val color: Color,
  val technical: String = "",
)

data class FieldHelpSpec(
  val fieldKey: String,
  val label: String,
  val shortHelper: String = "",
  val longHelper: String = "",
  val yesMeaning: String = "",
  val noMeaning: String = "",
  val unknownMeaning: String = "Choose Not sure if you do not know or do not want to decide.",
  val internalFieldName: String = "",
)

enum class StatusPillType {
  Positive,
  Warning,
  Danger,
  Neutral,
  Info,
}

internal val LocalCompassFloatingShell = staticCompositionLocalOf { false }

@Composable
fun compassGreen(): Color = Color(0xFF1F7A4D)

@Composable
fun compassAmber(): Color = Color(0xFFB7791F)

@Composable
fun compassRed(): Color = Color(0xFFC24135)

@Composable
fun compassBlue(): Color = Color(0xFF256A91)

@Composable
fun compassGray(): Color = MaterialTheme.colorScheme.onSurfaceVariant

@Composable
internal fun compassPlusIconTint(): Color =
  if (isSystemInDarkTheme()) Color(0xFF8ECDBF) else Color(0xFF1E7565)

@Composable
internal fun compassPlusIconCircle(): Color =
  if (isSystemInDarkTheme()) Color(0xFF173B34) else Color(0xFFE8F0E4)

@Composable
internal fun compassPlusProtectionCircle(): Color =
  if (isSystemInDarkTheme()) Color(0xFF493137).copy(alpha = 0.76f) else Color(0xFFF4E4E6)

@Composable
internal fun compassPlusDecorativeLeaf(): Color =
  if (isSystemInDarkTheme()) Color(0xFF7EA08A).copy(alpha = 0.42f) else Color(0xFFAFC8B4).copy(alpha = 0.68f)

@Composable
fun compassRiskColor(value: String): Color {
  val normalized = value.lowercase()
  val numeric = normalized.toDoubleOrNull()
  if (numeric != null) {
    return when {
      numeric >= 70.0 -> compassRed()
      numeric >= 35.0 -> compassAmber()
      else -> compassGreen()
    }
  }
  return when {
    normalized in setOf("green", "continue", "stable", "ready") -> compassGreen()
    normalized in setOf("yellow", "amber", "protect", "hold", "caution") -> compassAmber()
    normalized in setOf("red", "stabilize", "high") -> compassRed()
    else -> compassGray()
  }
}

fun CompassMode.showsDetails(): Boolean = this != CompassMode.Simple

fun CompassMode.showsOperatorData(): Boolean = this == CompassMode.Operator

@Composable
fun CompassCard(
  title: String,
  modifier: Modifier = Modifier,
  tag: String? = null,
  accent: Color = MaterialTheme.colorScheme.outline.copy(alpha = 0.28f),
  debug: Boolean = false,
  content: @Composable ColumnScope.() -> Unit,
) {
  val floating = LocalCompassFloatingShell.current
  val shape = RoundedCornerShape(if (floating) 24.dp else 14.dp)
  val cardModifier = modifier
    .fillMaxWidth()
    .then(if (tag != null) Modifier.testTag(tag) else Modifier)
    .then(
      if (floating) {
        Modifier
      } else {
        Modifier.border(1.dp, accent.copy(alpha = if (debug) 0.18f else 0.30f), shape)
      },
    )
  Card(
    modifier = cardModifier,
    shape = shape,
    colors = CardDefaults.cardColors(
      containerColor = when {
        debug -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = if (floating) 0.30f else 0.38f)
        floating && !isSystemInDarkTheme() -> Color(0xFFFFFDF7)
        else -> MaterialTheme.colorScheme.surface
      },
      contentColor = MaterialTheme.colorScheme.onSurface,
    ),
    elevation = CardDefaults.cardElevation(defaultElevation = if (floating) 4.dp else 0.dp),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(if (floating) 18.dp else 14.dp),
      verticalArrangement = Arrangement.spacedBy(if (floating) 10.dp else 7.dp),
    ) {
      if (title.isNotBlank()) {
        Text(
          title,
          color = MaterialTheme.colorScheme.onSurface,
          fontSize = 18.sp,
          fontWeight = FontWeight.SemiBold,
        )
      }
      content()
    }
  }
}

@Composable
fun CompassHeroCard(
  title: String,
  status: CompassStatus,
  isSaved: Boolean,
  dailyMeaning: String,
  whyItems: List<String> = emptyList(),
  savedStatus: String,
  nextAction: String,
  confidence: String,
  missingFields: List<String>,
  lastSavedText: String = "",
  tag: String,
  primaryButtonLabel: String,
  onPrimary: () -> Unit,
  titleTrailingText: String = "",
  secondaryButtonLabel: String? = null,
  onSecondary: (() -> Unit)? = null,
  primaryTrailingContent: @Composable RowScope.() -> Unit = {},
) {
  var showWhy by remember { mutableStateOf(false) }
  val floating = LocalCompassFloatingShell.current
  val heroShape = RoundedCornerShape(if (floating) 26.dp else 18.dp)
  val compactConfidence = confidence.lowercase()
  val statusLine = savedStatus.ifBlank { "${status.label} · $compactConfidence" }
  val encouragementOptions = stringArrayResource(R.array.compass_encouragement_lines)
  val encouragementLine = remember(showWhy, encouragementOptions.size) {
    if (showWhy && encouragementOptions.isNotEmpty()) encouragementOptions.random() else ""
  }
  if (showWhy) {
    AlertDialog(
      onDismissRequest = { showWhy = false },
      containerColor = if (isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFBFAF6),
      confirmButton = {
        TextButton(onClick = { showWhy = false }) {
          Text(stringResource(R.string.close))
        }
      },
      title = { Text(stringResource(R.string.compass_why_this_conclusion)) },
      text = {
        SelectionContainer {
          Column(
            modifier = Modifier
              .heightIn(max = 420.dp)
              .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp),
          ) {
            whyItems.take(8).forEach {
              Text("• $it")
            }
            if (encouragementLine.isNotBlank()) {
              Text(
                encouragementLine,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
              )
            }
          }
        }
      },
    )
  }
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag)
      .then(
        if (floating) {
          Modifier.border(1.dp, status.color.copy(alpha = 0.10f), heroShape)
        } else {
          Modifier.border(2.dp, status.color.copy(alpha = 0.42f), heroShape)
        },
      ),
    shape = heroShape,
    colors = CardDefaults.cardColors(
      containerColor = when {
        floating && isSystemInDarkTheme() -> MaterialTheme.colorScheme.surface
        floating -> Color(0xFFFFFDF7)
        else -> status.color.copy(alpha = 0.08f)
      },
      contentColor = MaterialTheme.colorScheme.onSurface,
    ),
    elevation = CardDefaults.cardElevation(defaultElevation = if (floating) 6.dp else 0.dp),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(if (floating) 22.dp else 14.dp),
      verticalArrangement = Arrangement.spacedBy(if (floating) 11.dp else 9.dp),
    ) {
      Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.weight(1f)) {
          Text(
            title,
            color = MaterialTheme.colorScheme.onSurface,
            fontSize = 26.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(
            dailyMeaning,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
            color = if (whyItems.isEmpty()) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.primary,
            modifier = Modifier
              .testTag("today-daily-meaning")
              .then(if (whyItems.isEmpty()) Modifier else Modifier.clickable { showWhy = true }),
          )
          if (whyItems.isNotEmpty()) {
            Text(
              stringResource(R.string.compass_tap_guidance_for_why),
              color = MaterialTheme.colorScheme.onSurfaceVariant,
              fontSize = 12.sp,
            )
          }
          Text(
            statusLine,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.testTag("today-status-pill"),
          )
        }
        if (titleTrailingText.isNotBlank()) {
          StatusPill(
            label = titleTrailingText,
            color = if (isSaved) compassGreen() else compassAmber(),
            tag = "today-checkin-completion-status",
            type = if (isSaved) StatusPillType.Positive else StatusPillType.Info,
          )
        }
      }
      Text(stringResource(R.string.compass_next_helpful_step), fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
      DailyNextActionText(
        text = nextAction,
        clickable = whyItems.isNotEmpty(),
        onClick = { showWhy = true },
        modifier = Modifier.testTag("today-next-action"),
      )
      Text(
        if (missingFields.isEmpty()) stringResource(R.string.compass_no_major_fields_missing) else stringResource(R.string.compass_missing_details, missingFields.take(3).joinToString(", ")),
        fontSize = 15.sp,
        color = if (missingFields.isEmpty()) compassGreen() else compassAmber(),
        modifier = Modifier.testTag("today-missing-fields"),
      )
      if (isSaved && lastSavedText.isNotBlank()) {
        Text(
          stringResource(R.string.compass_last_saved, lastSavedText),
          color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.78f),
          fontSize = 12.sp,
          modifier = Modifier.testTag("daily-last-saved"),
        )
      }
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Button(onClick = onPrimary, modifier = Modifier.testTag("daily-approve-button")) {
          Text(primaryButtonLabel)
        }
        if (secondaryButtonLabel != null && onSecondary != null) {
          IconButton(
            onClick = onSecondary,
            modifier = Modifier
              .size(36.dp)
              .testTag("daily-add-details-button"),
          ) {
            Icon(Icons.Filled.Add, contentDescription = secondaryButtonLabel, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
          }
        }
        Spacer(Modifier.weight(1f))
        primaryTrailingContent()
      }
    }
  }
}

@Composable
private fun DailyNextActionText(
  text: String,
  clickable: Boolean,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
) {
  val lines = dailyGuidanceLines(text)
  val textColor = if (clickable) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
  Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(3.dp)) {
    lines.forEach { line ->
      Row(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.Top) {
        if (line.bulleted) {
          Text(
            "•",
            fontSize = 22.sp,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface,
          )
        }
        Text(
          line.text,
          fontSize = 22.sp,
          fontWeight = FontWeight.SemiBold,
          color = textColor,
          modifier = if (clickable) Modifier.clickable { onClick() } else Modifier,
        )
      }
    }
  }
}

data class DailyGuidanceLine(val text: String, val bulleted: Boolean)

fun dailyGuidanceLines(text: String): List<DailyGuidanceLine> =
  text
    .lineSequence()
    .map { it.trim() }
    .filter { it.isNotBlank() }
    .map { line ->
      if (line.startsWith("•")) {
        DailyGuidanceLine(line.removePrefix("•").trimStart(), bulleted = true)
      } else {
        DailyGuidanceLine(line, bulleted = false)
      }
    }
    .toList()

@Composable
fun StatusPill(
  label: String,
  color: Color,
  tag: String? = null,
  onClick: (() -> Unit)? = null,
  type: StatusPillType = StatusPillType.Neutral,
) {
  Row(
    modifier = Modifier
      .then(if (tag != null) Modifier.testTag(tag) else Modifier)
      .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
      .background(color.copy(alpha = 0.12f), RoundedCornerShape(999.dp))
      .border(1.dp, color.copy(alpha = 0.28f), RoundedCornerShape(999.dp))
      .padding(horizontal = 10.dp, vertical = 6.dp),
    horizontalArrangement = Arrangement.spacedBy(5.dp),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Icon(
      imageVector = when (type) {
        StatusPillType.Positive -> Icons.Filled.CheckCircle
        StatusPillType.Warning,
        StatusPillType.Danger -> Icons.Filled.Warning
        StatusPillType.Info,
        StatusPillType.Neutral -> Icons.Filled.Info
      },
      contentDescription = null,
      tint = color,
      modifier = Modifier.size(14.dp),
    )
    Text(label, color = color, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
  }
}

@Composable
fun SegmentedField(
  label: String,
  selected: String,
  options: List<Pair<String, String>>,
  tagPrefix: String,
  mode: CompassMode = CompassMode.Detailed,
  enabled: Boolean = true,
  riskValues: Set<String> = emptySet(),
  positiveValues: Set<String> = setOf("yes"),
  cautionValues: Set<String> = emptySet(),
  help: FieldHelpSpec? = null,
  highlightMissing: Boolean = false,
  onSelect: (String) -> Unit,
) {
  val fieldModifier = Modifier
    .fillMaxWidth()
    .then(if (highlightMissing) Modifier.testTag("${tagPrefix}_missing") else Modifier)
    .then(missingFieldModifier(highlightMissing))
  Column(verticalArrangement = Arrangement.spacedBy(5.dp), modifier = fieldModifier) {
    FieldLabel(
      label = label,
      mode = mode,
      help = help,
    )
    FlowRow(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.fillMaxWidth()) {
      options.forEach { (value, text) ->
        val displayText = if (!mode.showsOperatorData() && value == "unknown") stringResource(R.string.not_sure) else text
        val selectedHere = selected == value
        val color = when {
          selectedHere && value in riskValues -> compassRed()
          selectedHere && value in cautionValues -> compassAmber()
          selectedHere && value in positiveValues -> compassGreen()
          selectedHere && value == "unknown" && highlightMissing -> compassAmber()
          selectedHere && value == "unknown" -> compassGray()
          selectedHere -> MaterialTheme.colorScheme.primary
          else -> MaterialTheme.colorScheme.outline
        }
        FilterChip(
          selected = selectedHere,
          onClick = { if (enabled) onSelect(value) },
          enabled = enabled,
          label = { Text(displayText) },
          colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = color.copy(alpha = 0.16f),
            selectedLabelColor = color,
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f),
            labelColor = MaterialTheme.colorScheme.onSurfaceVariant,
            disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.30f),
            disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.55f),
          ),
          modifier = Modifier
            .defaultMinSize(minHeight = 42.dp)
            .testTag("${tagPrefix}_${value.lowercase().replace("+", "plus").replace("/", "_").replace("?", "unknown")}"),
          border = FilterChipDefaults.filterChipBorder(
            enabled = enabled,
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
fun IntensitySliderField(
  label: String,
  value: Int?,
  tag: String,
  mode: CompassMode = CompassMode.Detailed,
  help: FieldHelpSpec? = null,
  highlightMissing: Boolean = false,
  onChange: (Int?) -> Unit,
) {
  val notSureText = if (mode.showsOperatorData()) stringResource(R.string.operator_unknown) else stringResource(R.string.not_sure)
  val fieldModifier = Modifier
    .fillMaxWidth()
    .then(if (highlightMissing) Modifier.testTag("$tag-missing") else Modifier)
    .then(missingFieldModifier(highlightMissing))
  Column(verticalArrangement = Arrangement.spacedBy(4.dp), modifier = fieldModifier) {
    FieldLabel(
      label = label,
      mode = mode,
      help = help,
      compact = true,
      valueText = value?.let { localizedIntensityLabel(it) } ?: notSureText,
    )
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .testTag(tag),
      horizontalArrangement = Arrangement.spacedBy(3.dp),
      verticalAlignment = Alignment.CenterVertically,
    ) {
      CompactNumericToken(
        text = notSureText,
        selected = value == null,
        onClick = { onChange(null) },
        modifier = Modifier
          .widthIn(min = 68.dp)
          .testTag("${tag}-not-sure"),
        highlight = highlightMissing,
      )
      listOf(0, 2, 4, 6, 8, 10).forEach { number ->
        CompactNumericToken(
          text = number.toString(),
          selected = value == number,
          onClick = { onChange(number) },
          modifier = Modifier
            .weight(1f)
            .then(if (number == 0) Modifier.testTag("${tag}-0") else Modifier),
        )
      }
    }
  }
}

@Composable
private fun CompactNumericToken(
  text: String,
  selected: Boolean,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
  highlight: Boolean = false,
) {
  val selectedBackground = if (isSystemInDarkTheme()) {
    MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.72f)
  } else {
    Color(0xFFE8DEFF)
  }
  val selectedBorder = if (isSystemInDarkTheme()) {
    MaterialTheme.colorScheme.primary.copy(alpha = 0.64f)
  } else {
    Color(0xFFC7B8F5)
  }
  val borderColor = when {
    selected -> selectedBorder
    highlight -> compassAmber().copy(alpha = 0.42f)
    else -> MaterialTheme.colorScheme.outline.copy(alpha = 0.16f)
  }
  val textColor = if (selected) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant
  Box(
    modifier = modifier
      .heightIn(min = 38.dp)
      .background(if (selected) selectedBackground else Color.Transparent, RoundedCornerShape(14.dp))
      .border(1.dp, borderColor, RoundedCornerShape(14.dp))
      .clickable(onClick = onClick)
      .padding(horizontal = 6.dp, vertical = 8.dp),
    contentAlignment = Alignment.Center,
  ) {
    Text(
      text = text,
      color = textColor,
      fontSize = 13.sp,
      fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
      maxLines = 1,
    )
  }
}

@Composable
fun CountStepper(
  label: String,
  value: Int?,
  tag: String,
  min: Int = 0,
  max: Int = 8,
  mode: CompassMode = CompassMode.Detailed,
  help: FieldHelpSpec? = null,
  highlightMissing: Boolean = false,
  onChange: (Int?) -> Unit,
) {
  val notSureText = if (mode.showsOperatorData()) stringResource(R.string.operator_unknown) else stringResource(R.string.not_sure)
  val fieldModifier = Modifier
    .fillMaxWidth()
    .then(if (highlightMissing) Modifier.testTag("$tag-missing") else Modifier)
    .then(missingFieldModifier(highlightMissing))
  Column(
    modifier = fieldModifier
      .testTag(tag),
    verticalArrangement = Arrangement.spacedBy(4.dp),
  ) {
    FieldLabel(label = label, mode = mode, help = help, compact = true)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
      FilterChip(
        selected = value == null,
        onClick = { onChange(null) },
        label = { Text(notSureText) },
        modifier = Modifier.testTag("${tag}-not-sure"),
        border = FilterChipDefaults.filterChipBorder(
          enabled = true,
          selected = value == null,
          borderColor = if (highlightMissing) compassAmber().copy(alpha = 0.58f) else compassGray().copy(alpha = 0.45f),
          selectedBorderColor = if (highlightMissing) compassAmber() else compassGray(),
        ),
      )
      IconButton(
        onClick = {
          val current = value
          if (current == null || current <= min) {
            onChange(null)
          } else {
            onChange(current - 1)
          }
        },
        modifier = Modifier
          .size(40.dp)
          .testTag("${tag}-decrease"),
      ) {
        Icon(Icons.Filled.Remove, contentDescription = stringResource(R.string.compass_decrease, label))
      }
      Text(
        value?.toString() ?: "--",
        fontSize = 18.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.widthIn(min = 24.dp),
      )
      IconButton(
        onClick = { onChange(((value ?: (min - 1)) + 1).coerceIn(min, max)) },
        modifier = Modifier
          .size(40.dp)
          .testTag("${tag}-increase"),
      ) {
        Icon(Icons.Filled.Add, contentDescription = stringResource(R.string.compass_increase, label))
      }
    }
  }
}

@Composable
fun RecommendationIcon(
  label: String,
  color: Color,
  notEnoughData: Boolean,
  highRisk: Boolean,
  fallback: @Composable () -> Unit,
) {
  if (notEnoughData) {
    Box(
      modifier = Modifier
        .size(72.dp)
        .background(compassPlusIconCircle(), CircleShape)
        .semantics { contentDescription = label }
        .testTag("weekly-not-enough-data-brand-icon"),
      contentAlignment = Alignment.Center,
    ) {
      Icon(
        painter = painterResource(R.drawable.ll_ic_compass_mark),
        contentDescription = null,
        tint = compassPlusIconTint(),
        modifier = Modifier.size(42.dp),
      )
    }
    return
  }
  if (!highRisk) {
    fallback()
    return
  }
  val floating = LocalCompassFloatingShell.current
  Box(
    modifier = Modifier
      .size(if (floating) 76.dp else 60.dp)
      .background(color.copy(alpha = if (floating) 0.14f else 0.11f), CircleShape)
      .semantics { contentDescription = label },
    contentAlignment = Alignment.Center,
  ) {
    Box(
      modifier = Modifier
        .size(if (floating) 58.dp else 46.dp)
        .background(compassPlusProtectionCircle(), CircleShape),
      contentAlignment = Alignment.Center,
    ) {
      Icon(
        painter = painterResource(R.drawable.ll_ic_recovery_shield_moon),
        contentDescription = null,
        tint = color,
        modifier = Modifier.size(if (floating) 34.dp else 28.dp),
      )
    }
  }
}

@Composable
fun BrandCompassMark(
  sizeDp: Int,
  alpha: Float = 1f,
  tag: String? = null,
) {
  val dark = isSystemInDarkTheme()
  val teal = if (dark) Color(0xFF9FD5C0) else Color(0xFF2F7E65)
  val sage = if (dark) Color(0xFFB7D8C2) else Color(0xFF8DB99B)
  val amber = if (dark) Color(0xFFE5C170) else Color(0xFFC99137)
  Canvas(
    modifier = Modifier
      .size(sizeDp.dp)
      .then(if (tag != null) Modifier.testTag(tag) else Modifier)
      .semantics { contentDescription = "Life Load" },
  ) {
    val strokeWidth = size.minDimension * 0.07f
    drawCircle(
      color = teal.copy(alpha = 0.36f * alpha),
      radius = size.minDimension * 0.40f,
      center = center,
      style = androidx.compose.ui.graphics.drawscope.Stroke(width = strokeWidth),
    )
    drawCircle(
      color = sage.copy(alpha = 0.22f * alpha),
      radius = size.minDimension * 0.28f,
      center = center,
      style = androidx.compose.ui.graphics.drawscope.Stroke(width = size.minDimension * 0.035f),
    )
    fun trianglePath(apexX: Float, apexY: Float, leftX: Float, leftY: Float, rightX: Float, rightY: Float): Path = Path().apply {
      moveTo(size.width * apexX, size.height * apexY)
      lineTo(size.width * leftX, size.height * leftY)
      lineTo(size.width * rightX, size.height * rightY)
      close()
    }
    drawPath(trianglePath(0.50f, 0.16f, 0.42f, 0.48f, 0.58f, 0.48f), teal.copy(alpha = 0.95f * alpha))
    drawPath(trianglePath(0.50f, 0.84f, 0.42f, 0.52f, 0.58f, 0.52f), sage.copy(alpha = 0.70f * alpha))
    drawPath(trianglePath(0.16f, 0.50f, 0.48f, 0.42f, 0.48f, 0.58f), sage.copy(alpha = 0.62f * alpha))
    drawPath(trianglePath(0.84f, 0.50f, 0.52f, 0.42f, 0.52f, 0.58f), sage.copy(alpha = 0.62f * alpha))
    drawPath(trianglePath(0.50f, 0.20f, 0.46f, 0.40f, 0.54f, 0.40f), amber.copy(alpha = 0.95f * alpha))
  }
}

@Composable
private fun missingFieldModifier(active: Boolean): Modifier =
  if (!active) {
    Modifier
  } else {
    Modifier
      .background(compassAmber().copy(alpha = 0.08f), RoundedCornerShape(12.dp))
      .border(1.dp, compassAmber().copy(alpha = 0.42f), RoundedCornerShape(12.dp))
      .padding(8.dp)
  }

@Composable
fun FieldLabel(
  label: String,
  mode: CompassMode,
  help: FieldHelpSpec?,
  compact: Boolean = false,
  valueText: String = "",
) {
  var open by remember { mutableStateOf(false) }
  val localizedHelp = localizedFieldHelp(help)
  Row(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(label, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        if (valueText.isNotBlank()) {
          Text(
            valueText,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
          )
        }
      }
      if (localizedHelp != null && mode.showsDetails() && localizedHelp.shortHelper.isNotBlank()) {
        Text(localizedHelp.shortHelper, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
      }
      if (localizedHelp != null && mode.showsOperatorData() && localizedHelp.internalFieldName.isNotBlank()) {
        Text(localizedHelp.internalFieldName, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
      }
    }
    if (localizedHelp != null && (localizedHelp.shortHelper.isNotBlank() || localizedHelp.longHelper.isNotBlank() || localizedHelp.yesMeaning.isNotBlank() || localizedHelp.noMeaning.isNotBlank())) {
      IconButton(onClick = { open = true }, modifier = Modifier.size(if (compact) 40.dp else 44.dp)) {
        Icon(
          Icons.Filled.Info,
          contentDescription = stringResource(R.string.compass_help_for, label),
          tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.68f),
          modifier = Modifier.size(18.dp),
        )
      }
    }
  }
  if (open && localizedHelp != null) {
    AlertDialog(
      onDismissRequest = { open = false },
      containerColor = if (isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFBFAF6),
      title = { Text(label) },
      text = {
        SelectionContainer {
          Column(
            modifier = Modifier
              .heightIn(max = 420.dp)
              .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp),
          ) {
            if (localizedHelp.shortHelper.isNotBlank()) Text(localizedHelp.shortHelper)
            if (localizedHelp.longHelper.isNotBlank()) Text(localizedHelp.longHelper)
            if (localizedHelp.yesMeaning.isNotBlank()) Text(stringResource(R.string.compass_yes_meaning, localizedHelp.yesMeaning))
            if (localizedHelp.noMeaning.isNotBlank()) Text(stringResource(R.string.compass_no_meaning, localizedHelp.noMeaning))
            if (localizedHelp.unknownMeaning.isNotBlank()) Text(stringResource(R.string.compass_not_sure_meaning, localizedHelp.unknownMeaning))
            if (mode.showsOperatorData() && localizedHelp.internalFieldName.isNotBlank()) {
              Text(stringResource(R.string.compass_internal_field, localizedHelp.internalFieldName), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
          }
        }
      },
      confirmButton = {
        TextButton(onClick = { open = false }) { Text(stringResource(R.string.close)) }
      },
    )
  }
}

@Composable
private fun localizedFieldHelp(help: FieldHelpSpec?): FieldHelpSpec? {
  if (help == null) return null
  val helperRes = when (help.fieldKey) {
    "sleep_on_time" -> R.string.field_sleep_helper
    "food_on_track" -> R.string.field_food_helper
    "alcohol_today" -> R.string.field_alcohol_helper
    "eating_episode" -> R.string.field_eating_episode_helper
    "movement_type" -> R.string.field_activity_type_helper
    "movement_minutes" -> R.string.field_movement_minutes_helper
    "rehab_done" -> R.string.field_rehab_helper
    "decompression_done" -> R.string.field_decompression_helper
    "shutdown" -> R.string.field_shutdown_helper
    "phone_after_21" -> R.string.field_phone_after_21_helper
    "project_overrun" -> R.string.field_project_overrun_helper
    "foot_pain" -> R.string.field_foot_pain_helper
    "shoulder_pain" -> R.string.field_shoulder_pain_helper
    "migraine" -> R.string.field_migraine_helper
    "mood" -> R.string.field_mood_helper
    "stress" -> R.string.field_stress_helper
    "energy" -> R.string.field_energy_helper
    "coffee" -> R.string.field_coffee_helper
    "relationship_tension" -> R.string.field_relationship_tension_helper
    "homework_handled" -> R.string.field_homework_label
    else -> null
  }
  return if (helperRes == null) {
    help
  } else {
    help.copy(
      shortHelper = stringResource(helperRes),
      longHelper = "",
      yesMeaning = "",
      noMeaning = "",
      unknownMeaning = "",
    )
  }
}

@Composable
fun CompassTextField(
  label: String,
  value: String,
  tag: String,
  minLines: Int = 1,
  onValueChange: (String) -> Unit,
) {
  OutlinedTextField(
    value = value,
    onValueChange = onValueChange,
    label = { Text(label) },
    minLines = minLines,
    shape = RoundedCornerShape(12.dp),
    modifier = Modifier
      .fillMaxWidth()
      .testTag(tag),
  )
}

@Composable
fun ExpandableCompassSection(
  title: String,
  summary: String,
  expanded: Boolean,
  tag: String,
  onToggle: () -> Unit,
  summaryColor: Color? = null,
  content: @Composable ColumnScope.() -> Unit,
) {
  CompassCard(title = title, tag = tag, accent = if (expanded) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      Text(summary, color = summaryColor ?: MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
      IconButton(onClick = onToggle, modifier = Modifier.testTag("${tag}_toggle")) {
        Icon(if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown, contentDescription = if (expanded) "Collapse $title" else "Expand $title")
      }
    }
    if (expanded) content()
  }
}

@Composable
fun CompassModeSelector(
  selected: CompassMode,
  onSelect: (CompassMode) -> Unit,
  tagPrefix: String = "compass-mode",
) {
  SegmentedField(
    label = stringResource(R.string.compass_mode),
    selected = selected.name,
    options = CompassMode.entries.map { it.name to it.label },
    tagPrefix = tagPrefix,
  ) { value ->
    onSelect(CompassMode.valueOf(value))
  }
}

fun booleanChoice(value: Boolean?): String = when (value) {
  true -> "yes"
  false -> "no"
  null -> "unknown"
}

fun alcoholChoice(value: String?): String = when (value) {
  "none" -> "none"
  "social" -> "social"
  "home" -> "home"
  else -> "unknown"
}

fun homeworkChoice(done: Boolean?, status: String?): String = when {
  status == "na" -> "na"
  done == true || status == "yes" -> "yes"
  done == false || status == "no" -> "no"
  else -> "unknown"
}

@Composable
fun confidenceLabel(state: LifeLoadUiState): String {
  val confidence = state.score.confidence
  return when {
    !isCheckInSaved(state) -> stringResource(R.string.confidence_not_saved)
    !scoreAvailableForUi(state) -> stringResource(R.string.confidence_pending)
    confidence == null -> stringResource(R.string.confidence_partial)
    confidence >= 0.8 -> stringResource(R.string.confidence_high)
    confidence >= 0.55 -> stringResource(R.string.confidence_medium)
    else -> stringResource(R.string.confidence_partial)
  }
}

fun missingFields(entry: LifeLoadEntry): List<String> = buildList {
  if (entry.sleepOk == null) add("sleep")
  if (entry.nutritionOk == null) add("food")
  if (entry.alcohol == null) add("alcohol")
  if (entry.binge == null) add("eating")
  if (entry.primaryActivityType.isBlank()) add("movement")
  if (entry.stress == null) add("stress")
  if (entry.energy == null) add("energy")
  if (entry.footPain == null && entry.shoulderPain == null) add("pain")
}

fun missingFieldsLabel(entry: LifeLoadEntry): String {
  val missing = missingFields(entry)
  return if (missing.isEmpty()) {
    "No major fields missing"
  } else {
    "Partial confidence: ${missing.take(3).joinToString(", ")} missing"
  }
}

private fun dailyRiskToken(state: LifeLoadUiState): String =
  state.score.zone.ifBlank { state.score.mode }.lowercase()

private fun scoreAvailableForUi(state: LifeLoadUiState): Boolean =
  state.scoreAvailable ?: (state.score.zone.isNotBlank() || state.score.mode.isNotBlank() ||
    state.score.nextAction.isNotBlank() || state.score.why.isNotEmpty() ||
    state.score.warnings.isNotEmpty() || state.score.redFlags.isNotEmpty() ||
    state.score.lifeLoadScore != 0.0 || state.score.confidence != null)

private fun isRecoveryRisk(state: LifeLoadUiState, risk: String = dailyRiskToken(state)): Boolean =
  risk in setOf("red", "stabilize") || state.score.redFlags.isNotEmpty()

private fun isCautionRisk(state: LifeLoadUiState, risk: String = dailyRiskToken(state)): Boolean =
  risk in setOf("orange", "yellow", "protect", "hold", "caution") ||
    state.score.lifeLoadScore * 10.0 >= state.score.guidanceMediumThreshold

@Composable
fun dailyStatus(state: LifeLoadUiState): CompassStatus {
  val pending = state.localDebug.pendingApprovalCount > 0 || state.localDebug.outboxCount > 0
  val conflict = state.localDebug.conflictCount > 0
  return when {
    conflict -> CompassStatus(stringResource(R.string.daily_status_conflict), stringResource(R.string.daily_status_conflict_detail), compassRed(), "conflicts=${state.localDebug.conflictCount}")
    state.hasUnsavedChanges -> CompassStatus(stringResource(R.string.daily_status_unsaved), stringResource(R.string.daily_status_unsaved_detail), compassBlue(), "state=${state.entryState}")
    pending -> CompassStatus(stringResource(R.string.daily_status_pending_sync), stringResource(R.string.daily_status_pending_sync_detail), compassAmber(), "outbox=${state.localDebug.outboxCount}")
    isCheckInSaved(state) && !scoreAvailableForUi(state) -> CompassStatus(stringResource(R.string.daily_status_saved_pending_guidance), stringResource(R.string.daily_status_saved_pending_guidance_detail), compassAmber(), "score=unavailable")
    isCheckInSaved(state) -> CompassStatus(stringResource(R.string.daily_status_saved), stringResource(R.string.daily_status_saved_detail), compassGreen(), "state=${state.entryState}")
    state.hasDraft -> CompassStatus(stringResource(R.string.daily_status_draft), stringResource(R.string.daily_status_draft_detail), compassBlue(), "state=${state.entryState}")
    state.error.isNotBlank() -> CompassStatus(stringResource(R.string.daily_status_offline), stringResource(R.string.daily_status_offline_detail), compassAmber(), state.error)
    else -> CompassStatus(stringResource(R.string.daily_status_ready), stringResource(R.string.daily_status_ready_detail), compassBlue(), "state=${state.entryState}")
  }
}

@Composable
fun dailyHeadline(state: LifeLoadUiState): String {
  val risk = dailyRiskToken(state)
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  return when {
    state.hasUnsavedChanges -> stringResource(R.string.daily_headline_unsaved)
    !isCheckInSaved(state) -> stringResource(R.string.daily_headline_checkin_ready)
    !scoreAvailableForUi(state) -> stringResource(R.string.daily_headline_saved_pending)
    selected == today && isCautionRisk(state, risk) -> stringResource(R.string.daily_headline_tonight_simple)
    selected != null && selected.isBefore(today) && isCautionRisk(state, risk) -> stringResource(R.string.daily_headline_evening_simple)
    risk in setOf("green", "continue") -> stringResource(R.string.daily_headline_steady)
    isRecoveryRisk(state, risk) -> stringResource(R.string.daily_headline_recovery_48h)
    isCautionRisk(state, risk) -> stringResource(R.string.daily_headline_tonight_simple)
    else -> stringResource(R.string.daily_headline_saved)
  }
}

fun dailyMeaning(state: LifeLoadUiState, missing: List<String> = missingFields(state.draftEntry)): String {
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val risk = dailyRiskToken(state)
  val day = if (selected == null || selected == today) "Today" else "This day"
  val saved = isCheckInSaved(state)
  return when {
    selected != null && selected.isAfter(today) -> "This check-in is for a future day."
    state.hasUnsavedChanges -> "This check-in has unsaved changes."
    !saved && selected != null && selected.isBefore(today.minusDays(1)) -> "This day was missed."
    !saved -> "$day’s check-in is still open."
    !scoreAvailableForUi(state) -> "This check-in is saved locally; guidance is still pending."
    isRecoveryRisk(state, risk) -> "$day points toward recovery priority."
    isCautionRisk(state, risk) -> "$day carried more load."
    missing.isNotEmpty() -> "$day looks mostly steady."
    else -> "$day looks steady."
  }
}

@Composable
fun localizedDailyMeaning(state: LifeLoadUiState, missing: List<String> = missingFields(state.draftEntry)): String {
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val risk = dailyRiskToken(state)
  val day = if (selected == null || selected == today) stringResource(R.string.daily_day_today) else stringResource(R.string.daily_day_this_day)
  val saved = isCheckInSaved(state)
  return when {
    selected != null && selected.isAfter(today) -> stringResource(R.string.daily_meaning_future)
    state.hasUnsavedChanges -> stringResource(R.string.daily_meaning_unsaved)
    !saved && selected != null && selected.isBefore(today.minusDays(1)) -> stringResource(R.string.daily_meaning_missed)
    !saved -> stringResource(R.string.daily_meaning_open)
    !scoreAvailableForUi(state) -> stringResource(R.string.daily_meaning_saved_pending)
    isRecoveryRisk(state, risk) -> stringResource(R.string.daily_meaning_recovery, day)
    isCautionRisk(state, risk) -> stringResource(R.string.daily_meaning_more_load, day)
    missing.isNotEmpty() -> stringResource(R.string.daily_meaning_mostly_steady, day)
    else -> stringResource(R.string.daily_meaning_steady, day)
  }
}

fun dailySavedStatus(state: LifeLoadUiState, missing: List<String> = missingFields(state.draftEntry)): String {
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val day = if (selected == null || selected == today) "Today" else "This day"
  val saved = isCheckInSaved(state)
  return when {
    state.hasUnsavedChanges -> "Unsaved changes are stored locally; save when ready."
    saved && !scoreAvailableForUi(state) -> "Your check-in is saved locally; guidance is still pending."
    saved && missing.isNotEmpty() -> "$day is saved, but some details are still missing."
    saved -> "Your core check-in is saved."
    selected != null && selected.isAfter(today) -> "Future check-ins are not ready to save yet."
    state.hasDraft -> "A partial check-in is saved locally."
    else -> "Save the basics when ready."
  }
}

@Composable
fun localizedDailySavedStatus(state: LifeLoadUiState, missing: List<String> = missingFields(state.draftEntry)): String {
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val day = if (selected == null || selected == today) stringResource(R.string.daily_day_today) else stringResource(R.string.daily_day_this_day)
  val saved = isCheckInSaved(state)
  return when {
    state.hasUnsavedChanges -> stringResource(R.string.daily_unsaved_saved_status)
    saved && !scoreAvailableForUi(state) -> stringResource(R.string.daily_saved_pending)
    saved && missing.isNotEmpty() -> stringResource(R.string.daily_saved_missing, day)
    saved -> stringResource(R.string.daily_saved_core)
    selected != null && selected.isAfter(today) -> stringResource(R.string.daily_saved_future)
    state.hasDraft -> stringResource(R.string.daily_saved_partial)
    else -> stringResource(R.string.daily_saved_ready)
  }
}

fun dailyHelpfulStep(state: LifeLoadUiState, missing: List<String> = missingFields(state.draftEntry)): String {
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val risk = dailyRiskToken(state)
  val backendNextAction = state.score.nextAction.trim()
  val saved = isCheckInSaved(state)
  return when {
    selected != null && selected.isAfter(today) -> "Wait until this day arrives."
    state.hasUnsavedChanges -> "• Your latest edit is stored locally.\n• Save when the check-in looks right.\n• Guidance uses the last approved result."
    !saved && selected != null && selected.isBefore(today.minusDays(1)) -> "• Add what you remember.\n• Approximate is fine.\n• Skip what you do not know."
    !saved && missing.isNotEmpty() -> "• Save the basics first.\n• Add details only if they matter today."
    !saved -> "• Save the basics first.\n• Details can stay optional."
    !scoreAvailableForUi(state) -> "• Keep this check-in saved.\n• Guidance will appear after evaluation."
    missing.isNotEmpty() -> "• Add missing details if useful.\n• Treat guidance as partial.\n• Keep the core check-in saved."
    isRecoveryRisk(state, risk) -> "• Sleep first.\n• Reduce optional load.\n• Keep the next 48 hours simple."
    isCautionRisk(state, risk) -> "• Keep tonight simple.\n• Avoid late projects.\n• Protect sleep."
    backendNextAction.isNotBlank() && backendNextAction != "Keep steady." -> backendNextAction
    else -> "• Protect sleep.\n• Keep food simple.\n• Repeat what worked."
  }
}

@Composable
fun localizedDailyHelpfulStep(state: LifeLoadUiState, missing: List<String> = missingFields(state.draftEntry)): String {
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull()
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val risk = dailyRiskToken(state)
  val backendNextAction = state.score.nextAction.trim()
  val saved = isCheckInSaved(state)
  return when {
    selected != null && selected.isAfter(today) -> stringResource(R.string.daily_helpful_future)
    state.hasUnsavedChanges -> stringResource(R.string.daily_helpful_unsaved)
    !saved && selected != null && selected.isBefore(today.minusDays(1)) -> stringResource(R.string.daily_helpful_missed)
    !saved && missing.isNotEmpty() -> stringResource(R.string.daily_helpful_missing)
    !saved -> stringResource(R.string.daily_helpful_save_basics)
    !scoreAvailableForUi(state) -> stringResource(R.string.daily_saved_pending)
    missing.isNotEmpty() -> stringResource(R.string.daily_helpful_partial)
    isRecoveryRisk(state, risk) -> stringResource(R.string.daily_helpful_recovery)
    isCautionRisk(state, risk) -> stringResource(R.string.daily_helpful_caution)
    backendNextAction.isNotBlank() && backendNextAction != "Keep steady." && Locale.getDefault().language != "de" -> backendNextAction
    else -> stringResource(R.string.daily_helpful_default)
  }
}

@Composable
fun nextActionText(state: LifeLoadUiState): String {
  if (state.hasUnsavedChanges) return stringResource(R.string.daily_helpful_unsaved)
  if (isCheckInSaved(state) && !scoreAvailableForUi(state)) return stringResource(R.string.daily_saved_pending)
  return state.score.nextAction.ifBlank {
    if (!isCheckInSaved(state)) {
      val missing = missingFields(state.draftEntry)
      if (missing.isEmpty()) stringResource(R.string.daily_next_action_save_when_ready)
      else stringResource(R.string.daily_next_action_add_missing, missing.take(3).joinToString(", "))
    } else {
      stringResource(R.string.daily_next_action_saved_confidence, confidenceLabel(state).lowercase())
    }
  }
}

fun formatDate(date: String): String =
  runCatching {
    val parsed = LocalDate.parse(date)
    parsed.format(DateTimeFormatter.ofPattern("EEE, d MMM", Locale.getDefault()))
  }.getOrDefault(date)

fun formatLastSavedAt(value: String, zoneId: ZoneId = ZoneId.of("Europe/Vienna")): String {
  val raw = value.trim()
  if (raw.isBlank()) return ""
  val localDateTime = runCatching {
    Instant.parse(raw).atZone(zoneId).toLocalDateTime()
  }.getOrNull()
    ?: runCatching { OffsetDateTime.parse(raw).atZoneSameInstant(zoneId).toLocalDateTime() }.getOrNull()
    ?: runCatching { LocalDateTime.parse(raw) }.getOrNull()
    ?: return raw
  val today = LocalDate.now(zoneId)
  val pattern = if (localDateTime.toLocalDate() == today) {
    "HH:mm"
  } else {
    "MMM d, HH:mm"
  }
  return localDateTime.format(DateTimeFormatter.ofPattern(pattern, Locale.getDefault()))
}

@Composable
fun localizedIntensityLabel(value: Int): String = when {
  value <= 0 -> stringResource(R.string.compass_intensity_none, value)
  value <= 2 -> stringResource(R.string.compass_intensity_low, value)
  value <= 4 -> stringResource(R.string.compass_intensity_moderate, value)
  value <= 6 -> stringResource(R.string.compass_intensity_high, value)
  value <= 8 -> stringResource(R.string.compass_intensity_very_high, value)
  else -> stringResource(R.string.compass_intensity_extreme, value)
}

fun intensityLabel(value: Int): String = when {
  value <= 0 -> "0 · none"
  value <= 2 -> "$value · low"
  value <= 4 -> "$value · moderate"
  value <= 6 -> "$value · high"
  value <= 8 -> "$value · very high"
  else -> "$value · extreme"
}
