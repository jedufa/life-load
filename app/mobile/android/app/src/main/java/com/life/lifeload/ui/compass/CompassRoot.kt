package com.life.lifeload.ui.compass

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import com.life.lifeload.R
import com.life.lifeload.ui.LifeLoadUiActions
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.LifeLoadUiVariant
import com.life.lifeload.ui.LifeLoadUiVariantRegistry
import com.life.lifeload.ui.isCheckInSaved
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun CompassRoot(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  var screen by rememberSaveable { mutableStateOf(CompassScreen.Week) }
  var mode by rememberSaveable { mutableStateOf(CompassMode.Simple) }
  var expandMissingSignals by rememberSaveable { mutableStateOf(false) }
  var systemHelpOpen by rememberSaveable { mutableStateOf(false) }
  val listState = rememberLazyListState()
  val coroutineScope = rememberCoroutineScope()

  if (systemHelpOpen) {
    LifeLoadSystemHelpDialog(onDismiss = { systemHelpOpen = false })
  }

  Scaffold(
    topBar = {
      CompassHeader(
        screen = screen,
        mode = mode,
        state = state,
        actions = actions,
        onOpenSystemHelp = { systemHelpOpen = true },
      )
    },
    bottomBar = {
      CompassBottomBar(
        screen = screen,
        onScreenSelected = { next ->
          screen = next
          if (next == CompassScreen.Settings) actions.onOpenSettings()
          coroutineScope.launch { listState.animateScrollToItem(0) }
        },
      )
    },
  ) { padding ->
    LazyColumn(
      state = listState,
      modifier = Modifier
        .fillMaxSize()
          .background(
            Brush.verticalGradient(
            listOf(
              MaterialTheme.colorScheme.background,
              MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.34f),
            ),
          ),
        )
        .padding(padding)
        .padding(horizontal = 16.dp)
        .testTag("compass-content"),
      verticalArrangement = Arrangement.spacedBy(10.dp),
  ) {
      when (screen) {
        CompassScreen.Today -> compassTodayItems(
          state = state,
          actions = actions,
          mode = mode,
          openDetails = {
            mode = CompassMode.Detailed
            expandMissingSignals = true
            val missing = missingFields(state.draftEntry)
            val quickMissing = missing.any { it in setOf("sleep", "food", "alcohol", "eating") }
            coroutineScope.launch { listState.animateScrollToItem(if (quickMissing) 1 else 3) }
          },
          expandMissingSignals = expandMissingSignals,
        )
        CompassScreen.Week -> compassWeekItems(
          state = state,
          actions = actions,
          mode = mode,
        )
        CompassScreen.Settings -> compassSettingsItems(
          state = state,
          actions = actions,
          mode = mode,
          setMode = { mode = it },
          selectedVariant = selectedVariant,
          onVariantSelected = onVariantSelected,
        )
      }
    }
  }
}

@Composable
private fun CompassBottomBar(
  screen: CompassScreen,
  onScreenSelected: (CompassScreen) -> Unit,
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.background)
      .navigationBarsPadding()
      .heightIn(min = 58.dp)
      .padding(horizontal = 10.dp, vertical = 4.dp)
      .testTag("compass-bottom-nav"),
    horizontalArrangement = Arrangement.SpaceEvenly,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    CompassBottomBarItem(
      selected = screen == CompassScreen.Week,
      icon = Icons.AutoMirrored.Filled.TrendingUp,
      label = stringResource(R.string.nav_guidance),
      tag = "nav-week",
      onClick = { onScreenSelected(CompassScreen.Week) },
    )
    CompassBottomBarItem(
      selected = screen == CompassScreen.Today,
      icon = Icons.Filled.Today,
      label = stringResource(R.string.nav_check_in),
      tag = "nav-today",
      onClick = { onScreenSelected(CompassScreen.Today) },
    )
    CompassBottomBarItem(
      selected = screen == CompassScreen.Settings,
      icon = Icons.Filled.Settings,
      label = stringResource(R.string.nav_settings),
      tag = "nav-settings",
      onClick = { onScreenSelected(CompassScreen.Settings) },
    )
  }
}

