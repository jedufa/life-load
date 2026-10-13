package com.life.lifeload.ui

import android.app.Application
import android.content.Context
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.life.lifeload.BuildConfig
import com.life.lifeload.R
import com.life.lifeload.data.AuthConfig
import com.life.lifeload.data.HttpLifeLoadApi
import com.life.lifeload.data.LifeLoadAuthRequiredException
import com.life.lifeload.data.LifeLoadAuthSession
import com.life.lifeload.data.LifeLoadRepository
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.domain.LifeLoadDashboard
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadEntryPayload
import com.life.lifeload.domain.LifeLoadExtractStatus
import com.life.lifeload.domain.LifeLoadFormulaContract
import com.life.lifeload.domain.LifeLoadProfileCatalog
import com.life.lifeload.domain.LifeLoadProfileSetupState
import com.life.lifeload.domain.LifeLoadProposal
import com.life.lifeload.domain.LifeLoadReminderSettings
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.LifeLoadStatusLights
import com.life.lifeload.domain.LifeLoadBackendStatus
import com.life.lifeload.domain.LifeLoadDbStatus
import com.life.lifeload.domain.LifeLoadSyncStatus
import com.life.lifeload.domain.LifeLoadWeekContext
import com.life.lifeload.notifications.LifeLoadReminderScheduler
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.LocalDate
import java.time.ZoneId
import java.util.LinkedHashMap
import java.util.Locale

data class LifeLoadLocalDebugState(
  val available: Boolean = false,
  val message: String = "",
  val schemaVersion: String = "",
  val redaction: String = "",
  val entryCount: Int = 0,
  val outboxCount: Int = 0,
  val conflictCount: Int = 0,
  val approvedCount: Int = 0,
  val draftCount: Int = 0,
  val pendingApprovalCount: Int = 0,
)

data class LifeLoadUiState(
  val authSession: LifeLoadAuthSession = LifeLoadAuthSession(),
  val authLoading: Boolean = false,
  val authMessage: String = "",
  val authError: String = "",
  val currentDate: LocalDate = yesterdayDate(),
  val selectedDate: String = yesterdayIso(),
  val entry: LifeLoadEntry = LifeLoadEntry(date = yesterdayIso()),
  val draftEntry: LifeLoadEntry = LifeLoadEntry(date = yesterdayIso()),
  val score: LifeLoadScore = LifeLoadScore(),
  val dailySummary: LifeLoadScore = LifeLoadScore(),
  val weeklyContext: LifeLoadWeekContext = LifeLoadWeekContext(),
  val dashboard: LifeLoadDashboard = LifeLoadDashboard(date = todayIso()),
  val latestProposal: LifeLoadProposal? = null,
  val formulaContract: LifeLoadFormulaContract = LifeLoadFormulaContract(),
  val settings: LifeLoadSettings = LifeLoadSettings(),
  val settingsOpen: Boolean = false,
  val settingsSaving: Boolean = false,
  val settingsMessage: String = "",
  val loading: Boolean = false,
  val dashboardLoading: Boolean = false,
  val dashboardSlowLoading: Boolean = false,
  val analysisLocked: Boolean = false,
  val entryState: String = "blank",
  val hasDraft: Boolean = false,
  val hasUnsavedChanges: Boolean = false,
  val entryExists: Boolean = false,
  val scoreAvailable: Boolean? = null,
  val approvedAt: String = "",
  val draftUpdatedAt: String = "",
  val message: String = "",
  val error: String = "",
  val backupMessage: String = "",
  val privacyMessage: String = "",
  val statusLights: LifeLoadStatusLights = LifeLoadStatusLights(),
  val localDebug: LifeLoadLocalDebugState = LifeLoadLocalDebugState(),
  val profileSetup: LifeLoadProfileSetupState = LifeLoadProfileSetupState(),
  val profileOnboardingCompleted: Boolean = false,
)

private fun yesterdayIso(): String = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
private fun yesterdayDate(): LocalDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1)
private fun todayIso(): String = LocalDate.now(ZoneId.of("Europe/Vienna")).toString()

