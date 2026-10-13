package com.life.lifeload.ui

import android.app.Application
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.life.lifeload.BuildConfig
import com.life.lifeload.R
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.domain.LifeLoadBackendStatus
import com.life.lifeload.domain.LifeLoadDbStatus
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadExtractStatus
import com.life.lifeload.domain.LifeLoadFormulaSettings
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.LifeLoadSyncStatus
import com.life.lifeload.domain.LifeLoadTrendPoint
import com.life.lifeload.domain.onboardingVisibleForNewUser
import com.life.lifeload.ui.profile.DevProfileSelectorCard
import com.life.lifeload.ui.profile.ProfileOnboardingForFlag
import com.life.lifeload.ui.profile.TrackingSetupSettingsEntryCard
import com.life.lifeload.ui.profile.defaultProfileFeatureFlags
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val LifeLoadInk = Color(0xFF241F18)
private val LifeLoadMuted = Color(0xFF766D61)
private val LifeLoadPanel = Color(0xFFFFFDF7)
private val LifeLoadPanelWarm = Color(0xFFF2E7D3)
private val LifeLoadLine = Color(0xFF4F4331)
private val LifeLoadGreen = Color(0xFF286F46)
private val LifeLoadYellow = Color(0xFF937016)
private val LifeLoadOrange = Color(0xFFB35D1C)
private val LifeLoadRed = Color(0xFFA93832)
private val LifeLoadBlue = Color(0xFF315F84)
private val LifeLoadAccent = Color(0xFF1F6959)

private val CompactScreenPadding = 6.dp
private val CompactSectionGap = 6.dp
private val CompactCardPadding = 8.dp
private val CompactInlineGap = 4.dp
private val CompactFieldGap = 4.dp
private val CompactTightGap = 2.dp

private val LifeLoadLabelTextStyle = TextStyle(
  fontSize = 12.sp,
  lineHeight = 16.sp,
  fontWeight = FontWeight.Medium,
)

private fun compactScreenContentPadding(): PaddingValues = PaddingValues(CompactScreenPadding)

internal enum class LifeLoadDestination {
  Weekly,
  Daily,
  Settings,
}

internal fun defaultLifeLoadDestinationName(): String = LifeLoadDestination.Weekly.name

internal fun weeklyEscalationActive(state: LifeLoadUiState): Boolean {
  val risk = state.dashboard.drift?.riskLevel?.lowercase().orEmpty()
  if (risk in setOf("orange", "red", "hold", "stabilize", "protect")) return true
  val mode = state.dashboard.drift?.mode?.lowercase().orEmpty()
  if (mode in setOf("hold", "stabilize", "protect")) return true
  val latestRiskScore = state.dashboard.trendPoints.lastOrNull()?.driftRiskScore ?: 0.0
  return latestRiskScore >= 60.0
}

internal data class WeeklyReviewSnapshot(
  val approvedDayCount: Int,
  val highestRiskDay: String,
  val oneCorrection: String,
  val evidence: String,
)

internal fun approvedWeeklyHistoryDays(days: List<LifeLoadHistoryDay>): List<LifeLoadHistoryDay> =
  days.filter { day ->
    val approved = day.canonicalCompleted ||
      day.approvedAt.isNotBlank() ||
      day.state == "approved" ||
      day.state == "pending_approval" ||
      day.state == "draft_over_approved"
    approved && day.scoreAvailable != false
  }

internal fun visibleDashboardHistoryDays(state: LifeLoadUiState): List<LifeLoadHistoryDay> {
  val dashboardDate = runCatching { LocalDate.parse(state.dashboard.date) }.getOrNull()
  return state.dashboard.historyDays.filter { day ->
    val date = runCatching { LocalDate.parse(day.date) }.getOrNull() ?: return@filter false
    dashboardDate == null || !date.isAfter(dashboardDate)
  }
}

internal fun approvedWeeklyDayCount(state: LifeLoadUiState): Int {
  val authoritativeDates = state.dashboard.weekly.approvedDayDates.filter { it.isNotBlank() }
  val history = visibleDashboardHistoryDays(state)
  val approvedHistory = history.filter { day ->
    day.canonicalCompleted ||
      day.approvedAt.isNotBlank() ||
      day.state == "approved" ||
      day.state == "pending_approval" ||
      day.state == "draft_over_approved"
  }
  val evaluatedHistoryDates = approvedWeeklyHistoryDays(approvedHistory).map { it.date }.toSet()
  return if (approvedHistory.isNotEmpty()) evaluatedHistoryDates.size
  else authoritativeDates.distinct().size
}

internal fun weeklyReviewSnapshot(state: LifeLoadUiState): WeeklyReviewSnapshot {
  val approvedDays = approvedWeeklyHistoryDays(visibleDashboardHistoryDays(state))
  val approvedDayCount = approvedWeeklyDayCount(state)
  val highestRisk = approvedDays.maxByOrNull { it.lifeLoadScore }
  val drift = state.dashboard.drift
  val signals = drift?.contributingSignals.orEmpty().take(3)
  val correction = concreteWeeklyCorrection(
    candidates = listOf(
      drift?.nextAction.orEmpty(),
      state.dashboard.weekly.nextAction,
      highestRisk?.nextAction.orEmpty(),
    ),
    signals = signals,
  )
  val evidence = when {
    approvedDayCount == 0 -> "No saved check-ins in this view yet."
    signals.isNotEmpty() -> "Signals: ${signals.joinToString(", ") { supportLabel(it) }}"
    else -> "Based on saved check-ins only."
  }
  return WeeklyReviewSnapshot(
    approvedDayCount = approvedDayCount,
    highestRiskDay = highestRisk?.date.orEmpty(),
    oneCorrection = correction,
    evidence = evidence,
  )
}

internal fun concreteWeeklyCorrection(candidates: List<String>, signals: List<String>): String {
  candidates.map(String::trim).firstOrNull { it.isNotBlank() && !it.isVagueWeeklyAction() }?.let { return it }
  val normalizedSignals = signals.map { it.lowercase() }
  return when {
    normalizedSignals.any { "project" in it } -> "No project work after 20:45 for the next two evenings."
    normalizedSignals.any { "late phone" in it || "phone" in it } -> "Put the phone away by 21:00 tonight."
    normalizedSignals.any { "sleep" in it } -> "Set a fixed shutdown alarm tonight."
    normalizedSignals.any { "nutrition" in it || "food" in it } -> "Plan the next normal dinner before 17:00."
    else -> "Pick one recovery-protecting boundary for the next 48 hours."
  }
}

private fun String.isVagueWeeklyAction(): Boolean {
  val normalized = trim().lowercase().trimEnd('.', '!', '?')
  if (normalized.split(Regex("\\s+")).size <= 2) return true
  return normalized in setOf(
    "protect sleep",
    "protect shutdown",
    "protect shutdown tonight",
    "recover first",
    "take it easy",
    "be careful",
    "hold the line",
    "no recommendation yet",
  )
}

internal fun dailyFieldsEnabled(state: LifeLoadUiState): Boolean =
  !state.loading && !state.analysisLocked

internal fun defaultCoreFieldsExpanded(): Boolean = true

internal fun defaultSecondaryFieldsExpanded(): Boolean = false

internal fun isCheckInSaved(state: LifeLoadUiState): Boolean =
  isCheckInSaved(state.approvedAt, state.entryState)

internal fun isCheckInSaved(approvedAt: String, entryState: String): Boolean =
  approvedAt.isNotBlank() || entryState in setOf("approved", "pending_approval", "draft_over_approved")

internal fun missingDayRecoveryActive(
  selectedDate: String,
  approvedAt: String,
  currentDate: LocalDate = LocalDate.now(),
  entryState: String = "",
): Boolean {
  val parsed = runCatching { LocalDate.parse(selectedDate) }.getOrNull() ?: return false
  return !isCheckInSaved(approvedAt, entryState) && parsed.isBefore(currentDate.minusDays(1))
}

internal fun approvalFeedbackText(state: LifeLoadUiState): String = when {
  state.hasUnsavedChanges ->
    "Unsaved changes are stored locally. Save the check-in when ready."
  isCheckInSaved(state) && state.score.nextAction.isNotBlank() ->
    "Check-in saved. Next: ${state.score.nextAction}"
  isCheckInSaved(state) ->
    "Check-in saved. Continue with the next normal step."
  state.hasDraft ->
    "Draft saved locally. Save the check-in when today's useful truth looks right."
  else ->
    "Check-in not saved yet."
}

internal fun dailyCloseoutPrompt(selectedDate: String, currentDate: LocalDate = LocalDate.now()): String {
  val parsed = runCatching { LocalDate.parse(selectedDate) }.getOrNull()
  val dayLabel = when (parsed) {
    currentDate -> "today"
    currentDate.minusDays(1) -> "yesterday"
    null -> "the selected day"
    else -> "this day"
  }
  return "Describe $dayLabel: sleep, food, alcohol, activity, pain, stress, evening behavior."
}

@Composable
private fun localizedApprovalFeedbackText(state: LifeLoadUiState): String = when {
  state.hasUnsavedChanges -> stringResource(R.string.compass_unsaved_draft_exists)
  isCheckInSaved(state) && state.score.nextAction.isNotBlank() ->
    stringResource(R.string.compass_approval_next, state.score.nextAction)
  isCheckInSaved(state) ->
    stringResource(R.string.compass_approval_saved)
  state.hasDraft ->
    stringResource(R.string.compass_approval_draft)
  else ->
    stringResource(R.string.compass_approval_not_saved)
}

@Composable
private fun localizedDailyCloseoutPrompt(selectedDate: String, currentDate: LocalDate = LocalDate.now()): String {
  val parsed = runCatching { LocalDate.parse(selectedDate) }.getOrNull()
  return when (parsed) {
    currentDate -> stringResource(R.string.compass_daily_prompt_today)
    currentDate.minusDays(1) -> stringResource(R.string.compass_daily_prompt_yesterday)
    null -> stringResource(R.string.compass_daily_prompt_selected)
    else -> stringResource(R.string.compass_daily_prompt_this_day)
  }
}

@Composable
private fun lifeLoadColorScheme(darkTheme: Boolean) = if (darkTheme) {
  MaterialTheme.colorScheme.copy(
    primary = Color(0xFF72D6C2),
    onPrimary = Color(0xFF082C25),
    secondary = Color(0xFF7EDFA3),
    tertiary = Color(0xFFFFC766),
    background = Color(0xFF10140F),
    onBackground = Color(0xFFF4EFE5),
    surface = Color(0xFF1B2119),
    onSurface = Color(0xFFF4EFE5),
    surfaceVariant = Color(0xFF263022),
    onSurfaceVariant = Color(0xFFD5CCBE),
    outline = Color(0xFF7E8A73),
    error = Color(0xFFFF8F86),
    onError = Color(0xFF3B0806),
  )
} else {
  MaterialTheme.colorScheme.copy(
    primary = LifeLoadAccent,
    onPrimary = LifeLoadPanel,
    secondary = LifeLoadGreen,
    tertiary = LifeLoadYellow,
    background = Color(0xFFF5EFE3),
    onBackground = LifeLoadInk,
    surface = LifeLoadPanel,
    onSurface = LifeLoadInk,
    surfaceVariant = LifeLoadPanelWarm,
    onSurfaceVariant = LifeLoadMuted,
    outline = LifeLoadLine.copy(alpha = 0.45f),
    error = LifeLoadRed,
    onError = LifeLoadPanel,
  )
}

@Composable
private fun lifeLoadTypography() = MaterialTheme.typography.copy(
  titleLarge = MaterialTheme.typography.titleLarge.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
  titleMedium = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
  titleSmall = MaterialTheme.typography.titleSmall.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
  bodyMedium = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.SansSerif),
  bodySmall = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.SansSerif),
  labelMedium = MaterialTheme.typography.labelMedium.copy(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold),
)

private fun lifeLoadBackgroundBrush(darkTheme: Boolean): Brush = Brush.linearGradient(
  colors = if (darkTheme) {
    listOf(
      Color(0xFF0E120D),
      Color(0xFF151D14),
      Color(0xFF18251E),
    )
  } else {
    listOf(
      Color(0xFFF5EFE3),
      Color(0xFFF7F0E2),
      Color(0xFFE6F0DC),
    )
  },
)

@Composable
fun LifeLoadRoute(
  vm: LifeLoadViewModel = viewModel(
    factory = LifeLoadViewModel.factory(LocalContext.current.applicationContext as Application),
  ),
) {
  val state by vm.uiState.collectAsStateWithLifecycle()
  val context = LocalContext.current
  var selectedVariant by remember { mutableStateOf(DebugUiVariantStore.resolve(context)) }
  val actions = remember(vm) {
    LifeLoadUiActions(
      onRefresh = vm::refreshSelectedDate,
      onPreviousDate = vm::selectPreviousDate,
      onNextDate = vm::selectNextDate,
      onShiftDate = vm::shiftSelectedDate,
      onToday = vm::selectToday,
      onYesterday = vm::selectYesterday,
      onDiaryChanged = vm::updateDiaryText,
      onAnalyzeDiary = vm::analyzeDiary,
      onApprove = vm::approveEntry,
      onOpenSettings = vm::openSettings,
      onCloseSettings = vm::closeSettings,
      onSettingsChanged = vm::updateSettings,
      onReminderSettingsChanged = vm::updateReminderSettings,
      onSaveSettings = vm::saveSettings,
      onRefreshLocalDebug = vm::refreshLocalDebugDiagnostics,
      onImportLocalHistory = vm::importRecentLocalHistory,
      onSyncLocalOutbox = vm::syncLocalOutbox,
      onMirrorLocalDebug = vm::mirrorLocalDebugBundle,
      onExportLocalData = vm::exportLocalData,
      onExportLocalDataToUri = vm::exportLocalDataToUri,
      onImportLocalDataFromUri = vm::importLocalDataFromUri,
      onRestoreFromServer = vm::restoreFromServer,
      onDeleteLocalData = vm::deleteLocalData,
      onSignIn = vm::signIn,
      onRegister = vm::register,
      onSignOut = vm::signOut,
      onTagsChanged = vm::updateTagsFromText,
      onBooleanField = vm::updateBooleanField,
      onIntField = vm::updateIntField,
      onStringField = vm::updateStringField,
      onProfileSelected = vm::selectProfile,
      onOptionalPackToggled = vm::toggleOptionalPack,
      onResetProfileDefaults = vm::resetProfileDefaults,
      onCompleteProfileOnboarding = vm::completeProfileOnboarding,
    )
  }
  LifeLoadVariantHost(
    state = state,
    actions = actions,
    selectedVariant = selectedVariant,
    onVariantSelected = { variant ->
      selectedVariant = variant
      DebugUiVariantStore.save(context, variant)
    },
  )
}