@Composable
private fun CompassBottomBarItem(
  selected: Boolean,
  icon: ImageVector,
  label: String,
  tag: String,
  onClick: () -> Unit,
) {
  val selectedColor = if (isSystemInDarkTheme()) {
    MaterialTheme.colorScheme.primary
  } else {
    MaterialTheme.colorScheme.primary.copy(alpha = 0.92f)
  }
  val contentColor = if (selected) selectedColor else MaterialTheme.colorScheme.onSurfaceVariant
  val background = if (selected) selectedColor.copy(alpha = if (isSystemInDarkTheme()) 0.18f else 0.12f) else Color.Transparent
  Column(
    modifier = Modifier
      .heightIn(min = 48.dp)
      .background(background, RoundedCornerShape(14.dp))
      .clickable(onClick = onClick)
      .padding(horizontal = 14.dp, vertical = 5.dp)
      .testTag(tag),
    horizontalAlignment = Alignment.CenterHorizontally,
    verticalArrangement = Arrangement.Center,
  ) {
    Icon(icon, contentDescription = null, tint = contentColor, modifier = Modifier.size(21.dp))
    Text(label, color = contentColor, fontSize = 11.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
  }
}

@Composable
private fun CompassHeader(
  screen: CompassScreen,
  mode: CompassMode,
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  onOpenSystemHelp: () -> Unit,
) {
  val status = dailyStatus(state)
  val showAttentionStatus = state.error.isNotBlank() ||
    state.localDebug.pendingApprovalCount > 0 ||
    state.localDebug.outboxCount > 0 ||
    state.localDebug.conflictCount > 0
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.background)
      .statusBarsPadding()
      .padding(horizontal = 16.dp, vertical = 3.dp),
    verticalArrangement = Arrangement.spacedBy(0.dp),
  ) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically) {
        BrandCompassMark(sizeDp = 24, tag = "compass-header-brand-mark")
        Column {
          Text(stringResource(R.string.life_load), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
          Text(compassScreenLabel(screen, state), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
      }
      Row(horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.CenterVertically) {
        if (mode.showsOperatorData()) {
          StatusPill(
            label = status.technical.ifBlank { status.label },
            color = status.color,
            tag = "compass-header-status",
            type = headerStatusType(status.label),
          )
        } else if (mode.showsDetails() && showAttentionStatus) {
          StatusPill(status.label, status.color, "compass-header-status", type = headerStatusType(status.label))
        }
        if (screen == CompassScreen.Settings) {
          IconButton(onClick = onOpenSystemHelp, modifier = Modifier.size(40.dp).testTag("life-load-system-help")) {
            Icon(Icons.AutoMirrored.Filled.HelpOutline, contentDescription = stringResource(R.string.life_load_help_content_description))
          }
        }
        if (screen != CompassScreen.Settings) {
          HeaderDateControls(state = state, actions = actions)
        }
      }
    }
  }
}

@Composable
internal fun LifeLoadSystemHelpDialog(onDismiss: () -> Unit) {
  AlertDialog(
    onDismissRequest = onDismiss,
    modifier = Modifier
      .fillMaxWidth(0.92f)
      .widthIn(max = 560.dp),
    containerColor = if (isSystemInDarkTheme()) MaterialTheme.colorScheme.surface else Color(0xFFFBFAF6),
    properties = DialogProperties(usePlatformDefaultWidth = false),
    confirmButton = {
      TextButton(onClick = onDismiss) {
        Text(stringResource(R.string.close))
      }
    },
    title = { Text(stringResource(R.string.life_load_help_title)) },
    text = {
      SelectionContainer {
        Column(
          modifier = Modifier
            .heightIn(max = 460.dp)
            .verticalScroll(rememberScrollState()),
          verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
          HelpSection(
            title = stringResource(R.string.life_load_help_why_title),
            body = stringResource(R.string.life_load_help_why_body),
          )
          HelpSection(
            title = stringResource(R.string.life_load_help_formula_title),
            body = stringResource(R.string.life_load_help_formula_body),
          )
          HelpSection(
            title = stringResource(R.string.life_load_help_combinations_title),
            body = stringResource(R.string.life_load_help_combinations_body),
          )
          HelpSection(
            title = stringResource(R.string.life_load_help_science_title),
            body = stringResource(R.string.life_load_help_science_body),
          )
          HelpSection(
            title = stringResource(R.string.life_load_help_limits_title),
            body = stringResource(R.string.life_load_help_limits_body),
          )
        }
      }
    },
  )
}

