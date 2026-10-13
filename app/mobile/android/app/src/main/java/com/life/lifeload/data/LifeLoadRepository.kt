package com.life.lifeload.data

import com.life.lifeload.data.local.LifeLoadLocalEntryRecord
import com.life.lifeload.data.local.LifeLoadLocalExportResult
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.data.local.LifeLoadLocalStoreStatus
import com.life.lifeload.domain.LifeLoadAnalyzeResult
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadGarminImportResult
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadPlatformContract
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadSelectedProfileConfig
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.LifeLoadScore
import org.json.JSONObject
import kotlinx.coroutines.CancellationException
import java.time.LocalDate

data class LifeLoadLocalImportResult(
  val requested: Int,
  val imported: Int,
  val failed: Int,
  val failures: List<String> = emptyList(),
)

data class LifeLoadLocalSyncResult(
  val attempted: Int,
  val uploaded: Int,
  val failed: Int,
  val conflicts: Int,
)

data class LifeLoadDebugMirrorResult(
  val path: String,
  val entryCount: Int,
  val pendingOutboxCount: Int,
  val conflictOutboxCount: Int,
)

data class LifeLoadPrivacyExportResult(
  val path: String,
  val entryCount: Int,
  val outboxCount: Int,
)

data class LifeLoadPrivacyExportBundleResult(
  val bundleJson: String,
  val entryCount: Int,
  val outboxCount: Int,
)

