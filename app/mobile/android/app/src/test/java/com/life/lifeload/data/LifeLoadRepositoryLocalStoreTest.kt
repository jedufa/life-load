package com.life.lifeload.data

import androidx.test.core.app.ApplicationProvider
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.domain.LifeLoadAnalyzeResult
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadGarminImportResult
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadPlatformContract
import com.life.lifeload.domain.LifeLoadProposal
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.domain.LifeLoadSettings
import org.json.JSONObject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Locale

@Config(sdk = [34])
@RunWith(RobolectricTestRunner::class)
class LifeLoadRepositoryLocalStoreTest {
  private val stores = mutableListOf<LifeLoadLocalStore>()

  @After
  fun tearDown() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    stores.forEach { store ->
      store.close()
      context.deleteDatabase(store.databaseName)
    }
  }

  @Test
  fun importRecentHistorySeedsLocalStoreFromBackendPayload() = runTest {
    val store = localStore("repo_seed.db")
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    repository.importRecentHistory("2026-05-06", days = 1)

    val record = store.getEntry("2026-05-06")
    assertNotNull(record)
    assertEquals("server", record?.source)
    assertEquals("backend day 2026-05-06", record?.entry?.diaryText)
  }

  @Test
  fun loadEntryFallsBackToLocalStoreWhenBackendIsUnavailable() = runTest {
    val store = localStore("repo_read_fallback.db")
    val repositoryWithBackend = LifeLoadRepository(RepositoryFakeApi(), localStore = store)
    repositoryWithBackend.importRecentHistory("2026-05-06", days = 1)
    val repositoryOffline = LifeLoadRepository(RepositoryFakeApi(loadError = RuntimeException("offline")), localStore = store)

    val payload = repositoryOffline.loadEntry("2026-05-06")

    assertEquals("approved", payload.entryState)
    assertEquals("backend day 2026-05-06", payload.approvedEntry?.diaryText)
    assertEquals("green", payload.score.zone)
  }

  @Test
  fun loadEntryReturnsBlankLocalDayWhenOfflineAndNoServerOrLocalRowExists() = runTest {
    val store = localStore("repo_offline_blank.db")
    val repository = LifeLoadRepository(RepositoryFakeApi(loadError = RuntimeException("offline")), localStore = store)

    val payload = repository.loadEntry("2026-05-06")

    assertEquals("blank", payload.entryState)
    assertEquals(false, payload.entryExists)
    assertEquals("2026-05-06", payload.draftEntry.date)
    assertEquals(0, store.status().entryCount)
  }

  @Test
  fun saveDraftFallsBackToLocalStoreAndQueuesOutbox() = runTest {
    val store = localStore("repo_draft_fallback.db")
    val repository = LifeLoadRepository(RepositoryFakeApi(saveError = RuntimeException("offline")), localStore = store)

    val payload = repository.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "offline draft"))

    assertEquals("draft", payload.entryState)
    assertEquals("offline draft", payload.draftEntry.diaryText)
    assertEquals("draft_upsert", store.pendingOutbox().single().operation)
  }

  @Test
  fun saveDraftUsesPhoneStoreFirstEvenWhenBackendIsAvailable() = runTest {
    val store = localStore("repo_draft_local_first.db")
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    val payload = repository.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "local first draft"))

    assertEquals("draft", payload.entryState)
    assertEquals("local first draft", store.getEntry("2026-05-06")?.entry?.diaryText)
    assertEquals("draft_upsert", store.pendingOutbox().single().operation)
    assertEquals(emptyList<String>(), api.writeOrder)
  }

  @Test
  fun approveFallsBackToLocalStoreAndQueuesApprovalOutbox() = runTest {
    val store = localStore("repo_approve_fallback.db")
    val repository = LifeLoadRepository(RepositoryFakeApi(approveError = RuntimeException("offline")), localStore = store)

    val payload = repository.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "offline approval"))

    assertEquals("pending_approval", payload.entryState)
    assertEquals(true, payload.hasDraft)
    assertEquals("", payload.approvedAt)
    assertEquals("offline approval", payload.draftEntry.diaryText)
    assertEquals(null, payload.approvedEntry)
    assertEquals("approve", store.pendingOutbox().single().operation)
  }

  @Test
  fun loadDashboardIncludesRecentLocalPendingApprovals() = runTest {
    val store = localStore("repo_dashboard_local_pending.db")
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "local pending one"))
    store.approve(LifeLoadEntry(date = "2026-05-07", diaryText = "local pending two"))
    val repository = LifeLoadRepository(RepositoryFakeApi(), localStore = store)

    val dashboard = repository.loadDashboard("2026-05-08")

    val localDays = dashboard.historyDays.filter { it.date in setOf("2026-05-06", "2026-05-07") }
    assertEquals(listOf("2026-05-07", "2026-05-06"), localDays.map { it.date })
    assertEquals(listOf("pending_approval", "pending_approval"), localDays.map { it.state })
    assertEquals(listOf(true, true), localDays.map { it.canonicalCompleted })
    assertEquals(listOf("local pending two", "local pending one"), localDays.map { it.diarySummary })
  }

  @Test
  fun loadDashboardPrefersNewerLocalSavedRowOverBackendHistorySameDate() = runTest {
    val store = localStore("repo_dashboard_local_override.db")
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "new local approval"))
    val repository = LifeLoadRepository(
      RepositoryFakeApi(
        dashboardHistoryDays = listOf(
          LifeLoadHistoryDay(date = "2026-05-06", state = "approved", diarySummary = "stale backend approval"),
        ),
      ),
      localStore = store,
    )

    val day = repository.loadDashboard("2026-05-06").historyDays.first { it.date == "2026-05-06" }

    assertEquals("pending_approval", day.state)
    assertEquals("new local approval", day.diarySummary)
  }

  @Test
  fun loadDashboardUsesLocalSavedRowsWhenBackendDashboardFails() = runTest {
    val store = localStore("repo_dashboard_local_when_offline.db")
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "offline local one"))
    store.approve(LifeLoadEntry(date = "2026-05-07", diaryText = "offline local two"))
    store.approve(LifeLoadEntry(date = "2026-05-08", diaryText = "offline local three"))
    val repository = LifeLoadRepository(
      RepositoryFakeApi(dashboardError = RuntimeException("dashboard offline")),
      localStore = store,
    )

    val dashboard = repository.loadDashboard("2026-05-08")

    assertEquals(listOf("2026-05-08", "2026-05-07", "2026-05-06"), dashboard.historyDays.map { it.date })
    assertEquals(listOf("pending_approval", "pending_approval", "pending_approval"), dashboard.historyDays.map { it.state })
  }

  @Test
  fun loadLocalDashboardIncludesRecentPendingApprovalsWithoutBackendSession() = runTest {
    val store = localStore("repo_local_dashboard_signed_out.db")
    store.approve(LifeLoadEntry(date = "2026-05-05", diaryText = "local pending one"))
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "local pending two"))
    store.approve(LifeLoadEntry(date = "2026-05-07", diaryText = "local pending three"))
    store.approve(LifeLoadEntry(date = "2026-05-08", diaryText = "local pending four"))
    val repository = LifeLoadRepository(RepositoryFakeApi(dashboardError = RuntimeException("auth required")), localStore = store)

    val dashboard = repository.loadLocalDashboard("2026-05-08")

    assertEquals(listOf("2026-05-08", "2026-05-07", "2026-05-06", "2026-05-05"), dashboard.historyDays.map { it.date })
    assertEquals(listOf("pending_approval", "pending_approval", "pending_approval", "pending_approval"), dashboard.historyDays.map { it.state })
    assertEquals(listOf(true, true, true, true), dashboard.historyDays.map { it.canonicalCompleted })
  }

  @Test
  fun restoreImportDoesNotOverwriteNewerPendingLocalChange() = runTest {
    val store = localStore("repo_restore_pending_preserved.db")
    store.approve(LifeLoadEntry(date = "2026-05-07", diaryText = "new local approval"))
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    val result = repository.importRecentHistory(anchorDate = "2026-05-08", days = 2)

    assertEquals(2, result.imported)
    assertEquals("new local approval", store.getEntry("2026-05-07")?.entry?.diaryText)
    assertEquals("pending_approval", store.getEntry("2026-05-07")?.state)
    assertEquals("backend day 2026-05-08", store.getEntry("2026-05-08")?.entry?.diaryText)
  }

  @Test
  fun repositoryDoesNotFallbackOnCancellation() = runTest {
    val store = localStore("repo_cancel.db")
    val repository = LifeLoadRepository(RepositoryFakeApi(loadError = CancellationException("cancelled")), localStore = store)

    try {
      repository.importRecentHistory("2026-05-06", days = 1)
      fail("Expected cancellation to be rethrown")
    } catch (error: CancellationException) {
      assertEquals("cancelled", error.message)
    }

    assertEquals(0, store.status().entryCount)
    assertEquals(0, store.status().pendingOutboxCount)
  }

  @Test
  fun importRecentHistorySeedsLocalWindowFromBackend() = runTest {
    val store = localStore("repo_import_history.db")
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    val result = repository.importRecentHistory(anchorDate = "2026-05-08", days = 3)

    assertEquals(3, result.requested)
    assertEquals(3, result.imported)
    assertEquals(0, result.failed)
    assertEquals(listOf("2026-05-08", "2026-05-07", "2026-05-06"), api.loadedDates)
    assertEquals(3, store.status().entryCount)
    assertEquals("backend day 2026-05-07", store.getEntry("2026-05-07")?.entry?.diaryText)
  }

  @Test
  fun importRecentHistoryReportsPartialFailuresWithoutErasingImportedRows() = runTest {
    val store = localStore("repo_import_history_partial.db")
    val repository = LifeLoadRepository(
      RepositoryFakeApi(loadFailures = setOf("2026-05-07")),
      localStore = store,
    )

    val result = repository.importRecentHistory(anchorDate = "2026-05-08", days = 3)

    assertEquals(3, result.requested)
    assertEquals(2, result.imported)
    assertEquals(1, result.failed)
    assertEquals(listOf("2026-05-07"), result.failures)
    assertEquals(2, store.status().entryCount)
    assertNotNull(store.getEntry("2026-05-08"))
    assertNotNull(store.getEntry("2026-05-06"))
    assertEquals(null, store.getEntry("2026-05-07"))
  }

  @Test
  fun syncPendingOutboxUploadsDraftAndMarksRowUploaded() = runTest {
    val store = localStore("repo_sync_draft.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "offline draft"))
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    val result = repository.syncPendingOutbox()

    assertEquals(1, result.attempted)
    assertEquals(1, result.uploaded)
    assertEquals(0, result.failed)
    assertEquals(0, result.conflicts)
    assertEquals(0, store.status().pendingOutboxCount)
    assertEquals("server", store.getEntry("2026-05-06")?.source)
    assertEquals(listOf("save:2026-05-06:draft"), api.writeOrder)
  }

  @Test
  fun syncPendingApprovalSavesDraftBeforeApproveAndMarksUploaded() = runTest {
    val store = localStore("repo_sync_approve.db")
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "offline approval"))
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    val result = repository.syncPendingOutbox()

    assertEquals(1, result.attempted)
    assertEquals(1, result.uploaded)
    assertEquals(0, result.failed)
    assertEquals(0, store.status().pendingOutboxCount)
    assertEquals("approved", store.getEntry("2026-05-06")?.state)
    assertEquals("server", store.getEntry("2026-05-06")?.source)
    assertEquals(listOf("save:2026-05-06:draft", "approve:2026-05-06"), api.writeOrder)
  }

  @Test
  fun syncPendingOutboxKeepsLocalTruthWhenServerResponseConflicts() = runTest {
    val store = localStore("repo_sync_conflict.db")
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "offline approval"))
    val repository = LifeLoadRepository(
      RepositoryFakeApi(conflictingApproveResponse = true),
      localStore = store,
    )

    val result = repository.syncPendingOutbox()

    assertEquals(1, result.attempted)
    assertEquals(0, result.uploaded)
    assertEquals(0, result.failed)
    assertEquals(1, result.conflicts)
    assertEquals(0, store.status().pendingOutboxCount)
    assertEquals(1, store.status().conflictOutboxCount)
    assertEquals("pending_approval", store.getEntry("2026-05-06")?.state)
    assertEquals("offline approval", store.getEntry("2026-05-06")?.entry?.diaryText)
  }

  @Test
  fun mirrorRedactedLocalDebugBundleSendsOnlyRedactedBundle() = runTest {
    val store = localStore("repo_mirror_redacted.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "private mirror text"))
    val api = RepositoryFakeApi()
    val repository = LifeLoadRepository(api, localStore = store)

    val result = repository.mirrorRedactedLocalDebugBundle()

    assertEquals("runtime/mobile_debug_mirror/life_load_android_local_debug_bundle_v1_redacted.json", result.path)
    assertEquals(1, result.entryCount)
    val mirrored = api.mirroredBundle ?: error("expected mirror bundle")
    assertEquals("redacted", mirrored.getString("redaction"))
    assertTrue(!mirrored.toString().contains("private mirror text"))
  }

  @Test
  fun localBackupBundleExportAndImportRoundTripsLocalStore() {
    val source = localStore("repo_export_source.db")
    source.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "portable backup draft"))
    val sourceRepository = LifeLoadRepository(RepositoryFakeApi(), localStore = source)

    val exported = sourceRepository.exportLocalDataBundle()
    val target = localStore("repo_export_target.db")
    val targetRepository = LifeLoadRepository(RepositoryFakeApi(), localStore = target)
    val status = targetRepository.importLocalDataBundle(exported.bundleJson)

    assertEquals(1, exported.entryCount)
    assertEquals(1, exported.outboxCount)
    assertEquals(1, status.entryCount)
    assertEquals(1, status.pendingOutboxCount)
    assertEquals("portable backup draft", target.getEntry("2026-05-06")?.entry?.diaryText)
    assertEquals("draft_upsert", target.pendingOutbox().single().operation)
  }

  @Test
  fun importRecentHistoryUsesIsoDateMathAcrossLocaleAndDstBoundary() = runTest {
    val originalLocale = Locale.getDefault()
    Locale.setDefault(Locale.GERMANY)
    try {
      val store = localStore("repo_import_history_locale_dst.db")
      val api = RepositoryFakeApi()
      val repository = LifeLoadRepository(api, localStore = store)

      val result = repository.importRecentHistory(anchorDate = "2026-03-30", days = 3)
      val offlinePayload = LifeLoadRepository(
        RepositoryFakeApi(loadError = RuntimeException("offline")),
        localStore = store,
      ).loadEntry("2026-03-29")

      assertEquals(3, result.imported)
      assertEquals(listOf("2026-03-30", "2026-03-29", "2026-03-28"), api.loadedDates)
      assertEquals("2026-03-28", offlinePayload.previousDate)
      assertEquals("2026-03-30", offlinePayload.nextDate)
      assertEquals("backend day 2026-03-29", offlinePayload.approvedEntry?.diaryText)
    } finally {
      Locale.setDefault(originalLocale)
    }
  }

  private fun localStore(name: String): LifeLoadLocalStore {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    context.deleteDatabase(name)
    return LifeLoadLocalStore(context, name).also { stores += it }
  }
}

