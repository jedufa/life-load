package com.life.lifeload

import com.life.lifeload.data.HttpLifeLoadApi
import com.life.lifeload.domain.LifeLoadEntry
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HttpLifeLoadApiTest {
  @Test
  fun saveEntryParsesDerivedTrendForImmediateCompassRefresh() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "date":"2026-05-09",
              "default_date":"2026-05-09",
              "previous_date":"2026-05-08",
              "next_date":"2026-05-10",
              "entry_state":"approved",
              "has_draft":false,
              "entry_exists":true,
              "approved_at":"2026-05-09T20:30:00Z",
              "draft_updated_at":"",
              "entry":{"date":"2026-05-09","diary_text":"late project","tags":[]},
              "approved_entry":{"date":"2026-05-09","diary_text":"late project","tags":[]},
              "score":{"zone":"yellow","next_action":"Keep tonight simple.","life_load_score":4.0,"base_score":3.5,"profile_adjusted_score":4.0,"guidance_thresholds":{"medium":32,"high":65},"profile_modifiers":["protective"],"profile_effects":["protective increased late-phone strain"]},
              "derived":{
                "weekly":{"zone":"yellow","next_action":"Keep tonight simple.","red_flags":["late phone"]},
                "trend":{
                  "rows":[
                    {"date":"2026-05-08","features":{"drift_risk_score":25.0,"life_load_rolling_avg_7d":2.0,"life_margin_7d":3.0}},
                    {"date":"2026-05-09","features":{"drift_risk_score":62.0,"life_load_rolling_avg_7d":4.0,"life_margin_7d":-1.0,"phone_after_21_count_7d":2,"phone_after_21_weighted_7d":0.46,"phone_after_21_recent_count_3d":0,"phone_after_21_older_count_4_to_7d":2,"phone_after_21_most_recent_days_ago":5,"phone_after_21_trend":"fading"}}
                  ]
                },
                "drift":{"snapshot":{"date":"2026-05-09","risk_level":"yellow","mode":"hold","next_action":"Keep tonight simple.","contributing_signals":["late phone"]}}
              }
            }
            """.trimIndent(),
          ),
      )
      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val payload = api.saveEntry(LifeLoadEntry(date = "2026-05-09"), action = "approve")

      val derived = payload.derivedDashboard
      assertEquals("2026-05-09", derived?.date)
      assertEquals("yellow", derived?.weekly?.zone)
      assertEquals(listOf("protective"), payload.score.profileModifiers)
      assertEquals(listOf("protective increased late-phone strain"), payload.score.profileEffects)
      assertEquals(3.5, payload.score.baseScore, 0.001)
      assertEquals(4.0, payload.score.profileAdjustedScore, 0.001)
      assertEquals(32, payload.score.guidanceMediumThreshold)
      assertEquals(65, payload.score.guidanceHighThreshold)
      assertEquals(2, derived?.trendPoints?.size)
      assertEquals(62.0, derived?.trendPoints?.last()?.driftRiskScore ?: 0.0, 0.001)
      assertEquals(0.46, derived?.trendPoints?.last()?.phoneAfter21Weighted7d ?: 0.0, 0.001)
      assertEquals(0, derived?.trendPoints?.last()?.phoneAfter21RecentCount3d)
      assertEquals(2, derived?.trendPoints?.last()?.phoneAfter21OlderCount4To7d)
      assertEquals(5, derived?.trendPoints?.last()?.phoneAfter21MostRecentDaysAgo)
      assertEquals("fading", derived?.trendPoints?.last()?.phoneAfter21Trend)
      assertEquals("yellow", derived?.drift?.riskLevel)
    }
  }

  @Test
  fun getEntryRetriesAfterUnexpectedDisconnect() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "date":"2026-05-02",
              "default_date":"2026-05-02",
              "previous_date":"2026-05-01",
              "next_date":"2026-05-03",
              "entry_state":"draft",
              "has_draft":true,
              "entry_exists":true,
              "approved_at":"",
              "draft_updated_at":"2026-05-03T18:00:00Z",
              "entry":{
                "date":"2026-05-02",
                "diary_text":"ok",
                "tags":[],
                "after_work_decompression_done":false,
                "evening_chain_broken":true,
                "wife_conflict_count":2,
                "wife_conflict_school":true,
                "wife_conflict_chores":false,
                "wife_conflict_other":false,
                "alone_home":true,
                "primary_activity_type":"run",
                "activity_types":["run","crossfit"]
              },
              "approved_entry":null,
              "score":{"zone":"Yellow","next_action":"Protect shutdown","life_load_score":1.0,"training_load":0.0,"recovery_score":0.0,"strain_score":1.0,"hard_sessions":0,"rehab_sessions":0,"acute_training_load":3.2,"chronic_training_load":1.4,"training_load_ratio":2.29,"training_ramp":0.2,"warnings":[],"red_flags":[]},
              "latest_proposal":null
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().retryOnConnectionFailure(true).build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val payload = api.getEntry("2026-05-02")

      assertEquals("2026-05-02", payload.date)
      assertEquals("ok", payload.entry.diaryText)
      assertEquals(false, payload.entry.afterWorkDecompressionDone)
      assertEquals(true, payload.entry.eveningChainBroken)
      assertEquals(2, payload.entry.wifeConflictCount)
      assertEquals(true, payload.entry.wifeConflictSchool)
      assertEquals(false, payload.entry.wifeConflictChores)
      assertEquals(false, payload.entry.wifeConflictOther)
      assertEquals(true, payload.entry.aloneHome)
      assertEquals("run", payload.entry.primaryActivityType)
      assertEquals(listOf("run", "crossfit"), payload.entry.activityTypes)
      assertEquals(3.2, payload.score.acuteTrainingLoad, 0.001)
      assertEquals(1.4, payload.score.chronicTrainingLoad, 0.001)
      assertEquals(2.29, payload.score.trainingLoadRatio ?: 0.0, 0.001)
      assertEquals(0.2, payload.score.trainingRamp, 0.001)
      assertTrue(server.requestCount >= 2)
    }
  }

  @Test
  fun draftPayloadKeepsDraftSeparateFromApprovedBaseline() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "date":"2026-05-03",
              "entry_state":"draft",
              "has_draft":true,
              "entry_exists":false,
              "entry":{"date":"2026-05-03","diary_text":"draft only","energy":0},
              "approved_entry":null,
              "score_available":false
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val payload = api.getEntry("2026-05-03")

      assertEquals("draft", payload.entryState)
      assertEquals(true, payload.hasDraft)
      assertEquals("draft only", payload.draftEntry.diaryText)
      assertEquals(null, payload.approvedEntry)
      assertEquals(false, payload.scoreAvailable)
    }
  }

  @Test
  fun contractParsesFormulaAndTrendFields() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_platform_contract_v1",
              "entry_fields":["date","sleep_ok","alone_home"],
              "score":{"output_keys":["life_load_score","training_load","recovery_score"]},
              "trend":{"feature_fields":["acute_load_7d","chronic_capacity_42d","life_margin_7d"]},
              "formula":{
                "schema_version":"life_load_formula_v1",
                "scoring_contract_version":"life_load_scoring_contract_v1",
                "sections":[
                  {
                    "title":"Training Load",
                    "body":"Activity points are duration-sensitive.",
                    "items":[{"input":"Bike commute","effect":"0.55 per 30 min"}]
                  }
                ]
              }
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val contract = api.getContract()

      assertEquals("life_load_platform_contract_v1", contract.schemaVersion)
      assertEquals(listOf("date", "sleep_ok", "alone_home"), contract.entryFields)
      assertEquals(listOf("acute_load_7d", "chronic_capacity_42d", "life_margin_7d"), contract.trendFeatureFields)
      assertEquals("life_load_formula_v1", contract.formula.schemaVersion)
      assertEquals("Training Load", contract.formula.sections.first().title)
      assertEquals("Bike commute", contract.formula.sections.first().items.first().input)
    }
  }

  @Test
  fun settingsRoundTripUsesRedactedPasswordContract() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_settings_v1",
              "settings":{
                "garmin":{"enabled":true,"email":"subs@example.test","password_set":true,"auto_import":false,"auto_import_days":7},
                "daily_flow":{"default_date":"yesterday","entry_cache_days":7,"secondary_cards_collapsed":true},
                "formula":{"profile":"protective","profile_modifiers":["protective","sports_light"],"include_training_trend_brake":true,"include_garmin_recovery":false,"include_relationship_stress":true,"include_alone_home":false,"include_after_work_decompression":true,"include_project_overrun":true,"include_late_phone":true,"include_home_office":false},
                "debug":{"show_formula_button":true,"show_garmin_import_buttons":false}
              }
            }
            """.trimIndent(),
          ),
      )
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_settings_v1",
              "settings":{
                "garmin":{"enabled":false,"email":"changed@example.test","password_set":true,"auto_import":true,"auto_import_days":3},
                "daily_flow":{"default_date":"today","entry_cache_days":5,"secondary_cards_collapsed":true},
                "formula":{"profile":"balanced","profile_modifiers":["balanced","protective"],"include_training_trend_brake":true,"include_garmin_recovery":true,"include_relationship_stress":true,"include_alone_home":true,"include_after_work_decompression":true,"include_project_overrun":true,"include_late_phone":true,"include_home_office":true},
                "debug":{"show_formula_button":true,"show_garmin_import_buttons":true}
              }
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val loaded = api.getSettings()
      val saved = api.saveSettings(
        loaded.copy(
          garmin = loaded.garmin.copy(enabled = false, email = "changed@example.test", autoImport = true, autoImportDays = 3),
          dailyFlow = loaded.dailyFlow.copy(defaultDate = "today", entryCacheDays = 5),
        ),
        garminPassword = "new-secret",
      )

      assertEquals("subs@example.test", loaded.garmin.email)
      assertEquals(true, loaded.garmin.passwordSet)
      assertEquals(false, loaded.garmin.autoImport)
      assertEquals(7, loaded.dailyFlow.entryCacheDays)
      assertEquals("protective", loaded.formula.profile)
      assertEquals(setOf("protective", "sports_light"), loaded.formula.profileModifiers)
      assertEquals(false, loaded.formula.includeAloneHome)
      assertEquals(false, loaded.debug.showGarminImportButtons)
      assertEquals("changed@example.test", saved.garmin.email)
      assertEquals("today", saved.dailyFlow.defaultDate)
      val post = server.takeRequest()
      assertEquals("GET", post.method)
      val saveRequest = server.takeRequest()
      assertEquals("POST", saveRequest.method)
      val saveBody = saveRequest.body.readUtf8()
      assertTrue(saveBody.contains("new-secret"))
      assertTrue(saveBody.contains("profile_modifiers"))
    }
  }

  @Test
  fun settingsParserKeepsGarminOptInWhenFieldsAreMissing() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_settings_v1",
              "settings":{}
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val loaded = api.getSettings()

      assertEquals(false, loaded.garmin.enabled)
      assertEquals(false, loaded.garmin.autoImport)
      assertEquals(false, loaded.garmin.passwordSet)
      assertEquals("", loaded.garmin.email)
    }
  }

  @Test
  fun dashboardParsesTrendDriftAndHistoryForPreventionCards() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "date":"2026-05-04",
              "db_root":"/tmp/life_load.sqlite",
              "dashboard_state":{
                "zone":"orange",
                "next_action":"Protect shutdown for 48h.",
                "net_life_load":24.0,
                "success_score":0.57,
                "hard_sessions":2,
                "recovery_score":7.0,
                "sleep_compliance":{"completed":4,"target":5},
                "nutrition_compliance":{"completed":5,"target":5},
                "red_flags":["late phone"]
              },
              "trend":{
                "rows":[
                  {"date":"2026-05-03","features":{"life_load_rolling_avg_7d":12.0,"acute_load_7d":12.0,"chronic_capacity_42d":14.0,"life_margin_7d":2.0,"drift_risk_score":32.0,"recommended_mode":"caution","sleep_compliance_7d":0.7,"nutrition_compliance_7d":0.8,"project_overrun_count_7d":1,"phone_after_21_count_7d":1,"pain_avg_7d":2.5,"red_flag_count_7d":0}},
                  {"date":"2026-05-04","features":{"life_load_rolling_avg_7d":15.5,"acute_load_7d":15.5,"chronic_capacity_42d":10.0,"life_margin_7d":-5.5,"weight_kg_latest":101.4,"weight_latest_days_old":1,"weight_change_14d":1.4,"weight_change_30d":1.9,"weight_change_14d_usable":true,"weight_change_30d_usable":true,"drift_risk_score":68.0,"recommended_mode":"hold","sleep_compliance_7d":0.6,"nutrition_compliance_7d":0.7,"project_overrun_count_7d":2,"project_overrun_weighted_7d":1.55,"project_overrun_recent_count_3d":2,"project_overrun_older_count_4_to_7d":0,"project_overrun_most_recent_days_ago":1,"project_overrun_trend":"recent","phone_after_21_count_7d":3,"phone_after_21_weighted_7d":1.01,"phone_after_21_recent_count_3d":0,"phone_after_21_older_count_4_to_7d":3,"phone_after_21_most_recent_days_ago":4,"phone_after_21_trend":"fading","pain_avg_7d":3.0,"red_flag_count_7d":1}}
                ]
              },
              "drift":{
                "snapshot":{
                  "date":"2026-05-04",
                  "risk_level":"orange",
                  "mode":"hold",
                  "next_action":"No project work after 20:45 for three days.",
                  "evidence_note":"Triggered by late phone and project overrun.",
                  "contributing_signals":["late phone","project overrun","sleep drift"]
                }
              },
              "recent_weeks":[],
              "history":[
                {"date":"2026-05-04","state":"draft_over_approved","approved_at":"2026-05-04T20:00:00Z","canonical_completed":true,"zone":"orange","next_action":"Hold progression.","life_load_score":15.5,"diary_summary":"heavy day","mood":5,"stress":8,"energy":4}
              ]
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val dashboard = api.getDashboard("2026-05-04", weeks = 8)

      assertEquals("orange", dashboard.drift?.riskLevel)
      assertEquals("No project work after 20:45 for three days.", dashboard.drift?.nextAction)
      assertEquals(listOf("late phone", "project overrun", "sleep drift"), dashboard.drift?.contributingSignals)
      assertEquals(2, dashboard.trendPoints.size)
      assertEquals(15.5, dashboard.trendPoints.last().lifeLoadRollingAvg7d, 0.001)
      assertEquals(10.0, dashboard.trendPoints.last().chronicCapacity42d, 0.001)
      assertEquals(-5.5, dashboard.trendPoints.last().lifeMargin7d, 0.001)
      assertEquals(101.4, dashboard.trendPoints.last().weightKgLatest, 0.001)
      assertEquals(1, dashboard.trendPoints.last().weightLatestDaysOld)
      assertEquals(1.4, dashboard.trendPoints.last().weightChange14d, 0.001)
      assertEquals(1.9, dashboard.trendPoints.last().weightChange30d, 0.001)
      assertTrue(dashboard.trendPoints.last().weightChange14dUsable)
      assertTrue(dashboard.trendPoints.last().weightChange30dUsable)
      assertEquals(68.0, dashboard.trendPoints.last().driftRiskScore, 0.001)
      assertEquals("hold", dashboard.trendPoints.last().recommendedMode)
      assertEquals(3, dashboard.trendPoints.last().phoneAfter21Count7d)
      assertEquals(1.01, dashboard.trendPoints.last().phoneAfter21Weighted7d, 0.001)
      assertEquals(0, dashboard.trendPoints.last().phoneAfter21RecentCount3d)
      assertEquals(3, dashboard.trendPoints.last().phoneAfter21OlderCount4To7d)
      assertEquals(4, dashboard.trendPoints.last().phoneAfter21MostRecentDaysAgo)
      assertEquals("fading", dashboard.trendPoints.last().phoneAfter21Trend)
      assertEquals(1.55, dashboard.trendPoints.last().projectOverrunWeighted7d, 0.001)
      assertEquals(2, dashboard.trendPoints.last().projectOverrunRecentCount3d)
      assertEquals(0, dashboard.trendPoints.last().projectOverrunOlderCount4To7d)
      assertEquals(1, dashboard.trendPoints.last().projectOverrunMostRecentDaysAgo)
      assertEquals("recent", dashboard.trendPoints.last().projectOverrunTrend)
      assertEquals("heavy day", dashboard.historyDays.first().diarySummary)
      assertTrue(dashboard.historyDays.first().canonicalCompleted)
      assertEquals("2026-05-04T20:00:00Z", dashboard.historyDays.first().approvedAt)
    }
  }

  @Test
  fun coreBackendAnalyzeAndApproveUseDraftAndApproveEndpoints() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_entry_payload_v1",
              "date":"2026-05-04",
              "entry":null,
              "draftEntry":{
                "date":"2026-05-04",
                "diary_text":"videos after 21",
                "structured":{"phone_after_21":true,"alcohol":"none","homework_done":"yes"},
                "summary":"Late phone.",
                "updated_at":"2026-05-05T06:00:00Z"
              },
              "summary":null,
              "week_context":{"week_start":"2026-05-04","week_end":"2026-05-10","approved_days":0},
              "proposal":{"summary":"Late phone.","fields":{"phone_after_21":true},"red_flags":[{"type":"late_phone","severity":"yellow","evidence":"videos"}]}
            }
            """.trimIndent(),
          ),
      )
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_approval_v1",
              "date":"2026-05-04",
              "entry":{"date":"2026-05-04","diary_text":"videos after 21","phone_after_21":true,"alcohol":"none","approved_at":"2026-05-05T06:10:00Z"},
              "summary":{
                "zone":"yellow",
                "mode":"protect",
                "life_load_score":3.0,
                "strain_score":2.0,
                "recovery_score":0.0,
                "training_load":0.0,
                "why":["Late phone"],
                "confidence":0.75,
                "next_action":{"primary_action":"Phone outside bedroom by 21:00 tonight.","minimum_action":"One decompression step before dinner.","avoid":"No project work after 20:45."}
              },
              "weekly_summary":{"week_start":"2026-05-04","week_end":"2026-05-10","approved_days":1,"zone":"yellow","mode":"protect","next_action":{"primary_action":"Protect shutdown."}}
            }
            """.trimIndent(),
          ),
      )

      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val analyzed = api.analyzeDiary(com.life.lifeload.domain.LifeLoadEntry(date = "2026-05-04", diaryText = "videos after 21"))
      val approved = api.approveEntry(analyzed.payload.draftEntry)

      assertEquals("/api/mobile/life-load/analyze-diary", server.takeRequest().path)
      assertEquals("/api/mobile/life-load/approve", server.takeRequest().path)
      assertEquals(true, analyzed.payload.draftEntry.phoneAfter21)
      assertEquals("none", analyzed.payload.draftEntry.alcohol)
      assertEquals("Phone outside bedroom by 21:00 tonight.", approved.score.nextAction)
      assertEquals("protect", approved.score.mode)
      assertEquals(listOf("Late phone"), approved.score.why)
    }
  }

  @Test
  fun coreBlankEntryPayloadKeepsSelectedDate() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_entry_payload_v1",
              "date":"2026-05-04",
              "entry":null,
              "draftEntry":null,
              "summary":null,
              "week_context":{"week_start":"2026-05-04","week_end":"2026-05-10","approved_days":0}
            }
            """.trimIndent(),
          ),
      )
      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val payload = api.getEntry("2026-05-04")

      assertEquals("2026-05-04", payload.entry.date)
      assertEquals("2026-05-04", payload.draftEntry.date)
      assertEquals("blank", payload.entryState)
    }
  }

  @Test
  fun corePayloadKeepsUnknownWorkIntensityAndParsesStringWeekSignals() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_entry_payload_v1",
              "date":"2026-05-04",
              "entry":{
                "date":"2026-05-04",
                "diary_text":"approved",
                "coffee_cups":4,
                "family_stress":"heavy"
              },
              "draftEntry":null,
              "summary":{
                "zone":"orange",
                "mode":"hold",
                "why_json":"[\"Extreme work\",\"Late phone\"]",
                "red_flags_json":"[\"pain warning\"]",
                "next_action":{"primary_action":"Walk 20 minutes only."}
              },
              "week_context":{
                "week_start":"2026-05-04",
                "week_end":"2026-05-10",
                "approved_days":1,
                "top_drift_signals_json":"[\"repeated late phone\",\"pain warning\"]",
                "next_action":{"primary_action":"Protect shutdown."}
              }
            }
            """.trimIndent(),
          ),
      )
      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val payload = api.getEntry("2026-05-04")

      assertEquals("", payload.entry.workIntensity)
      assertEquals(4, payload.entry.coffeeCups)
      assertEquals(8, payload.entry.familyStress)
      assertEquals(listOf("Extreme work", "Late phone"), payload.score.why)
      assertEquals(listOf("pain warning"), payload.score.redFlags)
      assertEquals(listOf("repeated late phone", "pain warning"), payload.weeklyContext.topDriftSignals)
      assertEquals("Protect shutdown.", payload.weeklyContext.nextAction)
    }
  }

  @Test
  fun scoreParsesNextActionWhenBackendReturnsJsonString() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_entry_payload_v1",
              "date":"2026-05-05",
              "entry":{"date":"2026-05-05","diary_text":"approved"},
              "draftEntry":null,
              "summary":{
                "zone":"green",
                "mode":"continue",
                "life_load_score":-4.0,
                "why":["No major drift signals"],
                "next_action":"{\"primary_action\":\"Repeat the baseline; do not add extra ambition.\",\"minimum_action\":\"Short shutdown check at 20:45.\",\"avoid\":\"No heroic add-ons.\"}"
              },
              "week_context":{"week_start":"2026-05-04","week_end":"2026-05-10","approved_days":1}
            }
            """.trimIndent(),
          ),
      )
      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val payload = api.getEntry("2026-05-05")

      assertEquals("Repeat the baseline; do not add extra ambition.", payload.score.nextAction)
      assertEquals("Short shutdown check at 20:45.", payload.score.minimumAction)
      assertEquals("No heroic add-ons.", payload.score.avoid)
      assertEquals(-4.0, payload.score.lifeLoadScore, 0.001)
    }
  }

  @Test
  fun coreDashboardParsesTrendAndHistoryRows() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_dashboard_v1",
              "date":"2026-05-04",
              "daily_zone":"yellow",
              "mode":"protect",
              "why":["repeated late phone"],
              "weekly_context":{"week_start":"2026-05-04","week_end":"2026-05-10","approved_days":2,"zone":"yellow"},
              "drift_signals":{
                "risk_level":"yellow",
                "recommended_mode":"protect",
                "top_contributing_signals":["repeated late phone"],
                "next_action":{"primary_action":"Phone outside bedroom by 21:00 tonight."}
              },
              "trend":{
                "rows":[
                  {"date":"2026-05-03","features":{"life_load_rolling_avg_7d":4.0,"acute_load_7d":1.0,"chronic_capacity_42d":5.0,"life_margin_7d":1.0,"drift_risk_score":4.0,"red_flag_count_7d":1}}
                ]
              },
              "history":[
                {"date":"2026-05-03","state":"approved","zone":"yellow","next_action":"Protect shutdown.","life_load_score":4.0,"diary_summary":"late phone"}
              ]
            }
            """.trimIndent(),
          ),
      )
      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val dashboard = api.getDashboard("2026-05-04", weeks = 8)

      assertEquals("yellow", dashboard.drift?.riskLevel)
      assertEquals(listOf("repeated late phone"), dashboard.drift?.contributingSignals)
      assertEquals(1, dashboard.trendPoints.size)
      assertEquals(4.0, dashboard.trendPoints.first().lifeLoadRollingAvg7d, 0.001)
      assertEquals("late phone", dashboard.historyDays.first().diarySummary)
    }
  }

  @Test
  fun analyzeWarningsBecomeProposalErrorWhenAiFails() = runBlocking {
    MockWebServer().use { server ->
      server.enqueue(
        MockResponse()
          .setResponseCode(200)
          .setBody(
            """
            {
              "schema_version":"life_load_entry_payload_v1",
              "date":"2026-05-04",
              "entry":null,
              "draftEntry":{"date":"2026-05-04","diary_text":"no alcohol","structured":{},"summary":"","updated_at":"2026-05-05T06:00:00Z"},
              "summary":null,
              "week_context":{"week_start":"2026-05-04","week_end":"2026-05-10","approved_days":0},
              "proposal":null,
              "warnings":["AI unavailable"]
            }
            """.trimIndent(),
          ),
      )
      val api = HttpLifeLoadApi(
        client = OkHttpClient.Builder().build(),
        serverBaseUrl = server.url("/").toString().trimEnd('/'),
      )

      val result = api.analyzeDiary(com.life.lifeload.domain.LifeLoadEntry(date = "2026-05-04", diaryText = "no alcohol"))

      assertEquals("AI unavailable", result.proposal.fallbackError)
      assertEquals(null, result.payload.draftEntry.alcohol)
    }
  }
}
