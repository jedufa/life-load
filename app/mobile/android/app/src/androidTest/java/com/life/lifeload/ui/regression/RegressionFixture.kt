package com.life.lifeload.ui.regression

import android.content.Context
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadScore
import java.io.File
import java.time.LocalDate

object RegressionFixture {
  val mondayNormal: LocalDate = LocalDate.parse("2026-05-04")
  val wednesdayOverload: LocalDate = LocalDate.parse("2026-05-06")
  val saturdayWeekend: LocalDate = LocalDate.parse("2026-05-09")
  val futureMonday: LocalDate = LocalDate.parse("2026-05-11")

  const val privacySecret = "PRIVATE_TEST_DIARY_DO_NOT_LEAK_12345"

  fun resetAppState(context: Context) {
    ServerConfig.resetBaseUrl(context)
    resetLocalStore(context)
    deleteExportFiles(context)
  }

  fun resetLocalStore(context: Context) {
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }
  }

  fun deleteExportFiles(context: Context) {
    File(context.filesDir, "life_load_exports").deleteRecursively()
  }

  fun forceBackendUnavailable(context: Context) {
    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
  }

  fun restoreBackend(context: Context) {
    ServerConfig.resetBaseUrl(context)
  }

  fun entry(
    date: LocalDate,
    note: String = "synthetic fixture note",
    sleepOk: Boolean? = true,
    nutritionOk: Boolean? = true,
    alcohol: String? = "none",
    binge: Boolean? = false,
  ): LifeLoadEntry =
    LifeLoadEntry(
      date = date.toString(),
      diaryText = note,
      diarySummary = "synthetic fixture summary",
      tags = listOf("fixture"),
      sleepOk = sleepOk,
      nutritionOk = nutritionOk,
      alcohol = alcohol,
      binge = binge,
    )

  fun seedDraft(context: Context, entry: LifeLoadEntry = entry(mondayNormal)): LifeLoadEntry =
    LifeLoadLocalStore(context).use { store ->
      store.saveDraft(entry).entry
    }

  fun seedPendingApproval(context: Context, entry: LifeLoadEntry = entry(wednesdayOverload)): LifeLoadEntry =
    LifeLoadLocalStore(context).use { store ->
      store.approve(entry).entry
    }

  fun seedServerApproved(
    context: Context,
    entry: LifeLoadEntry = entry(saturdayWeekend),
    score: LifeLoadScore = LifeLoadScore(zone = "moderate", nextAction = "Keep the next action small.", lifeLoadScore = 42.0),
  ): LifeLoadEntry {
    val payload = LifeLoadEntryPayload(
      date = entry.date,
      defaultDate = entry.date,
      previousDate = entry.date,
      nextDate = entry.date,
      entryState = "approved",
      hasDraft = false,
      entryExists = true,
      approvedAt = "${entry.date}T20:00:00Z",
      draftUpdatedAt = "",
      entry = entry,
      draftEntry = entry,
      approvedEntry = entry,
      score = score,
      latestProposal = null,
    )
    LifeLoadLocalStore(context).use { store -> store.upsertFromServer(payload) }
    return entry
  }
}
