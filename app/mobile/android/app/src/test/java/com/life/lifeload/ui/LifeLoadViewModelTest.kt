package com.life.lifeload.ui

import android.app.Application
import com.life.lifeload.data.LifeLoadAuthSession
import com.life.lifeload.data.LifeLoadApi
import com.life.lifeload.data.LifeLoadDebugMirrorResult
import com.life.lifeload.data.LifeLoadRepository
import com.life.lifeload.domain.LifeLoadAnalyzeResult
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadDbStatus
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadGarminSettings
import com.life.lifeload.domain.LifeLoadPlatformContract
import com.life.lifeload.domain.LifeLoadExtractStatus
import com.life.lifeload.domain.LifeLoadProposal
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.LifeLoadSyncStatus
import com.life.lifeload.domain.LifeLoadWeeklyMini
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.suspendCancellableCoroutine
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

@OptIn(ExperimentalCoroutinesApi::class)
class LifeLoadViewModelTest {
  private val dispatcher = StandardTestDispatcher()

  @Before
  fun setUp() {
    Dispatchers.setMain(dispatcher)
  }

  @After
  fun tearDown() {
    Dispatchers.resetMain()
  }

  @Test
  fun defaultsToYesterdayAndLoadsEntry() = runTest(dispatcher) {
    val app = Application()
    val yesterday = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val api = FakeLifeLoadApi(date = yesterday)
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()

    assertEquals(yesterday, vm.uiState.value.selectedDate)
    assertEquals(yesterday, vm.uiState.value.draftEntry.date)
    assertTrue(api.loadedDates.contains(yesterday))
  }

  @Test
  fun initialLoadWarmsSelectedDayAndFourPreviousDaysInBackground() = runTest(dispatcher) {
    val app = Application()
    val yesterday = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1)
    val api = FakeLifeLoadApi(date = yesterday.toString())
    LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()