class LifeLoadViewModel(
  application: Application,
  private val repository: LifeLoadRepository = LifeLoadRepository(
    HttpLifeLoadApi(
      serverBaseUrlProvider = { ServerConfig.resolveBaseUrl(application) },
      authTokenProvider = { AuthConfig.resolve(application).sessionToken },
    ),
    localStore = LifeLoadLocalStore(application, defaultProfileId = BuildConfig.LIFE_LOAD_DEFAULT_PROFILE_ID),
  ),
  initialAuthSession: LifeLoadAuthSession = AuthConfig.resolve(application),
) : AndroidViewModel(application) {
  private val _uiState = MutableStateFlow(LifeLoadUiState(authSession = initialAuthSession))
  val uiState: StateFlow<LifeLoadUiState> = _uiState.asStateFlow()

  private var loadJob: Job? = null
  private var prefetchJob: Job? = null
  private var dashboardSlowLoadingJob: Job? = null
  private var draftPersistenceJob: Job? = null
  private var entryCacheDays = 5
  private val entryCache = object : LinkedHashMap<String, LifeLoadEntryPayload>(5, 0.75f, true) {
    override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, LifeLoadEntryPayload>?): Boolean = size > entryCacheDays
  }
  private val prefetchInFlight = mutableSetOf<String>()

  private fun s(id: Int): String = runCatching { getApplication<Application>().getString(id) }.getOrElse { fallbackString(id) }
  private fun s(id: Int, vararg args: Any): String =
    runCatching { getApplication<Application>().getString(id, *args) }
      .getOrElse { String.format(Locale.getDefault(), fallbackString(id), *args) }
  private fun errorText(error: Throwable): String = error.message ?: error::class.java.simpleName

  private fun fallbackString(id: Int): String = when (id) {
    R.string.vm_settings_changed_local -> "Settings changed locally"
    R.string.settings_saving -> "Saving..."
    R.string.settings_reminder_updated -> "Reminder updated"
    R.string.settings_reminder_update_failed -> "Reminder update failed"
    R.string.compass_unsaved_draft_exists -> "Unsaved draft exists"
    R.string.vm_settings_saved -> "Settings saved."
    R.string.vm_settings_save_failed -> "Settings could not be saved."
    R.string.vm_profile_changed_hidden_preserved -> "Profile changed. Check-in fields updated."
    R.string.vm_optional_pack_enabled -> "Optional pack enabled."
    R.string.vm_optional_pack_disabled -> "Optional pack disabled."
    R.string.vm_profile_defaults_restored -> "Profile defaults restored. History is preserved."
    R.string.vm_profile_setup_ready -> "Profile setup ready."
    R.string.vm_future_days_blank -> "Future days stay blank until they arrive."
    R.string.vm_garmin_refreshing_before_save -> "Refreshing Garmin before saving check-in..."
    R.string.vm_garmin_import_skipped -> "Garmin import skipped: %s."
    R.string.vm_garmin_auto_import_off -> "Garmin auto-import is off."
    R.string.vm_checkin_saved_refreshing_guidance -> "Check-in saved; refreshing guidance..."
    R.string.vm_checkin_saved_local_sync_pending -> "Check-in saved locally; sync pending."
    R.string.vm_checkin_saved_recalculated -> "Check-in saved and recalculated."
    R.string.vm_checkin_saved_dashboard_pending -> "Check-in saved; dashboard refresh pending."
    R.string.vm_diary_required_before_analysis -> "Diary text is required before analysis."
    R.string.vm_ai_extraction_attention -> "AI extraction needs attention; draft was preserved for retry."
    R.string.vm_ai_analyzed_model -> "AI analyzed the diary with %s."
    R.string.vm_diary_analyzed -> "Diary analyzed."
    R.string.vm_diary_analysis_attention -> "Diary analysis needs attention."
    R.string.vm_importing_garmin_days -> "Importing Garmin for %d days..."
    R.string.vm_importing_garmin_selected_day -> "Importing Garmin for selected day..."
    R.string.vm_garmin_import_attention -> "Garmin import needs attention."
    R.string.vm_redacted_diagnostics_loaded -> "Redacted diagnostics loaded."
    R.string.vm_local_diagnostics_failed -> "Local diagnostics failed: %s"
    R.string.vm_importing_recent_history -> "Importing recent history..."
    R.string.vm_imported_recent_history -> "Imported %d/%d day(s); %d failed."
    R.string.vm_recent_history_import_failed -> "Recent history import failed: %s"
    R.string.vm_restoring_from_server -> "Restoring from server..."
    R.string.vm_restored_from_server -> "Restored %d/%d day(s); %d failed."
    R.string.vm_restore_from_server_failed -> "Restore from server failed: %s"
    R.string.vm_syncing_pending_local_changes -> "Syncing pending local changes..."
    R.string.vm_synced_local_changes -> "Synced %d/%d; %d failed; %d conflict(s)."
    R.string.vm_local_sync_failed -> "Local sync failed: %s"
    R.string.vm_mirroring_redacted_diagnostics -> "Mirroring redacted diagnostics..."
    R.string.vm_mirrored_redacted_diagnostics -> "Mirrored %d local row(s) to %s; %d pending."
    R.string.vm_debug_mirror_failed -> "Debug mirror failed: %s"
    R.string.vm_exported_local_data -> "Exported %d row(s) to %s; %d pending."
    R.string.vm_exported_backup_file -> "Saved backup file with %d row(s); %d pending."
    R.string.vm_imported_backup_file -> "Imported backup file with %d row(s); %d pending."
    R.string.vm_local_diagnostics_refreshed_after_export -> "Local diagnostics refreshed after export."
    R.string.vm_export_failed -> "Export failed: %s"
    R.string.vm_import_failed -> "Import failed: %s"
    R.string.vm_local_data_deleted -> "Local data deleted."
    R.string.vm_local_data_deleted_rows_remain -> "Local data deleted; %d rows remain."
    R.string.vm_delete_failed -> "Delete failed: %s"
    R.string.vm_profile_setup_failed -> "Profile setup failed: %s"
    R.string.vm_local_diagnostics_unavailable -> "Local diagnostics are not available in this repository."
    R.string.vm_saved -> "Saved."
    R.string.vm_saved_local_sync_pending -> "Saved locally; sync pending."
    R.string.vm_cached_day_refreshing -> "Cached day shown; refreshing..."
    R.string.vm_dashboard_load_failed -> "Could not load the dashboard."
    R.string.vm_dashboard_attention -> "Dashboard needs attention: %s"
    R.string.vm_entry_load_failed -> "Could not load the entry."
    R.string.vm_cached_day_refresh_failed -> "Showing cached day; refresh failed."
    R.string.vm_garmin_data_fresh -> "Garmin data is fresh."
    R.string.vm_garmin_token_missing -> "Garmin token is not connected yet."
    R.string.vm_garmin_imported -> "Garmin imported: %d passive row(s), %d activity row(s) across %d day(s)."
    else -> ""
  }

  init {
    refreshProfileOnboardingState()
    refreshProfileSetupState()
    loadDate(_uiState.value.selectedDate, refreshDashboard = true)
  }

  fun signIn(email: String, password: String) {
    authenticate(email, password, register = false)
  }

  fun register(email: String, password: String) {
    authenticate(email, password, register = true)
  }

  private fun authenticate(email: String, password: String, register: Boolean) {
    val normalizedEmail = email.trim()
    if (normalizedEmail.isBlank() || password.isBlank()) {
      _uiState.update { it.copy(authError = "Email and password are required.", authMessage = "") }
      return
    }
    _uiState.update { it.copy(authLoading = true, authError = "", authMessage = "") }
    viewModelScope.launch {
      try {
        val session = if (register) repository.register(normalizedEmail, password) else repository.login(normalizedEmail, password)
        AuthConfig.save(getApplication(), session.copy(email = normalizedEmail))
        _uiState.update {
          it.copy(
            authSession = session.copy(email = normalizedEmail),
            authMessage = if (register) "Account created." else "Signed in.",
            authError = "",
            authLoading = false,
          )
        }
        runCatching { repository.syncPendingOutbox() }
        refreshProfileOnboardingState()
        refreshProfileSetupState()
        loadDate(_uiState.value.selectedDate, refreshDashboard = true)
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update { it.copy(authLoading = false, authError = errorText(error), authMessage = "") }
      }
    }
  }

  fun signOut() {
    viewModelScope.launch {
      runCatching { repository.logout() }
      clearAuthSession("Signed out.")
    }
  }

  private fun clearAuthSession(message: String) {
    AuthConfig.clear(getApplication())
    entryCache.clear()
    _uiState.update {
      it.copy(
        authSession = LifeLoadAuthSession(),
        authMessage = message,
        authError = "",
        authLoading = false,
      )
    }
    loadDate(_uiState.value.selectedDate, refreshDashboard = false)
  }

  private fun handleAuthFailure(error: Throwable): Boolean {
    if (error !is LifeLoadAuthRequiredException) return false
    clearAuthSession("Session expired. Sign in again.")
    return true
  }

  fun refreshSelectedDate() {
    loadDate(_uiState.value.selectedDate, refreshDashboard = true)
  }

  fun selectPreviousDate() = shiftDate(days = -1)
  fun selectNextDate() = shiftDate(days = 1)
  fun shiftSelectedDate(days: Long) = shiftDate(days = days)
  fun selectToday() = loadDate(todayIso(), refreshDashboard = true)
  fun selectYesterday() = loadDate(yesterdayIso(), refreshDashboard = true)

  fun openSettings() {
    _uiState.update { it.copy(settingsOpen = true, settingsMessage = "") }
    refreshLocalDebugDiagnostics()
  }

  fun closeSettings() {
    _uiState.update { it.copy(settingsOpen = false, settingsMessage = "") }
  }

  fun updateSettings(settings: LifeLoadSettings) {
    entryCacheDays = settings.dailyFlow.entryCacheDays.coerceIn(1, 14)
    _uiState.update { it.copy(settings = settings, settingsMessage = s(R.string.vm_settings_changed_local)) }
  }

  fun updateReminderSettings(reminder: LifeLoadReminderSettings) {
    val previousReminder = _uiState.value.settings.reminder
    val settings = _uiState.value.settings.copy(reminder = reminder)
    entryCacheDays = settings.dailyFlow.entryCacheDays.coerceIn(1, 14)
    _uiState.update { it.copy(settings = settings, settingsSaving = true, settingsMessage = "", error = "") }
    viewModelScope.launch {
      try {
        val saved = repository.saveSettings(settings, "")
        entryCacheDays = saved.dailyFlow.entryCacheDays.coerceIn(1, 14)
        LifeLoadReminderScheduler.apply(getApplication(), saved.reminder)
        _uiState.update {
          it.copy(
            settings = saved,
            settingsSaving = false,
            settingsMessage = getApplication<Application>().getString(R.string.settings_reminder_updated),
          )
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(
            settings = it.settings.copy(reminder = previousReminder),
            settingsSaving = false,
            settingsMessage = "",
            error = error.message ?: getApplication<Application>().getString(R.string.settings_reminder_update_failed),
          )
        }
      }
    }
  }

  fun saveSettings(garminPassword: String = "") {
    val settings = _uiState.value.settings
    viewModelScope.launch {
      _uiState.update { it.copy(settingsSaving = true, settingsMessage = s(R.string.settings_saving), error = "") }
      try {
        val saved = repository.saveSettings(settings, garminPassword)
        entryCacheDays = saved.dailyFlow.entryCacheDays.coerceIn(1, 14)
        LifeLoadReminderScheduler.apply(getApplication(), saved.reminder)
        _uiState.update {
          it.copy(
            settings = saved,
            settingsSaving = false,
            settingsMessage = s(R.string.vm_settings_saved),
          )
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(
            settingsSaving = false,
            settingsMessage = "",
            error = error.message ?: s(R.string.vm_settings_save_failed),
          )
        }
      }
    }
  }

  fun selectProfile(profileId: String) {
    val currentPacks = _uiState.value.profileSetup.optionalPackIds
    saveProfileSetup(
      profileId = profileId,
      optionalPackIds = currentPacks.filter { packId ->
        packId in LifeLoadProfileCatalog.profiles[profileId]?.allowedOptionalPackIds.orEmpty()
      }.toSet(),
      message = s(R.string.vm_profile_changed_hidden_preserved),
    )
  }

  fun toggleOptionalPack(packId: String, enabled: Boolean) {
    val current = _uiState.value.profileSetup
    val nextPacks = if (enabled) current.optionalPackIds + packId else current.optionalPackIds - packId
    saveProfileSetup(
      profileId = current.selectedConfig.activeProfileId,
      optionalPackIds = nextPacks,
      message = if (enabled) s(R.string.vm_optional_pack_enabled) else s(R.string.vm_optional_pack_disabled),
    )
  }

  fun resetProfileDefaults() {
    saveProfileSetup(
      profileId = _uiState.value.profileSetup.selectedConfig.activeProfileId,
      optionalPackIds = emptySet(),
      message = s(R.string.vm_profile_defaults_restored),
    )
  }

  fun completeProfileOnboarding() {
    runCatching {
      profileOnboardingPrefs()
        .edit()
        .putBoolean(KEY_PROFILE_ONBOARDING_COMPLETED, true)
        .apply()
    }
    _uiState.update { it.copy(profileOnboardingCompleted = true, message = s(R.string.vm_profile_setup_ready)) }
  }

  private fun shiftDate(days: Long) {
    val next = LocalDate.parse(_uiState.value.selectedDate).plusDays(days)
    val today = LocalDate.parse(todayIso())
    if (next.isAfter(today)) {
      _uiState.update { it.copy(message = s(R.string.vm_future_days_blank)) }
      return
    }
    loadDate(next.toString(), refreshDashboard = true)
  }

  fun updateDiaryText(value: String) {
    mutateDraft { it.copy(diaryText = value) }
  }

  fun updateTagsFromText(value: String) {
    mutateDraft {
      it.copy(
        tags = value.split(",").map(String::trim).filter(String::isNotBlank).distinct(),
      )
    }
  }

  fun updateBooleanField(field: String, value: Boolean?) {
    if (!draftFieldActive(field)) return
    mutateDraft { entry ->
      when (field) {
        "sleep_ok" -> entry.copy(sleepOk = value)
        "nutrition_ok" -> entry.copy(nutritionOk = value)
        "alcohol" -> entry.copy(alcohol = if (value == true) "home" else if (value == false) "none" else null)
        "binge" -> entry.copy(binge = value)
        "migraine_warning" -> entry.copy(migraineWarning = value)
        "decompression_done" -> entry.copy(decompressionDone = value)
        "after_work_decompression_done" -> entry.copy(afterWorkDecompressionDone = value)
        "evening_chain_broken" -> entry.copy(eveningChainBroken = value)
        "shutdown_done" -> entry.copy(shutdownDone = value)
        "phone_after_21" -> entry.copy(phoneAfter21 = value)
        "project_overrun" -> entry.copy(projectOverrun = value)
        "home_office" -> entry.copy(homeOffice = value)
        "alone_home" -> entry.copy(aloneHome = value)
        "homework_done" -> entry.copy(homeworkDone = value)
        "rehab_done" -> entry.copy(rehabDone = value)
        "wife_conflict_school" -> entry.copy(wifeConflictSchool = value)
        "wife_conflict_chores" -> entry.copy(wifeConflictChores = value)
        "wife_conflict_other" -> entry.copy(wifeConflictOther = value)
        else -> entry
      }
    }
  }

  fun updateIntField(field: String, value: Int?) {
    if (!draftFieldActive(field)) return
    mutateDraft { entry ->
      when (field) {
        "mood" -> entry.copy(mood = value)
        "stress" -> entry.copy(stress = value)
        "energy" -> entry.copy(energy = value)
        "coffee_cups" -> entry.copy(coffeeCups = value?.coerceIn(0, 8))
        "foot_pain" -> entry.copy(footPain = value)
        "shoulder_pain" -> entry.copy(shoulderPain = value)
        "family_stress" -> entry.copy(familyStress = value)
        "wife_conflict_count" -> entry.copy(wifeConflictCount = value?.coerceIn(0, 12))
        "activity_duration_min" -> entry.copy(activityDurationMin = value)
        else -> entry
      }
    }
  }

  fun updateStringField(field: String, value: String) {
    if (!draftFieldActive(field)) return
    mutateDraft { entry ->
      when (field) {
        "work_intensity" -> entry.copy(workIntensity = value)
        "alcohol" -> entry.copy(alcohol = value.ifBlank { null })
        "homework_done" -> entry.copy(homeworkStatus = value.ifBlank { null }, homeworkDone = when (value) {
          "yes" -> true
          "no" -> false
          else -> null
        })
        "primary_activity_type" -> entry.copy(
          primaryActivityType = value,
          activityTypes = listOfNotNull(value.takeIf(String::isNotBlank)),
        )
        "activity_types" -> {
          val types = value.split(",").map(String::trim).filter(String::isNotBlank).distinct()
          entry.copy(primaryActivityType = types.firstOrNull().orEmpty(), activityTypes = types)
        }
        "other_symptoms" -> entry.copy(otherSymptoms = value)
        "diary_summary" -> entry.copy(diarySummary = value)
        else -> entry
      }
    }
  }

  fun approveEntry() {
    draftPersistenceJob?.cancel()
    val entry = _uiState.value.draftEntry.sanitizedForActiveProfile()
    viewModelScope.launch {
      setSyncStatus(LifeLoadSyncStatus.SAVING)
      val settings = _uiState.value.settings
      val garminAutoImport = settings.garmin.enabled &&
        settings.garmin.autoImport &&
        settings.garmin.passwordSet &&
        settings.garmin.email.isNotBlank()
      val garminMessage = ""
      try {
        repository.saveDraft(entry)
        val payload = repository.approve(entry)
        val derivedDashboard = payload.derivedDashboard
        val localPending = payload.entryState == "pending_approval"
        val pendingSyncStatus = if (localPending) LifeLoadSyncStatus.DRAFT else LifeLoadSyncStatus.SAVED
        val immediateMessage = listOf(
          when {
            localPending -> s(R.string.vm_checkin_saved_local_sync_pending)
            derivedDashboard != null -> s(R.string.vm_checkin_saved_refreshing_guidance)
            else -> s(R.string.vm_checkin_saved_dashboard_pending)
          },
          garminMessage,
        ).filter(String::isNotBlank).joinToString(" ")
        if (derivedDashboard != null) {
          applyPayload(
            payload,
            dashboard = mergeDashboardSnapshot(_uiState.value.dashboard, derivedDashboard),
            message = immediateMessage,
            syncStatus = pendingSyncStatus,
          )
        } else {
          applyEntryPayload(payload, message = immediateMessage, syncStatus = pendingSyncStatus)
        }
        syncPendingInBackgroundIfSignedIn(entry.date)
        if (garminAutoImport) importGarminAfterCheckInSaved(entry.date)
        val signedIn = _uiState.value.authSession.isSignedIn
        val dashboard = runCatching {
          if (signedIn) repository.loadDashboard(entry.date) else repository.loadLocalDashboard(entry.date)
        }.getOrNull()
        if (dashboard != null) {
          applyPayload(
            payload,
            dashboard = dashboard,
            message = listOf(if (localPending) s(R.string.vm_checkin_saved_local_sync_pending) else s(R.string.vm_checkin_saved_recalculated), garminMessage).filter(String::isNotBlank).joinToString(" "),
            backendStatus = if (localPending) LifeLoadBackendStatus.ERROR else LifeLoadBackendStatus.ONLINE,
            syncStatus = if (localPending) LifeLoadSyncStatus.DRAFT else LifeLoadSyncStatus.SAVED,
          )
        } else {
          if (derivedDashboard == null) {
            applyEntryPayload(
              payload,
              message = listOf(if (localPending) s(R.string.vm_checkin_saved_local_sync_pending) else s(R.string.vm_checkin_saved_dashboard_pending), garminMessage).filter(String::isNotBlank).joinToString(" "),
            )
          } else {
            _uiState.update {
              it.copy(
                message = listOf(if (localPending) s(R.string.vm_checkin_saved_local_sync_pending) else s(R.string.vm_checkin_saved_dashboard_pending), garminMessage).filter(String::isNotBlank).joinToString(" "),
              )
            }
          }
          _uiState.update {
            it.copy(
              dashboardLoading = false,
              dashboardSlowLoading = false,
              statusLights = it.statusLights.copy(
                backend = LifeLoadBackendStatus.ERROR,
                db = LifeLoadDbStatus.READY,
                sync = if (localPending) LifeLoadSyncStatus.DRAFT else LifeLoadSyncStatus.SAVED,
              ),
            )
          }
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        setError(error)
        setSyncStatus(LifeLoadSyncStatus.ERROR)
      }
    }
  }

  private fun importGarminAfterCheckInSaved(date: String) {
    viewModelScope.launch {
      runCatching { repository.importGarmin(date, days = 1) }
        .onSuccess { result ->
          if (_uiState.value.selectedDate != date) return@onSuccess
          val garminMessage = garminImportMessage(result.daysImported, result.passiveUpserted, result.activityUpserted, result.skippedReason)
          val signedIn = _uiState.value.authSession.isSignedIn
          val dashboard = runCatching {
            if (signedIn) repository.loadDashboard(date) else repository.loadLocalDashboard(date)
          }.getOrNull()
          if (dashboard != null && _uiState.value.selectedDate == date) {
            applyDashboard(dashboard)
          }
          if (_uiState.value.selectedDate == date && garminMessage.isNotBlank()) {
            _uiState.update { it.copy(message = listOf(it.message, garminMessage).filter(String::isNotBlank).joinToString(" ")) }
          }
        }
        .onFailure { error ->
          if (_uiState.value.selectedDate == date) {
            val garminMessage = s(R.string.vm_garmin_import_skipped, errorText(error))
            _uiState.update { it.copy(message = listOf(it.message, garminMessage).filter(String::isNotBlank).joinToString(" ")) }
          }
        }
    }
  }

  fun analyzeDiary() {
    val requestDate = _uiState.value.selectedDate
    val entry = _uiState.value.draftEntry.sanitizedForActiveProfile()
    if (entry.diaryText.isBlank()) {
      _uiState.update { it.copy(error = s(R.string.vm_diary_required_before_analysis)) }
      return
    }
    _uiState.update {
      it.copy(
        error = "",
        message = "",
        analysisLocked = true,
        statusLights = it.statusLights.copy(extract = LifeLoadExtractStatus.ANALYZING),
      )
    }
    viewModelScope.launch {
      try {
        val result = repository.analyze(entry)
        if (_uiState.value.selectedDate == requestDate) {
          val message = if (result.proposal.fallbackError.isNotBlank()) {
            s(R.string.vm_ai_extraction_attention)
          } else if (result.extractorModel.isNotBlank()) {
            s(R.string.vm_ai_analyzed_model, result.extractorModel)
          } else {
            s(R.string.vm_diary_analyzed)
          }
          applyEntryPayload(result.payload, message = message)
        }
        _uiState.update {
          it.copy(
            analysisLocked = false,
            statusLights = it.statusLights.copy(extract = LifeLoadExtractStatus.IDLE),
          )
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(
            analysisLocked = false,
            error = error.message ?: s(R.string.vm_diary_analysis_attention),
            statusLights = it.statusLights.copy(extract = LifeLoadExtractStatus.ERROR),
          )
        }
      }
    }
  }

  fun importGarmin(days: Int) {
    val requestDate = _uiState.value.selectedDate
    viewModelScope.launch {
      _uiState.update {
        it.copy(
          error = "",
          message = if (days > 1) s(R.string.vm_importing_garmin_days, days) else s(R.string.vm_importing_garmin_selected_day),
          statusLights = it.statusLights.copy(sync = LifeLoadSyncStatus.SAVING),
        )
      }
      try {
        val result = repository.importGarmin(requestDate, days)
        val payload = result.payload
        if (payload != null && _uiState.value.selectedDate == requestDate) {
          applyEntryPayload(payload, message = garminImportMessage(result.daysImported, result.passiveUpserted, result.activityUpserted, result.skippedReason))
        } else {
          loadDate(requestDate, refreshDashboard = true)
        }
        runCatching { repository.loadDashboard(requestDate) }
          .onSuccess { dashboard -> applyDashboard(dashboard) }
        setSyncStatus(LifeLoadSyncStatus.SAVED)
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(
            error = error.message ?: s(R.string.vm_garmin_import_attention),
            message = "",
            statusLights = it.statusLights.copy(sync = LifeLoadSyncStatus.ERROR),
          )
        }
      }
    }
  }

  private fun mutateDraft(transform: (LifeLoadEntry) -> LifeLoadEntry) {
    if (_uiState.value.analysisLocked || _uiState.value.loading) return
    var changedDraft: LifeLoadEntry? = null
    _uiState.update {
      val nextDraft = transform(it.draftEntry)
        .copy(date = it.selectedDate)
        .sanitizedForActiveProfile(it)
      changedDraft = nextDraft
      it.copy(
        draftEntry = nextDraft,
        entry = nextDraft,
        hasDraft = true,
        hasUnsavedChanges = true,
        error = "",
        message = s(R.string.compass_unsaved_draft_exists),
        statusLights = it.statusLights.copy(sync = LifeLoadSyncStatus.DRAFT),
      )
    }
    changedDraft?.let { draft ->
      draftPersistenceJob?.cancel()
      draftPersistenceJob = viewModelScope.launch {
        delay(250)
        runCatching { repository.persistDraftLocally(draft) }
          .onSuccess { persisted ->
            if (persisted) {
              entryCache.remove(draft.date)
            } else if (repository.canPersistDraftLocally()) {
              _uiState.update { it.copy(error = "Could not preserve this edit locally; keep this date open and try again.") }
            }
          }
          .onFailure { error ->
            if (error is CancellationException) throw error
            if (repository.canPersistDraftLocally()) {
              _uiState.update { it.copy(error = "Could not preserve this edit locally; keep this date open and try again.") }
            }
          }
      }
    }
  }

  fun saveDraftNow() {
    draftPersistenceJob?.cancel()
    viewModelScope.launch {
      persistDraft()
    }
  }

  fun refreshLocalDebugDiagnostics() {
    viewModelScope.launch {
      try {
        _uiState.update { it.copy(localDebug = readLocalDebugDiagnostics(s(R.string.vm_redacted_diagnostics_loaded))) }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(localDebug = LifeLoadLocalDebugState(message = s(R.string.vm_local_diagnostics_failed, errorText(error))))
        }
      }
    }
  }

  fun importRecentLocalHistory(days: Int = 7) {
    viewModelScope.launch {
      try {
        _uiState.update { it.copy(localDebug = it.localDebug.copy(message = s(R.string.vm_importing_recent_history))) }
        val result = repository.importRecentHistory(_uiState.value.selectedDate, days)
        val message = s(R.string.vm_imported_recent_history, result.imported, result.requested, result.failed)
        _uiState.update { it.copy(localDebug = readLocalDebugDiagnostics(message)) }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(localDebug = LifeLoadLocalDebugState(message = s(R.string.vm_recent_history_import_failed, errorText(error))))
        }
      }
    }
  }

  fun restoreFromServer() {
    if (!_uiState.value.authSession.isSignedIn) {
      _uiState.update { it.copy(authError = "Sign in to restore from the server.", authMessage = "") }
      return
    }
    viewModelScope.launch {
      try {
        _uiState.update { it.copy(localDebug = it.localDebug.copy(message = s(R.string.vm_restoring_from_server))) }
        val result = repository.importRecentHistory(_uiState.value.selectedDate, days = 730)
        val message = s(R.string.vm_restored_from_server, result.imported, result.requested, result.failed)
        _uiState.update { it.copy(localDebug = readLocalDebugDiagnostics(message)) }
        loadDate(_uiState.value.selectedDate, refreshDashboard = true)
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(localDebug = LifeLoadLocalDebugState(message = s(R.string.vm_restore_from_server_failed, errorText(error))))
        }
      }
    }
  }

  fun syncLocalOutbox() {
    viewModelScope.launch {
      try {
        _uiState.update { it.copy(localDebug = it.localDebug.copy(message = s(R.string.vm_syncing_pending_local_changes))) }
        val result = repository.syncPendingOutbox()
        val message = s(R.string.vm_synced_local_changes, result.uploaded, result.attempted, result.failed, result.conflicts)
        _uiState.update { it.copy(localDebug = readLocalDebugDiagnostics(message)) }
        loadDate(_uiState.value.selectedDate, refreshDashboard = true)
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(localDebug = LifeLoadLocalDebugState(message = s(R.string.vm_local_sync_failed, errorText(error))))
        }
      }
    }
  }

  fun mirrorLocalDebugBundle() {
    viewModelScope.launch {
      try {
        _uiState.update { it.copy(localDebug = it.localDebug.copy(message = s(R.string.vm_mirroring_redacted_diagnostics))) }
        val result = repository.mirrorRedactedLocalDebugBundle()
        val message = s(R.string.vm_mirrored_redacted_diagnostics, result.entryCount, result.path, result.pendingOutboxCount)
        _uiState.update { it.copy(localDebug = readLocalDebugDiagnostics(message)) }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update {
          it.copy(localDebug = LifeLoadLocalDebugState(message = s(R.string.vm_debug_mirror_failed, errorText(error))))
        }
      }
    }
  }

  fun exportLocalData() {
    viewModelScope.launch {
      try {
        val result = repository.exportLocalData()
        _uiState.update {
          it.copy(
            privacyMessage = s(R.string.vm_exported_local_data, result.entryCount, result.path, result.outboxCount),
            localDebug = readLocalDebugDiagnostics(s(R.string.vm_local_diagnostics_refreshed_after_export)),
          )
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update { it.copy(privacyMessage = s(R.string.vm_export_failed, errorText(error))) }
      }
    }
  }

  fun exportLocalDataToUri(uri: Uri) {
    viewModelScope.launch {
      try {
        val result = repository.exportLocalDataBundle()
        val resolver = getApplication<Application>().contentResolver
        resolver.openOutputStream(uri, "wt")?.bufferedWriter(Charsets.UTF_8).use { writer ->
          requireNotNull(writer) { "could not open backup file" }
          writer.write(result.bundleJson)
        }
        _uiState.update {
          it.copy(
            backupMessage = s(R.string.vm_exported_backup_file, result.entryCount, result.outboxCount),
            localDebug = readLocalDebugDiagnostics(s(R.string.vm_local_diagnostics_refreshed_after_export)),
          )
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update { it.copy(backupMessage = s(R.string.vm_export_failed, errorText(error))) }
      }
    }
  }

  fun importLocalDataFromUri(uri: Uri) {
    draftPersistenceJob?.cancel()
    viewModelScope.launch {
      try {
        val resolver = getApplication<Application>().contentResolver
        val bundleJson = resolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8).use { reader ->
          requireNotNull(reader) { "could not open backup file" }
          reader.readText()
        }
        val importedDate = latestEntryDateInBackup(bundleJson)
        val status = repository.importLocalDataBundle(bundleJson)
        entryCache.clear()
        val message = s(R.string.vm_imported_backup_file, status.entryCount, status.pendingOutboxCount)
        _uiState.update {
          it.copy(
            backupMessage = message,
            privacyMessage = message,
            localDebug = readLocalDebugDiagnostics(message),
          )
        }
        refreshProfileSetupState()
        loadDate(importedDate ?: _uiState.value.selectedDate, refreshDashboard = true)
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update { it.copy(backupMessage = s(R.string.vm_import_failed, errorText(error))) }
      }
    }
  }

  private fun latestEntryDateInBackup(bundleJson: String): String? = runCatching {
    val entries = JSONObject(bundleJson).optJSONArray("entries") ?: return@runCatching null
    (0 until entries.length())
      .mapNotNull { index -> entries.optJSONObject(index)?.optString("date")?.takeIf(String::isNotBlank) }
      .filter { date -> runCatching { LocalDate.parse(date) }.isSuccess }
      .maxOrNull()
  }.getOrNull()

  fun deleteLocalData() {
    draftPersistenceJob?.cancel()
    viewModelScope.launch {
      try {
        val status = repository.deleteLocalData()
        val selectedDate = _uiState.value.selectedDate
        val blank = LifeLoadEntry(date = selectedDate)
        entryCache.clear()
        runCatching { profileOnboardingPrefs().edit().clear().apply() }
        _uiState.update {
          it.copy(
            entry = blank,
            draftEntry = blank,
            score = LifeLoadScore(),
            dailySummary = LifeLoadScore(),
            latestProposal = null,
            entryState = "blank",
            hasDraft = false,
            entryExists = false,
            approvedAt = "",
            draftUpdatedAt = "",
            message = s(R.string.vm_local_data_deleted),
            error = "",
            privacyMessage = s(R.string.vm_local_data_deleted_rows_remain, status.entryCount),
            statusLights = it.statusLights.copy(db = LifeLoadDbStatus.UNKNOWN, sync = LifeLoadSyncStatus.SAVED),
            localDebug = readLocalDebugDiagnostics(s(R.string.vm_local_data_deleted)),
            profileSetup = LifeLoadProfileSetupState(
              selectedConfig = LifeLoadProfileCatalog.buildSelectedProfileConfig(BuildConfig.LIFE_LOAD_DEFAULT_PROFILE_ID),
            ),
            profileOnboardingCompleted = false,
          )
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        _uiState.update { it.copy(privacyMessage = s(R.string.vm_delete_failed, errorText(error))) }
      }
    }
  }

  private fun refreshProfileSetupState() {
    runCatching { repository.selectedProfileConfig() }
      .onSuccess { config ->
        _uiState.update {
          val profileState = LifeLoadProfileSetupState(
            selectedConfig = config,
            optionalPackIds = config.optionalPackIds.toSet(),
          )
          val activeFields = activeLegacyFieldKeys(profileState)
          val sanitizedEntry = it.entry.sanitizedForProfile(activeFields)
          val sanitizedDraft = it.draftEntry.sanitizedForProfile(activeFields)
          it.copy(
            entry = sanitizedEntry,
            draftEntry = sanitizedDraft,
            profileSetup = profileState,
          )
        }
      }
  }

  private fun refreshProfileOnboardingState() {
    _uiState.update { it.copy(profileOnboardingCompleted = readProfileOnboardingCompleted()) }
  }

  private fun readProfileOnboardingCompleted(): Boolean =
    runCatching { profileOnboardingPrefs().getBoolean(KEY_PROFILE_ONBOARDING_COMPLETED, false) }
      .getOrDefault(false)

  private fun profileOnboardingPrefs() =
    getApplication<Application>().getSharedPreferences(PREFS_PROFILE_ONBOARDING, Context.MODE_PRIVATE)

  private fun activeLegacyFieldKeys(profileSetup: LifeLoadProfileSetupState = _uiState.value.profileSetup): Set<String> =
    LifeLoadProfileCatalog.renderableFields(profileSetup.selectedConfig)
      .mapNotNull { it.legacyFieldKey }
      .toSet()
      .let { keys ->
        if (profileSetup.selectedConfig.activeProfileId == "personal_legacy") {
          keys + "other_symptoms"
        } else {
          keys
        }
      }

  private fun draftFieldActive(field: String): Boolean {
    val activeFields = activeLegacyFieldKeys()
    return when (field) {
      "diary_summary" -> true
      "activity_types" -> "primary_activity_type" in activeFields
      "homework_done" -> "homework_done" in activeFields || "homework_status" in activeFields
      else -> field in activeFields
    }
  }

  private fun LifeLoadEntry.sanitizedForActiveProfile(state: LifeLoadUiState = _uiState.value): LifeLoadEntry =
    sanitizedForProfile(activeLegacyFieldKeys(state.profileSetup))

  private fun LifeLoadEntry.sanitizedForProfile(activeFields: Set<String>): LifeLoadEntry =
    copy(
      sleepOk = sleepOk.takeIf { "sleep_ok" in activeFields },
      nutritionOk = nutritionOk.takeIf { "nutrition_ok" in activeFields },
      alcohol = alcohol.takeIf { "alcohol" in activeFields },
      binge = binge.takeIf { "binge" in activeFields },
      mood = mood.takeIf { "mood" in activeFields },
      stress = stress.takeIf { "stress" in activeFields },
      energy = energy.takeIf { "energy" in activeFields },
      coffeeCups = coffeeCups.takeIf { "coffee_cups" in activeFields },
      footPain = footPain.takeIf { "foot_pain" in activeFields },
      shoulderPain = shoulderPain.takeIf { "shoulder_pain" in activeFields },
      migraineWarning = migraineWarning.takeIf { "migraine_warning" in activeFields },
      decompressionDone = decompressionDone.takeIf { "decompression_done" in activeFields },
      afterWorkDecompressionDone = afterWorkDecompressionDone.takeIf { "after_work_decompression_done" in activeFields },
      eveningChainBroken = eveningChainBroken.takeIf { "evening_chain_broken" in activeFields },
      shutdownDone = shutdownDone.takeIf { "shutdown_done" in activeFields },
      phoneAfter21 = phoneAfter21.takeIf { "phone_after_21" in activeFields },
      projectOverrun = projectOverrun.takeIf { "project_overrun" in activeFields },
      primaryActivityType = primaryActivityType.takeIf { "primary_activity_type" in activeFields }.orEmpty(),
      activityTypes = activityTypes.takeIf { "primary_activity_type" in activeFields }.orEmpty(),
      activityDurationMin = activityDurationMin.takeIf { "activity_duration_min" in activeFields },
      rehabDone = rehabDone.takeIf { "rehab_done" in activeFields },
      otherSymptoms = otherSymptoms.takeIf { "other_symptoms" in activeFields }.orEmpty(),
      workIntensity = workIntensity.takeIf { "work_intensity" in activeFields }.orEmpty(),
      familyStress = familyStress.takeIf { "family_stress" in activeFields },
      wifeConflictCount = wifeConflictCount.takeIf { "wife_conflict_count" in activeFields },
      wifeConflictSchool = wifeConflictSchool.takeIf { "wife_conflict_school" in activeFields },
      wifeConflictChores = wifeConflictChores.takeIf { "wife_conflict_chores" in activeFields },
      wifeConflictOther = wifeConflictOther.takeIf { "wife_conflict_other" in activeFields },
      homeOffice = homeOffice.takeIf { "home_office" in activeFields },
      aloneHome = aloneHome.takeIf { "alone_home" in activeFields },
      homeworkDone = homeworkDone.takeIf { "homework_done" in activeFields },
      homeworkStatus = homeworkStatus.takeIf { "homework_status" in activeFields },
    )

  private fun saveProfileSetup(
    profileId: String,
    optionalPackIds: Set<String>,
    message: String,
  ) {
    val config = LifeLoadProfileCatalog.buildSelectedProfileConfig(profileId, optionalPackIds = optionalPackIds)
    runCatching { repository.saveSelectedProfileConfig(config) }
      .onSuccess {
        _uiState.update {
          val profileState = LifeLoadProfileSetupState(
            selectedConfig = config,
            optionalPackIds = optionalPackIds,
            message = message,
          )
          val activeFields = activeLegacyFieldKeys(profileState)
          val sanitizedEntry = it.entry.sanitizedForProfile(activeFields)
          val sanitizedDraft = it.draftEntry.sanitizedForProfile(activeFields)
          it.copy(
            entry = sanitizedEntry,
            draftEntry = sanitizedDraft,
            profileSetup = profileState,
          )
        }
      }
      .onFailure { error ->
        _uiState.update { it.copy(error = s(R.string.vm_profile_setup_failed, errorText(error))) }
      }
  }

  private fun readLocalDebugDiagnostics(message: String): LifeLoadLocalDebugState {
    val bundle = repository.exportLocalDebugBundle(redacted = true)
      ?: return LifeLoadLocalDebugState(message = s(R.string.vm_local_diagnostics_unavailable))
    val root = JSONObject(bundle)
    val counts = root.optJSONObject("counts") ?: JSONObject()
    return LifeLoadLocalDebugState(
      available = true,
      message = message,
      schemaVersion = root.optString("schema_version"),
      redaction = root.optString("redaction"),
      entryCount = counts.optInt("entries"),
      outboxCount = counts.optInt("outbox"),
      conflictCount = counts.optInt("conflicts"),
      approvedCount = counts.optInt("approved"),
      draftCount = counts.optInt("draft"),
      pendingApprovalCount = counts.optInt("pending_approval"),
    )
  }

  private suspend fun persistDraft() {
    try {
      val entry = _uiState.value.draftEntry.sanitizedForActiveProfile()
      val payload = repository.saveDraft(entry)
      syncPendingInBackgroundIfSignedIn(entry.date)
      val dashboard: LifeLoadDashboard? = null
      if (dashboard != null) {
        applyPayload(payload, dashboard = dashboard, message = s(R.string.vm_saved))
        setSyncStatus(LifeLoadSyncStatus.SAVED)
      } else {
        applyEntryPayload(payload, message = s(R.string.vm_saved_local_sync_pending))
        _uiState.update {
          it.copy(
            dashboardLoading = false,
            dashboardSlowLoading = false,
            statusLights = it.statusLights.copy(
              backend = LifeLoadBackendStatus.ERROR,
              db = LifeLoadDbStatus.READY,
              sync = LifeLoadSyncStatus.DRAFT,
            ),
          )
        }
      }
    } catch (error: CancellationException) {
      throw error
    } catch (error: Throwable) {
      setError(error)
      setSyncStatus(LifeLoadSyncStatus.ERROR)
    }
  }

  private fun syncPendingInBackgroundIfSignedIn(date: String) {
    if (!_uiState.value.authSession.isSignedIn) return
    viewModelScope.launch {
      runCatching { repository.syncPendingOutbox() }
        .onSuccess { result ->
          val message = s(R.string.vm_synced_local_changes, result.uploaded, result.attempted, result.failed, result.conflicts)
          _uiState.update { it.copy(localDebug = readLocalDebugDiagnostics(message)) }
          repository.cachedLocalEntry(date)?.let { payload ->
            if (_uiState.value.selectedDate == date && result.failed == 0 && result.conflicts == 0) {
              applyEntryPayload(payload, message = _uiState.value.message)
            }
          }
        }
    }
  }

  private fun loadDate(date: String, refreshDashboard: Boolean = false) {
    val current = _uiState.value
    if (current.hasUnsavedChanges && current.draftEntry.date == current.selectedDate) {
      draftPersistenceJob?.cancel()
      val persisted = runCatching { repository.persistDraftLocally(current.draftEntry.sanitizedForActiveProfile()) }
      if (persisted.isFailure || (repository.canPersistDraftLocally() && persisted.getOrNull() != true)) {
        _uiState.update { it.copy(error = "Could not preserve this edit locally; keep this date open and try again.") }
        return
      }
      entryCache.remove(current.selectedDate)
    }
    loadJob?.cancel()
    val parsedDate = LocalDate.parse(date)
    val cached = entryCache[date] ?: repository.cachedLocalEntry(date)?.also { entryCache[date] = it }
    _uiState.update {
      val activeFields = activeLegacyFieldKeys(it.profileSetup)
      it.copy(
        currentDate = parsedDate,
        selectedDate = date,
        entry = (cached?.approvedEntry ?: cached?.entry ?: LifeLoadEntry(date = date)).sanitizedForProfile(activeFields),
        draftEntry = (cached?.draftEntry ?: LifeLoadEntry(date = date)).sanitizedForProfile(activeFields),
        score = cached?.score ?: LifeLoadScore(),
        dailySummary = cached?.score ?: LifeLoadScore(),
        weeklyContext = cached?.weeklyContext ?: LifeLoadWeekContext(),
        latestProposal = cached?.latestProposal,
        loading = cached == null,
        dashboardLoading = refreshDashboard,
        dashboardSlowLoading = false,
        error = "",
        message = if (cached == null) "" else s(R.string.vm_cached_day_refreshing),
        analysisLocked = false,
        entryState = cached?.entryState ?: "blank",
        hasDraft = cached?.hasDraft ?: false,
        hasUnsavedChanges = cached?.hasLocalDraft ?: false,
        entryExists = cached?.entryExists ?: false,
        scoreAvailable = cached?.scoreAvailable,
        approvedAt = cached?.approvedAt ?: "",
        draftUpdatedAt = cached?.draftUpdatedAt ?: "",
        statusLights = it.statusLights.copy(extract = LifeLoadExtractStatus.IDLE),
      )
    }
    loadJob = viewModelScope.launch {
      try {
        val signedIn = _uiState.value.authSession.isSignedIn
        if (refreshDashboard) {
          dashboardSlowLoadingJob?.cancel()
          dashboardSlowLoadingJob = launch {
            delay(1_200)
            if (_uiState.value.selectedDate == date && _uiState.value.dashboardLoading) {
              _uiState.update { it.copy(dashboardSlowLoading = true) }
            }
          }
        }
        val healthDeferred = if (signedIn) async { runCatching { repository.isBackendHealthy() } } else null
        val contractDeferred = if (signedIn) async { runCatching { repository.loadContract() } } else null
        val settingsDeferred = if (signedIn) async { runCatching { repository.loadSettings() } } else null
        val dashboardDeferred = if (refreshDashboard) {
          async {
            runCatching {
              if (signedIn) repository.loadDashboard(date) else repository.loadLocalDashboard(date)
            }
          }
        } else {
          null
        }
        val payload = repository.loadEntry(date)
        cacheEntryPayload(payload)
        if (_uiState.value.selectedDate == date) {
          applyEntryPayload(payload, message = "")
          prefetchEntryWindow(date)
        }
        contractDeferred?.await()?.onSuccess { contract ->
          if (_uiState.value.selectedDate == date) {
            _uiState.update { it.copy(formulaContract = contract.formula) }
          }
        }
        settingsDeferred?.await()?.onSuccess { settings ->
          entryCacheDays = settings.dailyFlow.entryCacheDays.coerceIn(1, 14)
          LifeLoadReminderScheduler.apply(getApplication(), settings.reminder)
          if (_uiState.value.selectedDate == date) {
            _uiState.update { it.copy(settings = settings) }
          }
        }
        val healthy = healthDeferred?.await()?.getOrDefault(false) ?: false
        if (_uiState.value.selectedDate == date) {
          if (dashboardDeferred == null) {
            _uiState.update {
              it.copy(
                dashboardLoading = false,
                dashboardSlowLoading = false,
                statusLights = it.statusLights.copy(
                  backend = if (healthy) LifeLoadBackendStatus.ONLINE else LifeLoadBackendStatus.ERROR,
                  db = if (it.entryExists || it.hasDraft || it.entryState != "blank") LifeLoadDbStatus.READY else it.statusLights.db,
                ),
              )
            }
          } else {
            dashboardDeferred.await()
              .onSuccess { dashboard ->
                applyDashboard(
                  dashboard = dashboard,
                  backendStatus = if (healthy) LifeLoadBackendStatus.ONLINE else LifeLoadBackendStatus.ERROR,
                )
              }
              .onFailure { error ->
                _uiState.update {
                  it.copy(
                    dashboardLoading = false,
                    dashboardSlowLoading = false,
                    error = s(R.string.vm_dashboard_attention, error.message ?: s(R.string.vm_dashboard_load_failed)),
                    statusLights = it.statusLights.copy(
                      backend = if (healthy) LifeLoadBackendStatus.ONLINE else LifeLoadBackendStatus.ERROR,
                      db = if (it.entryExists || it.hasDraft || it.entryState != "blank") LifeLoadDbStatus.READY else LifeLoadDbStatus.ERROR,
                    ),
                  )
                }
              }
          }
        }
      } catch (error: CancellationException) {
        throw error
      } catch (error: Throwable) {
        if (handleAuthFailure(error)) return@launch
        _uiState.update { state ->
          val hasCachedDay = entryCache[state.selectedDate] != null
          state.copy(
            loading = false,
            dashboardLoading = false,
            dashboardSlowLoading = false,
            error = if (hasCachedDay) "" else error.message ?: s(R.string.vm_entry_load_failed),
            message = if (hasCachedDay) s(R.string.vm_cached_day_refresh_failed) else state.message,
            statusLights = state.statusLights.copy(
              backend = LifeLoadBackendStatus.ERROR,
              db = if (hasCachedDay) LifeLoadDbStatus.READY else LifeLoadDbStatus.ERROR,
              sync = if (hasCachedDay) state.statusLights.sync else LifeLoadSyncStatus.ERROR,
            ),
          )
        }
      }
    }
  }

  private fun prefetchEntryWindow(anchorDate: String) {
    prefetchJob?.cancel()
    prefetchJob = viewModelScope.launch {
      val anchor = LocalDate.parse(anchorDate)
      val backwardDays = (entryCacheDays.coerceIn(1, 14) - 1).coerceAtLeast(0)
      val dates = (1..backwardDays)
        .map { offset -> anchor.minusDays(offset.toLong()).toString() }
        .filter { !LocalDate.parse(it).isAfter(LocalDate.parse(todayIso())) }
        .filter { it != _uiState.value.selectedDate }
      dates.forEach { date ->
        if (entryCache.containsKey(date) || !prefetchInFlight.add(date)) return@forEach
        try {
          cacheEntryPayload(repository.loadEntry(date))
        } catch (error: CancellationException) {
          throw error
        } catch (_: Throwable) {
          // Background cache warm-up must not disturb the daily closeout flow.
        } finally {
          prefetchInFlight.remove(date)
        }
      }
    }
  }

  private fun cacheEntryPayload(payload: LifeLoadEntryPayload) {
    entryCache[payload.date] = payload
  }

  private fun applyPayload(
    payload: LifeLoadEntryPayload,
    dashboard: LifeLoadDashboard,
    message: String,
    backendStatus: LifeLoadBackendStatus = LifeLoadBackendStatus.ONLINE,
    syncStatus: LifeLoadSyncStatus = LifeLoadSyncStatus.SAVED,
  ) {
    applyEntryPayload(payload, message = message)
    applyDashboard(dashboard = dashboard, backendStatus = backendStatus, syncStatus = syncStatus)
  }

  private fun applyEntryPayload(
    payload: LifeLoadEntryPayload,
    message: String,
    syncStatus: LifeLoadSyncStatus = LifeLoadSyncStatus.SAVED,
  ) {
    cacheEntryPayload(payload)
    _uiState.update {
      val activeFields = activeLegacyFieldKeys(it.profileSetup)
      val preserveLocalDraft = message.isBlank() &&
        it.hasDraft &&
        it.draftEntry.date == payload.date &&
        it.statusLights.sync == LifeLoadSyncStatus.DRAFT
      val draftBeforeWeekendDefault = if (preserveLocalDraft) {
        it.draftEntry
      } else if (payload.date == it.draftEntry.date) {
        payload.draftEntry.withRecentlyAddedFieldsFrom(it.draftEntry)
      } else {
        payload.draftEntry
      }
      val draft = if (isWeekendDate(payload.date) && draftBeforeWeekendDefault.homeworkStatus == null && draftBeforeWeekendDefault.homeworkDone == null) {
        draftBeforeWeekendDefault.copy(homeworkStatus = "na")
      } else {
        draftBeforeWeekendDefault
      }.sanitizedForProfile(activeFields)
      val entry = (payload.approvedEntry ?: payload.entry).sanitizedForProfile(activeFields)
      it.copy(
        currentDate = LocalDate.parse(payload.date),
        selectedDate = payload.date,
        entry = entry,
        draftEntry = draft,
        score = payload.score,
        dailySummary = payload.score,
        weeklyContext = payload.weeklyContext,
        latestProposal = payload.latestProposal,
        loading = false,
        entryState = payload.entryState,
        hasDraft = if (preserveLocalDraft) true else payload.hasDraft,
        hasUnsavedChanges = if (preserveLocalDraft) true else payload.hasLocalDraft,
        entryExists = payload.entryExists,
        scoreAvailable = payload.scoreAvailable,
        approvedAt = payload.approvedAt,
        draftUpdatedAt = payload.draftUpdatedAt,
        message = if (preserveLocalDraft) it.message else message,
        error = "",
        statusLights = it.statusLights.copy(
          sync = if (preserveLocalDraft) LifeLoadSyncStatus.DRAFT else syncStatus,
          extract = LifeLoadExtractStatus.IDLE,
        ),
      )
    }
  }

  private fun LifeLoadEntry.withRecentlyAddedFieldsFrom(previous: LifeLoadEntry): LifeLoadEntry = copy(
    afterWorkDecompressionDone = afterWorkDecompressionDone ?: previous.afterWorkDecompressionDone,
    eveningChainBroken = eveningChainBroken ?: previous.eveningChainBroken,
    wifeConflictCount = wifeConflictCount ?: previous.wifeConflictCount,
    wifeConflictSchool = wifeConflictSchool ?: previous.wifeConflictSchool,
    wifeConflictChores = wifeConflictChores ?: previous.wifeConflictChores,
    wifeConflictOther = wifeConflictOther ?: previous.wifeConflictOther,
    aloneHome = aloneHome ?: previous.aloneHome,
  )

  private fun applyDashboard(
    dashboard: LifeLoadDashboard,
    backendStatus: LifeLoadBackendStatus = LifeLoadBackendStatus.ONLINE,
    syncStatus: LifeLoadSyncStatus = LifeLoadSyncStatus.SAVED,
  ) {
    _uiState.update {
      it.copy(
        dashboard = dashboard,
        dashboardLoading = false,
        dashboardSlowLoading = false,
        statusLights = it.statusLights.copy(
          backend = backendStatus,
          db = if (dashboard.dbRoot.isNotBlank() || it.entryExists || it.hasDraft) LifeLoadDbStatus.READY else LifeLoadDbStatus.UNKNOWN,
          sync = syncStatus,
        ),
      )
    }
  }

  private fun mergeDashboardSnapshot(current: LifeLoadDashboard, derived: LifeLoadDashboard): LifeLoadDashboard =
    current.copy(
      date = derived.date.ifBlank { current.date },
      weekly = if (
        derived.weekly.zone.isNotBlank() ||
        derived.weekly.nextAction.isNotBlank() ||
        derived.weekly.redFlagCount > 0
      ) derived.weekly else current.weekly,
      trendPoints = if (derived.trendPoints.isNotEmpty()) derived.trendPoints else current.trendPoints,
      drift = derived.drift ?: current.drift,
    )

  private fun setSyncStatus(status: LifeLoadSyncStatus) {
    _uiState.update { it.copy(statusLights = it.statusLights.copy(sync = status)) }
  }

  private fun setError(error: Throwable) {
    if (handleAuthFailure(error)) return
    _uiState.update {
      it.copy(
        loading = false,
        error = error.message ?: error::class.java.simpleName,
        statusLights = it.statusLights.copy(backend = LifeLoadBackendStatus.ERROR),
      )
    }
  }

  private fun garminImportMessage(daysImported: Int, passiveUpserted: Int, activityUpserted: Int, skippedReason: String): String {
    if (skippedReason == "fresh") return s(R.string.vm_garmin_data_fresh)
    if (skippedReason == "missing_tokenstore") return s(R.string.vm_garmin_token_missing)
    if (skippedReason.isNotBlank()) return s(R.string.vm_garmin_import_skipped, skippedReason)
    return s(R.string.vm_garmin_imported, passiveUpserted, activityUpserted, daysImported)
  }

  companion object {
    private const val PREFS_PROFILE_ONBOARDING = "life_load_profile_onboarding"
    private const val KEY_PROFILE_ONBOARDING_COMPLETED = "completed"

    fun factory(application: Application): ViewModelProvider.Factory = object : ViewModelProvider.Factory {
      @Suppress("UNCHECKED_CAST")
      override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(LifeLoadViewModel::class.java)) {
          return LifeLoadViewModel(application) as T
        }
        throw IllegalArgumentException("Unknown model class: ${modelClass.name}")
      }
    }
  }
}

private fun isWeekendDate(date: String): Boolean {
  val day = runCatching { LocalDate.parse(date) }.getOrNull() ?: return false
  return day.dayOfWeek == java.time.DayOfWeek.SATURDAY || day.dayOfWeek == java.time.DayOfWeek.SUNDAY
}
