package com.life.lifeload.ui

import android.net.Uri
import com.life.lifeload.domain.LifeLoadSettings
import com.life.lifeload.domain.LifeLoadReminderSettings

data class LifeLoadUiActions(
  val onRefresh: () -> Unit,
  val onPreviousDate: () -> Unit,
  val onNextDate: () -> Unit,
  val onShiftDate: (Long) -> Unit,
  val onToday: () -> Unit,
  val onYesterday: () -> Unit,
  val onDiaryChanged: (String) -> Unit,
  val onAnalyzeDiary: () -> Unit,
  val onApprove: () -> Unit,
  val onOpenSettings: () -> Unit,
  val onCloseSettings: () -> Unit,
  val onSettingsChanged: (LifeLoadSettings) -> Unit,
  val onReminderSettingsChanged: (LifeLoadReminderSettings) -> Unit = {},
  val onSaveSettings: (String) -> Unit,
  val onRefreshLocalDebug: () -> Unit,
  val onImportLocalHistory: (Int) -> Unit,
  val onSyncLocalOutbox: () -> Unit,
  val onMirrorLocalDebug: () -> Unit,
  val onExportLocalData: () -> Unit,
  val onExportLocalDataToUri: (Uri) -> Unit = {},
  val onImportLocalDataFromUri: (Uri) -> Unit = {},
  val onRestoreFromServer: () -> Unit = {},
  val onDeleteLocalData: () -> Unit,
  val onSignIn: (String, String) -> Unit = { _, _ -> },
  val onRegister: (String, String) -> Unit = { _, _ -> },
  val onSignOut: () -> Unit = {},
  val onTagsChanged: (String) -> Unit,
  val onBooleanField: (String, Boolean?) -> Unit,
  val onIntField: (String, Int?) -> Unit,
  val onStringField: (String, String) -> Unit,
  val onProfileSelected: (String) -> Unit = {},
  val onOptionalPackToggled: (String, Boolean) -> Unit = { _, _ -> },
  val onResetProfileDefaults: () -> Unit = {},
  val onCompleteProfileOnboarding: () -> Unit = {},
)