@Composable
private fun HelpSection(title: String, body: String) {
  Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
    Text(title, fontWeight = FontWeight.SemiBold)
    Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
  }
}

@Composable
private fun HeaderDateControls(state: LifeLoadUiState, actions: LifeLoadUiActions) {
  val today = LocalDate.now(ZoneId.of("Europe/Vienna"))
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull() ?: today
  val canGoNext = selected.isBefore(today)
  val todayLabel = stringResource(R.string.today)
  val yesterdayLabel = stringResource(R.string.yesterday_short)
  Row(
    horizontalArrangement = Arrangement.spacedBy(0.dp),
    verticalAlignment = Alignment.CenterVertically,
    modifier = Modifier
      .heightIn(min = 48.dp)
      .testTag("daily-day-navigator"),
  ) {
    IconButton(onClick = actions.onPreviousDate, modifier = Modifier.size(48.dp).testTag("daily-previous-day")) {
      Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.previous_day), modifier = Modifier.size(28.dp))
    }
    Box(
      modifier = Modifier
        .heightIn(min = 48.dp)
        .widthIn(min = 68.dp)
        .clickable(onClick = actions.onToday)
        .testTag("daily-today"),
      contentAlignment = Alignment.Center,
    ) {
      Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(1.dp)) {
        Text(
          selected.format(DateTimeFormatter.ofPattern("MMM d", Locale.getDefault())),
          color = MaterialTheme.colorScheme.onSurface,
          fontSize = 14.sp,
          fontWeight = FontWeight.SemiBold,
          modifier = Modifier.testTag("daily-date-label"),
        )
        Text(
          headerDateSubLabel(selected, today, todayLabel, yesterdayLabel),
          color = MaterialTheme.colorScheme.onSurfaceVariant,
          fontSize = 11.sp,
          fontWeight = FontWeight.SemiBold,
        )
      }
    }
    IconButton(onClick = actions.onNextDate, enabled = canGoNext, modifier = Modifier.size(48.dp).testTag("daily-next-day")) {
      Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = stringResource(R.string.next_day), modifier = Modifier.size(28.dp))
    }
  }
}

private fun headerDateSubLabel(selected: LocalDate, today: LocalDate, todayLabel: String, yesterdayLabel: String): String {
  val weekday = selected.format(DateTimeFormatter.ofPattern("EEE", Locale.getDefault()))
  return when (selected) {
    today -> "$todayLabel · $weekday"
    today.minusDays(1) -> "$yesterdayLabel · $weekday"
    else -> weekday
  }
}

private fun headerStatusType(label: String): StatusPillType = when (label) {
  "Conflict" -> StatusPillType.Danger
  "Offline",
  "Pending sync" -> StatusPillType.Warning
  "Saved" -> StatusPillType.Positive
  else -> StatusPillType.Info
}

@Composable
private fun compassScreenLabel(screen: CompassScreen, state: LifeLoadUiState): String = when (screen) {
  CompassScreen.Today -> stringResource(
    R.string.check_in_header_with_status,
    stringResource(
      when {
        state.hasUnsavedChanges -> R.string.check_in_status_unsaved
        isCheckInSaved(state) -> R.string.check_in_status_done
        else -> R.string.check_in_status_open
      },
    ),
  )
  CompassScreen.Week -> stringResource(R.string.nav_guidance)
  CompassScreen.Settings -> stringResource(R.string.nav_settings)
}

@Composable
fun CompassVariantSelector(
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  SegmentedField(
    label = stringResource(R.string.gui_option),
    selected = selectedVariant.id,
    options = LifeLoadUiVariantRegistry.all.map { it.id to it.label },
    tagPrefix = "debug_gui_option",
  ) { id ->
    onVariantSelected(LifeLoadUiVariantRegistry.fromId(id))
  }
}
