package com.life.lifeload

import android.graphics.Color as AndroidColor
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.SideEffect
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.life.lifeload.notifications.LifeLoadReminderScheduler
import com.life.lifeload.i18n.LifeLoadLanguageStore
import com.life.lifeload.ui.AppShell
import com.life.lifeload.ui.theme.LifeLoadTheme
import com.life.lifeload.util.AppLogger

class MainActivity : ComponentActivity() {
  override fun attachBaseContext(newBase: Context) {
    super.attachBaseContext(LifeLoadLanguageStore.wrapContext(newBase))
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    AppLogger.init(applicationContext)
    AppLogger.i("MainActivity onCreate")
    LifeLoadReminderScheduler.rescheduleFromLocalSettings(applicationContext)
    WindowCompat.setDecorFitsSystemWindows(window, false)
    window.statusBarColor = AndroidColor.TRANSPARENT
    window.navigationBarColor = AndroidColor.TRANSPARENT
    setContent {
      val isDarkTheme = isSystemInDarkTheme()
      SideEffect {
        WindowInsetsControllerCompat(window, window.decorView).apply {
          show(WindowInsetsCompat.Type.statusBars())
          isAppearanceLightStatusBars = !isDarkTheme
          isAppearanceLightNavigationBars = !isDarkTheme
        }
      }
      LifeLoadTheme(darkTheme = isDarkTheme) {
        Surface(color = MaterialTheme.colorScheme.background) {
          AppShell()
        }
      }
    }
  }
}
