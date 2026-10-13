package com.life.lifeload.ui.compass

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.sp
import com.life.lifeload.BuildConfig
import com.life.lifeload.R
import com.life.lifeload.domain.onboardingVisibleForNewUser
import com.life.lifeload.ui.LifeLoadUiActions
import com.life.lifeload.ui.LifeLoadUiState
import com.life.lifeload.ui.LifeLoadUiVariant
import com.life.lifeload.ui.profile.ProfileOnboardingForFlag
import com.life.lifeload.ui.profile.defaultProfileFeatureFlags
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private const val compassFloatingShellEnabled = true

private enum class CompassPlusSurface {
  Guidance,
  CheckIn,
  Settings,
}

@Composable
fun CompassPlusRoot(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  if (!compassFloatingShellEnabled) {
    CompassRoot(state = state, actions = actions, selectedVariant = selectedVariant, onVariantSelected = onVariantSelected)
    return
  }

  var surface by rememberSaveable { mutableStateOf(CompassPlusSurface.Guidance) }
  var lastDailySurface by rememberSaveable { mutableStateOf(CompassPlusSurface.Guidance) }
  var mode by rememberSaveable { mutableStateOf(CompassMode.Simple) }
  var expandMissingSignals by rememberSaveable { mutableStateOf(false) }
  var systemHelpOpen by rememberSaveable { mutableStateOf(false) }
  val profileFeatureFlags = defaultProfileFeatureFlags()
  val listState = rememberLazyListState()
  val coroutineScope = rememberCoroutineScope()

  if (systemHelpOpen) {
    LifeLoadSystemHelpDialog(onDismiss = { systemHelpOpen = false })
  }
  if (onboardingVisibleForNewUser(profileFeatureFlags, state.profileOnboardingCompleted)) {
    ProfileOnboardingForFlag(
      flags = profileFeatureFlags,
      hasExistingSelection = state.profileOnboardingCompleted,
      selectedProfileId = state.profileSetup.selectedConfig.activeProfileId,
      onProfileSelected = actions.onProfileSelected,
      onStartFirstCheckIn = {
        actions.onCompleteProfileOnboarding()
        surface = CompassPlusSurface.CheckIn
        lastDailySurface = CompassPlusSurface.CheckIn
        coroutineScope.launch { listState.animateScrollToItem(0) }
      },
    )
  }

  val background = compassPlusBackground()
  CompositionLocalProvider(LocalCompassFloatingShell provides true) {
    BoxWithConstraints(
      modifier = Modifier
        .fillMaxSize()
        .background(background),
    ) {
      val density = LocalDensity.current
      var headerHeightPx by remember { mutableStateOf(0) }
      val contentWidth = compassPlusContentWidth(maxWidth)
      val headerWidth = compassPlusHeaderWidth(maxWidth, contentWidth)
      val measuredHeaderHeight = with(density) { headerHeightPx.toDp() }
      val headerGap = (maxHeight * 0.010f).coerceIn(4.dp, 8.dp)
      val contentTopPadding = if (headerHeightPx > 0) {
        measuredHeaderHeight + headerGap
      } else {
        (maxHeight * 0.17f).coerceIn(104.dp, 128.dp)
      }

      LazyColumn(
        state = listState,
        modifier = Modifier
          .align(Alignment.TopCenter)
          .fillMaxHeight()
          .width(contentWidth)
          .navigationBarsPadding()
          .testTag("compass-plus-content"),
        contentPadding = PaddingValues(top = contentTopPadding, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
      ) {
        item {
          CompassPlusControlRow(
            surface = if (surface == CompassPlusSurface.Settings) lastDailySurface else surface,
            onSurfaceSelected = { next ->
              surface = next
              lastDailySurface = next
              if (next == CompassPlusSurface.Settings) actions.onOpenSettings()
              coroutineScope.launch { listState.animateScrollToItem(0) }
            },
          )
        }
        when (surface) {
          CompassPlusSurface.Guidance -> compassWeekItems(state = state, actions = actions, mode = mode)
          CompassPlusSurface.CheckIn -> compassTodayItems(
            state = state,
            actions = actions,
            mode = mode,
            openDetails = {
              surface = CompassPlusSurface.CheckIn
              mode = CompassMode.Detailed
              expandMissingSignals = true
              val missing = missingFields(state.draftEntry)
              val quickMissing = missing.any { it in setOf("sleep", "food", "alcohol", "eating") }
              coroutineScope.launch { listState.animateScrollToItem(if (quickMissing) 2 else 4) }
            },
            expandMissingSignals = expandMissingSignals,
          )
          CompassPlusSurface.Settings -> compassSettingsItems(
            state = state,
            actions = actions,
            mode = mode,
            setMode = { mode = it },
            selectedVariant = selectedVariant,
            onVariantSelected = onVariantSelected,
          )
        }
        item {
          Spacer(Modifier.height(8.dp))
        }
      }
      CompassPlusTopFade(
        modifier = Modifier
          .fillMaxWidth()
          .align(Alignment.TopCenter),
      )
      Box(
        modifier = Modifier
          .fillMaxWidth()
          .align(Alignment.TopCenter),
      ) {
        CompassPlusHeader(
          state = state,
          actions = actions,
          modifier = Modifier
            .align(Alignment.TopCenter)
            .width(headerWidth)
            .onSizeChanged { headerHeightPx = it.height },
          onOpenHelp = { systemHelpOpen = true },
          onOpenSettings = {
            if (surface != CompassPlusSurface.Settings) lastDailySurface = surface
            surface = CompassPlusSurface.Settings
            actions.onOpenSettings()
            coroutineScope.launch { listState.animateScrollToItem(0) }
          },
          onOpenPrivacy = {
            if (surface != CompassPlusSurface.Settings) lastDailySurface = surface
            surface = CompassPlusSurface.Settings
            actions.onOpenSettings()
            coroutineScope.launch { listState.animateScrollToItem(5) }
          },
        )
      }
    }
  }
}

private fun compassPlusContentWidth(screenWidth: Dp): Dp {
  val sideMargin = if (screenWidth >= 600.dp) 32.dp else 20.dp
  val available = screenWidth - (sideMargin * 2)
  val maxReadableWidth = when {
    screenWidth >= 840.dp -> 720.dp
    screenWidth >= 600.dp -> 640.dp
    else -> available
  }
  return available
    .coerceAtMost(maxReadableWidth)
    .coerceAtLeast(280.dp)
}

private fun compassPlusHeaderWidth(screenWidth: Dp, contentWidth: Dp): Dp =
  (contentWidth + 40.dp).coerceAtMost(screenWidth)

@Composable
private fun CompassPlusTopFade(modifier: Modifier = Modifier) {
  val topColor = if (isSystemInDarkTheme()) {
    MaterialTheme.colorScheme.background
  } else {
    Color(0xFFF7F1E6)
  }
  Box(
    modifier = modifier
      .height(164.dp)
      .background(
        Brush.verticalGradient(
          colorStops = arrayOf(
            0.00f to topColor,
            0.16f to topColor.copy(alpha = 0.92f),
            0.46f to topColor.copy(alpha = 0.36f),
            0.78f to topColor.copy(alpha = 0f),
          ),
        ),
      ),
  )
}

@Composable
private fun CompassPlusHeader(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  modifier: Modifier = Modifier,
  onOpenHelp: () -> Unit,
  onOpenSettings: () -> Unit,
  onOpenPrivacy: () -> Unit,
) {
  var menuOpen by rememberSaveable { mutableStateOf(false) }
  Row(
    modifier = modifier
      .fillMaxWidth()
      .statusBarsPadding()
      .padding(horizontal = 20.dp, vertical = 14.dp)
      .testTag("compass-plus-header"),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Card(
      modifier = Modifier
        .height(64.dp)
        .widthIn(min = 132.dp, max = 146.dp)
        .testTag("compass-plus-brand-container"),
      shape = RoundedCornerShape(30.dp),
      colors = CardDefaults.cardColors(containerColor = compassPlusFloatingSurface()),
      elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
    ) {
      Row(
        modifier = Modifier
          .height(64.dp)
          .clip(RoundedCornerShape(30.dp))
          .clickable(onClick = onOpenHelp)
          .padding(horizontal = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Box(
          modifier = Modifier
            .size(42.dp)
            .background(compassPlusIconCircle(), CircleShape)
            .testTag("compass-plus-brand-mark"),
          contentAlignment = Alignment.Center,
        ) {
          Icon(
            painter = painterResource(R.drawable.ll_ic_compass_mark),
            contentDescription = stringResource(R.string.life_load),
            tint = compassPlusIconTint(),
            modifier = Modifier.size(27.dp),
          )
        }
        Text(
          stringResource(R.string.life_load).replace(" ", "\n"),
          fontSize = 18.sp,
          fontWeight = FontWeight.SemiBold,
          lineHeight = 18.sp,
          maxLines = 2,
        )
      }
    }
    CompassPlusDatePill(
      state = state,
      actions = actions,
      modifier = Modifier
        .weight(1f)
        .padding(horizontal = 8.dp),
      compact = true,
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
      Box {
        CompassPlusCircleButton(tag = "compass-plus-overflow", onClick = { menuOpen = true }) {
          Icon(Icons.Filled.MoreVert, contentDescription = stringResource(R.string.compass_plus_overflow_content_description))
        }
        DropdownMenu(
          expanded = menuOpen,
          onDismissRequest = { menuOpen = false },
          containerColor = compassPlusFloatingSurface(),
          tonalElevation = 0.dp,
          shadowElevation = 6.dp,
        ) {
          DropdownMenuItem(
            text = { Text(stringResource(R.string.nav_settings)) },
            modifier = Modifier.testTag("compass-plus-menu-settings"),
            onClick = {
              menuOpen = false
              onOpenSettings()
            },
          )
          DropdownMenuItem(
            text = { Text(stringResource(R.string.compass_plus_privacy_backup)) },
            modifier = Modifier.testTag("compass-plus-menu-backup"),
            onClick = {
              menuOpen = false
              onOpenPrivacy()
            },
          )
          DropdownMenuItem(
            text = { Text(stringResource(R.string.life_load_help_title)) },
            modifier = Modifier.testTag("compass-plus-menu-help"),
            onClick = {
              menuOpen = false
              onOpenHelp()
            },
          )
          if (BuildConfig.DEBUG) {
            DropdownMenuItem(
              text = { Text(stringResource(R.string.settings_developer_diagnostics)) },
              modifier = Modifier.testTag("compass-plus-menu-developer"),
              onClick = {
                menuOpen = false
                onOpenSettings()
              },
            )
          }
        }
      }
    }
  }
}

@Composable
private fun CompassPlusCircleButton(
  tag: String,
  onClick: () -> Unit,
  content: @Composable () -> Unit,
) {
  Card(
    modifier = Modifier
      .size(48.dp),
    shape = CircleShape,
    colors = CardDefaults.cardColors(containerColor = compassPlusFloatingSurface()),
    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
  ) {
    IconButton(
      onClick = onClick,
      modifier = Modifier
        .fillMaxSize()
        .testTag(tag),
    ) {
      content()
    }
  }
}

@Composable
private fun CompassPlusControlRow(
  surface: CompassPlusSurface,
  onSurfaceSelected: (CompassPlusSurface) -> Unit,
) {
  Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("compass-plus-control-row")) {
    CompassPlusSurfaceToggle(surface = surface, onSurfaceSelected = onSurfaceSelected)
  }
}

@Composable
private fun CompassPlusDatePill(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  modifier: Modifier = Modifier,
  compact: Boolean = false,
) {
  val today = compassPlusToday()
  val selected = runCatching { LocalDate.parse(state.selectedDate) }.getOrNull() ?: today
  val canGoNext = compassPlusCanGoNext(selected = selected, today = today)
  val todayLabel = stringResource(R.string.today)
  val yesterdayLabel = stringResource(if (compact) R.string.yesterday_short else R.string.yesterday)
  Box(modifier = modifier.fillMaxWidth()) {
    Card(
      modifier = Modifier
        .widthIn(max = if (compact) 220.dp else 360.dp)
        .align(Alignment.Center)
        .testTag("compass-plus-date-pill"),
      shape = RoundedCornerShape(28.dp),
      colors = CardDefaults.cardColors(containerColor = compassPlusFloatingSurface()),
      elevation = CardDefaults.cardElevation(defaultElevation = if (compact) 4.dp else 5.dp),
    ) {
      Row(
        modifier = Modifier
          .fillMaxWidth()
          .heightIn(min = if (compact) 54.dp else 62.dp)
          .padding(horizontal = if (compact) 0.dp else 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Box(
          modifier = Modifier
            .width(if (compact) 38.dp else 54.dp)
            .height(if (compact) 54.dp else 62.dp)
            .clickable(onClick = actions.onPreviousDate)
            .testTag("compass-plus-previous-day"),
          contentAlignment = Alignment.Center,
        ) {
          Icon(
            Icons.AutoMirrored.Filled.ArrowBack,
            contentDescription = stringResource(R.string.previous_day),
            modifier = Modifier.size(if (compact) 24.dp else 28.dp),
          )
        }
        Box(
          modifier = Modifier
            .weight(1f)
            .height(if (compact) 54.dp else 62.dp)
            .clickable(onClick = actions.onToday)
            .testTag("compass-plus-date-label"),
          contentAlignment = Alignment.Center,
        ) {
          Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(
              selected.format(DateTimeFormatter.ofPattern("MMM d", Locale.getDefault())),
              color = MaterialTheme.colorScheme.primary,
              fontSize = if (compact) 14.sp else 16.sp,
              fontWeight = FontWeight.SemiBold,
              maxLines = 1,
              overflow = TextOverflow.Ellipsis,
            )
            Text(
              compassPlusDateSubLabel(selected, today, todayLabel, yesterdayLabel),
              color = MaterialTheme.colorScheme.onSurfaceVariant,
              fontSize = if (compact) 10.sp else 11.sp,
              fontWeight = FontWeight.SemiBold,
              maxLines = 1,
              overflow = TextOverflow.Ellipsis,
            )
          }
        }
        Box(
          modifier = Modifier
            .width(if (compact) 38.dp else 54.dp)
            .height(if (compact) 54.dp else 62.dp)
            .then(if (canGoNext) Modifier.clickable(onClick = actions.onNextDate) else Modifier)
            .testTag("compass-plus-next-day"),
          contentAlignment = Alignment.Center,
        ) {
          Icon(
            Icons.AutoMirrored.Filled.ArrowForward,
            contentDescription = stringResource(R.string.next_day),
            tint = MaterialTheme.colorScheme.onSurface.copy(alpha = if (canGoNext) 1f else 0.34f),
            modifier = Modifier.size(if (compact) 24.dp else 28.dp),
          )
        }
      }
    }
  }
}

internal fun compassPlusToday(): LocalDate = LocalDate.now(ZoneId.of("Europe/Vienna"))

internal fun compassPlusCanGoNext(selected: LocalDate, today: LocalDate = compassPlusToday()): Boolean =
  selected.isBefore(today)

private fun compassPlusDateSubLabel(selected: LocalDate, today: LocalDate, todayLabel: String, yesterdayLabel: String): String {
  val weekday = selected.format(DateTimeFormatter.ofPattern("EEE", Locale.getDefault()))
  return when (selected) {
    today -> "$todayLabel · $weekday"
    today.minusDays(1) -> "$yesterdayLabel · $weekday"
    else -> weekday
  }
}

@Composable
private fun CompassPlusSurfaceToggle(
  surface: CompassPlusSurface,
  onSurfaceSelected: (CompassPlusSurface) -> Unit,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .testTag("compass-plus-segmented-toggle"),
    shape = RoundedCornerShape(30.dp),
    colors = CardDefaults.cardColors(containerColor = compassPlusFloatingSurface()),
    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
  ) {
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .padding(6.dp),
      horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
      CompassPlusSegment(
        label = stringResource(R.string.nav_guidance),
        selected = surface == CompassPlusSurface.Guidance,
        tag = "compass-plus-guidance",
        onClick = { onSurfaceSelected(CompassPlusSurface.Guidance) },
        modifier = Modifier.weight(1f),
      )
      CompassPlusSegment(
        label = stringResource(R.string.nav_check_in),
        selected = surface == CompassPlusSurface.CheckIn,
        tag = "compass-plus-check-in",
        onClick = { onSurfaceSelected(CompassPlusSurface.CheckIn) },
        modifier = Modifier.weight(1f),
      )
    }
  }
}

