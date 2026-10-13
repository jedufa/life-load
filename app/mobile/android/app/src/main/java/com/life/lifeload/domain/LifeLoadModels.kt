package com.life.lifeload.domain

data class LifeLoadEntry(
  val date: String,
  val diaryText: String = "",
  val diarySummary: String = "",
  val tags: List<String> = emptyList(),
  val sleepOk: Boolean? = null,
  val nutritionOk: Boolean? = null,
  val alcohol: String? = null,
  val binge: Boolean? = null,
  val mood: Int? = null,
  val stress: Int? = null,
  val energy: Int? = null,
  val coffeeCups: Int? = null,
  val footPain: Int? = null,
  val shoulderPain: Int? = null,
  val migraineWarning: Boolean? = null,
  val decompressionDone: Boolean? = null,
  val afterWorkDecompressionDone: Boolean? = null,
  val eveningChainBroken: Boolean? = null,
  val shutdownDone: Boolean? = null,
  val phoneAfter21: Boolean? = null,
  val projectOverrun: Boolean? = null,
  val primaryActivityType: String = "",
  val activityTypes: List<String> = emptyList(),
  val activityDurationMin: Int? = null,
  val rehabDone: Boolean? = null,
  val otherSymptoms: String = "",
  val workIntensity: String = "",
  val familyStress: Int? = null,
  val wifeConflictCount: Int? = null,
  val wifeConflictSchool: Boolean? = null,
  val wifeConflictChores: Boolean? = null,
  val wifeConflictOther: Boolean? = null,
  val homeOffice: Boolean? = null,
  val aloneHome: Boolean? = null,
  val homeworkDone: Boolean? = null,
  val homeworkStatus: String? = null,
)

data class LifeLoadFlag(
  val type: String,
  val severity: String = "",
  val evidence: String = "",
)

data class LifeLoadScore(
  val zone: String = "",
  val mode: String = "",
  val nextAction: String = "",
  val minimumAction: String = "",
  val avoid: String = "",
  val why: List<String> = emptyList(),
  val confidence: Double? = null,
  val lifeLoadScore: Double = 0.0,
  val baseScore: Double = 0.0,
  val profileAdjustedScore: Double = 0.0,
  val guidanceMediumThreshold: Int = 35,
  val guidanceHighThreshold: Int = 70,
  val profileModifiers: List<String> = emptyList(),
  val profileEffects: List<String> = emptyList(),
  val trainingLoad: Double = 0.0,
  val recoveryScore: Double = 0.0,
  val strainScore: Double = 0.0,
  val hardSessions: Int = 0,
  val rehabSessions: Int = 0,
  val acuteTrainingLoad: Double = 0.0,
  val chronicTrainingLoad: Double = 0.0,
  val trainingLoadRatio: Double? = null,
  val trainingRamp: Double = 0.0,
  val warnings: List<String> = emptyList(),
  val redFlags: List<String> = emptyList(),
)

data class LifeLoadWeekContext(
  val weekStart: String = "",
  val weekEnd: String = "",
  val approvedDays: Int = 0,
  val zone: String = "",
  val mode: String = "",
  val topDriftSignals: List<String> = emptyList(),
  val nextAction: String = "",
)

data class LifeLoadFormulaItem(
  val input: String,
  val effect: String,
)

data class LifeLoadFormulaSection(
  val title: String,
  val body: String = "",
  val items: List<LifeLoadFormulaItem> = emptyList(),
)

data class LifeLoadFormulaContract(
  val schemaVersion: String = "",
  val scoringContractVersion: String = "",
  val sections: List<LifeLoadFormulaSection> = emptyList(),
)

data class LifeLoadPlatformContract(
  val schemaVersion: String = "",
  val entryFields: List<String> = emptyList(),
  val scoreOutputKeys: List<String> = emptyList(),
  val trendFeatureFields: List<String> = emptyList(),
  val formula: LifeLoadFormulaContract = LifeLoadFormulaContract(),
)

data class LifeLoadGarminSettings(
  val enabled: Boolean = false,
  val email: String = "",
  val passwordSet: Boolean = false,
  val autoImport: Boolean = false,
  val autoImportDays: Int = 3,
)

data class LifeLoadDailyFlowSettings(
  val defaultDate: String = "yesterday",
  val entryCacheDays: Int = 5,
  val secondaryCardsCollapsed: Boolean = true,
)

data class LifeLoadReminderSettings(
  val enabled: Boolean = false,
  val hour: Int = 21,
  val minute: Int = 30,
)

data class LifeLoadFormulaSettings(
  val profile: String = "balanced",
  val profileModifiers: Set<String> = emptySet(),
  val includeTrainingTrendBrake: Boolean = true,
  val includeGarminRecovery: Boolean = true,
  val includeRelationshipStress: Boolean = true,
  val includeAloneHome: Boolean = true,
  val includeAfterWorkDecompression: Boolean = true,
  val includeProjectOverrun: Boolean = true,
  val includeLatePhone: Boolean = true,
  val includeHomeOffice: Boolean = true,
)

data class LifeLoadDebugSettings(
  val showFormulaButton: Boolean = true,
  val showGarminImportButtons: Boolean = true,
)

data class LifeLoadSettings(
  val garmin: LifeLoadGarminSettings = LifeLoadGarminSettings(),
  val dailyFlow: LifeLoadDailyFlowSettings = LifeLoadDailyFlowSettings(),
  val reminder: LifeLoadReminderSettings = LifeLoadReminderSettings(),
  val formula: LifeLoadFormulaSettings = LifeLoadFormulaSettings(),
  val debug: LifeLoadDebugSettings = LifeLoadDebugSettings(),
)

