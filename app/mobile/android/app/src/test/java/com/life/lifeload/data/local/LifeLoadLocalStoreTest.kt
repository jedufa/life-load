package com.life.lifeload.data.local

import androidx.test.core.app.ApplicationProvider
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadScore
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.RobolectricTestRunner

@Config(sdk = [34])
@RunWith(RobolectricTestRunner::class)
class LifeLoadLocalStoreTest {
  private val stores = mutableListOf<LifeLoadLocalStore>()

  @After
  fun tearDown() {
    stores.forEach { store ->
      val context = ApplicationProvider.getApplicationContext<android.content.Context>()
      store.close()
      context.deleteDatabase(store.databaseName)
    }
  }

  @Test
  fun createsVersionedLocalSchemaAndStatus() {
    val store = localStore("schema.db")

    val tables = store.readableDatabase.rawQuery(
      "select name from sqlite_master where type = 'table'",
      emptyArray(),
    ).use { cursor ->
      buildList {
        while (cursor.moveToNext()) add(cursor.getString(0))
      }
    }

    assertTrue("local_entry" in tables)
    assertTrue("local_outbox" in tables)
    assertTrue("local_metadata" in tables)
    assertEquals(LIFE_LOAD_LOCAL_SCHEMA_VERSION, store.status().schemaVersion)
    assertEquals(0, store.status().entryCount)
    assertEquals(0, store.status().pendingOutboxCount)
  }

  @Test
  fun savesDraftAsLocalTruthAndQueuesDraftOutbox() {
    val store = localStore("draft.db")
    val entry = LifeLoadEntry(
      date = "2026-05-06",
      diaryText = "Local draft",
      sleepOk = true,
      nutritionOk = false,
      phoneAfter21 = true,
      tags = listOf("test", "offline"),
      primaryActivityType = "run",
      activityTypes = listOf("run", "crossfit"),
    )

    val record = store.saveDraft(entry)
    val outbox = store.pendingOutbox()

    assertEquals("draft", record.state)
    assertEquals("local", record.source)
    assertEquals("Local draft", record.entry.diaryText)
    assertEquals(true, record.entry.sleepOk)
    assertEquals(false, record.entry.nutritionOk)
    assertEquals(true, record.entry.phoneAfter21)
    assertEquals(listOf("test", "offline"), record.entry.tags)
    assertEquals("run", record.entry.primaryActivityType)
    assertEquals(listOf("run", "crossfit"), record.entry.activityTypes)
    assertEquals(1, outbox.size)
    assertEquals("draft_upsert", outbox[0].operation)
    assertEquals("2026-05-06", outbox[0].date)
    assertEquals("Local draft", JSONObject(outbox[0].payloadJson).getJSONObject("entry").getString("diary_text"))
    assertEquals(1, store.status().entryCount)
    assertEquals(1, store.status().pendingOutboxCount)
  }

  @Test
  fun approveStoresPendingApprovalAndQueuesApprovalOutbox() {
    val store = localStore("approve.db")
    val entry = LifeLoadEntry(
      date = "2026-05-06",
      diaryText = "Approve offline",
      stress = 7,
      projectOverrun = true,
    )

    val record = store.approve(entry)
    val outbox = store.pendingOutbox()

    assertEquals("pending_approval", record.state)
    assertEquals("local", record.source)
    assertEquals("Approve offline", record.entry.diaryText)
    assertEquals(7, record.entry.stress)
    assertEquals(true, record.entry.projectOverrun)
    assertEquals("", record.approvedAt)
    assertTrue(record.draftUpdatedAt.isNotBlank())
    assertEquals(1, outbox.size)
    assertEquals("approve", outbox[0].operation)
    assertEquals("2026-05-06", outbox[0].date)
  }