class LifeLoadRepository(
  private val api: LifeLoadApi,
  private val localStore: LifeLoadLocalStore? = null,
) {
  suspend fun register(email: String, password: String): LifeLoadAuthSession = api.register(email, password)

  suspend fun login(email: String, password: String): LifeLoadAuthSession = api.login(email, password)

  suspend fun logout() = api.logout()

  suspend fun isBackendHealthy(): Boolean = api.isBackendHealthy()

  suspend fun loadContract(): LifeLoadPlatformContract = api.getContract()

  suspend fun loadSettings(): LifeLoadSettings = api.getSettings()

  suspend fun saveSettings(settings: LifeLoadSettings, garminPassword: String = ""): LifeLoadSettings =
    api.saveSettings(settings, garminPassword)

  suspend fun loadEntry(date: String): LifeLoadEntryPayload =
    localStore?.getEntry(date)?.toPayload()
      ?: localStore?.blankPayload(date)
      ?: api.getEntry(date)

  fun cachedLocalEntry(date: String): LifeLoadEntryPayload? =
    localStore?.getEntry(date)?.toPayload()

  /** Persist the latest draft without contacting the server. This is used
   * before date navigation so a fast tap cannot discard an edit. */
  fun persistDraftLocally(entry: LifeLoadEntry): Boolean {
    val store = localStore ?: return false
    store.saveDraft(entry)
    return true
  }

  fun canPersistDraftLocally(): Boolean = localStore != null

  suspend fun saveDraft(entry: LifeLoadEntry): LifeLoadEntryPayload =
    localStore?.saveDraft(entry)?.toPayload() ?: api.saveEntry(entry, action = "draft")

  suspend fun approve(entry: LifeLoadEntry): LifeLoadEntryPayload =
    localStore?.approve(entry)?.toPayload() ?: api.approveEntry(entry)

  suspend fun analyze(entry: LifeLoadEntry): LifeLoadAnalyzeResult = api.analyzeDiary(entry)

  suspend fun importGarmin(date: String, days: Int): LifeLoadGarminImportResult = api.importGarmin(date, days)

  suspend fun loadDashboard(date: String, weeks: Int = 8): LifeLoadDashboard {
    if (localStore == null) return api.getDashboard(date, weeks)
    val localSaved = localHistoryDays(date)
    val dashboard = try {
      api.getDashboard(date, weeks)
    } catch (error: CancellationException) {
      throw error
    } catch (error: Throwable) {
      if (localSaved.isEmpty()) throw error
      LifeLoadDashboard(date = date)
    }
    if (localSaved.isEmpty()) return dashboard
    val mergedHistory = (localSaved + dashboard.historyDays)
      .distinctBy { it.date }
      .sortedByDescending { it.date }
    return dashboard.copy(historyDays = mergedHistory)
  }

  fun loadLocalDashboard(date: String): LifeLoadDashboard =
    LifeLoadDashboard(date = date, historyDays = localHistoryDays(date))

  private fun localHistoryDays(date: String): List<LifeLoadHistoryDay> =
    localStore?.recentSavedEntries(date, days = 14).orEmpty().map { it.toHistoryDay() }

  fun exportLocalDebugBundle(redacted: Boolean = true): String? =
    localStore?.exportDebugBundle(redacted = redacted)

  fun selectedProfileConfig(): LifeLoadSelectedProfileConfig =
    LifeLoadSelectedProfileConfig.fromJson(
      localStore?.selectedProfileConfig() ?: LifeLoadProfileCatalog.defaultSelectedProfileConfig().toJson(),
    )

  fun saveSelectedProfileConfig(config: LifeLoadSelectedProfileConfig) {
    localStore?.saveSelectedProfileConfig(config.toJson())
  }

  fun saveSelectedProfileConfig(config: JSONObject) {
    localStore?.saveSelectedProfileConfig(config)
  }

  fun exportLocalData(): LifeLoadPrivacyExportResult {
    val result: LifeLoadLocalExportResult =
      localStore?.exportLocalDataFile() ?: error("local data export is not available")
    return LifeLoadPrivacyExportResult(
      path = result.path,
      entryCount = result.entryCount,
      outboxCount = result.outboxCount,
    )
  }

  fun exportLocalDataBundle(): LifeLoadPrivacyExportBundleResult {
    val store = localStore ?: error("local data export is not available")
    val status = store.status()
    return LifeLoadPrivacyExportBundleResult(
      bundleJson = store.exportDebugBundle(redacted = false),
      entryCount = status.entryCount,
      outboxCount = status.pendingOutboxCount,
    )
  }

  fun importLocalDataBundle(bundleJson: String): LifeLoadLocalStoreStatus {
    val store = localStore ?: error("local data import is not available")
    store.restoreDebugBundle(bundleJson)
    return store.status()
  }

  fun deleteLocalData(): LifeLoadLocalStoreStatus =
    localStore?.deleteLocalDataAndExports() ?: error("local data delete is not available")

  suspend fun mirrorRedactedLocalDebugBundle(): LifeLoadDebugMirrorResult {
    val bundle = localStore?.exportDebugBundle(redacted = true) ?: error("local diagnostics are not available")
    return api.mirrorLocalDebugBundle(bundle)
  }

  suspend fun importRecentHistory(anchorDate: String, days: Int): LifeLoadLocalImportResult {
    val store = localStore ?: return LifeLoadLocalImportResult(requested = 0, imported = 0, failed = 0)
    val requested = days.coerceIn(1, 730)
    val anchor = LocalDate.parse(anchorDate)
    var imported = 0
    val failures = mutableListOf<String>()
    for (offset in 0 until requested) {
      val date = anchor.minusDays(offset.toLong()).toString()
      try {
        store.upsertFromServer(api.getEntry(date))
        imported += 1
      } catch (error: CancellationException) {
        throw error
      } catch (_: Throwable) {
        failures += date
      }
    }
    return LifeLoadLocalImportResult(
      requested = requested,
      imported = imported,
      failed = failures.size,
      failures = failures,
    )
  }

  suspend fun syncPendingOutbox(): LifeLoadLocalSyncResult {
    val store = localStore ?: return LifeLoadLocalSyncResult(attempted = 0, uploaded = 0, failed = 0, conflicts = 0)
    val rows = store.pendingOutbox()
    var uploaded = 0
    var failed = 0
    var conflicts = 0
    for (row in rows) {
      try {
        val entry = store.entryFromOutbox(row)
        val payload = when (row.operation) {
          "draft_upsert" -> api.saveEntry(entry, action = "draft")
          "approve" -> {
            api.saveEntry(entry, action = "draft")
            api.approveEntry(entry)
          }
          else -> throw IllegalStateException("unsupported local outbox operation ${row.operation}")
        }
        when (store.applyOutboxAcknowledgement(row, payload)) {
          com.life.lifeload.data.local.LifeLoadOutboxApplyResult.CONFLICT -> conflicts += 1
          com.life.lifeload.data.local.LifeLoadOutboxApplyResult.APPLIED,
          com.life.lifeload.data.local.LifeLoadOutboxApplyResult.STALE,
          -> uploaded += 1
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        failed += 1
        store.markOutboxFailed(row.id, error.message ?: error::class.java.simpleName)
      }
    }
    return LifeLoadLocalSyncResult(attempted = rows.size, uploaded = uploaded, failed = failed, conflicts = conflicts)
  }
}

private fun LifeLoadLocalEntryRecord.toPayload(): LifeLoadEntryPayload {
  val localDate = LocalDate.parse(date)
  val canonical = this.approvedEntry ?: entry.takeIf { state == "approved" }
  val canonicalScore = this.approvedScore ?: score.takeIf { state == "approved" }
  val draftEntry = if (state == "approved") LifeLoadEntry(date = date) else entry
  val evaluatedScore = if (state == "approved") score else LifeLoadScore()
  return LifeLoadEntryPayload(
    date = date,
    defaultDate = date,
    previousDate = localDate.minusDays(1).toString(),
    nextDate = localDate.plusDays(1).toString(),
    entryState = state,
    hasDraft = state == "draft" || state == "pending_approval" || state == "draft_over_approved",
    entryExists = true,
    approvedAt = approvedAt,
    draftUpdatedAt = draftUpdatedAt,
    entry = entry,
    draftEntry = draftEntry,
    approvedEntry = canonical,
    score = evaluatedScore,
    scoreAvailable = canonicalScore.isAvailable() || (state == "approved" && score.isAvailable()),
    hasLocalDraft = state == "draft" || state == "draft_over_approved",
    latestProposal = null,
    derivedDashboard = null,
  )
}

private fun LifeLoadLocalEntryRecord.toHistoryDay(): LifeLoadHistoryDay =
  LifeLoadHistoryDay(
    date = date,
    state = state,
    approvedAt = approvedAt,
    canonicalCompleted = state == "approved" || state == "pending_approval" || state == "draft_over_approved",
    zone = (approvedScore ?: score).zone.ifBlank { (approvedScore ?: score).mode },
    nextAction = (approvedScore ?: score).nextAction,
    lifeLoadScore = (approvedScore ?: score).lifeLoadScore,
    diarySummary = entry.diarySummary.ifBlank { entry.diaryText },
    mood = entry.mood,
    stress = entry.stress,
    energy = entry.energy,
    scoreAvailable = this.approvedScore.isAvailable() || (state == "approved" && score.isAvailable()),
  )

private fun LifeLoadLocalStore.blankPayload(date: String): LifeLoadEntryPayload {
  val localDate = LocalDate.parse(date)
  return LifeLoadEntryPayload(
    date = date,
    defaultDate = date,
    previousDate = localDate.minusDays(1).toString(),
    nextDate = localDate.plusDays(1).toString(),
    entryState = "blank",
    hasDraft = false,
    entryExists = false,
    approvedAt = "",
    draftUpdatedAt = "",
    entry = LifeLoadEntry(date = date),
    draftEntry = LifeLoadEntry(date = date),
    approvedEntry = null,
    score = LifeLoadScore(),
    scoreAvailable = false,
    latestProposal = null,
  )
}

private fun LifeLoadScore?.isAvailable(): Boolean = this != null && (
  zone.isNotBlank() || mode.isNotBlank() || nextAction.isNotBlank() ||
    why.isNotEmpty() || warnings.isNotEmpty() || redFlags.isNotEmpty() ||
    lifeLoadScore != 0.0 || confidence != null
  )