data class LifeLoadProposal(
  val proposalId: String = "",
  val summary: String = "",
  val nextAction: String = "",
  val extractorVersion: String = "",
  val fields: Map<String, Any?> = emptyMap(),
  val redFlags: List<LifeLoadFlag> = emptyList(),
  val fallbackError: String = "",
)

data class LifeLoadWeeklyMini(
  val zone: String = "",
  val nextAction: String = "",
  val approvedDayDates: List<String> = emptyList(),
  val netLifeLoad: Double = 0.0,
  val successScore: Double = 0.0,
  val hardSessions: Int = 0,
  val recoveryScore: Double = 0.0,
  val sleepCompleted: Int = 0,
  val sleepTarget: Int = 0,
  val nutritionCompleted: Int = 0,
  val nutritionTarget: Int = 0,
  val redFlagCount: Int = 0,
)

data class LifeLoadRecentWeek(
  val weekStart: String,
  val weekEnd: String,
  val zone: String,
  val nextAction: String,
  val netLifeLoad: Double,
  val successScore: Double,
)

data class LifeLoadTrendPoint(
  val date: String,
  val lifeLoadRollingAvg7d: Double = 0.0,
  val sleepCompliance7d: Double = 0.0,
  val nutritionCompliance7d: Double = 0.0,
  val projectOverrunCount7d: Int = 0,
  val projectOverrunWeighted7d: Double = 0.0,
  val projectOverrunRecentCount3d: Int = 0,
  val projectOverrunOlderCount4To7d: Int = 0,
  val projectOverrunMostRecentDaysAgo: Int = -1,
  val projectOverrunTrend: String = "",
  val phoneAfter21Count7d: Int = 0,
  val phoneAfter21Weighted7d: Double = 0.0,
  val phoneAfter21RecentCount3d: Int = 0,
  val phoneAfter21OlderCount4To7d: Int = 0,
  val phoneAfter21MostRecentDaysAgo: Int = -1,
  val phoneAfter21Trend: String = "",
  val painAvg7d: Double = 0.0,
  val redFlagCount7d: Int = 0,
  val acuteLoad7d: Double = 0.0,
  val chronicCapacity42d: Double = 0.0,
  val lifeMargin7d: Double = 0.0,
  val weightKgLatest: Double = 0.0,
  val weightLatestDaysOld: Int = -1,
  val weightChange14d: Double = 0.0,
  val weightChange30d: Double = 0.0,
  val weightChange14dUsable: Boolean = false,
  val weightChange30dUsable: Boolean = false,
  val driftRiskScore: Double = 0.0,
  val recommendedMode: String = "",
)

data class LifeLoadDriftSnapshot(
  val date: String = "",
  val riskLevel: String = "",
  val mode: String = "",
  val nextAction: String = "",
  val evidenceNote: String = "",
  val contributingSignals: List<String> = emptyList(),
)

data class LifeLoadHistoryDay(
  val date: String,
  val state: String = "",
  val approvedAt: String = "",
  val canonicalCompleted: Boolean = false,
  val zone: String = "",
  val nextAction: String = "",
  val lifeLoadScore: Double = 0.0,
  val diarySummary: String = "",
  val mood: Int? = null,
  val stress: Int? = null,
  val energy: Int? = null,
  val scoreAvailable: Boolean? = null,
)

data class LifeLoadDashboard(
  val date: String,
  val dbRoot: String = "",
  val weekly: LifeLoadWeeklyMini = LifeLoadWeeklyMini(),
  val recentWeeks: List<LifeLoadRecentWeek> = emptyList(),
  val trendPoints: List<LifeLoadTrendPoint> = emptyList(),
  val drift: LifeLoadDriftSnapshot? = null,
  val historyDays: List<LifeLoadHistoryDay> = emptyList(),
)

data class LifeLoadEntryPayload(
  val date: String,
  val defaultDate: String,
  val previousDate: String,
  val nextDate: String,
  val entryState: String,
  val hasDraft: Boolean,
  val entryExists: Boolean,
  val approvedAt: String,
  val draftUpdatedAt: String,
  val entry: LifeLoadEntry,
  val draftEntry: LifeLoadEntry,
  val approvedEntry: LifeLoadEntry?,
  val score: LifeLoadScore,
  val scoreAvailable: Boolean? = null,
  val hasLocalDraft: Boolean = false,
  val weeklyContext: LifeLoadWeekContext = LifeLoadWeekContext(),
  val latestProposal: LifeLoadProposal?,
  val derivedDashboard: LifeLoadDashboard? = null,
)

data class LifeLoadGarminImportResult(
  val payload: LifeLoadEntryPayload?,
  val daysImported: Int = 0,
  val passiveUpserted: Int = 0,
  val activityUpserted: Int = 0,
  val skippedReason: String = "",
)

data class LifeLoadAnalyzeResult(
  val payload: LifeLoadEntryPayload,
  val proposal: LifeLoadProposal,
  val extractorVersion: String = "",
  val extractorModel: String = "",
  val extractorTimeoutS: Int = 0,
)

enum class LifeLoadBackendStatus { ONLINE, OFFLINE, ERROR }
enum class LifeLoadDbStatus { READY, ERROR, UNKNOWN }
enum class LifeLoadSyncStatus { DRAFT, SAVING, SAVED, ERROR }
enum class LifeLoadExtractStatus { IDLE, ANALYZING, ERROR }

data class LifeLoadStatusLights(
  val backend: LifeLoadBackendStatus = LifeLoadBackendStatus.OFFLINE,
  val db: LifeLoadDbStatus = LifeLoadDbStatus.UNKNOWN,
  val sync: LifeLoadSyncStatus = LifeLoadSyncStatus.SAVED,
  val extract: LifeLoadExtractStatus = LifeLoadExtractStatus.IDLE,
)
