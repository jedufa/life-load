package com.life.lifeload.data

import com.life.lifeload.BuildConfig
import com.life.lifeload.domain.LifeLoadAnalyzeResult
import com.life.lifeload.data.LifeLoadDebugMirrorResult
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadDriftSnapshot
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadFlag
import com.life.lifeload.domain.LifeLoadHistoryDay
import com.life.lifeload.domain.LifeLoadFormulaContract
import com.life.lifeload.domain.LifeLoadFormulaItem
import com.life.lifeload.domain.LifeLoadFormulaSection
import com.life.lifeload.domain.LifeLoadGarminImportResult
import com.life.lifeload.domain.LifeLoadGarminSettings
import com.life.lifeload.domain.LifeLoadDailyFlowSettings
import com.life.lifeload.domain.LifeLoadDebugSettings
import com.life.lifeload.domain.LifeLoadFormulaSettings
import com.life.lifeload.domain.LifeLoadPlatformContract
import com.life.lifeload.domain.LifeLoadProposal
import com.life.lifeload.domain.LifeLoadRecentWeek
import com.life.lifeload.domain.LifeLoadReminderSettings
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.LifeLoadTrendPoint
import com.life.lifeload.domain.LifeLoadWeekContext
import com.life.lifeload.domain.LifeLoadWeeklyMini
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class LifeLoadAuthRequiredException(message: String) : IllegalStateException(message)

