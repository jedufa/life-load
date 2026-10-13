package com.life.lifeload.data.local

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadScore
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.LocalDate

const val LIFE_LOAD_LOCAL_SCHEMA_VERSION = 4
const val LIFE_LOAD_DEBUG_BUNDLE_VERSION = "life_load_android_local_debug_bundle_v1"
private const val SELECTED_PROFILE_CONFIG_ID = "selected_profile_config"
private const val FUTURE_OPTIONAL_PACKS_METADATA_KEY = "future_optional_packs"
private const val FUTURE_INFLUENCE_POLICIES_METADATA_KEY = "future_influence_policies"
private const val SYNC_GENERATION_METADATA_KEY = "sync_generation"

data class LifeLoadLocalEntryRecord(
  val date: String,
  val state: String,
  val entry: LifeLoadEntry,
  val score: LifeLoadScore,
  val approvedAt: String,
  val draftUpdatedAt: String,
  val source: String,
  val localUpdatedAt: String,
  val approvedEntry: LifeLoadEntry? = null,
  val approvedScore: LifeLoadScore? = null,
  val revision: Long = 0L,
)

data class LifeLoadOutboxRecord(
  val id: Long,
  val operation: String,
  val date: String,
  val payloadJson: String,
  val status: String,
  val createdAt: String,
  val lastError: String,
  val revision: Long = 0L,
  val generation: Long = 0L,
)

enum class LifeLoadOutboxApplyResult { APPLIED, STALE, CONFLICT }

data class LifeLoadLocalStoreStatus(
  val schemaVersion: Int,
  val entryCount: Int,
  val pendingOutboxCount: Int,
  val conflictOutboxCount: Int = 0,
)

data class LifeLoadLocalExportResult(
  val path: String,
  val entryCount: Int,
  val outboxCount: Int,
)