  @Test
  fun serverPayloadDoesNotOverwritePendingLocalWrite() {
    val store = localStore("server_pending_protection.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "local pending draft"))

    store.upsertFromServer(
      LifeLoadEntryPayload(
        date = "2026-05-06",
        defaultDate = "2026-05-06",
        previousDate = "2026-05-05",
        nextDate = "2026-05-07",
        entryState = "approved",
        hasDraft = false,
        entryExists = true,
        approvedAt = "2026-05-06T18:00:00Z",
        draftUpdatedAt = "",
        entry = LifeLoadEntry(date = "2026-05-06", diaryText = "server stale day"),
        draftEntry = LifeLoadEntry(date = "2026-05-06"),
        approvedEntry = LifeLoadEntry(date = "2026-05-06", diaryText = "server stale day"),
        score = LifeLoadScore(zone = "green"),
        latestProposal = null,
      ),
    )

    val record = store.getEntry("2026-05-06")
    assertEquals("draft", record?.state)
    assertEquals("local pending draft", record?.entry?.diaryText)
    assertEquals("local", record?.source)
  }

  @Test
  fun serverPayloadCanSeedLocalReadModelWithoutOutbox() {
    val store = localStore("server.db")
    val payload = LifeLoadEntryPayload(
      date = "2026-05-06",
      defaultDate = "2026-05-06",
      previousDate = "2026-05-05",
      nextDate = "2026-05-07",
      entryState = "approved",
      hasDraft = false,
      entryExists = true,
      approvedAt = "2026-05-06T18:00:00Z",
      draftUpdatedAt = "",
      entry = LifeLoadEntry(date = "2026-05-06", diaryText = "Approved history"),
      draftEntry = LifeLoadEntry(date = "2026-05-06"),
      approvedEntry = LifeLoadEntry(date = "2026-05-06", diaryText = "Approved history", energy = 6),
      score = LifeLoadScore(zone = "yellow", nextAction = "Keep the next step simple."),
      latestProposal = null,
    )

    store.upsertFromServer(payload)
    val record = store.getEntry("2026-05-06")

    assertNotNull(record)
    assertEquals("approved", record?.state)
    assertEquals("server", record?.source)
    assertEquals("Approved history", record?.entry?.diaryText)
    assertEquals(6, record?.entry?.energy)
    assertEquals("yellow", record?.score?.zone)
    assertEquals("Keep the next step simple.", record?.score?.nextAction)
    assertEquals(0, store.pendingOutbox().size)
  }

  @Test
  fun draftKeepsApprovedBaselineAndItsScore() {
    val store = localStore("approved_baseline.db")
    val approved = LifeLoadEntry(date = "2026-05-06", diaryText = "approved truth", energy = 7)
    val approvedScore = LifeLoadScore(zone = "yellow", nextAction = "Keep the evening small.")
    store.upsertFromServer(
      LifeLoadEntryPayload(
        date = approved.date,
        defaultDate = approved.date,
        previousDate = "2026-05-05",
        nextDate = "2026-05-07",
        entryState = "approved",
        hasDraft = false,
        entryExists = true,
        approvedAt = "2026-05-06T18:00:00Z",
        draftUpdatedAt = "",
        entry = approved,
        draftEntry = LifeLoadEntry(date = approved.date),
        approvedEntry = approved,
        score = approvedScore,
        latestProposal = null,
      ),
    )

    val draft = store.saveDraft(approved.copy(diaryText = "new local draft", energy = 2))

    assertEquals("draft_over_approved", draft.state)
    assertEquals("new local draft", draft.entry.diaryText)
    assertEquals("approved truth", draft.approvedEntry?.diaryText)
    assertEquals("yellow", draft.approvedScore?.zone)
    assertEquals(1, store.pendingOutbox().size)
  }

  @Test
  fun lateAcknowledgementCannotReplaceNewerLocalRevision() {
    val store = localStore("stale_ack_revision.db")
    val first = store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "first revision"))
    val firstOutbox = store.pendingOutbox().single()
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "newer revision"))

    val result = store.applyOutboxAcknowledgement(
      firstOutbox,
      LifeLoadEntryPayload(
        date = "2026-05-06",
        defaultDate = "2026-05-06",
        previousDate = "2026-05-05",
        nextDate = "2026-05-07",
        entryState = "draft",
        hasDraft = true,
        entryExists = true,
        approvedAt = "",
        draftUpdatedAt = "2026-05-06T18:00:00Z",
        entry = first.entry,
        draftEntry = first.entry,
        approvedEntry = null,
        score = LifeLoadScore(),
        latestProposal = null,
      ),
    )

    assertEquals(LifeLoadOutboxApplyResult.STALE, result)
    assertEquals("newer revision", store.getEntry("2026-05-06")?.entry?.diaryText)
    assertEquals(1, store.pendingOutbox().size)
  }

  @Test
  fun acknowledgementChangingAnyEntryFieldBecomesConflict() {
    val store = localStore("field_conflict.db")
    store.approve(LifeLoadEntry(date = "2026-05-06", diaryText = "same diary", stress = 4))
    val outbox = store.pendingOutbox().single()
    val returned = LifeLoadEntry(date = "2026-05-06", diaryText = "same diary", stress = 5)

    val result = store.applyOutboxAcknowledgement(
      outbox,
      LifeLoadEntryPayload(
        date = returned.date,
        defaultDate = returned.date,
        previousDate = "2026-05-05",
        nextDate = "2026-05-07",
        entryState = "approved",
        hasDraft = false,
        entryExists = true,
        approvedAt = "2026-05-06T18:00:00Z",
        draftUpdatedAt = "",
        entry = returned,
        draftEntry = LifeLoadEntry(date = returned.date),
        approvedEntry = returned,
        score = LifeLoadScore(zone = "green"),
        latestProposal = null,
      ),
    )

    assertEquals(LifeLoadOutboxApplyResult.CONFLICT, result)
    assertEquals(1, store.status().conflictOutboxCount)
    assertEquals("same diary", store.getEntry("2026-05-06")?.entry?.diaryText)
    assertEquals(4, store.getEntry("2026-05-06")?.entry?.stress)
  }

  @Test
  fun acknowledgementFromBeforeDeleteCannotRecreateLocalRows() {
    val store = localStore("delete_generation_ack.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "delete me"))
    val outbox = store.pendingOutbox().single()
    store.resetLocalData()

    val result = store.applyOutboxAcknowledgement(
      outbox,
      LifeLoadEntryPayload(
        date = "2026-05-06",
        defaultDate = "2026-05-06",
        previousDate = "2026-05-05",
        nextDate = "2026-05-07",
        entryState = "draft",
        hasDraft = true,
        entryExists = true,
        approvedAt = "",
        draftUpdatedAt = "2026-05-06T18:00:00Z",
        entry = LifeLoadEntry(date = "2026-05-06", diaryText = "delete me"),
        draftEntry = LifeLoadEntry(date = "2026-05-06", diaryText = "delete me"),
        approvedEntry = null,
        score = LifeLoadScore(),
        latestProposal = null,
      ),
    )

    assertEquals(LifeLoadOutboxApplyResult.STALE, result)
    assertEquals(null, store.getEntry("2026-05-06"))
    assertEquals(0, store.status().entryCount)
  }

  @Test
  fun restoringDraftWithoutApprovedBaselineKeepsBaselineNull() {
    val source = localStore("restore_null_baseline_source.db")
    source.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "draft only"))
    val target = localStore("restore_null_baseline_target.db")

    target.restoreDebugBundle(source.exportDebugBundle(redacted = false))

    val restored = target.getEntry("2026-05-06")
    assertEquals("draft only", restored?.entry?.diaryText)
    assertEquals(null, restored?.approvedEntry)
    assertEquals(null, restored?.approvedScore)
  }

  @Test
  fun serverPayloadWithNonFiniteScoreDoesNotCrashLocalCache() {
    val store = localStore("server_nan_score.db")
    val payload = LifeLoadEntryPayload(
      date = "2026-05-10",
      defaultDate = "2026-05-10",
      previousDate = "2026-05-09",
      nextDate = "2026-05-11",
      entryState = "blank",
      hasDraft = false,
      entryExists = false,
      approvedAt = "",
      draftUpdatedAt = "",
      entry = LifeLoadEntry(date = "2026-05-10"),
      draftEntry = LifeLoadEntry(date = "2026-05-10"),
      approvedEntry = null,
      score = LifeLoadScore(
        confidence = Double.NaN,
        lifeLoadScore = Double.NaN,
        trainingLoadRatio = Double.POSITIVE_INFINITY,
      ),
      latestProposal = null,
    )

    store.upsertFromServer(payload)
    val record = store.getEntry("2026-05-10")

    assertNotNull(record)
    assertEquals(0.0, record?.score?.lifeLoadScore ?: -1.0, 0.001)
    assertEquals(null, record?.score?.confidence)
    assertEquals(null, record?.score?.trainingLoadRatio)
  }

  @Test
  fun redactedDebugBundleOmitsPrivateEntryAndOutboxPayloadValues() {
    val store = localStore("debug_redacted.db")
    store.approve(
      LifeLoadEntry(
        date = "2026-05-06",
        diaryText = "private diary text",
        stress = 8,
        phoneAfter21 = true,
      ),
    )

    val bundle = store.exportDebugBundle(redacted = true)
    val parsed = JSONObject(bundle)

    assertEquals(LIFE_LOAD_DEBUG_BUNDLE_VERSION, parsed.getString("schema_version"))
    assertEquals("redacted", parsed.getString("redaction"))
    assertEquals(1, parsed.getJSONObject("status").getInt("entry_count"))
    assertEquals(1, parsed.getJSONObject("status").getInt("pending_outbox_count"))
    assertTrue(parsed.getJSONArray("entries").getJSONObject(0).getJSONObject("entry_json").getBoolean("redacted"))
    assertTrue(parsed.getJSONArray("outbox").getJSONObject(0).getJSONObject("payload_json").getBoolean("redacted"))
    assertFalse(bundle.contains("private diary text"))
  }

  @Test
  fun fullDebugBundleCanResetAndRestoreLocalData() {
    val store = localStore("debug_restore.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "restore this local draft"))
    val bundle = store.exportDebugBundle(redacted = false)

    store.resetLocalData()
    assertEquals(0, store.status().entryCount)
    assertEquals(0, store.status().pendingOutboxCount)

    store.restoreDebugBundle(bundle)
    val restored = store.getEntry("2026-05-06")

    assertEquals("draft", restored?.state)
    assertEquals("restore this local draft", restored?.entry?.diaryText)
    assertEquals("draft_upsert", store.pendingOutbox().single().operation)
  }

  @Test
  fun localPrivacyExportWritesFullLocalBundleAndDeleteRemovesExports() {
    val store = localStore("privacy_export_delete.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "export this local row"))

    val result = store.exportLocalDataFile()
    val exportFile = java.io.File(result.path)

    assertEquals(1, result.entryCount)
    assertEquals(1, result.outboxCount)
    assertTrue(exportFile.exists())
    assertTrue(exportFile.readText(Charsets.UTF_8).contains("\"redaction\":\"full_local_only\""))
    assertTrue(exportFile.readText(Charsets.UTF_8).contains("export this local row"))

    val status = store.deleteLocalDataAndExports()

    assertEquals(0, status.entryCount)
    assertEquals(0, status.pendingOutboxCount)
    assertFalse(exportFile.exists())
  }

  @Test
  fun redactedDebugBundleCannotRestoreLocalData() {
    val store = localStore("debug_reject_redacted.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "do not restore from redacted"))
    val bundle = store.exportDebugBundle(redacted = true)
    store.resetLocalData()

    try {
      store.restoreDebugBundle(bundle)
      throw AssertionError("redacted bundle restore should fail")
    } catch (error: IllegalArgumentException) {
      assertTrue(error.message.orEmpty().contains("redacted"))
    }
    assertEquals(0, store.status().entryCount)
  }

  @Test
  fun reopenedDatabaseKeepsSchemaAndLocalRows() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val name = "reopen_schema.db"
    context.deleteDatabase(name)
    LifeLoadLocalStore(context, name).use { store ->
      store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "persisted draft"))
      assertEquals(LIFE_LOAD_LOCAL_SCHEMA_VERSION, store.status().schemaVersion)
    }

    LifeLoadLocalStore(context, name).use { reopened ->
      assertEquals(LIFE_LOAD_LOCAL_SCHEMA_VERSION, reopened.status().schemaVersion)
      assertEquals("persisted draft", reopened.getEntry("2026-05-06")?.entry?.diaryText)
      assertEquals("draft_upsert", reopened.pendingOutbox().single().operation)
    }
    context.deleteDatabase(name)
  }

  @Test
  fun migratesLegacyVersionOneDatabaseBeforeDiagnosticsMirrorExport() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val name = "legacy_v1_mirror_export.db"
    context.deleteDatabase(name)
    context.openOrCreateDatabase(name, android.content.Context.MODE_PRIVATE, null).use { db ->
      db.execSQL(
        """
        CREATE TABLE local_entry (
          date TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          entry_json TEXT NOT NULL,
          approved_at TEXT NOT NULL DEFAULT '',
          draft_updated_at TEXT NOT NULL DEFAULT '',
          local_updated_at TEXT NOT NULL
        )
        """.trimIndent(),
      )
      db.execSQL(
        """
        CREATE TABLE local_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          operation TEXT NOT NULL,
          date TEXT NOT NULL,
          payload_json TEXT NOT NULL
        )
        """.trimIndent(),
      )
      db.execSQL(
        """
        INSERT INTO local_entry(date, state, entry_json, approved_at, draft_updated_at, local_updated_at)
        VALUES(
          '2026-05-06',
          'draft',
          '{"date":"2026-05-06","diary_text":"legacy local row"}',
          '',
          '2026-05-06T08:00:00Z',
          '2026-05-06T08:00:00Z'
        )
        """.trimIndent(),
      )
      db.execSQL(
        """
        INSERT INTO local_outbox(operation, date, payload_json)
        VALUES(
          'draft_upsert',
          '2026-05-06',
          '{"entry":{"date":"2026-05-06","diary_text":"legacy pending row"}}'
        )
        """.trimIndent(),
      )
      db.version = 1
    }

    LifeLoadLocalStore(context, name).use { migrated ->
      stores += migrated
      assertEquals(LIFE_LOAD_LOCAL_SCHEMA_VERSION, migrated.status().schemaVersion)
      assertEquals("legacy local row", migrated.getEntry("2026-05-06")?.entry?.diaryText)
      assertEquals("", migrated.pendingOutbox().single().lastError)

      val bundle = JSONObject(migrated.exportDebugBundle(redacted = true))
      assertEquals("redacted", bundle.getString("redaction"))
      assertEquals(1, bundle.getJSONObject("status").getInt("entry_count"))
      assertEquals(1, bundle.getJSONObject("status").getInt("pending_outbox_count"))
    }
  }

  @Test
  fun restoreRejectsUnsupportedDebugBundleVersionWithoutChangingLocalRows() {
    val store = localStore("debug_reject_schema.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-06", diaryText = "keep me"))
    val unsupported = JSONObject(store.exportDebugBundle(redacted = false))
      .put("schema_version", "unknown_bundle_v0")
      .toString()

    try {
      store.restoreDebugBundle(unsupported)
      throw AssertionError("unsupported bundle should fail")
    } catch (error: IllegalArgumentException) {
      assertTrue(error.message.orEmpty().contains("unsupported"))
    }

    assertEquals("keep me", store.getEntry("2026-05-06")?.entry?.diaryText)
    assertEquals(1, store.status().entryCount)
  }

  @Test
  fun old_export_bundle_still_imports() {
    val store = localStore("old_export_import.db")
    val oldBundle = JSONObject()
      .put("schema_version", LIFE_LOAD_DEBUG_BUNDLE_VERSION)
      .put("redaction", "full_local_only")
      .put(
        "entries",
        JSONArray().put(
          JSONObject()
            .put("date", "2026-05-17")
            .put("state", "draft")
            .put("entry_json", JSONObject().put("date", "2026-05-17").put("diary_text", "old fixed entry"))
            .put("score_json", JSONObject())
            .put("approved_at", "")
            .put("draft_updated_at", "")
            .put("source", "local")
            .put("local_updated_at", "2026-05-17T08:00:00Z"),
        ),
      )
      .put("outbox", JSONArray())
      .toString()

    store.restoreDebugBundle(oldBundle)

    assertEquals("old fixed entry", store.getEntry("2026-05-17")?.entry?.diaryText)
    assertEquals("personal_legacy", store.selectedProfileConfig().getString("active_profile_id"))
    assertEquals(emptyList<JSONObject>(), store.signalDefinitions())
    assertEquals(emptyList<JSONObject>(), store.signalEntries())
  }

  @Test
  fun new_additive_bundle_imports_without_losing_fixed_entries() {
    val store = localStore("new_additive_import.db")

    store.restoreDebugBundle(additiveBundleJson())

    assertEquals("fixed entry remains truth", store.getEntry("2026-05-17")?.entry?.diaryText)
    assertEquals("general_balance", store.selectedProfileConfig().getString("active_profile_id"))
    assertEquals("core.sleep_ok", store.signalDefinitions().first().getString("id"))
    assertEquals("core.sleep_ok", store.signalEntries().first().getString("signal_id"))
  }

  @Test
  fun unknown_future_signal_definitions_are_preserved_or_ignored_inertly() {
    val store = localStore("unknown_definition.db")

    store.restoreDebugBundle(additiveBundleJson())
    val unknown = store.signalDefinitions().single { it.getString("id") == "custom.future_signal" }

    assertEquals("Custom future signal", unknown.getString("label"))
    assertFalse(JSONObject(store.exportDebugBundle(redacted = false)).toString().contains("applied_to_scoring\":true"))
  }

  @Test
  fun unknown_future_signal_entries_are_preserved_or_ignored_inertly() {
    val store = localStore("unknown_entry.db")

    store.restoreDebugBundle(additiveBundleJson())
    val unknown = store.signalEntries().single { it.getString("signal_id") == "custom.future_signal" }

    assertEquals(9, unknown.getInt("value"))
    assertFalse(store.getEntry("2026-05-17")?.entry?.otherSymptoms == "9")
  }

  @Test
  fun additive_export_contains_fixed_entries() {
    val store = localStore("additive_export_entries.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", diaryText = "fixed entry export"))

    val bundle = JSONObject(store.exportDebugBundle(redacted = false))

    assertEquals("fixed entry export", bundle.getJSONArray("entries").getJSONObject(0).getJSONObject("entry_json").getString("diary_text"))
    assertTrue(bundle.getJSONObject("contract_notes").getBoolean("fixed_entries_are_compatibility_truth"))
  }

  @Test
  fun additive_export_contains_profile_signal_sections_when_present() {
    val store = localStore("additive_export_sections.db")
    store.saveSelectedProfileConfig(selectedConfig("general_balance"))
    store.saveSignalDefinition(signalDefinition("core.sleep_ok"))
    store.saveSignalEntry(signalEntry("2026-05-17", "core.sleep_ok", true))

    val bundle = JSONObject(store.exportDebugBundle(redacted = false))

    assertEquals("general_balance", bundle.getJSONObject("selected_profile_config").getString("active_profile_id"))
    assertEquals("core.sleep_ok", bundle.getJSONArray("signal_definitions").getJSONObject(0).getString("id"))
    assertEquals(true, bundle.getJSONArray("signal_entries").getJSONObject(0).getBoolean("value"))
  }

  @Test
  fun selected_profile_config_persists_across_restart() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val name = "selected_profile_restart.db"
    context.deleteDatabase(name)
    LifeLoadLocalStore(context, name).use { store ->
      store.saveSelectedProfileConfig(selectedConfig("general_balance"))
    }

    LifeLoadLocalStore(context, name).use { reopened ->
      assertEquals("general_balance", reopened.selectedProfileConfig().getString("active_profile_id"))
    }
    context.deleteDatabase(name)
  }

  @Test
  fun selected_profile_config_defaults_to_personal_legacy_for_current_state() {
    val store = localStore("selected_profile_default.db")

    assertEquals("personal_legacy", store.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun selected_profile_config_cleared_by_delete_reset() {
    val store = localStore("selected_profile_reset.db")
    store.saveSelectedProfileConfig(selectedConfig("general_balance"))

    store.resetLocalData()

    assertEquals("personal_legacy", store.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun selected_profile_config_export_import_roundtrip() {
    val source = localStore("selected_profile_export_source.db")
    source.saveSelectedProfileConfig(selectedConfig("general_balance"))
    val bundle = source.exportDebugBundle(redacted = false)
    val target = localStore("selected_profile_export_target.db")

    target.restoreDebugBundle(bundle)

    assertEquals("general_balance", target.selectedProfileConfig().getString("active_profile_id"))
  }

  @Test
  fun selected_profile_config_not_consumed_by_scoring() {
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/domain",
      "selected_profile_config",
      "local_profile_config",
    )
  }

  @Test
  fun selected_profile_config_not_used_by_compass_today() {
    val compassToday = repoFile("app/mobile/android/app/src/main/java/com/life/lifeload/ui/compass/CompassToday.kt").readText()

    assertFalse("selected_profile_config" in compassToday)
    assertFalse("selectedProfileConfig" in compassToday)
  }

  @Test
  fun signal_definitions_persist_across_restart() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val name = "signal_definition_restart.db"
    context.deleteDatabase(name)
    LifeLoadLocalStore(context, name).use { store ->
      store.saveSignalDefinition(signalDefinition("custom.future_signal"))
    }

    LifeLoadLocalStore(context, name).use { reopened ->
      assertEquals("custom.future_signal", reopened.signalDefinitions().single().getString("id"))
    }
    context.deleteDatabase(name)
  }

  @Test
  fun signal_entries_persist_across_restart() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val name = "signal_entry_restart.db"
    context.deleteDatabase(name)
    LifeLoadLocalStore(context, name).use { store ->
      store.saveSignalEntry(signalEntry("2026-05-17", "body.foot_pain", 0))
    }

    LifeLoadLocalStore(context, name).use { reopened ->
      assertEquals(0, reopened.signalEntries().single().getInt("value"))
    }
    context.deleteDatabase(name)
  }

  @Test
  fun signal_entries_preserve_absent_false_zero() {
    val store = localStore("signal_entry_values.db")
    store.saveSignalEntry(signalEntry("2026-05-17", "evening.phone_after_21", false))
    store.saveSignalEntry(signalEntry("2026-05-17", "body.foot_pain", 0))

    val values = store.signalEntries().associate { it.getString("signal_id") to it.get("value") }

    assertEquals(false, values["evening.phone_after_21"])
    assertEquals(0, values["body.foot_pain"])
    assertFalse("body.shoulder_pain" in values)
  }

  @Test
  fun signal_definitions_and_entries_cleared_by_delete_reset() {
    val store = localStore("signal_reset.db")
    store.saveSignalDefinition(signalDefinition("core.sleep_ok"))
    store.saveSignalEntry(signalEntry("2026-05-17", "core.sleep_ok", true))

    store.resetLocalData()

    assertEquals(0, store.signalDefinitions().size)
    assertEquals(0, store.signalEntries().size)
  }

  @Test
  fun signal_definitions_and_entries_export_import_roundtrip() {
    val source = localStore("signal_roundtrip_source.db")
    source.saveSignalDefinition(signalDefinition("custom.future_signal"))
    source.saveSignalEntry(signalEntry("2026-05-17", "custom.future_signal", 9))
    val target = localStore("signal_roundtrip_target.db")

    target.restoreDebugBundle(source.exportDebugBundle(redacted = false))

    assertEquals("custom.future_signal", target.signalDefinitions().single().getString("id"))
    assertEquals(9, target.signalEntries().single().getInt("value"))
  }

  @Test
  fun unknown_future_signal_definition_imports_inertly() {
    val store = localStore("unknown_inert_import.db")

    store.restoreDebugBundle(additiveBundleJson())

    assertEquals("custom.future_signal", store.signalDefinitions().single { it.getString("id") == "custom.future_signal" }.getString("id"))
  }

  @Test
  fun signal_entries_not_consumed_by_scoring() {
    assertProductionSourceDoesNotReference(
      "app/mobile/android/app/src/main/java/com/life/lifeload/domain",
      "signal_entries",
      "local_signal_entry",
    )
  }

  @Test
  fun LifeLoadEntry_json_unchanged_for_existing_entries() {
    val store = localStore("entry_json_unchanged.db")
    store.saveDraft(LifeLoadEntry(date = "2026-05-17", diaryText = "fixed only", phoneAfter21 = false, footPain = 0))
    store.saveSignalEntry(signalEntry("2026-05-17", "custom.future_signal", 9))

    val entryJson = JSONObject(store.exportDebugBundle(redacted = false))
      .getJSONArray("entries")
      .getJSONObject(0)
      .getJSONObject("entry_json")

    assertEquals(false, entryJson.getBoolean("phone_after_21"))
    assertEquals(0, entryJson.getInt("foot_pain"))
    assertFalse(entryJson.has("signal_entries"))
    assertFalse(entryJson.has("custom.future_signal"))
  }

  private fun localStore(name: String): LifeLoadLocalStore {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    context.deleteDatabase(name)
    return LifeLoadLocalStore(context, name).also { stores += it }
  }

  private fun selectedConfig(profileId: String): JSONObject =
    JSONObject()
      .put("active_profile_id", profileId)
      .put("template_version", 1)
      .put("enabled_signal_ids", JSONArray().put("core.sleep_ok"))
      .put("optional_signal_ids", JSONArray())
      .put("hidden_signal_ids", JSONArray())
      .put("disabled_signal_ids", JSONArray())
      .put("required_for_confidence_signal_ids", JSONArray().put("core.sleep_ok"))
      .put("optional_pack_ids", JSONArray())
      .put("user_added_signal_ids", JSONArray())
      .put("user_overridden_signal_ids", JSONArray())
      .put("guidance_bridge_policy_id", "fixed_field_legacy")
      .put("default_formula_modifier_id", JSONObject.NULL)
      .put("max_active_signals", 8)

  private fun signalDefinition(signalId: String): JSONObject =
    JSONObject()
      .put("id", signalId)
      .put("label", if (signalId.startsWith("custom.")) "Custom future signal" else "Sleep on time")
      .put("scale_type", if (signalId.startsWith("custom.")) "ordinal_0_10" else "boolean")
      .put("version", 1)

  private fun signalEntry(date: String, signalId: String, value: Any): JSONObject =
    JSONObject()
      .put("date", date)
      .put("signal_id", signalId)
      .put("value", value)
      .put("is_present", true)
      .put("source", "test")

  private fun additiveBundleJson(): String =
    JSONObject()
      .put("schema_version", LIFE_LOAD_DEBUG_BUNDLE_VERSION)
      .put("redaction", "full_local_only")
      .put(
        "entries",
        JSONArray().put(
          JSONObject()
            .put("date", "2026-05-17")
            .put("state", "draft")
            .put("entry_json", JSONObject().put("date", "2026-05-17").put("diary_text", "fixed entry remains truth"))
            .put("score_json", JSONObject())
            .put("approved_at", "")
            .put("draft_updated_at", "")
            .put("source", "local")
            .put("local_updated_at", "2026-05-17T08:00:00Z"),
        ),
      )
      .put("outbox", JSONArray())
      .put("selected_profile_config", selectedConfig("general_balance"))
      .put("signal_definitions", JSONArray().put(signalDefinition("core.sleep_ok")).put(signalDefinition("custom.future_signal")))
      .put("signal_entries", JSONArray().put(signalEntry("2026-05-17", "core.sleep_ok", true)).put(signalEntry("2026-05-17", "custom.future_signal", 9)))
      .put("optional_packs", JSONArray().put(JSONObject().put("id", "pattern_awareness_pack")))
      .put("influence_policies", JSONArray().put(JSONObject().put("signal_id", "core.sleep_ok").put("guidance_effect", "normal")))
      .toString()

  private fun assertProductionSourceDoesNotReference(relativeDir: String, vararg forbiddenReferences: String) {
    val matches = repoFile(relativeDir)
      .walkTopDown()
      .filter { it.isFile && it.extension == "kt" }
      .flatMap { file ->
        val text = file.readText(Charsets.UTF_8)
        forbiddenReferences
          .filter { it in text }
          .map { "${file.relativeTo(repoFile(""))}:$it" }
      }
      .toList()

    assertEquals(emptyList<String>(), matches)
  }

  private fun repoFile(relativePath: String): java.io.File {
    val userDir = System.getProperty("user.dir") ?: "."
    var current: java.io.File? = java.io.File(userDir).canonicalFile
    while (current != null) {
      if (java.io.File(current, "app/mobile/android").isDirectory && java.io.File(current, "app/backend/life_load").isDirectory) {
        return java.io.File(current, relativePath)
      }
      current = current.parentFile
    }
    throw AssertionError("Could not find repo root from $userDir")
  }
}