private class RepositoryFakeApi(
  private val loadError: Throwable? = null,
  private val loadFailures: Set<String> = emptySet(),
  private val saveError: Throwable? = null,
  private val approveError: Throwable? = null,
  private val conflictingApproveResponse: Boolean = false,
  private val dashboardHistoryDays: List<LifeLoadHistoryDay> = emptyList(),
  private val dashboardError: Throwable? = null,
) : LifeLoadApi {
  val loadedDates = mutableListOf<String>()
  val writeOrder = mutableListOf<String>()
  var mirroredBundle: JSONObject? = null

  override suspend fun isBackendHealthy(): Boolean = true

  override suspend fun register(email: String, password: String): LifeLoadAuthSession =
    LifeLoadAuthSession(email = email, userId = "usr_test", deviceId = "dev_test", sessionToken = "session_test")

  override suspend fun login(email: String, password: String): LifeLoadAuthSession =
    LifeLoadAuthSession(email = email, userId = "usr_test", deviceId = "dev_test", sessionToken = "session_test")

  override suspend fun logout() = Unit

  override suspend fun getContract(): LifeLoadPlatformContract = LifeLoadPlatformContract()

  override suspend fun getSettings(): LifeLoadSettings = LifeLoadSettings()

  override suspend fun saveSettings(settings: LifeLoadSettings, garminPassword: String): LifeLoadSettings = settings

  override suspend fun getEntry(date: String): LifeLoadEntryPayload {
    loadedDates += date
    loadError?.let { throw it }
    if (date in loadFailures) throw RuntimeException("offline for $date")
    return payload(
      date = date,
      state = "approved",
      entry = LifeLoadEntry(date = date, diaryText = "backend day $date", energy = 7),
      approved = true,
    )
  }

  override suspend fun saveEntry(entry: LifeLoadEntry, action: String): LifeLoadEntryPayload {
    saveError?.let { throw it }
    writeOrder += "save:${entry.date}:$action"
    return payload(date = entry.date, state = "draft", entry = entry, approved = false)
  }

  override suspend fun approveEntry(entry: LifeLoadEntry): LifeLoadEntryPayload {
    approveError?.let { throw it }
    writeOrder += "approve:${entry.date}"
    val returned = if (conflictingApproveResponse) entry.copy(diaryText = "server conflicting approval") else entry
    return payload(date = entry.date, state = "approved", entry = returned, approved = true)
  }

  override suspend fun analyzeDiary(entry: LifeLoadEntry): LifeLoadAnalyzeResult =
    LifeLoadAnalyzeResult(payload = payload(entry.date, "draft", entry, approved = false), proposal = LifeLoadProposal())

  override suspend fun importGarmin(date: String, days: Int): LifeLoadGarminImportResult = LifeLoadGarminImportResult(payload = null)

  override suspend fun getDashboard(date: String, weeks: Int): LifeLoadDashboard =
    dashboardError?.let { throw it } ?: LifeLoadDashboard(date = date, historyDays = dashboardHistoryDays)

  override suspend fun mirrorLocalDebugBundle(bundleJson: String): LifeLoadDebugMirrorResult {
    mirroredBundle = JSONObject(bundleJson)
    return LifeLoadDebugMirrorResult(
      path = "runtime/mobile_debug_mirror/life_load_android_local_debug_bundle_v1_redacted.json",
      entryCount = mirroredBundle?.optJSONObject("status")?.optInt("entry_count") ?: 0,
      pendingOutboxCount = mirroredBundle?.optJSONObject("status")?.optInt("pending_outbox_count") ?: 0,
      conflictOutboxCount = mirroredBundle?.optJSONObject("status")?.optInt("conflict_outbox_count") ?: 0,
    )
  }

  private fun payload(date: String, state: String, entry: LifeLoadEntry, approved: Boolean): LifeLoadEntryPayload =
    LifeLoadEntryPayload(
      date = date,
      defaultDate = date,
      previousDate = "2026-05-05",
      nextDate = "2026-05-07",
      entryState = state,
      hasDraft = !approved,
      entryExists = true,
      approvedAt = if (approved) "2026-05-06T18:00:00Z" else "",
      draftUpdatedAt = if (approved) "" else "2026-05-06T17:00:00Z",
      entry = entry,
      draftEntry = if (approved) LifeLoadEntry(date = date) else entry,
      approvedEntry = if (approved) entry else null,
      score = LifeLoadScore(zone = "green", nextAction = "Keep it simple."),
      latestProposal = null,
    )
}