class LifeLoadLocalStore(
  context: Context,
  name: String = "life_load_local.db",
  private val defaultProfileId: String = "personal_legacy",
) : SQLiteOpenHelper(context.applicationContext, name, null, LIFE_LOAD_LOCAL_SCHEMA_VERSION) {
  private val appContext = context.applicationContext

  override fun onCreate(db: SQLiteDatabase) {
    createCurrentSchema(db)
    writeSchemaVersion(db)
  }

  override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
    if (oldVersion < 1) {
      createCurrentSchema(db)
      writeSchemaVersion(db)
      return
    }
    if (oldVersion < 2) migrateToVersion2(db)
    if (oldVersion < 3) migrateToVersion3(db)
    if (oldVersion < 4) migrateToVersion4(db)
    writeSchemaVersion(db)
  }

  private fun createCurrentSchema(db: SQLiteDatabase) {
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_entry (
        date TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        entry_json TEXT NOT NULL,
        score_json TEXT NOT NULL DEFAULT '{}',
        approved_at TEXT NOT NULL DEFAULT '',
        draft_updated_at TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        source_updated_at TEXT NOT NULL DEFAULT '',
        local_updated_at TEXT NOT NULL,
        approved_entry_json TEXT,
        approved_score_json TEXT,
        revision INTEGER NOT NULL DEFAULT 0
      )
      """.trimIndent(),
    )
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation TEXT NOT NULL,
        date TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        last_error TEXT NOT NULL DEFAULT '',
        revision INTEGER NOT NULL DEFAULT 0,
        generation INTEGER NOT NULL DEFAULT 0
      )
      """.trimIndent(),
    )
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      )
      """.trimIndent(),
    )
    db.execSQL("CREATE INDEX IF NOT EXISTS idx_local_outbox_status_created ON local_outbox(status, created_at)")
    createFutureSignalTables(db)
    db.insertWithOnConflict(
      "local_metadata",
      null,
      ContentValues().apply {
        put("key", SYNC_GENERATION_METADATA_KEY)
        put("value", "0")
      },
      SQLiteDatabase.CONFLICT_IGNORE,
    )
  }

  private fun migrateToVersion2(db: SQLiteDatabase) {
    if (!tableExists(db, "local_entry") || !tableExists(db, "local_outbox")) {
      createCurrentSchema(db)
      return
    }
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      )
      """.trimIndent(),
    )
    addColumnIfMissing(db, "local_entry", "score_json", "TEXT NOT NULL DEFAULT '{}'")
    addColumnIfMissing(db, "local_entry", "approved_at", "TEXT NOT NULL DEFAULT ''")
    addColumnIfMissing(db, "local_entry", "draft_updated_at", "TEXT NOT NULL DEFAULT ''")
    addColumnIfMissing(db, "local_entry", "source", "TEXT NOT NULL DEFAULT ''")
    addColumnIfMissing(db, "local_entry", "source_updated_at", "TEXT NOT NULL DEFAULT ''")
    addColumnIfMissing(db, "local_entry", "local_updated_at", "TEXT NOT NULL DEFAULT ''")
    addColumnIfMissing(db, "local_outbox", "status", "TEXT NOT NULL DEFAULT 'pending'")
    addColumnIfMissing(db, "local_outbox", "created_at", "TEXT NOT NULL DEFAULT ''")
    addColumnIfMissing(db, "local_outbox", "last_error", "TEXT NOT NULL DEFAULT ''")
    db.execSQL("CREATE INDEX IF NOT EXISTS idx_local_outbox_status_created ON local_outbox(status, created_at)")
  }

  private fun migrateToVersion3(db: SQLiteDatabase) {
    createFutureSignalTables(db)
  }

  private fun migrateToVersion4(db: SQLiteDatabase) {
    addColumnIfMissing(db, "local_entry", "approved_entry_json", "TEXT")
    addColumnIfMissing(db, "local_entry", "approved_score_json", "TEXT")
    addColumnIfMissing(db, "local_entry", "revision", "INTEGER NOT NULL DEFAULT 0")
    addColumnIfMissing(db, "local_outbox", "revision", "INTEGER NOT NULL DEFAULT 0")
    addColumnIfMissing(db, "local_outbox", "generation", "INTEGER NOT NULL DEFAULT 0")
    db.insertWithOnConflict(
      "local_metadata",
      null,
      ContentValues().apply {
        put("key", SYNC_GENERATION_METADATA_KEY)
        put("value", "0")
      },
      SQLiteDatabase.CONFLICT_IGNORE,
    )
  }

  private fun createFutureSignalTables(db: SQLiteDatabase) {
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_profile_config (
        id TEXT PRIMARY KEY,
        config_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
      """.trimIndent(),
    )
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_signal_definition (
        signal_id TEXT PRIMARY KEY,
        definition_json TEXT NOT NULL,
        inert INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
      )
      """.trimIndent(),
    )
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS local_signal_entry (
        date TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        entry_json TEXT NOT NULL,
        inert INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(date, signal_id)
      )
      """.trimIndent(),
    )
  }

  private fun tableExists(db: SQLiteDatabase, table: String): Boolean =
    db.rawQuery(
      "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
      arrayOf(table),
    ).use { cursor -> cursor.moveToFirst() }

  private fun addColumnIfMissing(db: SQLiteDatabase, table: String, column: String, definition: String) {
    if (tableColumns(db, table).contains(column)) return
    db.execSQL("ALTER TABLE $table ADD COLUMN $column $definition")
  }

  private fun tableColumns(db: SQLiteDatabase, table: String): Set<String> =
    db.rawQuery("PRAGMA table_info($table)", emptyArray()).use { cursor ->
      buildSet {
        while (cursor.moveToNext()) add(cursor.getString(cursor.getColumnIndexOrThrow("name")))
      }
    }

  private fun writeSchemaVersion(db: SQLiteDatabase) {
    db.insertWithOnConflict(
      "local_metadata",
      null,
      ContentValues().apply {
        put("key", "schema_version")
        put("value", LIFE_LOAD_LOCAL_SCHEMA_VERSION.toString())
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  fun upsertFromServer(payload: LifeLoadEntryPayload, protectPendingLocalWrite: Boolean = true) {
    if (protectPendingLocalWrite && hasPendingLocalWrite(payload.date)) return
    val existing = getEntry(payload.date)
    val approved = payload.approvedEntry
      ?: payload.entry.takeIf { payload.entryState == "approved" }
      ?: existing?.approvedEntry
    val entry = payload.draftEntry.takeIf { payload.hasDraft }
      ?: payload.entry.takeIf { payload.entryState != "approved" }
      ?: approved
      ?: payload.entry
    val state = when {
      payload.hasDraft && approved != null -> "draft_over_approved"
      payload.hasDraft -> "draft"
      approved != null -> "approved"
      else -> payload.entryState.ifBlank { "blank" }
    }
    val now = nowIso()
    writableDatabase.insertWithOnConflict(
      "local_entry",
      null,
      ContentValues().apply {
        put("date", payload.date)
        put("state", state)
        put("entry_json", entryToJson(entry).toString())
        put("score_json", if (state == "approved") scoreToJson(payload.score).toString() else "{}")
        put("approved_entry_json", approved?.let { entryToJson(it).toString() })
        put("approved_score_json", if (approved != null && state == "approved") scoreToJson(payload.score).toString() else existing?.approvedScore?.let { scoreToJson(it).toString() })
        put("approved_at", payload.approvedAt.ifBlank { existing?.approvedAt.orEmpty() })
        put("draft_updated_at", payload.draftUpdatedAt)
        put("source", "server")
        put("source_updated_at", payload.approvedAt.ifBlank { payload.draftUpdatedAt })
        put("local_updated_at", now)
        put("revision", existing?.revision ?: 0L)
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  fun saveDraft(entry: LifeLoadEntry): LifeLoadLocalEntryRecord {
    val now = nowIso()
    val entryJson = entryToJson(entry).toString()
    writableDatabase.beginTransaction()
    try {
      val existing = queryEntry(writableDatabase, entry.date)
      val approvedEntry = existing?.approvedEntry ?: existing?.entry?.takeIf { existing.state == "approved" }
      val approvedScore = existing?.approvedScore ?: existing?.score?.takeIf { existing.state == "approved" }
      val revision = (existing?.revision ?: 0L) + 1L
      writableDatabase.insertWithOnConflict(
        "local_entry",
        null,
        ContentValues().apply {
          put("date", entry.date)
          put("state", if (approvedEntry != null) "draft_over_approved" else "draft")
          put("entry_json", entryJson)
          put("score_json", "{}")
          put("approved_entry_json", approvedEntry?.let { entryToJson(it).toString() })
          put("approved_score_json", approvedScore?.let { scoreToJson(it).toString() })
          put("approved_at", existing?.approvedAt.orEmpty())
          put("draft_updated_at", now)
          put("source", "local")
          put("source_updated_at", "")
          put("local_updated_at", now)
          put("revision", revision)
        },
        SQLiteDatabase.CONFLICT_REPLACE,
      )
      enqueueOutboxLocked(operation = "draft_upsert", entry = entry, createdAt = now, revision = revision)
      writableDatabase.setTransactionSuccessful()
    } finally {
      writableDatabase.endTransaction()
    }
    return requireEntry(entry.date)
  }

  fun approve(entry: LifeLoadEntry): LifeLoadLocalEntryRecord {
    val now = nowIso()
    val entryJson = entryToJson(entry).toString()
    writableDatabase.beginTransaction()
    try {
      val existing = queryEntry(writableDatabase, entry.date)
      val approvedEntry = existing?.approvedEntry ?: existing?.entry?.takeIf { existing.state == "approved" }
      val approvedScore = existing?.approvedScore ?: existing?.score?.takeIf { existing.state == "approved" }
      val revision = (existing?.revision ?: 0L) + 1L
      writableDatabase.delete(
        "local_outbox",
        "date = ? AND operation = 'draft_upsert' AND status = 'pending'",
        arrayOf(entry.date),
      )
      writableDatabase.insertWithOnConflict(
        "local_entry",
        null,
        ContentValues().apply {
          put("date", entry.date)
          put("state", "pending_approval")
          put("entry_json", entryJson)
          put("score_json", "{}")
          put("approved_entry_json", approvedEntry?.let { entryToJson(it).toString() })
          put("approved_score_json", approvedScore?.let { scoreToJson(it).toString() })
          put("approved_at", existing?.approvedAt.orEmpty())
          put("draft_updated_at", now)
          put("source", "local")
          put("source_updated_at", "")
          put("local_updated_at", now)
          put("revision", revision)
        },
        SQLiteDatabase.CONFLICT_REPLACE,
      )
      enqueueOutboxLocked(operation = "approve", entry = entry, createdAt = now, revision = revision)
      writableDatabase.setTransactionSuccessful()
    } finally {
      writableDatabase.endTransaction()
    }
    return requireEntry(entry.date)
  }

  fun getEntry(date: String): LifeLoadLocalEntryRecord? {
    return queryEntry(readableDatabase, date)
  }

  private fun queryEntry(db: SQLiteDatabase, date: String): LifeLoadLocalEntryRecord? {
    db.query(
      "local_entry",
      null,
      "date = ?",
      arrayOf(date),
      null,
      null,
      null,
      "1",
    ).use { cursor ->
      if (!cursor.moveToFirst()) return null
      return recordFromCursor(cursor)
    }
  }

  fun savedEntriesBetween(startDate: String, endDate: String): List<LifeLoadLocalEntryRecord> {
    readableDatabase.query(
      "local_entry",
      null,
      "date >= ? AND date <= ? AND state IN (?, ?, ?)",
      arrayOf(startDate, endDate, "approved", "pending_approval", "draft_over_approved"),
      null,
      null,
      "date DESC",
    ).use { cursor ->
      val rows = mutableListOf<LifeLoadLocalEntryRecord>()
      while (cursor.moveToNext()) {
        rows += recordFromCursor(cursor)
      }
      return rows
    }
  }

  fun recentSavedEntries(anchorDate: String, days: Int): List<LifeLoadLocalEntryRecord> {
    val anchor = LocalDate.parse(anchorDate)
    val start = anchor.minusDays((days.coerceAtLeast(1) - 1).toLong())
    return savedEntriesBetween(start.toString(), anchor.toString())
  }

  fun pendingOutbox(): List<LifeLoadOutboxRecord> {
    readableDatabase.query(
      "local_outbox",
      null,
      "status = ?",
      arrayOf("pending"),
      null,
      null,
      "created_at ASC, id ASC",
    ).use { cursor ->
      val rows = mutableListOf<LifeLoadOutboxRecord>()
      while (cursor.moveToNext()) {
        rows += LifeLoadOutboxRecord(
          id = cursor.getLong(cursor.getColumnIndexOrThrow("id")),
          operation = cursor.getString(cursor.getColumnIndexOrThrow("operation")),
          date = cursor.getString(cursor.getColumnIndexOrThrow("date")),
          payloadJson = cursor.getString(cursor.getColumnIndexOrThrow("payload_json")),
          status = cursor.getString(cursor.getColumnIndexOrThrow("status")),
          createdAt = cursor.getString(cursor.getColumnIndexOrThrow("created_at")),
          lastError = cursor.getString(cursor.getColumnIndexOrThrow("last_error")),
          revision = cursor.getLong(cursor.getColumnIndexOrThrow("revision")),
          generation = cursor.getLong(cursor.getColumnIndexOrThrow("generation")),
        )
      }
      return rows
    }
  }

  fun markOutboxUploaded(id: Long) {
    writableDatabase.update(
      "local_outbox",
      ContentValues().apply {
        put("status", "uploaded")
        put("last_error", "")
      },
      "id = ?",
      arrayOf(id.toString()),
    )
  }

  fun markOutboxFailed(id: Long, error: String) {
    writableDatabase.update(
      "local_outbox",
      ContentValues().apply {
        put("status", "pending")
        put("last_error", error.take(240))
      },
      "id = ?",
      arrayOf(id.toString()),
    )
  }

  fun markOutboxConflict(id: Long, error: String) {
    writableDatabase.update(
      "local_outbox",
      ContentValues().apply {
        put("status", "conflict")
        put("last_error", error.take(240))
      },
      "id = ?",
      arrayOf(id.toString()),
    )
  }

  fun entryFromOutbox(record: LifeLoadOutboxRecord): LifeLoadEntry =
    entryFromJson(JSONObject(record.payloadJson).getJSONObject("entry"))

  /**
   * Applies one server response only to the revision that produced it. A
   * response for an older revision can update the approved baseline while the
   * newer local draft remains active; it must never replace that draft.
   */
  fun applyOutboxAcknowledgement(record: LifeLoadOutboxRecord, payload: LifeLoadEntryPayload): LifeLoadOutboxApplyResult {
    if (record.generation != currentSyncGenerationLocked()) {
      markOutboxUploaded(record.id)
      return LifeLoadOutboxApplyResult.STALE
    }
    val sent = entryFromOutbox(record)
    val returned = if (record.operation == "approve") payload.approvedEntry ?: payload.entry else payload.draftEntry
    if (returned != sent) {
      markOutboxConflict(record.id, "server response did not match the complete local ${record.operation} payload")
      return LifeLoadOutboxApplyResult.CONFLICT
    }
    val current = getEntry(record.date)
    val hasNewerLocalRevision = current != null && current.revision > record.revision
    val acknowledgedBaseline = payload.approvedEntry ?: current?.approvedEntry
    val now = nowIso()
    writableDatabase.beginTransaction()
    try {
      val values = ContentValues().apply {
        put("date", record.date)
        if (record.operation == "approve" && !hasNewerLocalRevision) {
          put("state", "approved")
          put("entry_json", entryToJson(returned).toString())
          put("score_json", scoreToJson(payload.score).toString())
          put("approved_entry_json", entryToJson(returned).toString())
          put("approved_score_json", scoreToJson(payload.score).toString())
          put("approved_at", payload.approvedAt)
          put("draft_updated_at", "")
        } else if (record.operation == "approve") {
          put("state", "draft_over_approved")
          put("entry_json", entryToJson(current!!.entry).toString())
          put("score_json", "{}")
          put("approved_entry_json", entryToJson(returned).toString())
          put("approved_score_json", scoreToJson(payload.score).toString())
          put("approved_at", payload.approvedAt)
          put("draft_updated_at", current.draftUpdatedAt)
        } else {
          put("state", if (acknowledgedBaseline != null) "draft_over_approved" else "draft")
          put("entry_json", entryToJson(if (hasNewerLocalRevision) current!!.entry else returned).toString())
          put("score_json", "{}")
          put("approved_entry_json", acknowledgedBaseline?.let { entryToJson(it).toString() })
          put("approved_score_json", current?.approvedScore?.let { scoreToJson(it).toString() })
          put("approved_at", payload.approvedAt.ifBlank { current?.approvedAt.orEmpty() })
          put("draft_updated_at", if (hasNewerLocalRevision) current?.draftUpdatedAt.orEmpty() else payload.draftUpdatedAt)
        }
        put("source", "server")
        put("source_updated_at", payload.approvedAt.ifBlank { payload.draftUpdatedAt })
        put("local_updated_at", now)
        put("revision", current?.revision ?: record.revision)
      }
      writableDatabase.insertWithOnConflict("local_entry", null, values, SQLiteDatabase.CONFLICT_REPLACE)
      writableDatabase.update(
        "local_outbox",
        ContentValues().apply {
          put("status", "uploaded")
          put("last_error", "")
        },
        "id = ?",
        arrayOf(record.id.toString()),
      )
      writableDatabase.setTransactionSuccessful()
    } finally {
      writableDatabase.endTransaction()
    }
    return if (hasNewerLocalRevision) LifeLoadOutboxApplyResult.STALE else LifeLoadOutboxApplyResult.APPLIED
  }

  fun status(): LifeLoadLocalStoreStatus {
    val entries = scalarCount("SELECT COUNT(*) FROM local_entry")
    val pending = scalarCount("SELECT COUNT(*) FROM local_outbox WHERE status = 'pending'")
    val conflicts = scalarCount("SELECT COUNT(*) FROM local_outbox WHERE status = 'conflict'")
    return LifeLoadLocalStoreStatus(
      schemaVersion = LIFE_LOAD_LOCAL_SCHEMA_VERSION,
      entryCount = entries,
      pendingOutboxCount = pending,
      conflictOutboxCount = conflicts,
    )
  }

  fun selectedProfileConfig(): JSONObject =
    readableDatabase.query(
      "local_profile_config",
      arrayOf("config_json"),
      "id = ?",
      arrayOf(SELECTED_PROFILE_CONFIG_ID),
      null,
      null,
      null,
      "1",
    ).use { cursor ->
      if (cursor.moveToFirst()) JSONObject(cursor.getString(cursor.getColumnIndexOrThrow("config_json")))
      else defaultSelectedProfileConfig(defaultProfileId)
    }

  fun saveSelectedProfileConfig(config: JSONObject) {
    writableDatabase.insertWithOnConflict(
      "local_profile_config",
      null,
      ContentValues().apply {
        put("id", SELECTED_PROFILE_CONFIG_ID)
        put("config_json", JSONObject(config.toString()).toString())
        put("updated_at", nowIso())
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  fun signalDefinitions(): List<JSONObject> =
    jsonRows(
      table = "local_signal_definition",
      jsonColumn = "definition_json",
      orderBy = "signal_id ASC",
    )

  fun saveSignalDefinition(definition: JSONObject) {
    val signalId = definition.getString("id")
    writableDatabase.insertWithOnConflict(
      "local_signal_definition",
      null,
      ContentValues().apply {
        put("signal_id", signalId)
        put("definition_json", JSONObject(definition.toString()).toString())
        put("inert", if (definition.optBoolean("inert", signalId.isUnknownFutureSignalId())) 1 else 0)
        put("updated_at", nowIso())
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  fun signalEntries(): List<JSONObject> =
    jsonRows(
      table = "local_signal_entry",
      jsonColumn = "entry_json",
      orderBy = "date ASC, signal_id ASC",
    )

  fun saveSignalEntry(entry: JSONObject) {
    val signalId = entry.getString("signal_id")
    val date = entry.getString("date")
    writableDatabase.insertWithOnConflict(
      "local_signal_entry",
      null,
      ContentValues().apply {
        put("date", date)
        put("signal_id", signalId)
        put("entry_json", JSONObject(entry.toString()).toString())
        put("inert", if (entry.optBoolean("inert", signalId.isUnknownFutureSignalId())) 1 else 0)
        put("updated_at", nowIso())
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  fun exportDebugBundle(redacted: Boolean = true): String {
    val status = status()
    var approvedCount = 0
    var draftCount = 0
    var pendingApprovalCount = 0
    val entries = JSONArray()
    readableDatabase.query(
      "local_entry",
      null,
      null,
      null,
      null,
      null,
      "date ASC",
    ).use { cursor ->
      while (cursor.moveToNext()) {
        val entryJson = cursor.getString(cursor.getColumnIndexOrThrow("entry_json"))
        when (cursor.getString(cursor.getColumnIndexOrThrow("state"))) {
          "approved" -> approvedCount += 1
          "draft" -> draftCount += 1
          "pending_approval" -> pendingApprovalCount += 1
        }
        entries.put(
          JSONObject()
            .put("date", cursor.getString(cursor.getColumnIndexOrThrow("date")))
            .put("state", cursor.getString(cursor.getColumnIndexOrThrow("state")))
            .put("source", cursor.getString(cursor.getColumnIndexOrThrow("source")))
            .put("approved_at", cursor.getString(cursor.getColumnIndexOrThrow("approved_at")))
            .put("draft_updated_at", cursor.getString(cursor.getColumnIndexOrThrow("draft_updated_at")))
            .put("local_updated_at", cursor.getString(cursor.getColumnIndexOrThrow("local_updated_at")))
            .put("revision", cursor.getLong(cursor.getColumnIndexOrThrow("revision")))
            .put("entry_json", if (redacted) JSONObject().put("redacted", true) else JSONObject(entryJson))
            .put(
              "approved_entry_json",
              if (redacted || cursor.isNull(cursor.getColumnIndexOrThrow("approved_entry_json"))) JSONObject().put("redacted", redacted).put("present", !cursor.isNull(cursor.getColumnIndexOrThrow("approved_entry_json")))
              else JSONObject(cursor.getString(cursor.getColumnIndexOrThrow("approved_entry_json"))),
            )
            .put(
              "score_json",
              if (redacted) JSONObject().put("present", cursor.getString(cursor.getColumnIndexOrThrow("score_json")).isNotBlank())
              else JSONObject(cursor.getString(cursor.getColumnIndexOrThrow("score_json"))),
            )
            .put(
              "approved_score_json",
              if (redacted || cursor.isNull(cursor.getColumnIndexOrThrow("approved_score_json"))) JSONObject().put("redacted", redacted).put("present", !cursor.isNull(cursor.getColumnIndexOrThrow("approved_score_json")))
              else JSONObject(cursor.getString(cursor.getColumnIndexOrThrow("approved_score_json"))),
            ),
        )
      }
    }
    val outbox = JSONArray()
    readableDatabase.query(
      "local_outbox",
      null,
      null,
      null,
      null,
      null,
      "created_at ASC, id ASC",
    ).use { cursor ->
      while (cursor.moveToNext()) {
        val payloadJson = cursor.getString(cursor.getColumnIndexOrThrow("payload_json"))
        outbox.put(
          JSONObject()
            .put("operation", cursor.getString(cursor.getColumnIndexOrThrow("operation")))
            .put("date", cursor.getString(cursor.getColumnIndexOrThrow("date")))
            .put("status", cursor.getString(cursor.getColumnIndexOrThrow("status")))
            .put("created_at", cursor.getString(cursor.getColumnIndexOrThrow("created_at")))
            .put("last_error", cursor.getString(cursor.getColumnIndexOrThrow("last_error")))
            .put("revision", cursor.getLong(cursor.getColumnIndexOrThrow("revision")))
            .put("generation", cursor.getLong(cursor.getColumnIndexOrThrow("generation")))
            .put("payload_json", if (redacted) JSONObject().put("redacted", true) else JSONObject(payloadJson)),
        )
      }
    }
    val signalDefinitions = JSONArray()
    signalDefinitions().forEach { definition ->
      signalDefinitions.put(
        if (redacted) JSONObject().put("redacted", true).put("id", definition.optString("id"))
        else definition,
      )
    }
    val signalEntries = JSONArray()
    signalEntries().forEach { entry ->
      signalEntries.put(
        if (redacted) JSONObject().put("redacted", true).put("signal_id", entry.optString("signal_id"))
        else entry,
      )
    }
    return JSONObject()
      .put("schema_version", LIFE_LOAD_DEBUG_BUNDLE_VERSION)
      .put("redaction", if (redacted) "redacted" else "full_local_only")
      .put(
        "status",
        JSONObject()
          .put("schema_version", status.schemaVersion)
          .put("entry_count", status.entryCount)
          .put("pending_outbox_count", status.pendingOutboxCount)
          .put("conflict_outbox_count", status.conflictOutboxCount),
      )
      .put(
        "counts",
        JSONObject()
          .put("entries", status.entryCount)
          .put("outbox", status.pendingOutboxCount)
          .put("conflicts", status.conflictOutboxCount)
          .put("approved", approvedCount)
          .put("draft", draftCount)
          .put("pending_approval", pendingApprovalCount),
      )
      .put("entries", entries)
      .put("outbox", outbox)
      .put("profile_template", profileTemplateForExport())
      .put("selected_profile_config", if (redacted) JSONObject().put("redacted", true) else selectedProfileConfig())
      .put("signal_definitions", signalDefinitions)
      .put("signal_entries", signalEntries)
      .put("optional_packs", if (redacted) JSONArray() else metadataJsonArray(FUTURE_OPTIONAL_PACKS_METADATA_KEY))
      .put("influence_policies", if (redacted) JSONArray() else metadataJsonArray(FUTURE_INFLUENCE_POLICIES_METADATA_KEY))
      .put("contract_notes", futureExportContractNotes())
      .toString()
  }

  fun resetLocalData() {
    writableDatabase.beginTransaction()
    try {
      resetLocalDataLocked()
      writableDatabase.setTransactionSuccessful()
    } finally {
      writableDatabase.endTransaction()
    }
  }

  fun exportLocalDataFile(): LifeLoadLocalExportResult {
    val bundle = exportDebugBundle(redacted = false)
    val status = status()
    val exportDir = File(appContext.filesDir, "life_load_exports").apply { mkdirs() }
    val exportFile = File(exportDir, "life_load_local_export.json")
    exportFile.writeText(bundle, Charsets.UTF_8)
    return LifeLoadLocalExportResult(
      path = exportFile.absolutePath,
      entryCount = status.entryCount,
      outboxCount = status.pendingOutboxCount,
    )
  }

  fun deleteLocalDataAndExports(): LifeLoadLocalStoreStatus {
    resetLocalData()
    File(appContext.filesDir, "life_load_exports").deleteRecursively()
    return status()
  }

  fun restoreDebugBundle(bundleJson: String) {
    val bundle = JSONObject(bundleJson)
    require(bundle.optString("schema_version") == LIFE_LOAD_DEBUG_BUNDLE_VERSION) { "unsupported local debug bundle" }
    require(bundle.optString("redaction") == "full_local_only") { "redacted bundles cannot restore local data" }
    writableDatabase.beginTransaction()
    try {
      resetLocalDataLocked()
      val entries = bundle.optJSONArray("entries") ?: JSONArray()
      for (index in 0 until entries.length()) {
        val row = entries.getJSONObject(index)
        writableDatabase.insertWithOnConflict(
          "local_entry",
          null,
          ContentValues().apply {
            put("date", row.getString("date"))
            put("state", row.getString("state"))
            put("entry_json", row.getJSONObject("entry_json").toString())
            put("score_json", row.getJSONObject("score_json").toString())
            put(
              "approved_entry_json",
              row.optJSONObject("approved_entry_json")
                ?.takeIf { it.optBoolean("present", true) }
                ?.takeUnless { it.optBoolean("redacted", false) }
                ?.toString(),
            )
            put(
              "approved_score_json",
              row.optJSONObject("approved_score_json")
                ?.takeIf { it.optBoolean("present", true) }
                ?.takeUnless { it.optBoolean("redacted", false) }
                ?.toString(),
            )
            put("approved_at", row.optString("approved_at"))
            put("draft_updated_at", row.optString("draft_updated_at"))
            put("source", row.optString("source"))
            put("source_updated_at", "")
            put("local_updated_at", row.optString("local_updated_at").ifBlank { nowIso() })
            put("revision", row.optLong("revision", 0L))
          },
          SQLiteDatabase.CONFLICT_REPLACE,
        )
      }
      val outbox = bundle.optJSONArray("outbox") ?: JSONArray()
      for (index in 0 until outbox.length()) {
        val row = outbox.getJSONObject(index)
        writableDatabase.insert(
          "local_outbox",
          null,
          ContentValues().apply {
            put("operation", row.getString("operation"))
            put("date", row.getString("date"))
            put("payload_json", row.getJSONObject("payload_json").toString())
            put("status", row.optString("status", "pending"))
            put("created_at", row.optString("created_at").ifBlank { nowIso() })
            put("last_error", row.optString("last_error"))
            put("revision", row.optLong("revision", 0L))
            // Restored data belongs to the new local generation created by
            // resetLocalDataLocked; an old generation would be discarded as
            // a late response on the next sync.
            put("generation", currentSyncGenerationLocked())
          },
        )
      }
      restoreFutureSignalSectionsLocked(bundle)
      writableDatabase.setTransactionSuccessful()
    } finally {
      writableDatabase.endTransaction()
    }
  }

  private fun enqueueOutboxLocked(operation: String, entry: LifeLoadEntry, createdAt: String, revision: Long) {
    if (operation == "draft_upsert") {
      // A text edit can produce many local saves. Keep one latest draft
      // operation per date so sync replays the current revision only.
      writableDatabase.delete(
        "local_outbox",
        "date = ? AND operation = 'draft_upsert' AND status = 'pending'",
        arrayOf(entry.date),
      )
    }
    writableDatabase.insert(
      "local_outbox",
      null,
      ContentValues().apply {
        put("operation", operation)
        put("date", entry.date)
        put(
          "payload_json",
          JSONObject()
            .put("entry", entryToJson(entry))
            .put("revision", revision)
            .put("generation", currentSyncGenerationLocked())
            .toString(),
        )
        put("status", "pending")
        put("created_at", createdAt)
        put("last_error", "")
        put("revision", revision)
        put("generation", currentSyncGenerationLocked())
      },
    )
  }

  private fun recordFromCursor(cursor: Cursor): LifeLoadLocalEntryRecord {
    val approvedEntryIndex = cursor.getColumnIndexOrThrow("approved_entry_json")
    val approvedScoreIndex = cursor.getColumnIndexOrThrow("approved_score_json")
    return LifeLoadLocalEntryRecord(
      date = cursor.getString(cursor.getColumnIndexOrThrow("date")),
      state = cursor.getString(cursor.getColumnIndexOrThrow("state")),
      entry = entryFromJson(JSONObject(cursor.getString(cursor.getColumnIndexOrThrow("entry_json")))),
      score = scoreFromJson(JSONObject(cursor.getString(cursor.getColumnIndexOrThrow("score_json")))),
      approvedAt = cursor.getString(cursor.getColumnIndexOrThrow("approved_at")),
      draftUpdatedAt = cursor.getString(cursor.getColumnIndexOrThrow("draft_updated_at")),
      source = cursor.getString(cursor.getColumnIndexOrThrow("source")),
      localUpdatedAt = cursor.getString(cursor.getColumnIndexOrThrow("local_updated_at")),
      approvedEntry = if (cursor.isNull(approvedEntryIndex)) null else entryFromJson(JSONObject(cursor.getString(approvedEntryIndex))),
      approvedScore = if (cursor.isNull(approvedScoreIndex)) null else scoreFromJson(JSONObject(cursor.getString(approvedScoreIndex))),
      revision = cursor.getLong(cursor.getColumnIndexOrThrow("revision")),
    )
  }

  private fun resetLocalDataLocked() {
    val nextGeneration = currentSyncGenerationLocked() + 1L
    writableDatabase.delete("local_outbox", null, null)
    writableDatabase.delete("local_entry", null, null)
    writableDatabase.delete("local_profile_config", null, null)
    writableDatabase.delete("local_signal_definition", null, null)
    writableDatabase.delete("local_signal_entry", null, null)
    writableDatabase.delete(
      "local_metadata",
      "key IN (?, ?)",
      arrayOf(FUTURE_OPTIONAL_PACKS_METADATA_KEY, FUTURE_INFLUENCE_POLICIES_METADATA_KEY),
    )
    writableDatabase.insertWithOnConflict(
      "local_metadata",
      null,
      ContentValues().apply {
        put("key", SYNC_GENERATION_METADATA_KEY)
        put("value", nextGeneration.toString())
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  private fun hasPendingLocalWrite(date: String): Boolean =
    readableDatabase.rawQuery(
      "SELECT COUNT(*) FROM local_outbox WHERE date = ? AND status IN ('pending', 'conflict')",
      arrayOf(date),
    ).use { cursor ->
      cursor.moveToFirst() && cursor.getInt(0) > 0
    }

  private fun currentSyncGenerationLocked(): Long =
    writableDatabase.query(
      "local_metadata",
      arrayOf("value"),
      "key = ?",
      arrayOf(SYNC_GENERATION_METADATA_KEY),
      null,
      null,
      null,
      "1",
    ).use { cursor ->
      if (!cursor.moveToFirst()) 0L else cursor.getString(0).toLongOrNull() ?: 0L
    }

  private fun requireEntry(date: String): LifeLoadLocalEntryRecord =
    getEntry(date) ?: error("local entry was not saved for $date")

  private fun scalarCount(sql: String): Int =
    readableDatabase.rawQuery(sql, emptyArray()).use { cursor ->
      if (cursor.moveToFirst()) cursor.getInt(0) else 0
    }

  private fun jsonRows(table: String, jsonColumn: String, orderBy: String): List<JSONObject> =
    readableDatabase.query(
      table,
      arrayOf(jsonColumn),
      null,
      null,
      null,
      null,
      orderBy,
    ).use { cursor ->
      buildList {
        while (cursor.moveToNext()) add(JSONObject(cursor.getString(cursor.getColumnIndexOrThrow(jsonColumn))))
      }
    }

  private fun restoreFutureSignalSectionsLocked(bundle: JSONObject) {
    val config = bundle.optJSONObject("selected_profile_config")
    if (config != null && !config.optBoolean("redacted", false)) {
      writableDatabase.insertWithOnConflict(
        "local_profile_config",
        null,
        ContentValues().apply {
          put("id", SELECTED_PROFILE_CONFIG_ID)
          put("config_json", JSONObject(config.toString()).toString())
          put("updated_at", nowIso())
        },
        SQLiteDatabase.CONFLICT_REPLACE,
      )
    }
    restoreSignalDefinitionsLocked(bundle.optJSONArray("signal_definitions") ?: JSONArray())
    restoreSignalEntriesLocked(bundle.optJSONArray("signal_entries") ?: JSONArray())
    saveMetadataJsonArrayLocked(FUTURE_OPTIONAL_PACKS_METADATA_KEY, bundle.optJSONArray("optional_packs") ?: JSONArray())
    saveMetadataJsonArrayLocked(FUTURE_INFLUENCE_POLICIES_METADATA_KEY, bundle.optJSONArray("influence_policies") ?: JSONArray())
  }

  private fun restoreSignalDefinitionsLocked(definitions: JSONArray) {
    for (index in 0 until definitions.length()) {
      val definition = definitions.optJSONObject(index) ?: continue
      if (definition.optBoolean("redacted", false)) continue
      val signalId = definition.optString("id")
      if (signalId.isBlank()) continue
      writableDatabase.insertWithOnConflict(
        "local_signal_definition",
        null,
        ContentValues().apply {
          put("signal_id", signalId)
          put("definition_json", JSONObject(definition.toString()).toString())
          put("inert", if (signalId.isUnknownFutureSignalId()) 1 else 0)
          put("updated_at", nowIso())
        },
        SQLiteDatabase.CONFLICT_REPLACE,
      )
    }
  }

  private fun restoreSignalEntriesLocked(entries: JSONArray) {
    for (index in 0 until entries.length()) {
      val entry = entries.optJSONObject(index) ?: continue
      if (entry.optBoolean("redacted", false)) continue
      val signalId = entry.optString("signal_id")
      val date = entry.optString("date")
      if (signalId.isBlank() || date.isBlank()) continue
      writableDatabase.insertWithOnConflict(
        "local_signal_entry",
        null,
        ContentValues().apply {
          put("date", date)
          put("signal_id", signalId)
          put("entry_json", JSONObject(entry.toString()).toString())
          put("inert", if (signalId.isUnknownFutureSignalId()) 1 else 0)
          put("updated_at", nowIso())
        },
        SQLiteDatabase.CONFLICT_REPLACE,
      )
    }
  }

  private fun saveMetadataJsonArrayLocked(key: String, value: JSONArray) {
    writableDatabase.insertWithOnConflict(
      "local_metadata",
      null,
      ContentValues().apply {
        put("key", key)
        put("value", JSONArray(value.toString()).toString())
      },
      SQLiteDatabase.CONFLICT_REPLACE,
    )
  }

  private fun metadataJsonArray(key: String): JSONArray =
    readableDatabase.query(
      "local_metadata",
      arrayOf("value"),
      "key = ?",
      arrayOf(key),
      null,
      null,
      null,
      "1",
    ).use { cursor ->
      if (cursor.moveToFirst()) JSONArray(cursor.getString(cursor.getColumnIndexOrThrow("value"))) else JSONArray()
    }

  private fun profileTemplateForExport(): JSONObject {
    val config = selectedProfileConfig()
    return JSONObject()
      .put("id", config.optString("active_profile_id", "personal_legacy"))
      .put("version", config.optInt("template_version", 1))
      .put("signal_ids", config.optJSONArray("enabled_signal_ids") ?: JSONArray())
  }

  private fun futureExportContractNotes(): JSONObject =
    JSONObject()
      .put("fixed_entries_are_compatibility_truth", true)
      .put("signal_sections_are_additive_future_data", true)
      .put("unknown_signal_definitions_import_mode", "preserve_inert")
      .put("unknown_signal_entries_import_mode", "preserve_inert")
      .put(
        "delete_reset_must_clear",
        JSONArray(
          listOf(
            "selected_profile_config",
            "signal_definitions",
            "signal_entries",
            "optional_pack_selections",
            "influence_overrides",
          ),
        ),
      )
      .put("sensitive_labels_must_not_be_logged", true)
}

private fun nowIso(): String = Instant.now().toString()

private fun defaultSelectedProfileConfig(profileId: String = "personal_legacy"): JSONObject =
  LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId).toJson()

private fun String.isUnknownFutureSignalId(): Boolean =
  startsWith("custom.") || startsWith("future.")

private fun entryToJson(entry: LifeLoadEntry): JSONObject =
  JSONObject()
    .put("date", entry.date)
    .put("diary_text", entry.diaryText)
    .put("diary_summary", entry.diarySummary)
    .put("tags", JSONArray(entry.tags))
    .putNullable("sleep_ok", entry.sleepOk)
    .putNullable("nutrition_ok", entry.nutritionOk)
    .putNullable("alcohol", entry.alcohol)
    .putNullable("binge", entry.binge)
    .putNullable("mood", entry.mood)
    .putNullable("stress", entry.stress)
    .putNullable("energy", entry.energy)
    .putNullable("coffee_cups", entry.coffeeCups)
    .putNullable("foot_pain", entry.footPain)
    .putNullable("shoulder_pain", entry.shoulderPain)
    .putNullable("migraine_warning", entry.migraineWarning)
    .putNullable("decompression_done", entry.decompressionDone)
    .putNullable("after_work_decompression_done", entry.afterWorkDecompressionDone)
    .putNullable("evening_chain_broken", entry.eveningChainBroken)
    .putNullable("shutdown_done", entry.shutdownDone)
    .putNullable("phone_after_21", entry.phoneAfter21)
    .putNullable("project_overrun", entry.projectOverrun)
    .put("primary_activity_type", entry.primaryActivityType)
    .put("activity_types", JSONArray(entry.activityTypes))
    .putNullable("activity_duration_min", entry.activityDurationMin)
    .putNullable("rehab_done", entry.rehabDone)
    .put("other_symptoms", entry.otherSymptoms)
    .put("work_intensity", entry.workIntensity)
    .putNullable("family_stress", entry.familyStress)
    .putNullable("wife_conflict_count", entry.wifeConflictCount)
    .putNullable("wife_conflict_school", entry.wifeConflictSchool)
    .putNullable("wife_conflict_chores", entry.wifeConflictChores)
    .putNullable("wife_conflict_other", entry.wifeConflictOther)
    .putNullable("home_office", entry.homeOffice)
    .putNullable("alone_home", entry.aloneHome)
    .putNullable("homework_done", entry.homeworkDone)
    .putNullable("homework_status", entry.homeworkStatus)

private fun entryFromJson(obj: JSONObject): LifeLoadEntry =
  LifeLoadEntry(
    date = obj.optString("date"),
    diaryText = obj.optString("diary_text"),
    diarySummary = obj.optString("diary_summary"),
    tags = obj.optJSONArray("tags")?.let { array -> List(array.length()) { array.optString(it) } } ?: emptyList(),
    sleepOk = obj.optNullableBoolean("sleep_ok"),
    nutritionOk = obj.optNullableBoolean("nutrition_ok"),
    alcohol = obj.optNullableString("alcohol"),
    binge = obj.optNullableBoolean("binge"),
    mood = obj.optNullableInt("mood"),
    stress = obj.optNullableInt("stress"),
    energy = obj.optNullableInt("energy"),
    coffeeCups = obj.optNullableInt("coffee_cups"),
    footPain = obj.optNullableInt("foot_pain"),
    shoulderPain = obj.optNullableInt("shoulder_pain"),
    migraineWarning = obj.optNullableBoolean("migraine_warning"),
    decompressionDone = obj.optNullableBoolean("decompression_done"),
    afterWorkDecompressionDone = obj.optNullableBoolean("after_work_decompression_done"),
    eveningChainBroken = obj.optNullableBoolean("evening_chain_broken"),
    shutdownDone = obj.optNullableBoolean("shutdown_done"),
    phoneAfter21 = obj.optNullableBoolean("phone_after_21"),
    projectOverrun = obj.optNullableBoolean("project_overrun"),
    primaryActivityType = obj.optString("primary_activity_type"),
    activityTypes = obj.optJSONArray("activity_types")?.let { array ->
      List(array.length()) { array.optString(it) }.filter(String::isNotBlank)
    } ?: listOfNotNull(obj.optString("primary_activity_type").takeIf { it.isNotBlank() }),
    activityDurationMin = obj.optNullableInt("activity_duration_min"),
    rehabDone = obj.optNullableBoolean("rehab_done"),
    otherSymptoms = obj.optString("other_symptoms"),
    workIntensity = obj.optString("work_intensity"),
    familyStress = obj.optNullableInt("family_stress"),
    wifeConflictCount = obj.optNullableInt("wife_conflict_count"),
    wifeConflictSchool = obj.optNullableBoolean("wife_conflict_school"),
    wifeConflictChores = obj.optNullableBoolean("wife_conflict_chores"),
    wifeConflictOther = obj.optNullableBoolean("wife_conflict_other"),
    homeOffice = obj.optNullableBoolean("home_office"),
    aloneHome = obj.optNullableBoolean("alone_home"),
    homeworkDone = obj.optNullableBoolean("homework_done"),
    homeworkStatus = obj.optNullableString("homework_status"),
  )

private fun scoreToJson(score: LifeLoadScore): JSONObject =
  JSONObject()
    .put("zone", score.zone)
    .put("mode", score.mode)
    .put("next_action", score.nextAction)
    .put("minimum_action", score.minimumAction)
    .put("avoid", score.avoid)
    .put("why", JSONArray(score.why))
    .putNullableFinite("confidence", score.confidence)
    .put("life_load_score", score.lifeLoadScore.finiteOrZero())
    .put("base_score", score.baseScore.finiteOrZero())
    .put("profile_adjusted_score", score.profileAdjustedScore.finiteOrZero())
    .put(
      "guidance_thresholds",
      JSONObject()
        .put("medium", score.guidanceMediumThreshold)
        .put("high", score.guidanceHighThreshold),
    )
    .put("profile_modifiers", JSONArray(score.profileModifiers))
    .put("profile_effects", JSONArray(score.profileEffects))
    .put("training_load", score.trainingLoad.finiteOrZero())
    .put("recovery_score", score.recoveryScore.finiteOrZero())
    .put("strain_score", score.strainScore.finiteOrZero())
    .put("hard_sessions", score.hardSessions)
    .put("rehab_sessions", score.rehabSessions)
    .put("acute_training_load", score.acuteTrainingLoad.finiteOrZero())
    .put("chronic_training_load", score.chronicTrainingLoad.finiteOrZero())
    .putNullableFinite("training_load_ratio", score.trainingLoadRatio)
    .put("training_ramp", score.trainingRamp.finiteOrZero())
    .put("warnings", JSONArray(score.warnings))
    .put("red_flags", JSONArray(score.redFlags))

private fun scoreFromJson(obj: JSONObject): LifeLoadScore =
  LifeLoadScore(
    zone = obj.optString("zone"),
    mode = obj.optString("mode"),
    nextAction = obj.optString("next_action"),
    minimumAction = obj.optString("minimum_action"),
    avoid = obj.optString("avoid"),
    why = obj.optJSONArray("why").toStringList(),
    confidence = obj.optNullableDouble("confidence"),
    lifeLoadScore = obj.optDouble("life_load_score", 0.0),
    baseScore = obj.optDouble("base_score", 0.0),
    profileAdjustedScore = obj.optDouble("profile_adjusted_score", 0.0),
    guidanceMediumThreshold = obj.optJSONObject("guidance_thresholds")?.optInt("medium", 35) ?: 35,
    guidanceHighThreshold = obj.optJSONObject("guidance_thresholds")?.optInt("high", 70) ?: 70,
    profileModifiers = obj.optJSONArray("profile_modifiers").toStringList(),
    profileEffects = obj.optJSONArray("profile_effects").toStringList(),
    trainingLoad = obj.optDouble("training_load", 0.0),
    recoveryScore = obj.optDouble("recovery_score", 0.0),
    strainScore = obj.optDouble("strain_score", 0.0),
    hardSessions = obj.optInt("hard_sessions", 0),
    rehabSessions = obj.optInt("rehab_sessions", 0),
    acuteTrainingLoad = obj.optDouble("acute_training_load", 0.0),
    chronicTrainingLoad = obj.optDouble("chronic_training_load", 0.0),
    trainingLoadRatio = obj.optNullableDouble("training_load_ratio"),
    trainingRamp = obj.optDouble("training_ramp", 0.0),
    warnings = obj.optJSONArray("warnings").toStringList(),
    redFlags = obj.optJSONArray("red_flags").toStringList(),
  )

private fun JSONObject.putNullable(key: String, value: Any?): JSONObject =
  put(key, value ?: JSONObject.NULL)

private fun JSONObject.putNullableFinite(key: String, value: Double?): JSONObject =
  put(key, value?.takeIf { it.isFinite() } ?: JSONObject.NULL)

private fun Double.finiteOrZero(): Double = if (isFinite()) this else 0.0

private fun JSONObject.optNullableBoolean(key: String): Boolean? =
  if (has(key) && !isNull(key)) optBoolean(key) else null

private fun JSONObject.optNullableInt(key: String): Int? =
  if (has(key) && !isNull(key)) optInt(key) else null

private fun JSONObject.optNullableDouble(key: String): Double? =
  if (has(key) && !isNull(key)) optDouble(key) else null

private fun JSONObject.optNullableString(key: String): String? =
  if (has(key) && !isNull(key)) optString(key) else null

private fun JSONArray?.toStringList(): List<String> =
  if (this == null) emptyList() else List(length()) { optString(it) }