    val expectedDates = listOf(
      yesterday.toString(),
      yesterday.minusDays(1).toString(),
      yesterday.minusDays(2).toString(),
      yesterday.minusDays(3).toString(),
      yesterday.minusDays(4).toString(),
    )
    assertEquals(expectedDates, api.loadedDates.distinct().take(5))
  }

  @Test
  fun cachedPreviousDayIsShownImmediatelyWhileRefreshRuns() = runTest(dispatcher) {
    val app = Application()
    val yesterday = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1)
    val previous = yesterday.minusDays(1).toString()
    val api = FakeLifeLoadApi(date = yesterday.toString())
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    api.entryDelayMs = 5_000
    vm.selectPreviousDate()
    runCurrent()

    assertEquals(previous, vm.uiState.value.selectedDate)
    assertEquals(previous, vm.uiState.value.draftEntry.date)
    assertEquals(false, vm.uiState.value.loading)
    assertTrue(vm.uiState.value.message.contains("Cached day shown"))
  }

  @Test
  fun refreshResponseDoesNotOverwriteLocalDraftEdit() = runTest(dispatcher) {
    val app = Application()
    val yesterday = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1)
    val previous = yesterday.minusDays(1).toString()
    val api = FakeLifeLoadApi(date = yesterday.toString())
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    api.blockedEntryDate = previous
    api.entryGate = CompletableDeferred()
    vm.selectPreviousDate()
    runCurrent()
    vm.updateDiaryText("local edit while refresh is running")

    api.entryGate?.complete(Unit)
    advanceUntilIdle()

    assertEquals(previous, vm.uiState.value.selectedDate)
    assertEquals("local edit while refresh is running", vm.uiState.value.draftEntry.diaryText)
    assertEquals("Unsaved draft exists", vm.uiState.value.message)
  }

  @Test
  fun fieldEditUpdatesDraftOnly() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateDiaryText("worked hard and stayed up too late")
    advanceUntilIdle()

    assertEquals("worked hard and stayed up too late", vm.uiState.value.draftEntry.diaryText)
    assertEquals(null, api.lastSavedEntry)
    assertEquals("Unsaved draft exists", vm.uiState.value.message)
  }

  @Test
  fun fieldEditDoesNotResetRecentlyAddedFieldsWhenSaveResponseOmitsThem() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi(stripRecentlyAddedFieldsOnSave = true)
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateBooleanField("alone_home", true)
    advanceUntilIdle()

    assertEquals(null, api.lastSavedEntry)
    assertEquals(true, vm.uiState.value.draftEntry.aloneHome)
    assertEquals("Unsaved draft exists", vm.uiState.value.message)
  }

  @Test
  fun analyzeDiaryAppliesBackendProposal() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateDiaryText("bad sleep and videos after 21")
    advanceTimeBy(750)
    advanceUntilIdle()
    vm.analyzeDiary()

    assertEquals(LifeLoadExtractStatus.ANALYZING, vm.uiState.value.statusLights.extract)
    advanceUntilIdle()

    assertEquals("late phone", vm.uiState.value.score.redFlags.first())
    assertEquals("Detected summary", vm.uiState.value.draftEntry.diarySummary)
    assertEquals(1, api.analyzeCalls)
    assertEquals("AI analyzed the diary with gpt-5.4-mini.", vm.uiState.value.message)
    assertEquals(LifeLoadExtractStatus.IDLE, vm.uiState.value.statusLights.extract)
  }

  @Test
  fun approveCallsRepositoryAndKeepsDraftOnFailure() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi(approveError = RuntimeException("approve failed"))
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateDiaryText("rough day but no alcohol")
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(1, api.approveCalls)
    assertEquals("rough day but no alcohol", api.lastSavedEntry?.diaryText)
    assertEquals("rough day but no alcohol", vm.uiState.value.draftEntry.diaryText)
    assertTrue(vm.uiState.value.error.contains("approve failed"))
  }

  @Test
  fun approveCommitsEntryBeforeBackgroundGarminRefresh() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateSettings(garminConfiguredSettings())
    vm.updateDiaryText("normal day")
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(listOf("save:${vm.uiState.value.selectedDate}", "approve:${vm.uiState.value.selectedDate}", "garmin:${vm.uiState.value.selectedDate}:1"), api.writeOrder)
    assertTrue(vm.uiState.value.message.contains("Garmin imported"))
  }

  @Test
  fun approveStillCommitsWhenGarminImportFails() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi(garminError = RuntimeException("token expired"))
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateSettings(garminConfiguredSettings())
    vm.updateBooleanField("sleep_ok", true)
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(1, api.garminImportCalls)
    assertEquals(1, api.approveCalls)
    assertTrue(vm.uiState.value.message.contains("Garmin import skipped"))
  }

  @Test
  fun approveShowsSavedStateBeforeSlowGarminRefreshCompletes() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateSettings(garminConfiguredSettings())
    api.holdGarmin = true
    vm.updateDiaryText("timer should save before Garmin")
    vm.approveEntry()
    runCurrent()

    assertEquals(1, api.approveCalls)
    assertEquals(1, api.garminImportCalls)
    assertEquals("approved", vm.uiState.value.entryState)
    assertEquals(LifeLoadSyncStatus.SAVED, vm.uiState.value.statusLights.sync)
    assertTrue(vm.uiState.value.message.contains("Check-in saved"))
    assertTrue(
      "Garmin import should still be waiting after saved state applies",
      api.garminWaiting,
    )

    api.releaseGarmin()
    advanceUntilIdle()

    assertEquals("approved", vm.uiState.value.entryState)
    assertTrue(vm.uiState.value.message.contains("Garmin imported"))
  }

  @Test
  fun approveDoesNotImportGarminWithoutConfiguredCredentials() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateDiaryText("no Garmin account configured")
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(1, api.approveCalls)
    assertEquals(0, api.garminImportCalls)
    assertEquals(listOf("save:${vm.uiState.value.selectedDate}", "approve:${vm.uiState.value.selectedDate}"), api.writeOrder)
  }

  @Test
  fun approveDoesNotImportGarminWhenEnabledButMissingPassword() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateSettings(
      LifeLoadSettings(
        garmin = LifeLoadGarminSettings(
          enabled = true,
          email = "garmin@example.test",
          passwordSet = false,
          autoImport = true,
        ),
      ),
    )
    vm.updateDiaryText("Garmin toggle on but no saved password")
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(1, api.approveCalls)
    assertEquals(0, api.garminImportCalls)
    assertEquals(listOf("save:${vm.uiState.value.selectedDate}", "approve:${vm.uiState.value.selectedDate}"), api.writeOrder)
  }

  @Test
  fun approvePersistsManualEditsBeforeCommit() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateDiaryText("diary says no alcohol but extracted state was wrong")
    vm.updateStringField("alcohol", "none")
    vm.updateBooleanField("nutrition_ok", true)
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals("none", api.lastSavedEntry?.alcohol)
    assertEquals(true, api.lastSavedEntry?.nutritionOk)
    assertEquals(1, api.approveCalls)
    assertEquals("none", vm.uiState.value.entry.alcohol)
    assertEquals(true, vm.uiState.value.entry.nutritionOk)
  }

  @Test
  fun approveAllowsStructuredOnlyEntryWithoutDiaryText() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateBooleanField("sleep_ok", true)
    vm.updateIntField("coffee_cups", 3)
    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(1, api.approveCalls)
    assertEquals("", api.lastSavedEntry?.diaryText)
    assertEquals(true, api.lastSavedEntry?.sleepOk)
    assertEquals(3, api.lastSavedEntry?.coffeeCups)
  }

  @Test
  fun approveShowsSavedStateBeforeSlowDashboardRefreshCompletes() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    api.holdDashboard = true
    vm.updateDiaryText("save should feel immediate")
    vm.approveEntry()
    runCurrent()

    assertEquals(1, api.approveCalls)
    assertEquals("approved", vm.uiState.value.entryState)
    assertEquals(LifeLoadSyncStatus.SAVED, vm.uiState.value.statusLights.sync)
    assertTrue(vm.uiState.value.message.contains("Check-in saved"))
    assertTrue(
      "dashboard refresh should still be waiting after saved state applies",
      api.loadedDashboardDates.size >= 2,
    )

    api.releaseDashboard()
    advanceUntilIdle()

    assertEquals("approved", vm.uiState.value.entryState)
    assertTrue(vm.uiState.value.message.contains("Check-in saved"))
  }

  @Test
  fun profileSwitchClearsInactiveDraftFieldsAndIgnoresLaterHiddenEdits() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateStringField("alcohol", "home")
    vm.updateBooleanField("binge", true)
    vm.updateStringField("activity_types", "run")
    vm.updateIntField("foot_pain", 7)
    vm.updateIntField("shoulder_pain", 6)
    vm.updateIntField("coffee_cups", 4)
    vm.updateIntField("stress", 8)

    vm.selectProfile("general_balance")
    vm.updateStringField("alcohol", "social")
    vm.updateIntField("foot_pain", 9)
    vm.updateStringField("activity_types", "crossfit")
    vm.updateBooleanField("shutdown_done", true)

    val draft = vm.uiState.value.draftEntry
    assertEquals(null, draft.alcohol)
    assertEquals(null, draft.binge)
    assertEquals("", draft.primaryActivityType)
    assertEquals(emptyList<String>(), draft.activityTypes)
    assertEquals(null, draft.footPain)
    assertEquals(null, draft.shoulderPain)
    assertEquals(null, draft.coffeeCups)
    assertEquals(8, draft.stress)
    assertEquals(true, draft.shutdownDone)
  }

  @Test
  fun approveAndAnalyzeSendOnlyFieldsActiveForSelectedProfile() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    vm.updateStringField("alcohol", "home")
    vm.updateIntField("foot_pain", 7)
    vm.updateBooleanField("phone_after_21", true)
    vm.updateIntField("stress", 7)
    vm.updateDiaryText("stressful day")
    vm.selectProfile("general_balance")

    vm.approveEntry()
    advanceUntilIdle()

    assertEquals(null, api.lastSavedEntry?.alcohol)
    assertEquals(null, api.lastSavedEntry?.footPain)
    assertEquals(null, api.lastSavedEntry?.phoneAfter21)
    assertEquals(7, api.lastSavedEntry?.stress)

    vm.analyzeDiary()
    advanceUntilIdle()

    assertEquals(null, api.lastAnalyzedEntry?.alcohol)
    assertEquals(null, api.lastAnalyzedEntry?.footPain)
    assertEquals(null, api.lastAnalyzedEntry?.phoneAfter21)
    assertEquals(null, vm.uiState.value.draftEntry.phoneAfter21)
  }

  @Test
  fun weekendDefaultsHomeworkToNotApplicable() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    var attempts = 0
    while (
      attempts < 7 &&
      vm.uiState.value.currentDate.dayOfWeek != java.time.DayOfWeek.SATURDAY &&
      vm.uiState.value.currentDate.dayOfWeek != java.time.DayOfWeek.SUNDAY
    ) {
      vm.selectPreviousDate()
      advanceUntilIdle()
      attempts += 1
    }

    assertEquals("na", vm.uiState.value.draftEntry.homeworkStatus)
  }

  @Test
  fun dateLoadAppliesEntryBeforeDashboardCompletes() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi(holdDashboard = true)
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    runCurrent()

    assertEquals(false, vm.uiState.value.loading)
    assertTrue("dashboard should still be loading after entry applies: ${vm.uiState.value}", vm.uiState.value.dashboardLoading)
    assertEquals(false, vm.uiState.value.dashboardSlowLoading)
    assertEquals("draft", vm.uiState.value.entryState)

    advanceTimeBy(1_200)
    runCurrent()

    assertEquals(true, vm.uiState.value.dashboardSlowLoading)

    api.releaseDashboard()
    advanceUntilIdle()

    assertEquals(false, vm.uiState.value.dashboardLoading)
    assertEquals(false, vm.uiState.value.dashboardSlowLoading)
    assertEquals("yellow", vm.uiState.value.dashboard.weekly.zone)
  }

  @Test
  fun dateNavigationReloadsDashboardForSelectedDate() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi()
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()
    val initialDashboardDate = api.loadedDashboardDates.single()

    vm.selectPreviousDate()
    advanceUntilIdle()

    val selectedDate = vm.uiState.value.selectedDate
    assertEquals(
      listOf(initialDashboardDate, selectedDate),
      api.loadedDashboardDates.distinct().take(2),
    )
    assertEquals(false, vm.uiState.value.dashboardLoading)
    assertTrue(api.loadedDates.size >= 2)
  }

  @Test
  fun dashboardFailureAfterEntryLoadDoesNotMarkDatabaseError() = runTest(dispatcher) {
    val app = Application()
    val api = FakeLifeLoadApi(dashboardError = RuntimeException("timeout"))
    val vm = LifeLoadViewModel(app, repository = LifeLoadRepository(api), initialAuthSession = LifeLoadAuthSession(sessionToken = "test-session"))

    advanceUntilIdle()

    assertEquals(false, vm.uiState.value.loading)
    assertEquals(false, vm.uiState.value.dashboardLoading)
    assertEquals("draft", vm.uiState.value.entryState)
    assertEquals(LifeLoadDbStatus.READY, vm.uiState.value.statusLights.db)
    assertTrue(vm.uiState.value.error.contains("Dashboard needs attention"))
    assertTrue(vm.uiState.value.error.contains("timeout"))
  }
}