class HttpLifeLoadApi(
  private val client: OkHttpClient = OkHttpClient.Builder()
    .retryOnConnectionFailure(true)
    .connectTimeout(10, TimeUnit.SECONDS)
    .writeTimeout(30, TimeUnit.SECONDS)
    .readTimeout(30, TimeUnit.SECONDS)
    .callTimeout(35, TimeUnit.SECONDS)
    .build(),
  serverBaseUrl: String = BuildConfig.SERVER_BASE_URL,
  private val serverBaseUrlProvider: (() -> String)? = null,
  private val authTokenProvider: (() -> String)? = null,
) : LifeLoadApi {
  private val fallbackBaseUrl = ServerConfig.normalizeBaseUrl(serverBaseUrl)

  private fun baseUrl(): String = ServerConfig.normalizeBaseUrl(serverBaseUrlProvider?.invoke() ?: fallbackBaseUrl)
  private fun path(path: String): String = "${baseUrl()}$path"
  private fun authToken(): String = authTokenProvider?.invoke().orEmpty()

  private fun requestBuilder(url: String, authenticated: Boolean = true): Request.Builder {
    val builder = Request.Builder().url(url)
    if (authenticated) {
      val token = authToken()
      if (token.isNotBlank()) {
        builder.header("Authorization", "Bearer $token")
      }
    }
    return builder
  }

  override suspend fun isBackendHealthy(): Boolean {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/health"), authenticated = false).get().build()
      executeGetWithRetry(request).use { response ->
        response.isSuccessful
      }
    }
  }

  override suspend fun register(email: String, password: String): LifeLoadAuthSession {
    return authRequest("/api/mobile/life-load/auth/register", email, password)
  }

  override suspend fun login(email: String, password: String): LifeLoadAuthSession {
    return authRequest("/api/mobile/life-load/auth/login", email, password)
  }

  override suspend fun logout() {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/auth/logout"))
        .post(JSONObject().toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
      }
    }
  }

  private suspend fun authRequest(pathValue: String, email: String, password: String): LifeLoadAuthSession {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path(pathValue), authenticated = false)
        .post(
          JSONObject()
            .put("email", email)
            .put("password", password)
            .put("device_label", "Life Load Android")
            .put("platform", "android")
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        val obj = JSONObject(body)
        LifeLoadAuthSession(
          email = email.trim(),
          userId = obj.optString("user_id"),
          deviceId = obj.optString("device_id"),
          sessionToken = obj.optString("session_token"),
        )
      }
    }
  }

  override suspend fun getContract(): LifeLoadPlatformContract {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/contract"), authenticated = false).get().build()
      executeGetWithRetry(request).use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parsePlatformContract(JSONObject(body))
      }
    }
  }

  override suspend fun getSettings(): LifeLoadSettings {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/settings")).get().build()
      executeGetWithRetry(request).use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseSettings(JSONObject(body).optJSONObject("settings") ?: JSONObject(body))
      }
    }
  }

  override suspend fun saveSettings(settings: LifeLoadSettings, garminPassword: String): LifeLoadSettings {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/settings"))
        .post(
          JSONObject()
            .put("settings", settingsJson(settings, garminPassword))
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseSettings(JSONObject(body).optJSONObject("settings") ?: JSONObject(body))
      }
    }
  }

  override suspend fun getEntry(date: String): LifeLoadEntryPayload {
    return withContext(Dispatchers.IO) {
      val encoded = URLEncoder.encode(date, Charsets.UTF_8.name())
      val request = requestBuilder(path("/api/mobile/life-load/entry?date=$encoded")).get().build()
      executeGetWithRetry(request).use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseEntryPayload(JSONObject(body))
      }
    }
  }

  override suspend fun saveEntry(entry: LifeLoadEntry, action: String): LifeLoadEntryPayload {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/draft"))
        .post(
          JSONObject()
            .put("action", action)
            .put("entry", entryJson(entry))
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseEntryPayload(JSONObject(body))
      }
    }
  }

  override suspend fun analyzeDiary(entry: LifeLoadEntry): LifeLoadAnalyzeResult {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/analyze-diary"))
        .post(
          JSONObject()
            .put("date", entry.date)
            .put("diary_text", entry.diaryText)
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        val obj = JSONObject(body)
        val parsedProposal = parseProposal(obj.optJSONObject("proposal"))
        val warnings = stringArray(obj.optJSONArray("warnings")).joinToString("; ")
        val proposal = if (obj.optJSONObject("proposal") == null && warnings.isNotBlank()) {
          parsedProposal.copy(fallbackError = warnings)
        } else {
          parsedProposal
        }
        LifeLoadAnalyzeResult(
          payload = parseEntryPayload(obj),
          proposal = proposal,
          extractorVersion = obj.optString("extractor_version").ifBlank { proposal.extractorVersion },
          extractorModel = obj.optString("extractor_model").ifBlank { obj.optJSONObject("proposal")?.optString("extractor_model").orEmpty() },
          extractorTimeoutS = obj.optInt("extractor_timeout_s", 0),
        )
      }
    }
  }

  override suspend fun approveEntry(entry: LifeLoadEntry): LifeLoadEntryPayload {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/approve"))
        .post(
          JSONObject()
            .put("date", entry.date)
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseEntryPayload(JSONObject(body))
      }
    }
  }

  override suspend fun importGarmin(date: String, days: Int): LifeLoadGarminImportResult {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/garmin-live-import"))
        .post(
          JSONObject()
            .put("date", date)
            .put("days", days)
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseGarminImportResult(JSONObject(body))
      }
    }
  }

  override suspend fun getDashboard(date: String, weeks: Int): LifeLoadDashboard {
    return withContext(Dispatchers.IO) {
      val encodedDate = URLEncoder.encode(date, Charsets.UTF_8.name())
      val request = requestBuilder(path("/api/mobile/life-load/dashboard?date=$encodedDate&weeks=$weeks"))
        .get()
        .build()
      executeGetWithRetry(request).use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        parseDashboard(JSONObject(body))
      }
    }
  }

  override suspend fun mirrorLocalDebugBundle(bundleJson: String): LifeLoadDebugMirrorResult {
    return withContext(Dispatchers.IO) {
      val request = requestBuilder(path("/api/mobile/life-load/debug/local-mirror"))
        .post(
          JSONObject()
            .put("bundle", JSONObject(bundleJson))
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType()),
        )
        .build()
      client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        ensureSuccess(response.code, body)
        val obj = JSONObject(body)
        LifeLoadDebugMirrorResult(
          path = obj.optString("path"),
          entryCount = obj.optInt("entry_count"),
          pendingOutboxCount = obj.optInt("pending_outbox_count"),
          conflictOutboxCount = obj.optInt("conflict_outbox_count"),
        )
      }
    }
  }

  private fun parseGarminImportResult(obj: JSONObject): LifeLoadGarminImportResult {
    return LifeLoadGarminImportResult(
      payload = obj.optJSONObject("entry")?.let(::parseEntryPayload),
      daysImported = obj.optInt("days_imported", 0),
      passiveUpserted = obj.optInt("passive_upserted", 0),
      activityUpserted = obj.optInt("activity_upserted", 0),
      skippedReason = obj.optString("skipped_reason"),
    )
  }

  private fun executeGetWithRetry(request: Request): okhttp3.Response {
    try {
      return client.newCall(request).execute()
    } catch (error: IOException) {
      return client.newCall(request).execute()
    }
  }

  private fun ensureSuccess(code: Int, body: String) {
    if (code in 200..299) return
    val message = runCatching {
      JSONObject(body).optString("error").ifBlank { JSONObject(body).optString("message") }
    }.getOrDefault("")
    if (code == 401 || code == 403) {
      throw LifeLoadAuthRequiredException(message.ifBlank { "Sign in again." })
    }
    throw IllegalStateException(if (message.isNotBlank()) message else "HTTP $code")
  }

  private fun parseEntryPayload(obj: JSONObject): LifeLoadEntryPayload {
    val coreDraft = obj.optJSONObject("draftEntry")
    val date = obj.optString("date")
    val blank = LifeLoadEntry(date = date)
    val entryState = obj.optString("entry_state").ifBlank {
      if (obj.optJSONObject("entry") != null) "approved" else if (coreDraft != null) "draft" else "blank"
    }
    val active = obj.optJSONObject("entry")?.let(::parseEntry)
    val approved = obj.optJSONObject("approved_entry")?.let(::parseEntry)
      ?: active?.takeIf { entryState == "approved" }
    val draft = coreDraft?.let(::parseDraftEntry)
      ?: active?.takeIf { obj.optBoolean("has_draft", entryState == "draft" || entryState == "draft_over_approved") }
      ?: blank
    val summary = obj.optJSONObject("summary")
    val scoreObject = obj.optJSONObject("score") ?: summary
    return LifeLoadEntryPayload(
      date = date,
      defaultDate = obj.optString("default_date").ifBlank { date },
      previousDate = obj.optString("previous_date"),
      nextDate = obj.optString("next_date"),
      entryState = entryState,
      hasDraft = obj.optBoolean("has_draft", coreDraft != null || entryState == "draft" || entryState == "draft_over_approved"),
      entryExists = obj.optBoolean("entry_exists", obj.optJSONObject("entry") != null),
      approvedAt = obj.optString("approved_at").ifBlank { obj.optJSONObject("entry")?.optString("approved_at").orEmpty() },
      draftUpdatedAt = obj.optString("draft_updated_at").ifBlank { coreDraft?.optString("updated_at").orEmpty() },
      entry = active ?: draft,
      draftEntry = draft,
      approvedEntry = approved,
      score = parseScore(scoreObject),
      scoreAvailable = if (obj.has("score_available")) obj.optBoolean("score_available") else scoreObject?.let(::hasScoreFields),
      weeklyContext = parseWeekContext(obj.optJSONObject("week_context") ?: obj.optJSONObject("weekly_summary")),
      latestProposal = obj.optJSONObject("latest_proposal")?.let(::parseProposal) ?: obj.optJSONObject("proposal")?.let(::parseProposal),
      derivedDashboard = parseDerivedDashboard(date, obj.optJSONObject("derived")),
    )
  }

  private fun parseDerivedDashboard(date: String, obj: JSONObject?): LifeLoadDashboard? {
    if (obj == null) return null
    val trendRows = obj.optJSONObject("trend")?.optJSONArray("rows")
    val driftSnapshot = obj.optJSONObject("drift")?.optJSONObject("snapshot")
    val weekly = obj.optJSONObject("weekly")
    val trendPoints = jsonArray(trendRows).mapNotNull { item ->
      (item as? JSONObject)?.let(::parseTrendPoint)
    }
    if (trendPoints.isEmpty() && driftSnapshot == null && weekly == null) return null
    return LifeLoadDashboard(
      date = date,
      weekly = LifeLoadWeeklyMini(
        zone = weekly?.optString("zone").orEmpty(),
        nextAction = weekly?.optString("next_action").orEmpty(),
        netLifeLoad = weekly?.optDouble("net_life_load") ?: 0.0,
        hardSessions = weekly?.optInt("hard_sessions") ?: 0,
        redFlagCount = jsonArray(weekly?.optJSONArray("red_flags")).size,
      ),
      trendPoints = trendPoints,
      drift = driftSnapshot?.let(::parseDriftSnapshot),
    )
  }

  private fun parsePlatformContract(obj: JSONObject): LifeLoadPlatformContract {
    val score = obj.optJSONObject("score") ?: JSONObject()
    val trend = obj.optJSONObject("trend") ?: JSONObject()
    return LifeLoadPlatformContract(
      schemaVersion = obj.optString("schema_version"),
      entryFields = stringArray(obj.optJSONArray("entry_fields")),
      scoreOutputKeys = stringArray(score.optJSONArray("output_keys")),
      trendFeatureFields = stringArray(trend.optJSONArray("feature_fields")),
      formula = parseFormulaContract(obj.optJSONObject("formula")),
    )
  }

  private fun parseSettings(obj: JSONObject): LifeLoadSettings {
    val garmin = obj.optJSONObject("garmin") ?: JSONObject()
    val dailyFlow = obj.optJSONObject("daily_flow") ?: JSONObject()
    val reminder = obj.optJSONObject("reminder") ?: JSONObject()
    val formula = obj.optJSONObject("formula") ?: JSONObject()
    val debug = obj.optJSONObject("debug") ?: JSONObject()
    return LifeLoadSettings(
      garmin = LifeLoadGarminSettings(
        enabled = garmin.optBoolean("enabled", false),
        email = garmin.optString("email"),
        passwordSet = garmin.optBoolean("password_set", false),
        autoImport = garmin.optBoolean("auto_import", false),
        autoImportDays = garmin.optInt("auto_import_days", 3).coerceIn(1, 14),
      ),
      dailyFlow = LifeLoadDailyFlowSettings(
        defaultDate = dailyFlow.optString("default_date").ifBlank { "yesterday" },
        entryCacheDays = dailyFlow.optInt("entry_cache_days", 5).coerceIn(1, 14),
        secondaryCardsCollapsed = dailyFlow.optBoolean("secondary_cards_collapsed", true),
      ),
      reminder = LifeLoadReminderSettings(
        enabled = reminder.optBoolean("enabled", false),
        hour = reminder.optInt("hour", 21).coerceIn(0, 23),
        minute = reminder.optInt("minute", 30).coerceIn(0, 59),
      ),
      formula = LifeLoadFormulaSettings(
        profile = formula.optString("profile").ifBlank { "balanced" },
        profileModifiers = stringArray(formula.optJSONArray("profile_modifiers")).toSet(),
        includeTrainingTrendBrake = formula.optBoolean("include_training_trend_brake", true),
        includeGarminRecovery = formula.optBoolean("include_garmin_recovery", true),
        includeRelationshipStress = formula.optBoolean("include_relationship_stress", true),
        includeAloneHome = formula.optBoolean("include_alone_home", true),
        includeAfterWorkDecompression = formula.optBoolean("include_after_work_decompression", true),
        includeProjectOverrun = formula.optBoolean("include_project_overrun", true),
        includeLatePhone = formula.optBoolean("include_late_phone", true),
        includeHomeOffice = formula.optBoolean("include_home_office", true),
      ),
      debug = LifeLoadDebugSettings(
        showFormulaButton = debug.optBoolean("show_formula_button", true),
        showGarminImportButtons = debug.optBoolean("show_garmin_import_buttons", true),
      ),
    )
  }

  private fun parseFormulaContract(obj: JSONObject?): LifeLoadFormulaContract {
    val safe = obj ?: JSONObject()
    return LifeLoadFormulaContract(
      schemaVersion = safe.optString("schema_version"),
      scoringContractVersion = safe.optString("scoring_contract_version"),
      sections = jsonArray(safe.optJSONArray("sections")).mapNotNull { item ->
        (item as? JSONObject)?.let(::parseFormulaSection)
      },
    )
  }

  private fun parseFormulaSection(obj: JSONObject): LifeLoadFormulaSection {
    return LifeLoadFormulaSection(
      title = obj.optString("title"),
      body = obj.optString("body"),
      items = jsonArray(obj.optJSONArray("items")).mapNotNull { item ->
        (item as? JSONObject)?.let {
          LifeLoadFormulaItem(
            input = it.optString("input"),
            effect = it.optString("effect"),
          )
        }
      },
    )
  }

  private fun parseDashboard(obj: JSONObject): LifeLoadDashboard {
    if (obj.has("daily_zone") || obj.has("drift_signals")) {
      val weekly = parseWeekContext(obj.optJSONObject("weekly_context"))
      val drift = obj.optJSONObject("drift_signals")
      return LifeLoadDashboard(
        date = obj.optString("date"),
        dbRoot = "health.sqlite",
        weekly = LifeLoadWeeklyMini(
          zone = weekly.zone,
          nextAction = weekly.nextAction,
          sleepCompleted = obj.optJSONObject("weekly_context")?.optInt("sleep_count") ?: 0,
          nutritionCompleted = obj.optJSONObject("weekly_context")?.optInt("nutrition_count") ?: 0,
          redFlagCount = weekly.topDriftSignals.size,
        ),
        drift = LifeLoadDriftSnapshot(
          date = obj.optString("date"),
          riskLevel = drift?.optString("risk_level").orEmpty(),
          mode = drift?.optString("recommended_mode").orEmpty(),
          nextAction = stringifyNextAction(drift?.opt("next_action")),
          contributingSignals = stringArray(drift?.optJSONArray("top_contributing_signals")),
        ),
        trendPoints = jsonArray(obj.optJSONObject("trend")?.optJSONArray("rows")).mapNotNull { item ->
          (item as? JSONObject)?.let(::parseTrendPoint)
        },
        historyDays = jsonArray(obj.optJSONArray("history")).mapNotNull { item ->
          (item as? JSONObject)?.let(::parseHistoryDay)
        },
      )
    }
    val dashboard = obj.optJSONObject("dashboard_state")
    val sleepCompliance = dashboard?.optJSONObject("sleep_compliance")
    val nutritionCompliance = dashboard?.optJSONObject("nutrition_compliance")
    val redFlags = dashboard?.optJSONArray("red_flags")
    val recentWeeks = obj.optJSONArray("recent_weeks")
    val trendRows = obj.optJSONObject("trend")?.optJSONArray("rows")
    val driftSnapshot = obj.optJSONObject("drift")?.optJSONObject("snapshot")
    val historyRows = obj.optJSONArray("history")
    return LifeLoadDashboard(
      date = obj.optString("date"),
      dbRoot = obj.optString("db_root"),
      weekly = LifeLoadWeeklyMini(
        zone = dashboard?.optString("zone").orEmpty(),
        nextAction = dashboard?.optString("next_action").orEmpty(),
        approvedDayDates = stringArray(dashboard?.optJSONArray("approved_days")),
        netLifeLoad = dashboard?.optDouble("net_life_load") ?: 0.0,
        successScore = dashboard?.optDouble("success_score") ?: 0.0,
        hardSessions = dashboard?.optInt("hard_sessions") ?: 0,
        recoveryScore = dashboard?.optDouble("recovery_score") ?: 0.0,
        sleepCompleted = sleepCompliance?.optInt("completed") ?: 0,
        sleepTarget = sleepCompliance?.optInt("target") ?: 0,
        nutritionCompleted = nutritionCompliance?.optInt("completed") ?: 0,
        nutritionTarget = nutritionCompliance?.optInt("target") ?: 0,
        redFlagCount = redFlags?.length() ?: 0,
      ),
      recentWeeks = jsonArray(recentWeeks).map { item ->
        val week = item as JSONObject
        LifeLoadRecentWeek(
          weekStart = week.optString("week_start"),
          weekEnd = week.optString("week_end"),
          zone = week.optString("zone"),
          nextAction = week.optString("next_action"),
          netLifeLoad = week.optDouble("net_life_load"),
          successScore = week.optDouble("success_score"),
        )
      },
      trendPoints = jsonArray(trendRows).mapNotNull { item ->
        (item as? JSONObject)?.let(::parseTrendPoint)
      },
      drift = driftSnapshot?.let(::parseDriftSnapshot),
      historyDays = jsonArray(historyRows).mapNotNull { item ->
        (item as? JSONObject)?.let(::parseHistoryDay)
      },
    )
  }

  private fun parseTrendPoint(obj: JSONObject): LifeLoadTrendPoint {
    val features = obj.optJSONObject("features") ?: JSONObject()
    return LifeLoadTrendPoint(
      date = obj.optString("date"),
      lifeLoadRollingAvg7d = features.optDouble("life_load_rolling_avg_7d", 0.0),
      sleepCompliance7d = features.optDouble("sleep_compliance_7d", 0.0),
      nutritionCompliance7d = features.optDouble("nutrition_compliance_7d", 0.0),
      projectOverrunCount7d = features.optInt("project_overrun_count_7d", 0),
      projectOverrunWeighted7d = features.optDouble("project_overrun_weighted_7d", 0.0),
      projectOverrunRecentCount3d = features.optInt("project_overrun_recent_count_3d", 0),
      projectOverrunOlderCount4To7d = features.optInt("project_overrun_older_count_4_to_7d", 0),
      projectOverrunMostRecentDaysAgo = features.optInt("project_overrun_most_recent_days_ago", -1),
      projectOverrunTrend = features.optString("project_overrun_trend"),
      phoneAfter21Count7d = features.optInt("phone_after_21_count_7d", 0),
      phoneAfter21Weighted7d = features.optDouble("phone_after_21_weighted_7d", 0.0),
      phoneAfter21RecentCount3d = features.optInt("phone_after_21_recent_count_3d", 0),
      phoneAfter21OlderCount4To7d = features.optInt("phone_after_21_older_count_4_to_7d", 0),
      phoneAfter21MostRecentDaysAgo = features.optInt("phone_after_21_most_recent_days_ago", -1),
      phoneAfter21Trend = features.optString("phone_after_21_trend"),
      painAvg7d = features.optDouble("pain_avg_7d", 0.0),
      redFlagCount7d = features.optInt("red_flag_count_7d", 0),
      acuteLoad7d = features.optDouble("acute_load_7d", 0.0),
      chronicCapacity42d = features.optDouble("chronic_capacity_42d", 0.0),
      lifeMargin7d = features.optDouble("life_margin_7d", 0.0),
      weightKgLatest = features.optDouble("weight_kg_latest", 0.0),
      weightLatestDaysOld = features.optInt("weight_latest_days_old", -1),
      weightChange14d = features.optDouble("weight_change_14d", 0.0),
      weightChange30d = features.optDouble("weight_change_30d", 0.0),
      weightChange14dUsable = features.optBoolean("weight_change_14d_usable", false),
      weightChange30dUsable = features.optBoolean("weight_change_30d_usable", false),
      driftRiskScore = features.optDouble("drift_risk_score", 0.0),
      recommendedMode = features.optString("recommended_mode"),
    )
  }

  private fun parseDriftSnapshot(obj: JSONObject): LifeLoadDriftSnapshot = LifeLoadDriftSnapshot(
    date = obj.optString("date"),
    riskLevel = obj.optString("risk_level"),
    mode = obj.optString("mode"),
    nextAction = obj.optString("next_action"),
    evidenceNote = obj.optString("evidence_note"),
    contributingSignals = stringArray(obj.optJSONArray("contributing_signals")),
  )

  private fun parseHistoryDay(obj: JSONObject): LifeLoadHistoryDay = LifeLoadHistoryDay(
    date = obj.optString("date"),
    state = obj.optString("state"),
    approvedAt = obj.optString("approved_at"),
    canonicalCompleted = obj.optBoolean("canonical_completed", false),
    zone = obj.optString("zone"),
    nextAction = obj.optString("next_action"),
    lifeLoadScore = obj.optDouble("life_load_score", 0.0),
    diarySummary = obj.optString("diary_summary").ifBlank { obj.optString("diary_text") },
    mood = obj.optNullableInt("mood"),
    stress = obj.optNullableInt("stress"),
    energy = obj.optNullableInt("energy"),
    scoreAvailable = obj.optBoolean("score_available", obj.has("zone") || obj.has("life_load_score") || obj.has("next_action")),
  )

  private fun hasScoreFields(obj: JSONObject): Boolean =
    obj.has("zone") || obj.has("mode") || obj.has("life_load_score") || obj.has("next_action") || obj.has("warnings")

  private fun parseEntry(obj: JSONObject?): LifeLoadEntry {
    val safe = obj ?: JSONObject()
    return LifeLoadEntry(
      date = safe.optString("date"),
      diaryText = safe.optString("diary_text"),
      diarySummary = safe.optString("diary_summary"),
      tags = stringArray(safe.optJSONArray("tags")),
      sleepOk = safe.optNullableBoolean("sleep_ok"),
      nutritionOk = safe.optNullableBoolean("nutrition_ok"),
      alcohol = safe.optAlcoholValue("alcohol"),
      binge = safe.optNullableBoolean("binge"),
      mood = safe.optNullableInt("mood"),
      stress = safe.optNullableInt("stress"),
      energy = safe.optNullableInt("energy"),
      coffeeCups = safe.optNullableInt("coffee_cups"),
      footPain = safe.optNullableInt("foot_pain"),
      shoulderPain = safe.optNullableInt("shoulder_pain"),
      migraineWarning = safe.optNullableBoolean("migraine_warning"),
      decompressionDone = safe.optNullableBoolean("decompression_done"),
      afterWorkDecompressionDone = safe.optNullableBoolean("after_work_decompression_done"),
      eveningChainBroken = safe.optNullableBoolean("evening_chain_broken"),
      shutdownDone = safe.optNullableBoolean("shutdown_done"),
      phoneAfter21 = safe.optNullableBoolean("phone_after_21"),
      projectOverrun = safe.optNullableBoolean("project_overrun"),
      primaryActivityType = safe.optString("primary_activity_type"),
      activityTypes = stringArray(safe.optJSONArray("activity_types")).ifEmpty {
        listOfNotNull(safe.optString("primary_activity_type").takeIf { it.isNotBlank() })
      },
      activityDurationMin = safe.optNullableInt("activity_duration_min"),
      rehabDone = safe.optNullableBoolean("rehab_done"),
      otherSymptoms = safe.optString("other_symptoms"),
      workIntensity = safe.optString("work_intensity"),
      familyStress = safe.optFamilyStressValue("family_stress"),
      wifeConflictCount = safe.optNullableInt("wife_conflict_count"),
      wifeConflictSchool = safe.optNullableBoolean("wife_conflict_school"),
      wifeConflictChores = safe.optNullableBoolean("wife_conflict_chores"),
      wifeConflictOther = safe.optNullableBoolean("wife_conflict_other"),
      homeOffice = safe.optNullableBoolean("home_office"),
      aloneHome = safe.optNullableBoolean("alone_home"),
      homeworkDone = safe.optNullableBoolean("homework_done"),
      homeworkStatus = safe.optHomeworkStatus("homework_done"),
    )
  }

  private fun parseDraftEntry(obj: JSONObject): LifeLoadEntry {
    val fields = obj.optJSONObject("structured") ?: JSONObject()
    fields.put("date", obj.optString("date"))
    fields.put("diary_text", obj.optString("diary_text"))
    if (!fields.has("diary_summary")) fields.put("diary_summary", obj.optString("summary"))
    return parseEntry(fields)
  }

  private fun parseScore(obj: JSONObject?): LifeLoadScore {
    val safe = obj ?: JSONObject()
    val nextActionObj = nextActionObject(safe.opt("next_action"))
    return LifeLoadScore(
      zone = safe.optString("zone"),
      mode = safe.optString("mode"),
      nextAction = stringifyNextAction(safe.opt("next_action")),
      minimumAction = nextActionObj?.optString("minimum_action").orEmpty(),
      avoid = nextActionObj?.optString("avoid").orEmpty(),
      why = stringArrayish(safe.opt("why") ?: safe.opt("why_json")),
      confidence = safe.optNullableDouble("confidence"),
      lifeLoadScore = safe.optDouble("life_load_score"),
      baseScore = safe.optDouble("base_score"),
      profileAdjustedScore = safe.optDouble("profile_adjusted_score"),
      guidanceMediumThreshold = safe.optJSONObject("guidance_thresholds")?.optInt("medium", 35) ?: 35,
      guidanceHighThreshold = safe.optJSONObject("guidance_thresholds")?.optInt("high", 70) ?: 70,
      profileModifiers = stringArray(safe.optJSONArray("profile_modifiers")),
      profileEffects = stringArray(safe.optJSONArray("profile_effects")),
      trainingLoad = safe.optDouble("training_load"),
      recoveryScore = safe.optDouble("recovery_score"),
      strainScore = safe.optDouble("strain_score"),
      hardSessions = safe.optInt("hard_sessions"),
      rehabSessions = safe.optInt("rehab_sessions"),
      acuteTrainingLoad = safe.optDouble("acute_training_load"),
      chronicTrainingLoad = safe.optDouble("chronic_training_load"),
      trainingLoadRatio = safe.optNullableDouble("training_load_ratio"),
      trainingRamp = safe.optDouble("training_ramp"),
      warnings = stringArray(safe.optJSONArray("warnings")),
      redFlags = stringArrayish(safe.opt("red_flags") ?: safe.opt("red_flags_json")),
    )
  }

  private fun parseWeekContext(obj: JSONObject?): LifeLoadWeekContext {
    val safe = obj ?: JSONObject()
    return LifeLoadWeekContext(
      weekStart = safe.optString("week_start"),
      weekEnd = safe.optString("week_end"),
      approvedDays = safe.optInt("approved_days"),
      zone = safe.optString("zone"),
      mode = safe.optString("mode"),
      topDriftSignals = stringArrayish(safe.opt("top_drift_signals") ?: safe.opt("top_drift_signals_json")),
      nextAction = stringifyNextAction(safe.opt("next_action")),
    )
  }

  private fun parseProposal(obj: JSONObject?): LifeLoadProposal {
    val wrapper = obj ?: JSONObject()
    val safe = wrapper.optJSONObject("raw_json") ?: wrapper
    val fields = mutableMapOf<String, Any?>()
    safe.optJSONObject("fields")?.let { raw ->
      raw.keys().forEach { key -> fields[key] = raw.opt(key) }
    }
    return LifeLoadProposal(
      proposalId = safe.optString("proposal_id").ifBlank { wrapper.optString("proposal_id") },
      summary = safe.optString("summary"),
      nextAction = safe.optString("next_action"),
      extractorVersion = safe.optString("extractor_version").ifBlank { wrapper.optString("extractor_version") },
      fields = fields,
      redFlags = jsonArray(safe.optJSONArray("red_flags")).mapNotNull { item ->
        (item as? JSONObject)?.let {
          LifeLoadFlag(
            type = it.optString("type"),
            severity = it.optString("severity"),
            evidence = it.optString("evidence"),
          )
        }
      },
      fallbackError = safe.optString("fallback_error"),
    )
  }

  private fun entryJson(entry: LifeLoadEntry): JSONObject {
    return JSONObject()
      .put("date", entry.date)
      .put("diary_text", entry.diaryText)
      .put("diary_summary", entry.diarySummary)
      .put("tags", JSONArray(entry.tags))
      .putNullableBool("sleep_ok", entry.sleepOk)
      .putNullableBool("nutrition_ok", entry.nutritionOk)
      .put("alcohol", entry.alcohol ?: JSONObject.NULL)
      .putNullableBool("binge", entry.binge)
      .putNullableInt("mood", entry.mood)
      .putNullableInt("stress", entry.stress)
      .putNullableInt("energy", entry.energy)
      .putNullableInt("coffee_cups", entry.coffeeCups)
      .putNullableInt("foot_pain", entry.footPain)
      .putNullableInt("shoulder_pain", entry.shoulderPain)
      .putNullableBool("migraine_warning", entry.migraineWarning)
      .putNullableBool("decompression_done", entry.decompressionDone)
      .putNullableBool("after_work_decompression_done", entry.afterWorkDecompressionDone)
      .putNullableBool("evening_chain_broken", entry.eveningChainBroken)
      .putNullableBool("shutdown_done", entry.shutdownDone)
      .putNullableBool("phone_after_21", entry.phoneAfter21)
      .putNullableBool("project_overrun", entry.projectOverrun)
      .put("primary_activity_type", entry.primaryActivityType)
      .put("activity_types", JSONArray(entry.activityTypes))
      .putNullableInt("activity_duration_min", entry.activityDurationMin)
      .putNullableBool("rehab_done", entry.rehabDone)
      .put("other_symptoms", entry.otherSymptoms)
      .put("work_intensity", entry.workIntensity)
      .putNullableInt("family_stress", entry.familyStress)
      .putNullableInt("wife_conflict_count", entry.wifeConflictCount)
      .putNullableBool("wife_conflict_school", entry.wifeConflictSchool)
      .putNullableBool("wife_conflict_chores", entry.wifeConflictChores)
      .putNullableBool("wife_conflict_other", entry.wifeConflictOther)
      .putNullableBool("home_office", entry.homeOffice)
      .putNullableBool("alone_home", entry.aloneHome)
      .put("homework_done", entry.homeworkStatus ?: entry.homeworkDone ?: JSONObject.NULL)
  }

  private fun settingsJson(settings: LifeLoadSettings, garminPassword: String): JSONObject {
    val garmin = JSONObject()
      .put("enabled", settings.garmin.enabled)
      .put("email", settings.garmin.email)
      .put("auto_import", settings.garmin.autoImport)
      .put("auto_import_days", settings.garmin.autoImportDays)
    if (garminPassword.isNotBlank()) garmin.put("password", garminPassword)
    return JSONObject()
      .put("garmin", garmin)
      .put(
        "daily_flow",
        JSONObject()
          .put("default_date", settings.dailyFlow.defaultDate)
          .put("entry_cache_days", settings.dailyFlow.entryCacheDays)
          .put("secondary_cards_collapsed", settings.dailyFlow.secondaryCardsCollapsed),
      )
      .put(
        "reminder",
        JSONObject()
          .put("enabled", settings.reminder.enabled)
          .put("hour", settings.reminder.hour)
          .put("minute", settings.reminder.minute),
      )
      .put(
        "formula",
        JSONObject()
          .put("profile", settings.formula.profile)
          .put("profile_modifiers", JSONArray(settings.formula.profileModifiers.toList().sorted()))
          .put("include_training_trend_brake", settings.formula.includeTrainingTrendBrake)
          .put("include_garmin_recovery", settings.formula.includeGarminRecovery)
          .put("include_relationship_stress", settings.formula.includeRelationshipStress)
          .put("include_alone_home", settings.formula.includeAloneHome)
          .put("include_after_work_decompression", settings.formula.includeAfterWorkDecompression)
          .put("include_project_overrun", settings.formula.includeProjectOverrun)
          .put("include_late_phone", settings.formula.includeLatePhone)
          .put("include_home_office", settings.formula.includeHomeOffice),
      )
      .put(
        "debug",
        JSONObject()
          .put("show_formula_button", settings.debug.showFormulaButton)
          .put("show_garmin_import_buttons", settings.debug.showGarminImportButtons),
      )
  }

  private fun stringArray(array: JSONArray?): List<String> = jsonArray(array).mapNotNull { item ->
    item?.toString()?.takeIf { it.isNotBlank() }
  }

  private fun stringArrayish(value: Any?): List<String> {
    return when (value) {
      null, JSONObject.NULL -> emptyList()
      is JSONArray -> stringArray(value)
      is String -> {
        val trimmed = value.trim()
        if (trimmed.startsWith("[")) {
          runCatching { stringArray(JSONArray(trimmed)) }.getOrElse { listOf(trimmed).filter(String::isNotBlank) }
        } else {
          listOf(trimmed).filter(String::isNotBlank)
        }
      }
      else -> listOf(value.toString()).filter(String::isNotBlank)
    }
  }

  private fun jsonArray(array: JSONArray?): List<Any?> {
    if (array == null) return emptyList()
    return List(array.length()) { idx -> array.opt(idx) }
  }

  private fun JSONObject.putNullableBool(key: String, value: Boolean?): JSONObject =
    apply { if (value == null) put(key, JSONObject.NULL) else put(key, value) }

  private fun JSONObject.putNullableInt(key: String, value: Int?): JSONObject =
    apply { if (value == null) put(key, JSONObject.NULL) else put(key, value) }

  private fun JSONObject.optNullableBoolean(key: String): Boolean? {
    if (!has(key) || isNull(key)) return null
    return optBoolean(key)
  }

  private fun JSONObject.optAlcoholValue(key: String): String? {
    if (!has(key) || isNull(key)) return null
    val raw = opt(key)
    if (raw is Boolean) return if (raw) "home" else "none"
    return optString(key).takeIf { it.isNotBlank() && it != "null" }
  }

  private fun JSONObject.optHomeworkStatus(key: String): String? {
    if (!has(key) || isNull(key)) return null
    val raw = opt(key)
    if (raw is Boolean) return if (raw) "yes" else "no"
    return optString(key).takeIf { it.isNotBlank() && it != "null" }
  }

  private fun JSONObject.optNullableInt(key: String): Int? {
    if (!has(key) || isNull(key)) return null
    return optInt(key)
  }

  private fun JSONObject.optFamilyStressValue(key: String): Int? {
    if (!has(key) || isNull(key)) return null
    return when (opt(key)?.toString()?.trim()?.lowercase()) {
      "", "null" -> null
      "low" -> 2
      "normal" -> 5
      "heavy", "high", "extreme" -> 8
      else -> optInt(key)
    }
  }

  private fun JSONObject.optNullableDouble(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    return optDouble(key)
  }

  private fun stringifyNextAction(value: Any?): String {
    if (value == null || value == JSONObject.NULL) return ""
    val obj = nextActionObject(value)
    if (obj != null) {
      return obj.optString("primary_action")
        .ifBlank { obj.optString("minimum_action") }
        .ifBlank { obj.optString("avoid") }
    }
    return value.toString()
  }

  private fun nextActionObject(value: Any?): JSONObject? {
    if (value == null || value == JSONObject.NULL) return null
    if (value is JSONObject) return value
    val text = value.toString().trim()
    if (!text.startsWith("{")) return null
    return runCatching { JSONObject(text) }.getOrNull()
  }
}
