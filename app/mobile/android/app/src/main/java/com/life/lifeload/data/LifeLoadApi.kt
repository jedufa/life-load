package com.life.lifeload.data

import com.life.lifeload.domain.LifeLoadAnalyzeResult
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadGarminImportResult
import com.life.lifeload.domain.LifeLoadPlatformContract
import com.life.lifeload.domain.LifeLoadSettings

interface LifeLoadApi {
  suspend fun isBackendHealthy(): Boolean
  suspend fun register(email: String, password: String): LifeLoadAuthSession
  suspend fun login(email: String, password: String): LifeLoadAuthSession
  suspend fun logout()
  suspend fun getContract(): LifeLoadPlatformContract
  suspend fun getSettings(): LifeLoadSettings
  suspend fun saveSettings(settings: LifeLoadSettings, garminPassword: String = ""): LifeLoadSettings
  suspend fun getEntry(date: String): LifeLoadEntryPayload
  suspend fun saveEntry(entry: LifeLoadEntry, action: String = "draft"): LifeLoadEntryPayload
  suspend fun analyzeDiary(entry: LifeLoadEntry): LifeLoadAnalyzeResult
  suspend fun approveEntry(entry: LifeLoadEntry): LifeLoadEntryPayload
  suspend fun importGarmin(date: String, days: Int): LifeLoadGarminImportResult
  suspend fun getDashboard(date: String, weeks: Int = 8): LifeLoadDashboard
  suspend fun mirrorLocalDebugBundle(bundleJson: String): LifeLoadDebugMirrorResult
}