private class FakeLifeLoadApi(
  private val date: String = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString(),
  private val dashboardDelayMs: Long = 0,
  var holdDashboard: Boolean = false,
  private val stripRecentlyAddedFieldsOnSave: Boolean = false,
  private val settingsError: Throwable? = RuntimeException("settings unavailable in plain unit test"),
  private val dashboardError: Throwable? = null,
  private val approveError: Throwable? = null,
  private val garminError: Throwable? = null,
) : LifeLoadApi {
  val loadedDates = mutableListOf<String>()
  val loadedDashboardDates = mutableListOf<String>()
  val writeOrder = mutableListOf<String>()
  var lastSavedEntry: LifeLoadEntry? = null
  var entryDelayMs: Long = 0
  var blockedEntryDate: String? = null
  var entryGate: CompletableDeferred<Unit>? = null
  private var dashboardContinuation: CancellableContinuation<Unit>? = null
  var holdGarmin: Boolean = false
  var garminWaiting: Boolean = false
  private var garminContinuation: CancellableContinuation<Unit>? = null
  var analyzeCalls = 0
  var approveCalls = 0
  var garminImportCalls = 0
  var savedSettings: LifeLoadSettings = LifeLoadSettings()
  var lastAnalyzedEntry: LifeLoadEntry? = null

  private fun entryPayload(
    entry: LifeLoadEntry,
    state: String = "draft",
    approvedAt: String = "",
    draftUpdatedAt: String = "2026-05-03T12:00:00Z",
  ): LifeLoadEntryPayload = LifeLoadEntryPayload(
    date = entry.date,
    defaultDate = date,
    previousDate = LocalDate.parse(entry.date).minusDays(1).toString(),
    nextDate = LocalDate.parse(entry.date).plusDays(1).toString(),
    entryState = state,
    hasDraft = state == "draft" || state == "pending_approval",
    entryExists = true,
    approvedAt = approvedAt,
    draftUpdatedAt = draftUpdatedAt,
    entry = entry,
    draftEntry = if (state == "approved") LifeLoadEntry(date = entry.date) else entry,
    approvedEntry = if (state == "approved") entry else null,
    score = LifeLoadScore(zone = "yellow", nextAction = "Keep shutdown boring.", redFlags = emptyList()),
    latestProposal = null,
  )

  override suspend fun isBackendHealthy(): Boolean = true

  override suspend fun register(email: String, password: String): LifeLoadAuthSession =
    LifeLoadAuthSession(email = email, userId = "usr_test", deviceId = "dev_test", sessionToken = "session_test")

  override suspend fun login(email: String, password: String): LifeLoadAuthSession =
    LifeLoadAuthSession(email = email, userId = "usr_test", deviceId = "dev_test", sessionToken = "session_test")

  override suspend fun logout() = Unit

  override suspend fun getContract(): LifeLoadPlatformContract = LifeLoadPlatformContract()

  override suspend fun getSettings(): LifeLoadSettings {
    settingsError?.let { throw it }
    return savedSettings
  }

  override suspend fun saveSettings(settings: LifeLoadSettings, garminPassword: String): LifeLoadSettings {
    savedSettings = settings.copy(garmin = settings.garmin.copy(passwordSet = garminPassword.isNotBlank() || settings.garmin.passwordSet))
    return savedSettings
  }

  override suspend fun getEntry(date: String): LifeLoadEntryPayload {
    loadedDates += date
    if (date == blockedEntryDate) entryGate?.await()
    if (entryDelayMs > 0) delay(entryDelayMs)
    return entryPayload(LifeLoadEntry(date = date))
  }

  override suspend fun saveEntry(entry: LifeLoadEntry, action: String): LifeLoadEntryPayload {
    writeOrder += "save:${entry.date}"
    lastSavedEntry = entry
    return entryPayload(
      if (stripRecentlyAddedFieldsOnSave) {
        entry.copy(
          afterWorkDecompressionDone = null,
          eveningChainBroken = null,
          wifeConflictCount = null,
          wifeConflictSchool = null,
          wifeConflictChores = null,
          wifeConflictOther = null,
          aloneHome = null,
        )
      } else {
        entry
      },
    )
  }

  override suspend fun analyzeDiary(entry: LifeLoadEntry): LifeLoadAnalyzeResult {
    analyzeCalls += 1
    lastAnalyzedEntry = entry
    val analyzed = entry.copy(
      diarySummary = "Detected summary",
      phoneAfter21 = true,
      stress = 7,
    )
    return LifeLoadAnalyzeResult(
      payload = LifeLoadEntryPayload(
        date = entry.date,
        defaultDate = date,
        previousDate = LocalDate.parse(entry.date).minusDays(1).toString(),
        nextDate = LocalDate.parse(entry.date).plusDays(1).toString(),
        entryState = "draft",
        hasDraft = true,
        entryExists = true,
        approvedAt = "",
        draftUpdatedAt = "2026-05-03T12:05:00Z",
        entry = analyzed,
        draftEntry = analyzed,
        approvedEntry = null,
        score = LifeLoadScore(
          zone = "yellow",
          nextAction = "Protect shutdown tonight.",
          redFlags = listOf("late phone"),
        ),
        latestProposal = LifeLoadProposal(summary = "Detected summary"),
      ),
      proposal = LifeLoadProposal(summary = "Detected summary"),
      extractorVersion = "codex_diary_v0_1",
      extractorModel = "gpt-5.4-mini",
      extractorTimeoutS = 30,
    )
  }

  override suspend fun approveEntry(entry: LifeLoadEntry): LifeLoadEntryPayload {
    approveCalls += 1
    writeOrder += "approve:${entry.date}"
    approveError?.let { throw it }
    return entryPayload(entry, state = "approved", approvedAt = "2026-05-03T20:00:00Z", draftUpdatedAt = "")
  }

  override suspend fun importGarmin(date: String, days: Int): com.life.lifeload.domain.LifeLoadGarminImportResult {
    garminImportCalls += 1
    writeOrder += "garmin:$date:$days"
    garminError?.let { throw it }
    if (holdGarmin) {
      suspendCancellableCoroutine { continuation ->
        garminWaiting = true
        garminContinuation = continuation
      }
    }
    return com.life.lifeload.domain.LifeLoadGarminImportResult(
      payload = entryPayload(LifeLoadEntry(date = date)),
      daysImported = days,
      passiveUpserted = days,
      activityUpserted = 2,
    )
  }

  override suspend fun getDashboard(date: String, weeks: Int): LifeLoadDashboard {
    loadedDashboardDates += date
    dashboardError?.let { throw it }
    if (holdDashboard) {
      suspendCancellableCoroutine { continuation ->
        dashboardContinuation = continuation
      }
    }
    if (dashboardDelayMs > 0) delay(dashboardDelayMs)
    return LifeLoadDashboard(
      date = date,
      dbRoot = "/tmp/health.sqlite",
      weekly = LifeLoadWeeklyMini(
        zone = "yellow",
        nextAction = "Protect shutdown tonight.",
        sleepCompleted = 4,
        sleepTarget = 7,
        nutritionCompleted = 5,
        nutritionTarget = 7,
        hardSessions = 2,
        redFlagCount = 1,
      ),
    )
  }

  fun releaseDashboard() {
    dashboardContinuation?.resumeWith(Result.success(Unit))
    dashboardContinuation = null
  }

  fun releaseGarmin() {
    garminWaiting = false
    garminContinuation?.resumeWith(Result.success(Unit))
    garminContinuation = null
  }

  override suspend fun mirrorLocalDebugBundle(bundleJson: String): LifeLoadDebugMirrorResult =
    LifeLoadDebugMirrorResult(
      path = "runtime/mobile_debug_mirror/life_load_android_local_debug_bundle_v1_redacted.json",
      entryCount = 0,
      pendingOutboxCount = 0,
      conflictOutboxCount = 0,
    )
}

private fun garminConfiguredSettings(): LifeLoadSettings = LifeLoadSettings(
  garmin = LifeLoadGarminSettings(
    enabled = true,
    email = "garmin@example.test",
    passwordSet = true,
    autoImport = true,
  ),
)