@Composable
internal fun LifeLoadClassicScreen(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  LifeLoadScreen(
    state = state,
    onRefresh = actions.onRefresh,
    onPreviousDate = actions.onPreviousDate,
    onNextDate = actions.onNextDate,
    onToday = actions.onToday,
    onYesterday = actions.onYesterday,
    onDiaryChanged = actions.onDiaryChanged,
    onAnalyzeDiary = actions.onAnalyzeDiary,
    onApprove = actions.onApprove,
    onOpenSettings = actions.onOpenSettings,
    onCloseSettings = actions.onCloseSettings,
    onSettingsChanged = actions.onSettingsChanged,
    onSaveSettings = actions.onSaveSettings,
    onRefreshLocalDebug = actions.onRefreshLocalDebug,
    onImportLocalHistory = actions.onImportLocalHistory,
    onSyncLocalOutbox = actions.onSyncLocalOutbox,
    onMirrorLocalDebug = actions.onMirrorLocalDebug,
    onExportLocalData = actions.onExportLocalData,
    onDeleteLocalData = actions.onDeleteLocalData,
    onTagsChanged = actions.onTagsChanged,
    onBooleanField = actions.onBooleanField,
    onIntField = actions.onIntField,
    onStringField = actions.onStringField,
    onProfileSelected = actions.onProfileSelected,
    onOptionalPackToggled = actions.onOptionalPackToggled,
    onResetProfileDefaults = actions.onResetProfileDefaults,
    onCompleteProfileOnboarding = actions.onCompleteProfileOnboarding,
    selectedVariant = selectedVariant,
    onVariantSelected = onVariantSelected,
  )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun LifeLoadScreen(
  state: LifeLoadUiState,
  onRefresh: () -> Unit,
  onPreviousDate: () -> Unit,
  onNextDate: () -> Unit,
  onToday: () -> Unit,
  onYesterday: () -> Unit,
  onDiaryChanged: (String) -> Unit,
  onAnalyzeDiary: () -> Unit,
  onApprove: () -> Unit,
  onOpenSettings: () -> Unit,
  onCloseSettings: () -> Unit,
  onSettingsChanged: (LifeLoadSettings) -> Unit,
  onSaveSettings: (String) -> Unit,
  onRefreshLocalDebug: () -> Unit,
  onImportLocalHistory: (Int) -> Unit,
  onSyncLocalOutbox: () -> Unit,
  onMirrorLocalDebug: () -> Unit,
  onExportLocalData: () -> Unit,
  onDeleteLocalData: () -> Unit,
  onTagsChanged: (String) -> Unit,
  onBooleanField: (String, Boolean?) -> Unit,
  onIntField: (String, Int?) -> Unit,
  onStringField: (String, String) -> Unit,
  onProfileSelected: (String) -> Unit = {},
  onOptionalPackToggled: (String, Boolean) -> Unit = { _, _ -> },
  onResetProfileDefaults: () -> Unit = {},
  onCompleteProfileOnboarding: () -> Unit = {},
  selectedVariant: LifeLoadUiVariant = LifeLoadUiVariantRegistry.default,
  onVariantSelected: (LifeLoadUiVariant) -> Unit = {},
) {
  var secondaryExpanded by rememberSaveable { mutableStateOf(defaultSecondaryFieldsExpanded()) }
  var movementExpanded by rememberSaveable { mutableStateOf(false) }
  var eveningExpanded by rememberSaveable { mutableStateOf(false) }
  var painExpanded by rememberSaveable { mutableStateOf(false) }
  var moodExpanded by rememberSaveable { mutableStateOf(false) }
  var workExpanded by rememberSaveable { mutableStateOf(false) }
  var tagsExpanded by rememberSaveable { mutableStateOf(false) }
  var coreExpanded by rememberSaveable { mutableStateOf(defaultCoreFieldsExpanded()) }
  var formulaDialogVisible by rememberSaveable { mutableStateOf(false) }
  var garminPasswordDraft by rememberSaveable { mutableStateOf("") }
  var trackingSetupExpanded by rememberSaveable { mutableStateOf(false) }
  val draft = state.draftEntry
  val approved = isCheckInSaved(state)
  val weekend = isWeekend(state.selectedDate)
  val attentionItems = buildNeedsAttention(state)
  val detectedFields = buildDetectedFields(state)
  val fieldsEnabled = dailyFieldsEnabled(state)
  val missedDayRecovery = missingDayRecoveryActive(state.selectedDate, state.approvedAt, entryState = state.entryState)
  val darkTheme = isSystemInDarkTheme()
  val profileFeatureFlags = defaultProfileFeatureFlags()

  if (formulaDialogVisible) {
    FormulaExplanationDialog(
      score = state.score,
      formula = state.formulaContract,
      onDismiss = { formulaDialogVisible = false },
    )
  }
  var destinationName by rememberSaveable { mutableStateOf(defaultLifeLoadDestinationName()) }
  val destination = LifeLoadDestination.valueOf(destinationName)
  val drawerState = rememberDrawerState(DrawerValue.Closed)
  val coroutineScope = rememberCoroutineScope()

  fun selectDestination(next: LifeLoadDestination) {
    destinationName = next.name
    if (next == LifeLoadDestination.Settings) {
      onOpenSettings()
    } else {
      onCloseSettings()
    }
    coroutineScope.launch { drawerState.close() }
  }

  MaterialTheme(
    colorScheme = lifeLoadColorScheme(darkTheme),
    typography = lifeLoadTypography(),
  ) {
    if (destination == LifeLoadDestination.Daily && onboardingVisibleForNewUser(profileFeatureFlags, state.profileOnboardingCompleted)) {
      ProfileOnboardingForFlag(
        flags = profileFeatureFlags,
        hasExistingSelection = state.profileOnboardingCompleted,
        selectedProfileId = state.profileSetup.selectedConfig.activeProfileId,
        onProfileSelected = onProfileSelected,
        onStartFirstCheckIn = {
          onCompleteProfileOnboarding()
          destinationName = LifeLoadDestination.Daily.name
        },
      )
    }
    ModalNavigationDrawer(
      drawerState = drawerState,
      drawerContent = {
        LifeLoadDrawer(
          destination = destination,
          onSelectDestination = ::selectDestination,
        )
      },
    ) {
      LazyColumn(
        modifier = Modifier
          .fillMaxSize()
          .background(lifeLoadBackgroundBrush(darkTheme))
          .navigationBarsPadding()
          .imePadding()
          .testTag("life_load_content"),
        contentPadding = compactScreenContentPadding(),
        verticalArrangement = Arrangement.spacedBy(CompactSectionGap),
      ) {
        item {
          LifeLoadTopCard(
            state = state,
            destination = destination,
            onOpenDrawer = { coroutineScope.launch { drawerState.open() } },
            onOpenWeekly = { selectDestination(LifeLoadDestination.Weekly) },
            onRefresh = onRefresh,
            onShowFormula = { formulaDialogVisible = true },
          )
        }

        if (destination == LifeLoadDestination.Weekly) {
          if (state.dashboard.drift != null || state.dashboard.trendPoints.isNotEmpty()) {
            item {
              LifeLoadPreventionCard(state = state)
            }
          } else {
            item {
              WeeklyEmptyCard()
            }
          }
          if (state.dashboard.trendPoints.isNotEmpty()) {
            item {
              LifeLoadTrendGraphCard(state = state)
            }
          }
        }

        if (destination == LifeLoadDestination.Settings) {
          item {
            GarminSettingsCard(
              settings = state.settings,
              garminPasswordDraft = garminPasswordDraft,
              onPasswordChanged = { garminPasswordDraft = it },
              saving = state.settingsSaving,
              message = state.settingsMessage,
              onSettingsChanged = onSettingsChanged,
              onSave = {
                onSaveSettings(garminPasswordDraft)
                garminPasswordDraft = ""
              },
              onClose = { selectDestination(LifeLoadDestination.Daily) },
            )
          }
          item {
            LifeLoadSettingsCard(
              settings = state.settings,
              saving = state.settingsSaving,
              message = state.settingsMessage,
              onSettingsChanged = onSettingsChanged,
              onSave = {
                onSaveSettings("")
              },
              onClose = { selectDestination(LifeLoadDestination.Daily) },
            )
          }
          item {
            TrackingSetupSettingsEntryCard(
              flags = profileFeatureFlags,
              state = state.profileSetup,
              expanded = trackingSetupExpanded,
              onOpen = { trackingSetupExpanded = true },
              onClose = { trackingSetupExpanded = false },
              onProfileSelected = onProfileSelected,
              onOptionalPackToggled = onOptionalPackToggled,
              onResetDefaults = onResetProfileDefaults,
            )
          }
          if (systemStatusNeedsAttention(state)) item {
            SystemStatusCard(state = state)
          }
          if (BuildConfig.DEBUG) {
            item {
              DevProfileSelectorCard(
                flags = profileFeatureFlags,
                selectedProfileId = state.profileSetup.selectedConfig.activeProfileId,
                onProfileSelected = onProfileSelected,
              )
            }
            item {
              DebugUiVariantCard(
                selectedVariant = selectedVariant,
                onVariantSelected = onVariantSelected,
              )
            }
          }
          item {
            PrivacyControlsCard(
              message = state.privacyMessage,
              onExport = onExportLocalData,
              onDelete = onDeleteLocalData,
            )
          }
          if (BuildConfig.DEBUG) {
            item {
              LocalDiagnosticsCard(
                debug = state.localDebug,
                onRefresh = onRefreshLocalDebug,
                onImportHistory = { onImportLocalHistory(7) },
                onSync = onSyncLocalOutbox,
                onMirror = onMirrorLocalDebug,
              )
            }
          }
          item {
            ServerSettingsCard()
          }
        }

        if (destination == LifeLoadDestination.Daily) {
          item {
        Card(
          modifier = Modifier
            .fillMaxWidth()
            .border(
              width = 1.dp,
              color = if (state.analysisLocked) MaterialTheme.colorScheme.primary.copy(alpha = 0.34f) else MaterialTheme.colorScheme.outline.copy(alpha = 0.12f),
              shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
            ),
        ) {
          Column(
            modifier = Modifier
              .fillMaxWidth()
              .padding(CompactCardPadding),
            verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
          ) {
            Text(stringResource(R.string.nav_check_in), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            Row(
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
              verticalAlignment = Alignment.CenterVertically,
            ) {
              IconButton(onClick = onPreviousDate) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.previous_day))
              }
              Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(CompactTightGap),
              ) {
                Text(localizedSelectedDateLabel(state.selectedDate), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text(localizedDayStatusLabel(state), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
              }
              IconButton(onClick = onNextDate) {
                Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = stringResource(R.string.next_day))
              }
            }
            Row(
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.Center,
              verticalAlignment = Alignment.CenterVertically,
            ) {
              SmallButton(stringResource(R.string.today), onToday)
              SmallButton(stringResource(R.string.yesterday), onYesterday)
            }
            if (weekend) {
              InlineInfoChip(stringResource(com.life.lifeload.R.string.weekend_context_summary), MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (missedDayRecovery) {
              MissedDayRecoveryCard()
            }
            if (state.statusLights.backend == LifeLoadBackendStatus.ERROR && !state.loading && !state.analysisLocked) {
              BackendUnavailableNotice(status = state.statusLights.backend)
            }
            if (approved || (!approved && (state.score.zone.isNotBlank() || state.score.nextAction.isNotBlank()))) {
              LifeLoadHeroCard(state = state)
            }
            if (approved) {
              ApprovalFeedbackCard(text = localizedApprovalFeedbackText(state))
            }
            if (!approved && attentionItems.isNotEmpty()) {
              NeedsAttentionCard(items = attentionItems)
            }
            Text(
              localizedDailyCloseoutPrompt(state.selectedDate, state.currentDate),
              style = LifeLoadLabelTextStyle,
            )
            LifeLoadTextField(
              value = draft.diaryText,
              onValueChange = onDiaryChanged,
              label = stringResource(R.string.field_diary_label),
              modifier = Modifier.fillMaxWidth(),
              minLines = 6,
              enabled = fieldsEnabled,
              testTag = "daily_diary_text",
            )
            Row(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
              SmallButton(if (state.analysisLocked) stringResource(R.string.compass_analyzing) else stringResource(R.string.compass_analyze_diary), onAnalyzeDiary, enabled = fieldsEnabled, testTag = "daily_analyze_button")
              SmallButton(if (approved) stringResource(R.string.compass_update_checkin) else stringResource(R.string.compass_save_checkin), onApprove, enabled = fieldsEnabled, testTag = "daily_approve_button")
            }
            if (state.analysisLocked) {
              AnalyzingBanner()
            } else if (state.latestProposal != null) {
              Text(stringResource(R.string.compass_core_review_hint), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
          }
        }
      }

      if (detectedFields.isNotEmpty()) {
        item {
          DetectedReviewCard(fields = detectedFields)
        }
      }

          item {
            CollapsibleCard(title = stringResource(R.string.compass_core), expanded = coreExpanded, onToggle = { coreExpanded = !coreExpanded }) {
              TernaryChipRow(stringResource(R.string.field_sleep_label), draft.sleepOk, fieldsEnabled, testTagPrefix = "sleep_ok") { onBooleanField("sleep_ok", it) }
              TernaryChipRow(stringResource(R.string.field_food_label), draft.nutritionOk, fieldsEnabled, testTagPrefix = "nutrition_ok") { onBooleanField("nutrition_ok", it) }
              AlcoholChipRow(value = draft.alcohol, enabled = fieldsEnabled, testTagPrefix = "alcohol") { onStringField("alcohol", it) }
              TernaryChipRow(
                label = stringResource(R.string.field_eating_episode_label),
                value = draft.binge,
                enabled = fieldsEnabled,
                accent = if (draft.binge == true) MaterialTheme.colorScheme.tertiary else null,
                testTagPrefix = "binge",
              ) { onBooleanField("binge", it) }
            }
          }

          item {
            CollapsibleCard(
              title = stringResource(R.string.compass_detailed_signals),
              subtitle = stringResource(R.string.compass_detailed_signals_helper),
              expanded = secondaryExpanded,
              onToggle = { secondaryExpanded = !secondaryExpanded },
              testTag = "daily_more_signals_section",
            ) {
              InlineExpandableSection(title = stringResource(R.string.compass_movement), expanded = movementExpanded, onToggle = { movementExpanded = !movementExpanded }, testTag = "daily_movement_section") {
                OptionChipRow(
                  label = stringResource(R.string.field_activity_type_label),
                  selected = draft.primaryActivityType.ifBlank { "none" },
                  options = listOf("none", "walk", "bike", "run", "crossfit", "rehab", "meditation", "other"),
                  enabled = fieldsEnabled,
                  testTagPrefix = "primary_activity_type",
                ) { onStringField("primary_activity_type", it) }
                OptionChipRow(
                  label = stringResource(R.string.field_movement_minutes_label),
                  selected = draft.activityDurationMin?.toString() ?: "?",
                  options = listOf("0", "10", "20", "30", "45", "60", "custom", "?"),
                  enabled = fieldsEnabled,
                  testTagPrefix = "activity_duration_min",
                ) { onIntField("activity_duration_min", it.toIntOrNull()) }
              }

              InlineExpandableSection(title = stringResource(R.string.compass_recovery_evening), expanded = eveningExpanded, onToggle = { eveningExpanded = !eveningExpanded }, testTag = "daily_recovery_evening_section") {
                TernaryChipRow(stringResource(R.string.field_rehab_label), draft.rehabDone, fieldsEnabled, testTagPrefix = "rehab_done") { onBooleanField("rehab_done", it) }
                TernaryChipRow(stringResource(R.string.field_decompression_label), draft.decompressionDone, fieldsEnabled, testTagPrefix = "decompression_done") { onBooleanField("decompression_done", it) }
                TernaryChipRow(
                  label = stringResource(R.string.field_shutdown_label),
                  value = draft.shutdownDone,
                  enabled = fieldsEnabled,
                  accent = if (draft.shutdownDone == false) warningColor() else null,
                  testTagPrefix = "shutdown_done",
                ) { onBooleanField("shutdown_done", it) }
                TernaryChipRow(
                  label = stringResource(R.string.field_phone_after_21_label),
                  value = draft.phoneAfter21,
                  enabled = fieldsEnabled,
                  accent = if (draft.phoneAfter21 == true) warningColor() else null,
                  testTagPrefix = "phone_after_21",
                ) { onBooleanField("phone_after_21", it) }
                TernaryChipRow(
                  label = stringResource(R.string.field_project_overrun_label),
                  value = draft.projectOverrun,
                  enabled = fieldsEnabled,
                  accent = if (draft.projectOverrun == true) warningColor() else null,
                  testTagPrefix = "project_overrun",
                ) { onBooleanField("project_overrun", it) }
              }

              InlineExpandableSection(title = stringResource(R.string.compass_pain), expanded = painExpanded, onToggle = { painExpanded = !painExpanded }, testTag = "daily_pain_symptoms_section") {
                IntChipRow(stringResource(R.string.field_foot_pain_label), draft.footPain, fieldsEnabled, accentAtOrAbove = 5, testTagPrefix = "foot_pain") { onIntField("foot_pain", it) }
                TargetHint(stringResource(R.string.compass_target_pain))
                IntChipRow(stringResource(R.string.field_shoulder_pain_label), draft.shoulderPain, fieldsEnabled, accentAtOrAbove = 5, testTagPrefix = "shoulder_pain") { onIntField("shoulder_pain", it) }
                TernaryChipRow(
                  label = stringResource(R.string.field_migraine_label),
                  value = draft.migraineWarning,
                  enabled = fieldsEnabled,
                  accent = if (draft.migraineWarning == true) warningColor() else null,
                  testTagPrefix = "migraine_warning",
                ) { onBooleanField("migraine_warning", it) }
                LifeLoadTextField(
                  value = draft.otherSymptoms,
                  onValueChange = { onStringField("other_symptoms", it) },
                  label = stringResource(R.string.field_other_symptoms_label),
                  modifier = Modifier.fillMaxWidth(),
                  enabled = fieldsEnabled,
                  testTag = "other_symptoms",
                )
              }

              InlineExpandableSection(title = stringResource(R.string.compass_mood_stress), expanded = moodExpanded, onToggle = { moodExpanded = !moodExpanded }, testTag = "daily_mood_stress_energy_section") {
                IntChipRow(stringResource(R.string.field_mood_label), draft.mood, fieldsEnabled, testTagPrefix = "mood") { onIntField("mood", it) }
                IntChipRow(stringResource(R.string.field_stress_label), draft.stress, fieldsEnabled, accentAtOrAbove = 7, testTagPrefix = "stress") { onIntField("stress", it) }
                IntChipRow(stringResource(R.string.field_energy_label), draft.energy, fieldsEnabled, testTagPrefix = "energy") { onIntField("energy", it) }
                IntChipRow(stringResource(R.string.field_coffee_label), draft.coffeeCups, fieldsEnabled, maxValue = 8, testTagPrefix = "coffee_cups") { onIntField("coffee_cups", it) }
                TargetHint(stringResource(R.string.compass_target_coffee))
              }

              InlineExpandableSection(title = stringResource(R.string.compass_work_family), expanded = workExpanded, onToggle = { workExpanded = !workExpanded }, testTag = "daily_work_family_section") {
                OptionChipRow(
                  label = stringResource(R.string.field_work_intensity_label),
                  selected = draft.workIntensity.ifBlank { "?" },
                  options = listOf("?", "low", "normal", "heavy", "extreme"),
                  enabled = fieldsEnabled,
                  testTagPrefix = "work_intensity",
                ) { onStringField("work_intensity", if (it == "?") "" else it) }
                TernaryChipRow(stringResource(R.string.field_home_office_label), draft.homeOffice, fieldsEnabled, testTagPrefix = "home_office") { onBooleanField("home_office", it) }
                OptionChipRow(
                  label = stringResource(R.string.field_family_stress_label),
                  selected = familyStressLabel(draft.familyStress),
                  options = listOf("?", "low", "normal", "high"),
                  enabled = fieldsEnabled,
                  testTagPrefix = "family_stress",
                ) {
                  onIntField(
                    "family_stress",
                    when (it) {
                      "low" -> 2
                      "normal" -> 5
                      "high" -> 8
                      else -> null
                    },
                  )
                }
                OptionChipRow(
                  label = stringResource(R.string.field_relationship_tension_label),
                  selected = wifeConflictLabel(draft.wifeConflictCount),
                  options = listOf("0", "1", "2", "3", "4+"),
                  enabled = fieldsEnabled,
                  testTagPrefix = "wife_conflict_count",
                ) {
                  onIntField("wife_conflict_count", if (it == "4+") 4 else it.toIntOrNull())
                }
                TernaryChipRow(stringResource(R.string.field_alone_home_label), draft.aloneHome, fieldsEnabled, testTagPrefix = "alone_home") { onBooleanField("alone_home", it) }
                TernaryChipRow(stringResource(R.string.field_school_conflict_label), draft.wifeConflictSchool, fieldsEnabled, testTagPrefix = "wife_conflict_school") { onBooleanField("wife_conflict_school", it) }
                TernaryChipRow(stringResource(R.string.field_chores_conflict_label), draft.wifeConflictChores, fieldsEnabled, testTagPrefix = "wife_conflict_chores") { onBooleanField("wife_conflict_chores", it) }
                OptionChipRow(
                  label = stringResource(R.string.field_homework_label),
                  selected = draft.homeworkStatus ?: homeworkLabel(draft.homeworkDone),
                  options = listOf("?", "yes", "no", "n/a"),
                  enabled = fieldsEnabled,
                  testTagPrefix = "homework_done",
                ) { onStringField("homework_done", if (it == "n/a") "na" else it) }
                if (weekend) {
                  Text(
                    stringResource(com.life.lifeload.R.string.weekend_context_optional),
                    style = LifeLoadLabelTextStyle,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                  )
                }
              }

              InlineExpandableSection(title = stringResource(R.string.compass_tags), expanded = tagsExpanded, onToggle = { tagsExpanded = !tagsExpanded }, testTag = "daily_tags_notes_section") {
                LifeLoadTextField(
                  value = draft.tags.joinToString(", "),
                  onValueChange = onTagsChanged,
                  label = stringResource(R.string.compass_tags_label),
                  modifier = Modifier.fillMaxWidth(),
                  enabled = fieldsEnabled,
                  testTag = "daily_tags_text",
                )
              }
            }
          }
        }
      }
    }
  }
}

@Composable
private fun WeeklyEmptyCard() {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Text(stringResource(R.string.compass_guidance_empty_title), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      Text(
        stringResource(R.string.compass_guidance_empty_body),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
  }
}

@Composable
private fun LifeLoadDrawer(
  destination: LifeLoadDestination,
  onSelectDestination: (LifeLoadDestination) -> Unit,
) {
  ModalDrawerSheet(modifier = Modifier.width(304.dp)) {
    Column(
      modifier = Modifier
        .fillMaxSize()
        .padding(horizontal = 12.dp, vertical = 16.dp),
      verticalArrangement = Arrangement.spacedBy(CompactInlineGap),
    ) {
      Text(
        "Life Load",
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
      )
      NavigationDrawerItem(
        selected = destination == LifeLoadDestination.Daily,
        onClick = { onSelectDestination(LifeLoadDestination.Daily) },
        modifier = Modifier.testTag("drawer_daily"),
        icon = { Icon(Icons.Filled.CalendarMonth, contentDescription = null) },
        label = { Text(stringResource(R.string.nav_check_in)) },
      )
      NavigationDrawerItem(
        selected = destination == LifeLoadDestination.Weekly,
        onClick = { onSelectDestination(LifeLoadDestination.Weekly) },
        modifier = Modifier.testTag("drawer_weekly"),
        icon = { Icon(Icons.AutoMirrored.Filled.TrendingUp, contentDescription = null) },
        label = { Text(stringResource(R.string.nav_guidance)) },
      )
      Spacer(modifier = Modifier.weight(1f))
      HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
      NavigationDrawerItem(
        selected = destination == LifeLoadDestination.Settings,
        onClick = { onSelectDestination(LifeLoadDestination.Settings) },
        modifier = Modifier.testTag("drawer_settings"),
        icon = { Icon(Icons.Filled.Settings, contentDescription = null) },
        label = { Text(stringResource(R.string.nav_settings)) },
      )
    }
  }
}

@Composable
private fun LifeLoadTopCard(
  state: LifeLoadUiState,
  destination: LifeLoadDestination,
  onOpenDrawer: () -> Unit,
  onOpenWeekly: () -> Unit,
  onRefresh: () -> Unit,
  onShowFormula: () -> Unit,
) {
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.background.copy(alpha = 0.96f))
      .statusBarsPadding()
      .padding(horizontal = 8.dp, vertical = 4.dp),
    verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
  ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
          IconButton(onClick = onOpenDrawer) {
            Icon(Icons.Filled.Menu, contentDescription = stringResource(R.string.compass_open_navigation))
          }
          Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
            Text(stringResource(R.string.life_load), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(localizedDestinationLabel(destination), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
          }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
          if (state.loading) {
            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
          }
          if (destination != LifeLoadDestination.Settings && state.settings.debug.showFormulaButton) {
            SmallButton(stringResource(R.string.compass_guidance_scoring_button), onClick = onShowFormula, testTag = "formula_button")
          }
          IconButton(onClick = onRefresh) {
            Icon(Icons.Filled.Refresh, contentDescription = stringResource(R.string.refresh))
          }
        }
      }
      if (systemStatusNeedsAttention(state)) {
        Text(
          localizedLoadingOrStatusLabel(state),
          style = LifeLoadLabelTextStyle,
          color = if (state.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
        )
      }
      if (state.loading || state.dashboardSlowLoading) {
        ProcessingBanner(
          title = if (state.loading) stringResource(R.string.legacy_loading_selected_day) else stringResource(R.string.legacy_refreshing_week_context),
          detail = if (state.loading) stringResource(R.string.legacy_structured_fields_disabled) else stringResource(R.string.legacy_weekly_status_recalculating),
        )
      }
      if (state.message.isNotBlank()) {
        Text(state.message, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.primary)
      }
      if (state.error.isNotBlank()) {
        Text(state.error, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.error)
      }
      if (destination == LifeLoadDestination.Daily && weeklyEscalationActive(state)) {
        WeeklyEscalationPrompt(onOpenWeekly = onOpenWeekly)
      }
  }
}

private fun destinationLabel(destination: LifeLoadDestination): String = when (destination) {
  LifeLoadDestination.Weekly -> "Guidance"
  LifeLoadDestination.Daily -> "Check-in"
  LifeLoadDestination.Settings -> "Settings"
}

@Composable
private fun localizedDestinationLabel(destination: LifeLoadDestination): String = when (destination) {
  LifeLoadDestination.Weekly -> stringResource(R.string.nav_guidance)
  LifeLoadDestination.Daily -> stringResource(R.string.nav_check_in)
  LifeLoadDestination.Settings -> stringResource(R.string.nav_settings)
}

@Composable
private fun WeeklyEscalationPrompt(onOpenWeekly: () -> Unit) {
  Row(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Row(
      modifier = Modifier.weight(1f),
      horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Icon(Icons.Filled.Warning, contentDescription = null, tint = warningColor(), modifier = Modifier.size(16.dp))
      Text(stringResource(R.string.compass_guidance_needs_review), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    SmallButton(stringResource(R.string.compass_view_guidance), onClick = onOpenWeekly)
  }
}

@Composable
private fun BackendUnavailableNotice(status: LifeLoadBackendStatus) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.2f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .padding(horizontal = 8.dp, vertical = 8.dp),
    verticalAlignment = Alignment.CenterVertically,
    horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
  ) {
    Icon(Icons.Filled.Warning, contentDescription = null, tint = warningColor(), modifier = Modifier.size(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
      Text(
        if (status == LifeLoadBackendStatus.ERROR) stringResource(R.string.legacy_backend_needs_attention) else stringResource(R.string.legacy_backend_unavailable),
        style = LifeLoadLabelTextStyle,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      Text(
        stringResource(R.string.legacy_local_editing_queue),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
  }
}

@Composable
private fun MissedDayRecoveryCard() {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.secondary.copy(alpha = 0.08f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .border(1.dp, MaterialTheme.colorScheme.secondary.copy(alpha = 0.22f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .padding(horizontal = 8.dp, vertical = 8.dp),
    verticalAlignment = Alignment.CenterVertically,
    horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
  ) {
    Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = successColor(), modifier = Modifier.size(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
      Text(
        stringResource(R.string.legacy_resume_from_day),
        style = LifeLoadLabelTextStyle,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      Text(
        stringResource(R.string.legacy_skipped_day_copy),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LocalDiagnosticsCard(
  debug: LifeLoadLocalDebugState,
  onRefresh: () -> Unit,
  onImportHistory: () -> Unit,
  onSync: () -> Unit,
  onMirror: () -> Unit,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.tertiary.copy(alpha = 0.24f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp))
      .testTag("local_diagnostics_card"),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.legacy_local_diagnostics), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_debug_exports_redacted), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalAlignment = Alignment.CenterVertically) {
          SmallButton(stringResource(R.string.legacy_import_7d), onImportHistory, testTag = "local_history_import_7d")
          SmallButton(stringResource(R.string.legacy_sync), onSync, testTag = "local_outbox_sync")
          SmallButton(stringResource(R.string.legacy_mirror), onMirror, testTag = "local_debug_mirror")
          SmallButton(stringResource(R.string.refresh), onRefresh, testTag = "local_diagnostics_refresh")
        }
      }
      Text(debug.message, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("local_diagnostics_message"))
      if (debug.available) {
        Text(stringResource(R.string.legacy_schema_summary, debug.schemaVersion.ifBlank { stringResource(R.string.operator_unknown) }, debug.redaction.ifBlank { stringResource(R.string.legacy_redaction_unknown) }), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
          InlineInfoChip("entries ${debug.entryCount}", MaterialTheme.colorScheme.onSurfaceVariant)
          InlineInfoChip("outbox ${debug.outboxCount}", MaterialTheme.colorScheme.onSurfaceVariant)
          InlineInfoChip("conflicts ${debug.conflictCount}", warningColor())
          InlineInfoChip("approved ${debug.approvedCount}", successColor())
          InlineInfoChip("draft ${debug.draftCount}", MaterialTheme.colorScheme.primary)
          InlineInfoChip("pending ${debug.pendingApprovalCount}", warningColor())
        }
      }
    }
  }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun PrivacyControlsCard(
  message: String,
  onExport: () -> Unit,
  onDelete: () -> Unit,
) {
  var deleteArmed by rememberSaveable { mutableStateOf(false) }
  var securityDialogVisible by rememberSaveable { mutableStateOf(false) }
  if (securityDialogVisible) {
    ClassicSecurityNoticeDialog(onDismiss = { securityDialogVisible = false })
  }

  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.error.copy(alpha = 0.18f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp))
      .testTag("privacy_controls_card"),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.settings_privacy), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_export_remove_local_data), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        FlowRow(
          horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
          verticalArrangement = Arrangement.spacedBy(CompactInlineGap),
        ) {
          SmallButton(
            stringResource(com.life.lifeload.R.string.settings_security_button),
            onClick = { securityDialogVisible = true },
            testTag = "privacy_security_button",
          )
          SmallButton(stringResource(R.string.legacy_export), onExport, testTag = "privacy_export_local")
          SmallButton(
            if (deleteArmed) stringResource(R.string.settings_confirm_delete) else stringResource(R.string.legacy_delete_local),
            onClick = {
              if (deleteArmed) {
                onDelete()
                deleteArmed = false
              } else {
                deleteArmed = true
              }
            },
            testTag = if (deleteArmed) "privacy_delete_confirm" else "privacy_delete_local",
          )
        }
      }
      if (deleteArmed) {
        Text(
          stringResource(R.string.legacy_delete_local_confirm_copy),
          style = LifeLoadLabelTextStyle,
          color = MaterialTheme.colorScheme.error,
          modifier = Modifier.testTag("privacy_delete_warning"),
        )
      }
      if (message.isNotBlank()) {
        Text(message, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("privacy_message"))
      }
    }
  }
}

@Composable
private fun ClassicSecurityNoticeDialog(onDismiss: () -> Unit) {
  AlertDialog(
    onDismissRequest = onDismiss,
    confirmButton = {
      TextButton(
        onClick = onDismiss,
        modifier = Modifier.testTag("privacy_security_close_button"),
      ) {
        Text(stringResource(com.life.lifeload.R.string.close))
      }
    },
    title = { Text(stringResource(com.life.lifeload.R.string.settings_security_title)) },
    text = {
      Column(
        modifier = Modifier.testTag("privacy_security_dialog"),
        verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
      ) {
        Text(
          stringResource(com.life.lifeload.R.string.settings_security_intro),
          style = LifeLoadLabelTextStyle,
        )
        Text(
          stringResource(com.life.lifeload.R.string.settings_security_local_first),
          style = LifeLoadLabelTextStyle,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
          stringResource(com.life.lifeload.R.string.settings_security_minimize),
          style = LifeLoadLabelTextStyle,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
          stringResource(com.life.lifeload.R.string.settings_security_limits),
          style = LifeLoadLabelTextStyle,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
      }
    },
  )
}

@Composable
private fun DebugUiVariantCard(
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.secondary.copy(alpha = 0.22f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp))
      .testTag("debug_ui_variant_card"),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Text(stringResource(R.string.legacy_debug_ui_variant), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      Text(
        stringResource(R.string.legacy_debug_ui_variant_helper),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      OptionChipRow(
        label = stringResource(R.string.legacy_variant),
        selected = selectedVariant.id,
        options = LifeLoadUiVariantRegistry.all.map { it.id },
        enabled = true,
        testTagPrefix = "debug_ui_variant",
      ) { selected ->
        onVariantSelected(LifeLoadUiVariantRegistry.fromId(selected))
      }
      Text(
        "${selectedVariant.label}: ${selectedVariant.description}",
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
  }
}

@Composable
private fun ApprovalFeedbackCard(text: String) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .background(successColor().copy(alpha = 0.08f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .border(1.dp, successColor().copy(alpha = 0.22f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .padding(horizontal = 8.dp, vertical = 8.dp),
    verticalAlignment = Alignment.CenterVertically,
    horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
  ) {
    Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = successColor(), modifier = Modifier.size(16.dp))
    Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
      Text(stringResource(R.string.legacy_checkin_saved), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurfaceVariant)
      Text(text, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun ServerSettingsCard() {
  val context = LocalContext.current
  var serverUrlDraft by rememberSaveable { mutableStateOf(ServerConfig.resolveBaseUrl(context)) }

  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.18f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Text(stringResource(R.string.legacy_advanced), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      LifeLoadTextField(
        value = serverUrlDraft,
        onValueChange = { serverUrlDraft = it },
        label = stringResource(R.string.settings_server_url),
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        testTag = "settings_server_url",
      )
      Row(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalAlignment = Alignment.CenterVertically) {
        SmallButton(
          stringResource(R.string.settings_apply),
          onClick = {
            ServerConfig.saveBaseUrl(context, serverUrlDraft)
            serverUrlDraft = ServerConfig.resolveBaseUrl(context)
          },
          testTag = "settings_server_apply",
        )
        SmallButton(
          stringResource(R.string.settings_default),
          onClick = {
            ServerConfig.resetBaseUrl(context)
            serverUrlDraft = ServerConfig.resolveBaseUrl(context)
          },
          testTag = "settings_server_default",
        )
      }
    }
  }
}

@Composable
private fun GarminSettingsCard(
  settings: LifeLoadSettings,
  garminPasswordDraft: String,
  onPasswordChanged: (String) -> Unit,
  saving: Boolean,
  message: String,
  onSettingsChanged: (LifeLoadSettings) -> Unit,
  onSave: () -> Unit,
  onClose: () -> Unit,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.24f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.legacy_connected_data), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_connected_data_helper), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        SmallButton(stringResource(R.string.close), onClose, testTag = "settings_close_button")
      }

      SettingsSwitchRow(stringResource(R.string.legacy_garmin_active), settings.garmin.enabled, testTag = "settings_garmin_active") {
        onSettingsChanged(settings.copy(garmin = settings.garmin.copy(enabled = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_garmin_auto_import), settings.garmin.autoImport, testTag = "settings_garmin_auto_import") {
        onSettingsChanged(settings.copy(garmin = settings.garmin.copy(autoImport = it)))
      }
      LifeLoadTextField(
        value = settings.garmin.email,
        onValueChange = { onSettingsChanged(settings.copy(garmin = settings.garmin.copy(email = it))) },
        label = stringResource(R.string.settings_garmin_email),
        modifier = Modifier.fillMaxWidth(),
        testTag = "settings_garmin_email",
      )
      LifeLoadTextField(
        value = garminPasswordDraft,
        onValueChange = onPasswordChanged,
        label = if (settings.garmin.passwordSet) stringResource(R.string.legacy_garmin_password_saved) else stringResource(R.string.settings_garmin_password),
        modifier = Modifier.fillMaxWidth(),
        testTag = "settings_garmin_password",
      )
      OptionChipRow(
        label = stringResource(R.string.settings_auto_import_days),
        selected = settings.garmin.autoImportDays.toString(),
        options = listOf("1", "3", "5", "7", "14"),
        enabled = !saving,
        testTagPrefix = "settings_garmin_auto_import_days",
      ) { value ->
        onSettingsChanged(settings.copy(garmin = settings.garmin.copy(autoImportDays = value.toIntOrNull() ?: settings.garmin.autoImportDays)))
      }

      Row(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalAlignment = Alignment.CenterVertically) {
        SmallButton(if (saving) stringResource(R.string.settings_saving) else stringResource(R.string.legacy_save_garmin), onSave, enabled = !saving, testTag = "settings_garmin_save")
        if (message.isNotBlank()) {
          Text(message, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.primary)
        }
      }
    }
  }
}

@Composable
private fun LifeLoadSettingsCard(
  settings: LifeLoadSettings,
  saving: Boolean,
  message: String,
  onSettingsChanged: (LifeLoadSettings) -> Unit,
  onSave: () -> Unit,
  onClose: () -> Unit,
) {
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.24f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.nav_settings), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_settings_formula_helper), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        SmallButton(stringResource(R.string.close), onClose, testTag = "settings_formula_close_button")
      }

      Text(stringResource(R.string.legacy_checkin_flow), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      OptionChipRow(
        label = stringResource(R.string.settings_default_checkin_date),
        selected = settings.dailyFlow.defaultDate,
        options = listOf("yesterday", "today"),
        enabled = !saving,
        testTagPrefix = "settings_default_date",
      ) { value ->
        onSettingsChanged(settings.copy(dailyFlow = settings.dailyFlow.copy(defaultDate = value)))
      }
      OptionChipRow(
        label = stringResource(R.string.legacy_background_cache),
        selected = settings.dailyFlow.entryCacheDays.toString(),
        options = listOf("3", "5", "7", "14"),
        enabled = !saving,
        testTagPrefix = "settings_cache_days",
      ) { value ->
        onSettingsChanged(settings.copy(dailyFlow = settings.dailyFlow.copy(entryCacheDays = value.toIntOrNull() ?: settings.dailyFlow.entryCacheDays)))
      }

      Text(stringResource(R.string.compass_guidance_scoring_button), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      MultiOptionChipRow(
        label = stringResource(com.life.lifeload.R.string.settings_profile_future),
        selected = activeProfileModifiers(settings.formula),
        options = guidanceProfileOptions(),
        enabled = !saving,
        testTagPrefix = "settings_formula_profile",
      ) { value ->
        onSettingsChanged(settings.copy(formula = settings.formula.withToggledProfileModifier(value)))
      }
      Text(
        stringResource(com.life.lifeload.R.string.settings_profile_future_helper),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      SettingsSwitchRow(stringResource(R.string.legacy_training_trend_brake), settings.formula.includeTrainingTrendBrake, testTag = "settings_include_training_trend_brake") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeTrainingTrendBrake = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_garmin_recovery), settings.formula.includeGarminRecovery, testTag = "settings_include_garmin_recovery") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeGarminRecovery = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_relationship_stress), settings.formula.includeRelationshipStress, testTag = "settings_include_relationship_stress") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeRelationshipStress = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_alone_at_home), settings.formula.includeAloneHome, testTag = "settings_include_alone_home") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeAloneHome = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_after_work_decompression), settings.formula.includeAfterWorkDecompression, testTag = "settings_include_after_work_decompression") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeAfterWorkDecompression = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_project_overrun), settings.formula.includeProjectOverrun, testTag = "settings_include_project_overrun") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeProjectOverrun = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_late_phone), settings.formula.includeLatePhone, testTag = "settings_include_late_phone") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeLatePhone = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_home_office), settings.formula.includeHomeOffice, testTag = "settings_include_home_office") {
        onSettingsChanged(settings.copy(formula = settings.formula.copy(includeHomeOffice = it)))
      }

      Text(stringResource(R.string.legacy_display), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      SettingsSwitchRow(stringResource(R.string.legacy_show_guidance_scoring_button), settings.debug.showFormulaButton, testTag = "settings_show_formula_button") {
        onSettingsChanged(settings.copy(debug = settings.debug.copy(showFormulaButton = it)))
      }
      SettingsSwitchRow(stringResource(R.string.legacy_show_garmin_import_buttons), settings.debug.showGarminImportButtons, testTag = "settings_show_garmin_import_buttons") {
        onSettingsChanged(settings.copy(debug = settings.debug.copy(showGarminImportButtons = it)))
      }

      Row(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalAlignment = Alignment.CenterVertically) {
        SmallButton(if (saving) stringResource(R.string.settings_saving) else stringResource(R.string.settings_save_settings), onSave, enabled = !saving, testTag = "settings_save_button")
        if (message.isNotBlank()) {
          Text(message, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.primary)
        }
      }
    }
  }
}