@Composable
private fun CompassPlusSegment(
  label: String,
  selected: Boolean,
  tag: String,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
) {
  Box(
    modifier = modifier
      .heightIn(min = 48.dp)
      .clip(RoundedCornerShape(24.dp))
      .background(if (selected) compassPlusSelectedSegment() else Color.Transparent)
      .clickable(onClick = onClick)
      .testTag(tag),
    contentAlignment = Alignment.Center,
  ) {
    Text(
      label,
      color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
      fontSize = 15.sp,
      fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
    )
  }
}

@Composable
private fun compassPlusBackground(): Brush =
  if (isSystemInDarkTheme()) {
    Brush.verticalGradient(
      listOf(
        MaterialTheme.colorScheme.background,
        MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.34f),
      ),
    )
  } else {
    Brush.verticalGradient(listOf(Color(0xFFF7F1E6), Color(0xFFFFF7EC)))
  }

@Composable
private fun compassPlusFloatingSurface(): Color =
  if (isSystemInDarkTheme()) MaterialTheme.colorScheme.surface.copy(alpha = 0.96f) else Color(0xFFFFFDF7)

@Composable
private fun compassPlusSelectedSegment(): Color =
  if (isSystemInDarkTheme()) MaterialTheme.colorScheme.primary.copy(alpha = 0.18f) else Color(0xFFE8F0E4)

@Composable
private fun compassPlusBorder(): Color =
  if (isSystemInDarkTheme()) MaterialTheme.colorScheme.outline.copy(alpha = 0.28f) else Color(0xFFDDD3C5)

@Composable
private fun compassPlusSurfaceLabel(surface: CompassPlusSurface): String = when (surface) {
  CompassPlusSurface.Guidance -> stringResource(R.string.nav_guidance)
  CompassPlusSurface.CheckIn -> stringResource(R.string.nav_check_in)
  CompassPlusSurface.Settings -> stringResource(R.string.nav_settings)
}