@Composable
private fun SettingsSwitchRow(label: String, checked: Boolean, testTag: String? = null, onCheckedChange: (Boolean) -> Unit) {
  Row(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Text(label, style = LifeLoadLabelTextStyle, modifier = Modifier.weight(1f))
    Switch(
      checked = checked,
      onCheckedChange = onCheckedChange,
      modifier = if (testTag != null) Modifier.testTag(testTag) else Modifier,
    )
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LifeLoadPreventionCard(state: LifeLoadUiState) {
  val latestTrend = state.dashboard.trendPoints.lastOrNull()
  val previousTrend = state.dashboard.trendPoints.dropLast(1).lastOrNull()
  val drift = state.dashboard.drift
  val approvedDays = approvedWeeklyHistoryDays(state.dashboard.historyDays)
  val reviewSnapshot = weeklyReviewSnapshot(state)
  val risk = drift?.riskLevel?.ifBlank { state.dashboard.weekly.zone } ?: state.dashboard.weekly.zone.ifBlank { "unknown" }
  val color = zoneColor(risk)
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, color.copy(alpha = 0.18f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
          Text(stringResource(R.string.nav_guidance), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_last_days_next_48h), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        InlineInfoChip(risk.ifBlank { "unknown" }.uppercase(), color)
      }

      Text(
        drift?.nextAction?.ifBlank { drift.evidenceNote } ?: state.dashboard.weekly.nextAction.ifBlank { stringResource(R.string.legacy_no_drift_guidance) },
        style = LifeLoadLabelTextStyle,
        fontWeight = FontWeight.SemiBold,
      )

      TrendSnapshotVisualAid(latestTrend = latestTrend, risk = risk)
      WeeklyReviewSnapshotBlock(snapshot = reviewSnapshot)

      FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
        TrendPill(stringResource(R.string.legacy_saved_checkins), "${reviewSnapshot.approvedDayCount}/7", if (reviewSnapshot.approvedDayCount >= 5) "better" else "none")
        TrendPill(stringResource(R.string.legacy_load), qualitativeLoad(latestTrend?.lifeLoadRollingAvg7d), trendDirection(latestTrend?.lifeLoadRollingAvg7d, previousTrend?.lifeLoadRollingAvg7d))
        TrendPill(stringResource(R.string.legacy_sleep), percentValue(latestTrend?.sleepCompliance7d), trendDirection(latestTrend?.sleepCompliance7d, previousTrend?.sleepCompliance7d, higherIsBetter = true))
        TrendPill(stringResource(R.string.legacy_food), percentValue(latestTrend?.nutritionCompliance7d), trendDirection(latestTrend?.nutritionCompliance7d, previousTrend?.nutritionCompliance7d, higherIsBetter = true))
        TrendPill(stringResource(R.string.compass_pain), trendValue(latestTrend?.painAvg7d), trendDirection(latestTrend?.painAvg7d, previousTrend?.painAvg7d))
        TrendPill(stringResource(R.string.legacy_recovery_margin), qualitativeMargin(latestTrend?.lifeMargin7d), trendDirection(latestTrend?.lifeMargin7d, previousTrend?.lifeMargin7d, higherIsBetter = true))
        TrendPill(stringResource(R.string.legacy_risk_level), qualitativeRisk(latestTrend?.driftRiskScore), trendDirection(latestTrend?.driftRiskScore, previousTrend?.driftRiskScore))
        if ((latestTrend?.weightKgLatest ?: 0.0) > 0.0) {
          val weightValue = if (latestTrend?.weightChange14dUsable == true) "${signedTrendValue(latestTrend.weightChange14d)} kg" else "${latestTrend?.weightLatestDaysOld ?: "-"}d old"
          TrendPill(stringResource(R.string.legacy_weight), weightValue, trendDirection(latestTrend?.weightChange14d, previousTrend?.weightChange14d))
        }
        TrendPill(stringResource(R.string.legacy_late_phone_label), "${latestTrend?.phoneAfter21Count7d ?: 0}/7", trendDirection(latestTrend?.phoneAfter21Count7d?.toDouble(), previousTrend?.phoneAfter21Count7d?.toDouble()))
        TrendPill(stringResource(R.string.legacy_project_label), "${latestTrend?.projectOverrunCount7d ?: 0}/7", trendDirection(latestTrend?.projectOverrunCount7d?.toDouble(), previousTrend?.projectOverrunCount7d?.toDouble()))
      }

      if (!drift?.contributingSignals.isNullOrEmpty()) {
        Text(stringResource(R.string.legacy_signals_prefix, localizedSupportLabels(drift?.contributingSignals.orEmpty().take(3))), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
      } else {
        Text(drift?.evidenceNote?.ifBlank { stringResource(R.string.legacy_no_strong_drift) } ?: stringResource(R.string.legacy_trend_features_after_checkins), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }

      val days = approvedDays.take(7)
      if (days.isNotEmpty()) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
          Text(stringResource(R.string.legacy_recent_saved_checkins), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
          days.forEach { day ->
            RecentDayRow(day = day)
          }
        }
      } else {
        Text(stringResource(R.string.legacy_save_checkins_guidance), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
  }
}

@Composable
private fun WeeklyReviewSnapshotBlock(snapshot: WeeklyReviewSnapshot) {
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.16f), androidx.compose.foundation.shape.RoundedCornerShape(10.dp))
      .padding(CompactCardPadding)
      .testTag("weekly_review_snapshot"),
    verticalArrangement = Arrangement.spacedBy(CompactTightGap),
  ) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      Text(stringResource(R.string.legacy_weekly_review), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      Text(stringResource(R.string.legacy_saved_count_7, snapshot.approvedDayCount), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (snapshot.highestRiskDay.isNotBlank()) {
      Text(stringResource(R.string.legacy_highest_load, snapshot.highestRiskDay), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Text(stringResource(R.string.legacy_one_correction, snapshot.oneCorrection), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
    Text(snapshot.evidence, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

@Composable
private fun TrendSnapshotVisualAid(latestTrend: LifeLoadTrendPoint?, risk: String) {
  val load = trendLoadValue(latestTrend) ?: 0.0
  val capacity = capacityProxy(latestTrend) ?: 0.0
  val margin = latestTrend?.lifeMargin7d ?: (capacity - load)
  val riskScore = latestTrend?.driftRiskScore ?: 0.0
  val sleep = latestTrend?.sleepCompliance7d ?: 0.0
  val food = latestTrend?.nutritionCompliance7d ?: 0.0
  val weightChange = latestTrend?.weightChange14d ?: 0.0
  val marginColor = when {
    margin < -3.0 -> MaterialTheme.colorScheme.error
    margin < 0.0 -> warningColor()
    else -> successColor()
  }
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.16f), androidx.compose.foundation.shape.RoundedCornerShape(10.dp))
      .padding(CompactCardPadding),
    verticalArrangement = Arrangement.spacedBy(CompactTightGap),
  ) {
    Text(stringResource(R.string.legacy_snapshot), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
    SignalBar(stringResource(R.string.legacy_recent_load), trendValue(load), (load / 10.0).coerceIn(0.0, 1.0), zoneColor(if (load >= capacity && capacity > 0.0) "orange" else risk))
    SignalBar(stringResource(R.string.legacy_recovery_base), trendValue(capacity), (capacity / 10.0).coerceIn(0.0, 1.0), recoveryColor())
    SignalBar(stringResource(R.string.legacy_recovery_margin), qualitativeMargin(margin), ((margin + 5.0) / 10.0).coerceIn(0.0, 1.0), marginColor)
    SignalBar(stringResource(R.string.legacy_risk_level), qualitativeRisk(riskScore), (riskScore / 10.0).coerceIn(0.0, 1.0), zoneColor(risk))
    if ((latestTrend?.weightKgLatest ?: 0.0) > 0.0) {
      val usable = latestTrend?.weightChange14dUsable == true
      val label = if (usable) stringResource(R.string.legacy_weight_14d) else stringResource(R.string.legacy_weight_age)
      val value = if (usable) "${signedTrendValue(weightChange)} kg" else stringResource(R.string.legacy_days_old, "${latestTrend?.weightLatestDaysOld ?: "-"}")
      SignalBar(label, value, if (usable) (kotlin.math.abs(weightChange) / 2.0).coerceIn(0.0, 1.0) else 0.0, if (usable) weightTrendColor(weightChange) else MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Row(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), modifier = Modifier.fillMaxWidth()) {
      SignalBar(stringResource(R.string.legacy_sleep), percentValue(sleep), sleep.coerceIn(0.0, 1.0), successColor(), modifier = Modifier.weight(1f))
      SignalBar(stringResource(R.string.legacy_food), percentValue(food), food.coerceIn(0.0, 1.0), successColor(), modifier = Modifier.weight(1f))
    }
  }
}

@Composable
private fun SignalBar(label: String, value: String, fraction: Double, color: Color, modifier: Modifier = Modifier) {
  Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
      Text(label, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
      Text(value, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
    }
    Box(
      modifier = Modifier
        .fillMaxWidth()
        .height(7.dp)
        .background(MaterialTheme.colorScheme.outline.copy(alpha = 0.14f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp)),
    ) {
      Box(
        modifier = Modifier
          .fillMaxWidth(fraction.toFloat().coerceIn(0f, 1f))
          .height(7.dp)
          .background(color.copy(alpha = 0.85f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp)),
      )
    }
  }
}

@Composable
private fun TrendPill(label: String, value: String, direction: String) {
  val color = when (direction) {
    "better" -> successColor()
    "worse" -> warningColor()
    else -> MaterialTheme.colorScheme.onSurfaceVariant
  }
  Row(
    modifier = Modifier
      .border(1.dp, color.copy(alpha = 0.22f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
      .padding(horizontal = 8.dp, vertical = 4.dp),
    horizontalArrangement = Arrangement.spacedBy(CompactTightGap),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Text(label, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    Text(value, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
    Text(directionSymbol(direction), style = LifeLoadLabelTextStyle, color = color, fontWeight = FontWeight.SemiBold)
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LifeLoadTrendGraphCard(state: LifeLoadUiState) {
  val points = state.dashboard.trendPoints.takeLast(14)
  val latest = points.lastOrNull()
  val previous = points.dropLast(1).lastOrNull()
  val loadColor = zoneColor(trendLoadValue(latest)?.let { if (it >= 7.0) "orange" else if (it >= 4.5) "yellow" else "green" } ?: "unknown")
  val recoveryColor = recoveryColor()
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.14f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
      ) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.legacy_trend_curve), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_trend_curve_helper), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (latest != null) {
          Text(latest.date.takeLast(5), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
      }

      if (points.size < 2) {
        Text(
          stringResource(R.string.legacy_save_two_checkins_curve),
          style = LifeLoadLabelTextStyle,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        return@Column
      }

      TrendCurveCanvas(points = points, loadColor = loadColor, recoveryColor = recoveryColor)

      FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
        LegendPill(stringResource(R.string.legacy_recent_load), trendValue(trendLoadValue(latest)), trendDirection(trendLoadValue(latest), trendLoadValue(previous)), loadColor)
        LegendPill(stringResource(R.string.legacy_recovery_base), trendValue(capacityProxy(latest)), trendDirection(capacityProxy(latest), capacityProxy(previous), higherIsBetter = true), recoveryColor)
        LegendPill(stringResource(R.string.legacy_balance_line), "", "none", successColor())
        LegendPill(stringResource(R.string.legacy_recovery_margin), qualitativeMargin(latest?.lifeMargin7d), trendDirection(latest?.lifeMargin7d, previous?.lifeMargin7d, higherIsBetter = true), zoneColor(if ((latest?.lifeMargin7d ?: 0.0) < 0.0) "orange" else "green"))
        LegendPill(stringResource(R.string.legacy_signals_prefix, ""), "${latest?.redFlagCount7d ?: 0}/7", trendDirection(latest?.redFlagCount7d?.toDouble(), previous?.redFlagCount7d?.toDouble()), MaterialTheme.colorScheme.error)
      }
    }
  }
}

@Composable
private fun TrendCurveCanvas(points: List<LifeLoadTrendPoint>, loadColor: Color, recoveryColor: Color) {
  val gridColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.18f)
  val textColor = MaterialTheme.colorScheme.onSurfaceVariant
  val loadValues = points.map { trendLoadValue(it) ?: 0.0 }
  val recoveryValues = points.map { capacityProxy(it) ?: 0.0 }
  val allValues = loadValues + recoveryValues
  val minValue = 0.0
  val maxValue = maxOf(10.0, allValues.maxOrNull() ?: 10.0)
  val balanceValue = recoveryValues.lastOrNull() ?: 0.0
  val balanceColor = successColor()
  Canvas(
    modifier = Modifier
      .fillMaxWidth()
      .height(132.dp),
  ) {
    val left = 10.dp.toPx()
    val right = size.width - 10.dp.toPx()
    val top = 10.dp.toPx()
    val bottom = size.height - 18.dp.toPx()
    val width = right - left
    val height = bottom - top

    repeat(4) { index ->
      val y = top + height * index / 3f
      drawLine(color = gridColor, start = Offset(left, y), end = Offset(right, y), strokeWidth = 1.dp.toPx())
    }

    fun yFor(value: Double): Float {
      val span = (maxValue - minValue).takeIf { kotlin.math.abs(it) > 0.001 } ?: 1.0
      val normalized = ((value - minValue) / span).coerceIn(0.0, 1.0)
      return bottom - (normalized.toFloat() * height)
    }

    fun xFor(index: Int): Float {
      if (points.size <= 1) return left
      return left + width * index / (points.size - 1).toFloat()
    }

    fun drawSeries(values: List<Double>, color: Color) {
      values.zipWithNext().forEachIndexed { index, pair ->
        drawLine(
          color = color,
          start = Offset(xFor(index), yFor(pair.first)),
          end = Offset(xFor(index + 1), yFor(pair.second)),
          strokeWidth = 3.dp.toPx(),
          cap = StrokeCap.Round,
        )
      }
      values.forEachIndexed { index, value ->
        drawCircle(color = color, radius = 3.2.dp.toPx(), center = Offset(xFor(index), yFor(value)))
      }
    }

    val balanceY = yFor(balanceValue)
    drawLine(
      color = balanceColor.copy(alpha = 0.58f),
      start = Offset(left, balanceY),
      end = Offset(right, balanceY),
      strokeWidth = 1.6.dp.toPx(),
      pathEffect = PathEffect.dashPathEffect(floatArrayOf(9.dp.toPx(), 7.dp.toPx()), 0f),
    )

    drawSeries(loadValues, loadColor)
    drawSeries(recoveryValues, recoveryColor)

    if (points.isNotEmpty()) {
      drawContext.canvas.nativeCanvas.apply {
        val paint = android.graphics.Paint().apply {
          color = android.graphics.Color.argb(
            170,
            (textColor.red * 255).toInt(),
            (textColor.green * 255).toInt(),
            (textColor.blue * 255).toInt(),
          )
          textSize = 10.dp.toPx()
          isAntiAlias = true
        }
        drawText("balance", left + 4.dp.toPx(), (balanceY - 5.dp.toPx()).coerceAtLeast(top + 10.dp.toPx()), paint)
        drawText(points.first().date.takeLast(5), left, size.height - 3.dp.toPx(), paint)
        drawText(points.last().date.takeLast(5), right - 34.dp.toPx(), size.height - 3.dp.toPx(), paint)
      }
    }
  }
}

@Composable
private fun LegendPill(label: String, value: String, direction: String, color: Color) {
  Row(
    modifier = Modifier
      .border(1.dp, color.copy(alpha = 0.24f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
      .padding(horizontal = 8.dp, vertical = 4.dp),
    horizontalArrangement = Arrangement.spacedBy(CompactTightGap),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Box(modifier = Modifier.size(8.dp).background(color, androidx.compose.foundation.shape.RoundedCornerShape(999.dp)))
    Text(label, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (value.isNotBlank()) {
      Text(value, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
    }
    if (direction != "none") {
      Text(directionSymbol(direction), style = LifeLoadLabelTextStyle, color = color, fontWeight = FontWeight.SemiBold)
    }
  }
}

private fun capacityProxy(point: LifeLoadTrendPoint?): Double? {
  if (point == null) return null
  return point.chronicCapacity42d.takeIf { it > 0.0 } ?: (((point.sleepCompliance7d + point.nutritionCompliance7d) / 2.0) * 10.0)
}

private fun trendLoadValue(point: LifeLoadTrendPoint?): Double? {
  if (point == null) return null
  return point.acuteLoad7d.takeIf { it > 0.0 } ?: point.lifeLoadRollingAvg7d
}

@Composable
private fun RecentDayRow(day: com.life.lifeload.domain.LifeLoadHistoryDay) {
  val color = zoneColor(day.zone)
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.16f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .padding(horizontal = 8.dp, vertical = 6.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
      Text(day.date, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      Text(day.diarySummary.ifBlank { day.nextAction.ifBlank { day.state } }, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Text(day.zone.ifBlank { "-" }.uppercase(), style = LifeLoadLabelTextStyle, color = color, fontWeight = FontWeight.SemiBold)
  }
}

private data class AttentionItem(
  val label: String,
  val detail: String,
  val severe: Boolean = false,
)

private data class DetectedField(
  val label: String,
  val value: String,
)

@Composable
private fun ProcessingBanner(title: String, detail: String) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.2f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .padding(horizontal = 8.dp, vertical = 8.dp),
    verticalAlignment = Alignment.CenterVertically,
    horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
  ) {
    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
    Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
      Text(title, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurfaceVariant)
      Text(detail, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun AnalyzingBanner() {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.08f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
      .padding(horizontal = 8.dp, vertical = 8.dp),
    verticalAlignment = Alignment.CenterVertically,
    horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
  ) {
    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
    Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
      Text(stringResource(R.string.legacy_ai_analyzing_diary), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      Text(stringResource(R.string.legacy_ai_analyzing_diary_detail), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun InlineInfoChip(text: String, color: Color) {
  Row(
    modifier = Modifier
      .background(color.copy(alpha = 0.08f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
      .border(1.dp, color.copy(alpha = 0.25f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
      .padding(horizontal = 8.dp, vertical = 4.dp),
    verticalAlignment = Alignment.CenterVertically,
    horizontalArrangement = Arrangement.spacedBy(CompactInlineGap),
  ) {
    Text(text, style = LifeLoadLabelTextStyle, color = color)
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetectedReviewCard(fields: List<DetectedField>) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
        Icon(Icons.Filled.Psychology, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
        Text(stringResource(R.string.legacy_detected_by_ai), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      }
      FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
        fields.take(12).forEach { field ->
          InlineInfoChip("${field.label}: ${field.value}", MaterialTheme.colorScheme.primary)
        }
      }
    }
  }
}

@Composable
private fun NeedsAttentionCard(items: List<AttentionItem>) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.tertiary, modifier = Modifier.size(18.dp))
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
          Text(stringResource(R.string.legacy_review_before_saving), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(stringResource(R.string.legacy_review_before_saving_detail), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
      }
      items.take(6).forEach { item ->
        val color = if (item.severe) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.tertiary
        Column(
          modifier = Modifier
            .fillMaxWidth()
            .background(color.copy(alpha = 0.08f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
            .border(1.dp, color.copy(alpha = 0.22f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
            .padding(8.dp),
          verticalArrangement = Arrangement.spacedBy(CompactTightGap),
        ) {
          Text(item.label, style = LifeLoadLabelTextStyle, color = color, fontWeight = FontWeight.SemiBold)
          Text(item.detail, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
      }
    }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LifeLoadHeroCard(state: LifeLoadUiState) {
  val zone = state.score.zone.ifBlank { state.dashboard.weekly.zone.ifBlank { "unknown" } }
  val next = state.score.nextAction.ifBlank { state.dashboard.weekly.nextAction.ifBlank { stringResource(R.string.legacy_no_recommendation_yet) } }
  val signalEntry = if (state.draftEntry.diaryText.isNotBlank() || state.hasDraft) state.draftEntry else state.entry
  val color = zoneColor(zone)
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, color.copy(alpha = 0.26f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
      ) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.legacy_zone), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
          Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
            Box(
              modifier = Modifier
                .size(10.dp)
                .background(color, androidx.compose.foundation.shape.RoundedCornerShape(999.dp)),
            )
            Text(
              "${zone.uppercase()} - ${state.score.mode.ifBlank { modeForZone(zone) }.uppercase()}",
              style = MaterialTheme.typography.titleMedium,
              fontWeight = FontWeight.SemiBold,
              color = color,
            )
          }
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
          Text(stringResource(R.string.legacy_load), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
          Text(signedLoad(state.score.lifeLoadScore), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        }
      }

      Text(stringResource(R.string.legacy_next_prefix, next), style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      if (state.score.minimumAction.isNotBlank()) {
        Text(stringResource(R.string.legacy_minimum_win, state.score.minimumAction), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
      if (state.score.why.isNotEmpty()) {
        Text(stringResource(R.string.legacy_why_prefix, localizedSupportLabels(state.score.why.take(3))), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
      }

      FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
        HeroSignal(stringResource(R.string.legacy_sleep_timing), boolSignal(signalEntry.sleepOk), signalColor(signalEntry.sleepOk))
        HeroSignal(stringResource(R.string.legacy_food_on_track), boolSignal(signalEntry.nutritionOk), signalColor(signalEntry.nutritionOk))
        HeroSignal(stringResource(R.string.field_stress_label), signalEntry.stress?.let { if (it >= 7) "$it ↑" else "$it" } ?: "?", if ((signalEntry.stress ?: 0) >= 7) warningColor() else MaterialTheme.colorScheme.onSurfaceVariant)
        HeroSignal(stringResource(R.string.legacy_foot), signalEntry.footPain?.let { "$it/10" } ?: "?", if ((signalEntry.footPain ?: 0) >= 5) warningColor() else MaterialTheme.colorScheme.onSurfaceVariant)
        HeroSignal(stringResource(R.string.legacy_alcohol), localizedOptionLabel(signalEntry.alcohol ?: "?"), if (signalEntry.alcohol == "home") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
        HeroSignal(stringResource(R.string.legacy_binge), if (signalEntry.binge == true) stringResource(R.string.yes) else if (signalEntry.binge == false) stringResource(R.string.no) else "?", if (signalEntry.binge == true) warningColor() else MaterialTheme.colorScheme.onSurfaceVariant)
      }

      Text(
        stringResource(R.string.legacy_week_summary, state.dashboard.weekly.sleepCompleted, state.dashboard.weekly.sleepTarget, state.dashboard.weekly.nutritionCompleted, state.dashboard.weekly.nutritionTarget, state.dashboard.weekly.hardSessions, state.dashboard.weekly.redFlagCount),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      if (state.score.redFlags.isNotEmpty()) {
        Text(stringResource(R.string.legacy_support_signals, localizedSupportLabels(state.score.redFlags)), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.error)
      }
    }
  }
}

@Composable
private fun HeroSignal(label: String, value: String, color: Color) {
  Row(
    modifier = Modifier
      .border(1.dp, color.copy(alpha = 0.24f), androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
      .padding(horizontal = 8.dp, vertical = 4.dp),
    horizontalArrangement = Arrangement.spacedBy(CompactTightGap),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Text(label, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    Text(value, style = LifeLoadLabelTextStyle, color = color, fontWeight = FontWeight.SemiBold)
  }
}

private fun boolSignal(value: Boolean?): String = when (value) {
  true -> "✓"
  false -> "!"
  null -> "?"
}

private fun modeForZone(zone: String): String = when (zone.lowercase()) {
  "green" -> "continue"
  "yellow" -> "protect"
  "orange" -> "hold"
  "red" -> "stabilize"
  else -> "unknown"
}

private fun trendValue(value: Double?): String = if (value == null) "-" else oneDecimal(value)

private fun qualitativeLoad(value: Double?): String = when {
  value == null -> "unknown"
  value >= 7.0 -> "high"
  value >= 4.0 -> "moderate"
  else -> "low"
}

private fun qualitativeMargin(value: Double?): String = when {
  value == null -> "unknown"
  value >= 2.0 -> "positive"
  value >= 0.0 -> "narrow"
  else -> "negative"
}

private fun qualitativeRisk(value: Double?): String = when {
  value == null -> "unknown"
  value >= 70.0 -> "high"
  value >= 35.0 -> "medium"
  value >= 7.0 -> "high"
  value >= 5.0 -> "medium"
  else -> "low"
}

private fun signedLoad(value: Double): String = if (value > 0.0) "+${oneDecimal(value)}" else oneDecimal(value)

private fun signedTrendValue(value: Double?): String = if (value == null) "-" else "${if (value >= 0) "+" else ""}${oneDecimal(value)}"

private fun percentValue(value: Double?): String = if (value == null) "-" else "${(value * 100.0).toInt()}%"

@Composable
private fun weightTrendColor(changeKg: Double): Color = when {
  changeKg >= 2.0 -> MaterialTheme.colorScheme.error
  changeKg >= 1.0 -> warningColor()
  changeKg <= -0.5 -> successColor()
  else -> MaterialTheme.colorScheme.onSurfaceVariant
}

private fun trendDirection(current: Double?, previous: Double?, higherIsBetter: Boolean = false): String {
  if (current == null || previous == null) return "flat"
  val delta = current - previous
  if (kotlin.math.abs(delta) < 0.05) return "flat"
  val rising = delta > 0
  return if (higherIsBetter) {
    if (rising) "better" else "worse"
  } else {
    if (rising) "worse" else "better"
  }
}

private fun directionSymbol(direction: String): String = when (direction) {
  "better" -> "↓"
  "worse" -> "↑"
  else -> "→"
}

@Composable
private fun signalColor(value: Boolean?): Color = when (value) {
  true -> successColor()
  false -> warningColor()
  null -> MaterialTheme.colorScheme.onSurfaceVariant
}

@Composable
private fun LifeLoadTextField(
  value: String,
  onValueChange: (String) -> Unit,
  label: String,
  modifier: Modifier = Modifier,
  singleLine: Boolean = false,
  minLines: Int = 1,
  enabled: Boolean = true,
  testTag: String? = null,
) {
  val colorScheme = MaterialTheme.colorScheme
  OutlinedTextField(
    value = value,
    onValueChange = onValueChange,
    modifier = modifier
      .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
      .background(
      brush = Brush.verticalGradient(
        colors = listOf(
          colorScheme.surfaceVariant.copy(alpha = 0.96f),
          colorScheme.secondaryContainer.copy(alpha = 0.30f),
          colorScheme.primary.copy(alpha = 0.08f),
        ),
      ),
      shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
    ),
    enabled = enabled,
    singleLine = singleLine,
    minLines = minLines,
    label = { Text(label) },
    textStyle = LifeLoadLabelTextStyle,
    colors = OutlinedTextFieldDefaults.colors(
      focusedContainerColor = Color.Transparent,
      unfocusedContainerColor = Color.Transparent,
      disabledContainerColor = Color.Transparent,
      errorContainerColor = Color.Transparent,
      focusedBorderColor = colorScheme.primary.copy(alpha = 0.82f),
      unfocusedBorderColor = colorScheme.outline.copy(alpha = 0.78f),
      focusedLabelColor = colorScheme.primary,
      unfocusedLabelColor = colorScheme.onSurfaceVariant,
      cursorColor = colorScheme.primary,
    ),
  )
}

@Composable
private fun SmallButton(
  text: String,
  onClick: () -> Unit,
  enabled: Boolean = true,
  testTag: String? = null,
) {
  TextButton(
    onClick = onClick,
    enabled = enabled,
    modifier = if (testTag != null) Modifier.testTag(testTag) else Modifier,
    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp),
  ) {
    Text(text, style = LifeLoadLabelTextStyle)
  }
}

@Composable
private fun Chip(
  text: String,
  selected: Boolean,
  onClick: () -> Unit,
  enabled: Boolean = true,
  testTag: String? = null,
) {
  val borderColor = when {
    !enabled -> MaterialTheme.colorScheme.outline.copy(alpha = 0.35f)
    selected -> MaterialTheme.colorScheme.primary
    else -> MaterialTheme.colorScheme.outline.copy(alpha = 0.7f)
  }
  val backgroundColor = when {
    !enabled -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.42f)
    selected -> MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)
    else -> MaterialTheme.colorScheme.surface
  }
  val textColor = when {
    !enabled -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.72f)
    selected -> MaterialTheme.colorScheme.primary
    else -> MaterialTheme.colorScheme.onSurface
  }
  Box(
    modifier = Modifier
      .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
      .background(backgroundColor, androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
      .border(
        width = 1.dp,
        color = borderColor,
        shape = androidx.compose.foundation.shape.RoundedCornerShape(999.dp),
      )
      .clickable(enabled = enabled, onClick = onClick)
      .padding(horizontal = 8.dp, vertical = 4.dp),
  ) {
    Text(text, style = LifeLoadLabelTextStyle, color = textColor)
  }
}

@Composable
private fun SystemStatusCard(state: LifeLoadUiState) {
  val status = systemStatusSummary(state)
  Card(
    modifier = Modifier
      .fillMaxWidth()
      .border(1.dp, status.color.copy(alpha = 0.20f), androidx.compose.foundation.shape.RoundedCornerShape(12.dp)),
  ) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap), modifier = Modifier.weight(1f)) {
          Text(stringResource(R.string.legacy_system_status), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          Text(status.detail, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        InlineInfoChip(status.label, status.color)
      }
      Text(
        stringResource(R.string.legacy_system_status_line, state.statusLights.backend.name.lowercase(), state.statusLights.db.name.lowercase(), state.statusLights.sync.name.lowercase(), state.statusLights.extract.name.lowercase()),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
  }
}

private data class SystemStatusSummary(
  val label: String,
  val detail: String,
  val color: Color,
)

@Composable
private fun systemStatusSummary(state: LifeLoadUiState): SystemStatusSummary = when {
  state.statusLights.backend == LifeLoadBackendStatus.ERROR -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_local_mode),
    detail = stringResource(R.string.legacy_status_local_mode_detail),
    color = MaterialTheme.colorScheme.error,
  )
  state.statusLights.db == LifeLoadDbStatus.ERROR -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_data_check),
    detail = stringResource(R.string.legacy_status_data_check_detail),
    color = MaterialTheme.colorScheme.error,
  )
  state.statusLights.sync == LifeLoadSyncStatus.ERROR -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_sync_check),
    detail = stringResource(R.string.legacy_status_sync_check_detail),
    color = MaterialTheme.colorScheme.error,
  )
  state.statusLights.extract == LifeLoadExtractStatus.ERROR -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_analysis_check),
    detail = stringResource(R.string.legacy_status_analysis_check_detail),
    color = warningColor(),
  )
  state.statusLights.sync == LifeLoadSyncStatus.SAVING -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_saving),
    detail = stringResource(R.string.legacy_status_saving_detail),
    color = MaterialTheme.colorScheme.primary,
  )
  state.statusLights.extract == LifeLoadExtractStatus.ANALYZING -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_analyzing),
    detail = stringResource(R.string.legacy_status_analyzing_detail),
    color = MaterialTheme.colorScheme.primary,
  )
  state.statusLights.backend == LifeLoadBackendStatus.OFFLINE -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_server_off),
    detail = stringResource(R.string.legacy_status_server_off_detail),
    color = MaterialTheme.colorScheme.onSurfaceVariant,
  )
  else -> SystemStatusSummary(
    label = stringResource(R.string.legacy_status_ready),
    detail = stringResource(R.string.legacy_status_ready_detail),
    color = successColor(),
  )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AlcoholChipRow(
  value: String?,
  enabled: Boolean,
  testTagPrefix: String? = null,
  onSelect: (String) -> Unit,
) {
  OptionChipRow(
    label = stringResource(R.string.field_alcohol_label),
    selected = value ?: "?",
    options = listOf("none", "social", "home", "?"),
    enabled = enabled,
    testTagPrefix = testTagPrefix,
  ) { onSelect(if (it == "?") "" else it) }
}

@Composable
private fun FormulaExplanationDialog(
  score: com.life.lifeload.domain.LifeLoadScore,
  formula: com.life.lifeload.domain.LifeLoadFormulaContract,
  onDismiss: () -> Unit,
) {
  AlertDialog(
    onDismissRequest = onDismiss,
    confirmButton = {
      TextButton(onClick = onDismiss) {
        Text(stringResource(R.string.close))
      }
    },
    title = { Text(stringResource(R.string.compass_guidance_scoring_button)) },
    text = {
      LazyColumn(
        modifier = Modifier.heightIn(max = 460.dp),
        verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
      ) {
        item {
          Text(
            stringResource(R.string.legacy_formula_intro),
            style = LifeLoadLabelTextStyle,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
          )
        }
        item {
          Text(
            stringResource(R.string.legacy_formula_current, oneDecimal(score.lifeLoadScore), oneDecimal(score.recoveryScore), oneDecimal(score.strainScore), oneDecimal(score.trainingLoad)),
            style = LifeLoadLabelTextStyle,
            fontWeight = FontWeight.SemiBold,
          )
        }
        item {
          Text(
            stringResource(R.string.legacy_formula_training_context, oneDecimal(score.acuteTrainingLoad), oneDecimal(score.chronicTrainingLoad), score.trainingLoadRatio?.let(::twoDecimal) ?: "-", oneDecimal(score.trainingRamp)),
            style = LifeLoadLabelTextStyle,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
          )
        }
        if (formula.sections.isNotEmpty()) {
          items(formula.sections) { section ->
            FormulaSection(
              title = section.title,
              body = section.body,
              items = section.items.map { "${it.input}: ${it.effect}" },
            )
          }
        } else {
          item { FormulaSection(stringResource(R.string.legacy_formula_section_life_load_title), stringResource(R.string.legacy_formula_section_life_load_body)) }
          item { FormulaSection(stringResource(R.string.legacy_formula_section_training_title), stringResource(R.string.legacy_formula_section_training_body)) }
          item { FormulaSection(stringResource(R.string.legacy_formula_section_atl_ctl_title), stringResource(R.string.legacy_formula_section_atl_ctl_body)) }
          item { FormulaSection(stringResource(R.string.legacy_formula_section_strain_title), stringResource(R.string.legacy_formula_section_strain_body)) }
          item { FormulaSection(stringResource(R.string.legacy_formula_section_recovery_title), stringResource(R.string.legacy_formula_section_recovery_body)) }
          item { FormulaSection(stringResource(R.string.legacy_formula_section_hard_signals_title), stringResource(R.string.legacy_formula_section_hard_signals_body)) }
        }
        if (score.redFlags.isNotEmpty() || score.warnings.isNotEmpty()) {
          item {
            Text(
              stringResource(R.string.legacy_formula_current_support_signals, localizedSupportLabels(score.redFlags + score.warnings)),
              style = LifeLoadLabelTextStyle,
              color = MaterialTheme.colorScheme.error,
            )
          }
        }
      }
    },
  )
}

@Composable
private fun FormulaSection(title: String, body: String, items: List<String> = emptyList()) {
  Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
    Text(title, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
    Text(body, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    items.forEach { item ->
      Text("- $item", style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
  }
}

@Composable
private fun LifeLoadInterpretationCard(state: LifeLoadUiState) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Text(stringResource(R.string.legacy_interpretation), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
      Text(stringResource(R.string.legacy_detected_summary, state.entry.diarySummary.ifBlank { state.latestProposal?.summary ?: stringResource(R.string.legacy_no_extracted_summary) }), style = LifeLoadLabelTextStyle)
      Text(stringResource(R.string.legacy_status_value, state.score.zone.ifBlank { state.dashboard.weekly.zone.ifBlank { stringResource(R.string.operator_unknown) } }), style = LifeLoadLabelTextStyle)
      if (state.score.redFlags.isNotEmpty()) {
        Text(stringResource(R.string.legacy_support_signals, localizedSupportLabels(state.score.redFlags)), style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.error)
      }
      Text(stringResource(R.string.legacy_next_prefix, state.score.nextAction.ifBlank { state.dashboard.weekly.nextAction.ifBlank { stringResource(R.string.legacy_no_recommendation_yet) } }), style = LifeLoadLabelTextStyle)
      Text(
        stringResource(R.string.legacy_this_week_summary, state.dashboard.weekly.sleepCompleted, state.dashboard.weekly.sleepTarget, state.dashboard.weekly.nutritionCompleted, state.dashboard.weekly.nutritionTarget, state.dashboard.weekly.hardSessions, state.dashboard.weekly.redFlagCount),
        style = LifeLoadLabelTextStyle,
      )
    }
  }
}

private fun oneDecimal(value: Double): String = "%.1f".format(value)

private fun twoDecimal(value: Double): String = "%.2f".format(value)

@Composable
private fun CollapsibleCard(
  title: String,
  subtitle: String? = null,
  expanded: Boolean,
  onToggle: () -> Unit,
  testTag: String? = null,
  content: @Composable () -> Unit,
) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .padding(CompactCardPadding),
      verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
    ) {
      Row(
        modifier = Modifier
          .fillMaxWidth()
          .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
          .clickable(onClick = onToggle),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Column(
          modifier = Modifier.weight(1f),
          verticalArrangement = Arrangement.spacedBy(CompactTightGap),
        ) {
          Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
          if (subtitle != null && !expanded) {
            Text(subtitle, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
          }
        }
        Text(
          if (expanded) stringResource(R.string.legacy_hide) else stringResource(R.string.legacy_show),
          style = LifeLoadLabelTextStyle,
          color = MaterialTheme.colorScheme.primary,
        )
      }
      if (expanded) {
        content()
      }
    }
  }
}

@Composable
private fun InlineExpandableSection(
  title: String,
  expanded: Boolean,
  onToggle: () -> Unit,
  testTag: String? = null,
  content: @Composable () -> Unit,
) {
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .border(
        width = 1.dp,
        color = MaterialTheme.colorScheme.outline.copy(alpha = 0.14f),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
      )
      .padding(CompactCardPadding),
    verticalArrangement = Arrangement.spacedBy(CompactFieldGap),
  ) {
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
        .clickable(onClick = onToggle),
      horizontalArrangement = Arrangement.SpaceBetween,
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Text(title, style = LifeLoadLabelTextStyle, fontWeight = FontWeight.SemiBold)
      Text(
        if (expanded) stringResource(R.string.legacy_hide) else stringResource(R.string.legacy_show),
        style = LifeLoadLabelTextStyle,
        color = MaterialTheme.colorScheme.primary,
      )
    }
    if (expanded) {
      content()
    }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TernaryChipRow(
  label: String,
  value: Boolean?,
  enabled: Boolean,
  accent: Color? = null,
  testTagPrefix: String? = null,
  onChange: (Boolean?) -> Unit,
) {
  Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
    Text(
      label,
      style = LifeLoadLabelTextStyle,
      color = if (enabled) accent ?: MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
    )
    FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
      listOf(
        Triple("unknown", stringResource(R.string.not_sure), null),
        Triple("yes", stringResource(R.string.yes), true),
        Triple("no", stringResource(R.string.no), false),
      ).forEach { (key, option, optionValue) ->
        val selected = value == optionValue
        Chip(
          text = option,
          selected = selected,
          onClick = {
            if (!enabled) return@Chip
            onChange(optionValue)
          },
          enabled = enabled,
          testTag = testTagPrefix?.let { "${it}_$key" },
        )
      }
    }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun OptionChipRow(
  label: String,
  selected: String,
  options: List<String>,
  enabled: Boolean,
  testTagPrefix: String? = null,
  onSelect: (String) -> Unit,
) {
  Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
    Text(label, style = LifeLoadLabelTextStyle, color = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
      options.forEach { option ->
        Chip(
          text = localizedOptionLabel(option),
          selected = selected == option,
          onClick = { if (enabled) onSelect(option) },
          enabled = enabled,
          testTag = testTagPrefix?.let { "${it}_${option.lowercase().replace("?", "unknown")}" },
        )
      }
    }
  }
}

@Composable
private fun localizedOptionLabel(option: String): String = when (option) {
  "?" -> stringResource(R.string.not_sure)
  "none" -> stringResource(R.string.none)
  "social" -> stringResource(R.string.social)
  "home" -> stringResource(R.string.home)
  "walk" -> stringResource(R.string.walk)
  "bike" -> stringResource(R.string.bike)
  "run" -> stringResource(R.string.run)
  "crossfit" -> stringResource(R.string.crossfit)
  "rehab" -> stringResource(R.string.rehab)
  "meditation" -> stringResource(R.string.meditation)
  "other" -> stringResource(R.string.other)
  "custom" -> stringResource(R.string.custom)
  "low" -> stringResource(R.string.low)
  "normal" -> stringResource(R.string.normal)
  "heavy" -> stringResource(R.string.heavy)
  "extreme" -> stringResource(R.string.extreme)
  "high" -> stringResource(R.string.high)
  "yes" -> stringResource(R.string.yes)
  "no" -> stringResource(R.string.no)
  "n/a", "na" -> stringResource(R.string.na)
  else -> option
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MultiOptionChipRow(
  label: String,
  selected: Set<String>,
  options: List<Pair<String, String>>,
  enabled: Boolean,
  testTagPrefix: String? = null,
  onToggle: (String) -> Unit,
) {
  Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
    Text(label, style = LifeLoadLabelTextStyle, color = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
      options.forEach { (option, text) ->
        Chip(
          text = text,
          selected = option in selected,
          onClick = { if (enabled) onToggle(option) },
          enabled = enabled,
          testTag = testTagPrefix?.let { "${it}_${option.lowercase()}" },
        )
      }
    }
  }
}

@Composable
private fun guidanceProfileOptions(): List<Pair<String, String>> = listOf(
  "balanced" to stringResource(com.life.lifeload.R.string.settings_balanced),
  "protective" to stringResource(com.life.lifeload.R.string.settings_protective),
  "sports_light" to stringResource(com.life.lifeload.R.string.settings_sports_light),
)

private val guidanceProfileKeys = listOf("balanced", "protective", "sports_light")

private fun activeProfileModifiers(formula: LifeLoadFormulaSettings): Set<String> {
  val savedModifiers = formula.profileModifiers.filterTo(linkedSetOf()) { it in guidanceProfileKeys }
  if (savedModifiers.isNotEmpty()) return savedModifiers
  val legacyProfile = formula.profile.takeIf { it in guidanceProfileKeys } ?: "balanced"
  return linkedSetOf(legacyProfile)
}

private fun LifeLoadFormulaSettings.withToggledProfileModifier(key: String): LifeLoadFormulaSettings {
  if (key !in guidanceProfileKeys) return this
  val current = activeProfileModifiers(this)
  val next = if (key in current) current - key else current + key
  val normalized = next.ifEmpty { setOf("balanced") }
  val legacyProfile = guidanceProfileKeys.firstOrNull { it in normalized } ?: "balanced"
  return copy(profile = legacyProfile, profileModifiers = normalized)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun IntChipRow(
  label: String,
  value: Int?,
  enabled: Boolean,
  accentAtOrAbove: Int? = null,
  maxValue: Int = 10,
  testTagPrefix: String? = null,
  onChange: (Int?) -> Unit,
) {
  val accent = if (accentAtOrAbove != null && (value ?: -1) >= accentAtOrAbove) warningColor() else null
  val baseOptions = if (maxValue <= 8) listOf("0", "1", "2", "3", "4", "5", "6", "7", "8") else listOf("0", "2", "4", "6", "8", "10")
  val options = buildList {
    add("?")
    addAll(baseOptions)
    val current = value?.toString()
    if (current != null && current !in this) add(1, current)
  }
  Column(verticalArrangement = Arrangement.spacedBy(CompactTightGap)) {
    Text(
      label,
      style = LifeLoadLabelTextStyle,
      color = if (enabled) accent ?: MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
    )
    FlowRow(horizontalArrangement = Arrangement.spacedBy(CompactInlineGap), verticalArrangement = Arrangement.spacedBy(CompactInlineGap)) {
      options.forEach { option ->
        Chip(
          text = option,
          selected = (option == "?" && value == null) || (option != "?" && option.toIntOrNull() == value),
          onClick = { if (enabled) onChange(option.toIntOrNull()) },
          enabled = enabled,
          testTag = testTagPrefix?.let { "${it}_${option.lowercase().replace("?", "unknown")}" },
        )
      }
    }
  }
}

@Composable
private fun TargetHint(text: String) {
  Text(text, style = LifeLoadLabelTextStyle, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun warningColor(): Color = MaterialTheme.colorScheme.tertiary

@Composable
private fun successColor(): Color = MaterialTheme.colorScheme.secondary

@Composable
private fun recoveryColor(): Color = if (isSystemInDarkTheme()) Color(0xFF86C5FF) else LifeLoadBlue

@Composable
private fun zoneColor(zone: String): Color = when (zone.lowercase()) {
  "red" -> MaterialTheme.colorScheme.error
  "orange", "yellow" -> MaterialTheme.colorScheme.tertiary
  "green" -> successColor()
  else -> MaterialTheme.colorScheme.onSurfaceVariant
}

private fun loadingOrStatusLabel(state: LifeLoadUiState): String = when {
  state.loading -> "Loading day and dashboard..."
  state.analysisLocked -> "AI analyzing diary..."
  state.statusLights.sync == LifeLoadSyncStatus.SAVING -> "Syncing..."
  state.statusLights.sync == LifeLoadSyncStatus.DRAFT -> "Unsaved draft exists"
  else -> dayStatusLabel(state)
}

@Composable
private fun localizedLoadingOrStatusLabel(state: LifeLoadUiState): String = when {
  state.loading -> stringResource(R.string.compass_loading_day_dashboard)
  state.analysisLocked -> stringResource(R.string.compass_ai_analyzing_diary_short)
  state.statusLights.sync == LifeLoadSyncStatus.SAVING -> stringResource(R.string.compass_syncing)
  state.statusLights.sync == LifeLoadSyncStatus.DRAFT -> stringResource(R.string.compass_unsaved_draft_exists)
  else -> dayStatusLabel(state)
}

private fun systemStatusNeedsAttention(state: LifeLoadUiState): Boolean =
  state.loading ||
    state.dashboardSlowLoading ||
    state.analysisLocked ||
    state.error.isNotBlank() ||
    state.statusLights.backend == LifeLoadBackendStatus.ERROR ||
    state.statusLights.sync in setOf(LifeLoadSyncStatus.SAVING, LifeLoadSyncStatus.DRAFT, LifeLoadSyncStatus.ERROR) ||
    state.localDebug.outboxCount > 0 ||
    state.localDebug.conflictCount > 0

private fun supportLabel(value: String): String = when (value.trim()) {
  "alcohol" -> "Alcohol exposure logged; protect tomorrow morning"
  "binge" -> "Eating episode flagged recently; resume with the next normal meal"
  "sleep drift" -> "Sleep support needed"
  "garmin short sleep" -> "Garmin sleep suggests extra recovery"
  "nutrition drift" -> "Food plan support needed"
  "recovery compliance falling" -> "Recovery habits slipping"
  "recovery consistency falling" -> "Recovery consistency falling"
  "historical risk score high" -> "Recent pattern suggests higher risk"
  "risk score high" -> "Risk trend remains high"
  "relationship conflict" -> "Relationship stress logged"
  "repeated relationship conflict" -> "Relationship stress repeated today"
  "school conflict" -> "School-related conflict added load"
  "training spike from low base" -> "Training increased from a low base"
  "acute training spike" -> "Recent training load is elevated"
  "training load rising fast" -> "Training load is rising quickly"
  "chronic load ramp" -> "Longer-term load is ramping"
  "garmin high stress" -> "Garmin stress signal is high"
  "garmin elevated stress" -> "Garmin stress signal is elevated"
  "multiple hard sessions" -> "Multiple demanding sessions"
  "migraine warning" -> "Migraine signal logged"
  "pain flare" -> "Pain signal needs protection"
  "shutdown missed" -> "Shutdown support needed"
  "decompression missed" -> "Decompression support needed"
  "after-work decompression missed" -> "After-work reset was missed"
  "late phone" -> "Late phone use logged"
  "project spillover" -> "Project time ran late"
  "evening chain broken" -> "Evening sequence needs support"
  "emotional overload" -> "Emotional load is high"
  "accumulated emotional load" -> "Emotional load is accumulating"
  "alone at home trigger" -> "Alone-at-home risk context"
  "alone home food risk" -> "Alone-at-home food risk"
  "weight trend rising" -> "Weight trend is rising"
  "weight reset signal" -> "Weight reset signal"
  "missing structured data" -> "A few fields are still unknown"
  else -> value
}

@Composable
private fun localizedSupportLabel(value: String): String = when (value.trim()) {
  "alcohol" -> stringResource(R.string.legacy_support_alcohol)
  "binge" -> stringResource(R.string.legacy_support_binge)
  "sleep drift" -> stringResource(R.string.legacy_support_sleep_drift)
  "garmin short sleep" -> stringResource(R.string.legacy_support_garmin_short_sleep)
  "nutrition drift" -> stringResource(R.string.legacy_support_nutrition_drift)
  "recovery compliance falling" -> stringResource(R.string.legacy_support_recovery_compliance)
  "recovery consistency falling" -> stringResource(R.string.legacy_support_recovery_consistency)
  "historical risk score high" -> stringResource(R.string.legacy_support_historical_risk)
  "risk score high" -> stringResource(R.string.legacy_support_risk_high)
  "relationship conflict" -> stringResource(R.string.legacy_support_relationship)
  "repeated relationship conflict" -> stringResource(R.string.legacy_support_relationship_repeated)
  "school conflict" -> stringResource(R.string.legacy_support_school_conflict)
  "training spike from low base" -> stringResource(R.string.legacy_support_training_low_base)
  "acute training spike" -> stringResource(R.string.legacy_support_training_acute)
  "training load rising fast" -> stringResource(R.string.legacy_support_training_rising)
  "chronic load ramp" -> stringResource(R.string.legacy_support_chronic_ramp)
  "garmin high stress" -> stringResource(R.string.legacy_support_garmin_high_stress)
  "garmin elevated stress" -> stringResource(R.string.legacy_support_garmin_elevated_stress)
  "multiple hard sessions" -> stringResource(R.string.legacy_support_hard_sessions)
  "migraine warning" -> stringResource(R.string.legacy_support_migraine)
  "pain flare" -> stringResource(R.string.legacy_support_pain_flare)
  "shutdown missed" -> stringResource(R.string.legacy_support_shutdown)
  "decompression missed" -> stringResource(R.string.legacy_support_decompression)
  "after-work decompression missed" -> stringResource(R.string.legacy_support_after_work)
  "late phone" -> stringResource(R.string.legacy_support_late_phone)
  "project spillover" -> stringResource(R.string.legacy_support_project)
  "evening chain broken" -> stringResource(R.string.legacy_support_evening_chain)
  "emotional overload" -> stringResource(R.string.legacy_support_emotional)
  "accumulated emotional load" -> stringResource(R.string.legacy_support_emotional_accumulated)
  "alone at home trigger" -> stringResource(R.string.legacy_support_alone_home)
  "alone home food risk" -> stringResource(R.string.legacy_support_alone_food)
  "weight trend rising" -> stringResource(R.string.legacy_support_weight_rising)
  "weight reset signal" -> stringResource(R.string.legacy_support_weight_reset)
  "missing structured data" -> stringResource(R.string.legacy_support_missing_structured)
  else -> value
}

@Composable
private fun localizedSupportLabels(values: List<String>): String {
  val labels = mutableListOf<String>()
  for (value in values) {
    labels += localizedSupportLabel(value)
  }
  return labels.joinToString(", ")
}

@Composable
private fun buildDetectedFields(state: LifeLoadUiState): List<DetectedField> {
  val proposal = state.latestProposal ?: return emptyList()
  val yesText = stringResource(R.string.yes)
  val noText = stringResource(R.string.no)
  val labels = mapOf(
    "sleep_ok" to stringResource(R.string.field_sleep_label),
    "nutrition_ok" to stringResource(R.string.field_food_label),
    "alcohol" to stringResource(R.string.field_alcohol_label),
    "binge" to stringResource(R.string.field_eating_episode_label),
    "mood" to stringResource(R.string.field_mood_label),
    "stress" to stringResource(R.string.field_stress_label),
    "energy" to stringResource(R.string.field_energy_label),
    "coffee_cups" to stringResource(R.string.field_coffee_label),
    "foot_pain" to stringResource(R.string.field_foot_pain_label),
    "shoulder_pain" to stringResource(R.string.field_shoulder_pain_label),
    "phone_after_21" to stringResource(R.string.field_phone_after_21_label),
    "project_overrun" to stringResource(R.string.field_project_overrun_label),
    "shutdown_done" to stringResource(R.string.field_shutdown_label),
    "after_work_decompression_done" to stringResource(R.string.field_decompression_label),
    "evening_chain_broken" to stringResource(R.string.legacy_support_evening_chain),
    "primary_activity_type" to stringResource(R.string.field_activity_type_label),
    "activity_duration_min" to stringResource(R.string.field_movement_minutes_label),
    "rehab_done" to stringResource(R.string.field_rehab_label),
    "work_intensity" to stringResource(R.string.field_work_intensity_label),
    "alone_home" to stringResource(R.string.field_alone_home_label),
    "wife_conflict_count" to stringResource(R.string.field_relationship_tension_label),
    "wife_conflict_school" to stringResource(R.string.field_school_conflict_label),
    "wife_conflict_chores" to stringResource(R.string.field_chores_conflict_label),
    "wife_conflict_other" to stringResource(R.string.field_relationship_tension_label),
  )
  val highImpact = setOf(
    "alcohol",
    "binge",
    "sleep_ok",
    "nutrition_ok",
    "foot_pain",
    "shoulder_pain",
    "migraine_warning",
    "shutdown_done",
    "phone_after_21",
    "project_overrun",
    "stress",
    "energy",
    "coffee_cups",
    "alone_home",
    "after_work_decompression_done",
    "evening_chain_broken",
    "wife_conflict_count",
    "wife_conflict_school",
    "primary_activity_type",
    "activity_duration_min",
  )
  return proposal.fields.mapNotNull { (key, value) ->
    if (key !in highImpact) return@mapNotNull null
    val label = labels[key] ?: return@mapNotNull null
    val rendered = when (value) {
      null -> "?"
      is Boolean -> if (value) yesText else noText
      is List<*> -> value.joinToString(", ")
      else -> value.toString()
    }.ifBlank { "?" }
    DetectedField(label = label, value = rendered)
  }
}

@Composable
private fun buildNeedsAttention(state: LifeLoadUiState): List<AttentionItem> {
  val entry = state.draftEntry
  val items = mutableListOf<AttentionItem>()
  if (state.loading) items += AttentionItem(stringResource(R.string.legacy_attention_loading_title), stringResource(R.string.legacy_attention_loading_body))
  if (state.analysisLocked) items += AttentionItem(stringResource(R.string.legacy_attention_ai_title), stringResource(R.string.legacy_attention_ai_body))
  if (entry.alcohol == "home") items += AttentionItem(stringResource(R.string.legacy_attention_alcohol_title), stringResource(R.string.legacy_attention_alcohol_body), severe = true)
  if (entry.binge == true) items += AttentionItem(stringResource(R.string.legacy_attention_binge_title), stringResource(R.string.legacy_attention_binge_body), severe = false)
  if (entry.sleepOk == null) items += AttentionItem(stringResource(R.string.legacy_attention_sleep_unknown_title), stringResource(R.string.legacy_attention_sleep_unknown_body))
  if (entry.nutritionOk == null) items += AttentionItem(stringResource(R.string.legacy_attention_nutrition_unknown_title), stringResource(R.string.legacy_attention_nutrition_unknown_body))
  if (entry.shutdownDone == false) items += AttentionItem(stringResource(R.string.legacy_support_shutdown), stringResource(R.string.legacy_attention_shutdown_body))
  if (entry.afterWorkDecompressionDone == false) items += AttentionItem(stringResource(R.string.legacy_support_after_work), stringResource(R.string.legacy_attention_after_work_body))
  if (entry.eveningChainBroken == true) items += AttentionItem(stringResource(R.string.legacy_support_evening_chain), stringResource(R.string.legacy_attention_evening_body))
  if (entry.phoneAfter21 == true) items += AttentionItem(stringResource(R.string.legacy_support_late_phone), stringResource(R.string.legacy_attention_late_phone_body))
  if (entry.projectOverrun == true) items += AttentionItem(stringResource(R.string.legacy_attention_project_title), stringResource(R.string.legacy_attention_project_body))
  if (entry.aloneHome == true) items += AttentionItem(stringResource(R.string.legacy_attention_alone_title), stringResource(R.string.legacy_attention_alone_body), severe = entry.binge == true)
  if ((entry.footPain ?: 0) >= 5) items += AttentionItem(stringResource(R.string.legacy_attention_foot_title, entry.footPain ?: 0), stringResource(R.string.legacy_attention_foot_body), severe = true)
  if ((entry.shoulderPain ?: 0) >= 5) items += AttentionItem(stringResource(R.string.legacy_attention_shoulder_title, entry.shoulderPain ?: 0), stringResource(R.string.legacy_attention_shoulder_body), severe = true)
  if ((entry.stress ?: 0) >= 7) items += AttentionItem(stringResource(R.string.legacy_attention_stress_title, entry.stress ?: 0), stringResource(R.string.legacy_attention_stress_body))
  if ((entry.wifeConflictCount ?: 0) > 0) items += AttentionItem(stringResource(R.string.legacy_attention_relationship_title, entry.wifeConflictCount ?: 0), stringResource(R.string.legacy_attention_relationship_body), severe = (entry.wifeConflictCount ?: 0) >= 2)
  if (entry.migraineWarning == true) items += AttentionItem(stringResource(R.string.legacy_support_migraine), stringResource(R.string.legacy_attention_migraine_body), severe = true)
  if (entry.rehabDone == false) items += AttentionItem(stringResource(R.string.legacy_attention_rehab_title), stringResource(R.string.legacy_attention_rehab_body))
  return items
}

private fun familyStressLabel(value: Int?): String = when {
  value == null -> "?"
  value <= 3 -> "low"
  value <= 6 -> "normal"
  else -> "high"
}

private fun wifeConflictLabel(value: Int?): String = when {
  value == null || value <= 0 -> "0"
  value >= 4 -> "4+"
  else -> value.toString()
}

private fun homeworkLabel(value: Boolean?): String = when (value) {
  true -> "yes"
  false -> "no"
  null -> "?"
}

private fun dayStatusLabel(state: LifeLoadUiState): String {
  val parts = mutableListOf<String>()
  if (state.hasUnsavedChanges) parts += "Unsaved changes"
  else if (isCheckInSaved(state)) parts += "Check-in saved"
  else if (state.hasDraft) parts += "Draft"
  else parts += "Ready"
  if (state.draftUpdatedAt.isNotBlank()) parts += "updated"
  return parts.joinToString(" · ")
}

@Composable
private fun localizedDayStatusLabel(state: LifeLoadUiState): String {
  val parts = mutableListOf<String>()
  if (state.hasUnsavedChanges) parts += stringResource(R.string.check_in_status_unsaved)
  else if (isCheckInSaved(state)) parts += stringResource(R.string.legacy_status_checkin_saved)
  else if (state.hasDraft) parts += stringResource(R.string.legacy_status_draft)
  else parts += stringResource(R.string.legacy_status_ready)
  if (state.draftUpdatedAt.isNotBlank()) parts += stringResource(R.string.legacy_status_updated)
  return parts.joinToString(" · ")
}

@Composable
private fun localizedSelectedDateLabel(date: String): String {
  val parsed = runCatching { LocalDate.parse(date) }.getOrNull() ?: return date
  return parsed.format(DateTimeFormatter.ofPattern("EEEE, yyyy-MM-dd", Locale.getDefault()))
}

private fun selectedDateLabel(date: String): String {
  val parsed = runCatching { LocalDate.parse(date) }.getOrNull() ?: return date
  val day = parsed.dayOfWeek.name.lowercase().replaceFirstChar { it.titlecase() }
  return "$day, $date"
}

private fun isWeekend(date: String): Boolean {
  val day = runCatching { LocalDate.parse(date) }.getOrNull() ?: return false
  return day.dayOfWeek == DayOfWeek.SATURDAY || day.dayOfWeek == DayOfWeek.SUNDAY
}
