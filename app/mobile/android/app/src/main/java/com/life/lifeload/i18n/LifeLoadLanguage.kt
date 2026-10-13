package com.life.lifeload.i18n

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.res.Configuration
import java.util.Locale

enum class LifeLoadLanguageOption(val storageKey: String) {
  SYSTEM("system"),
  ENGLISH("en"),
  GERMAN("de"),
}

object LifeLoadLanguageStore {
  private const val PREFS_NAME = "life_load_language"
  private const val KEY_LANGUAGE = "selected_language"

  fun load(context: Context): LifeLoadLanguageOption {
    val raw = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .getString(KEY_LANGUAGE, LifeLoadLanguageOption.SYSTEM.storageKey)
    return LifeLoadLanguageOption.entries.firstOrNull { it.storageKey == raw } ?: LifeLoadLanguageOption.SYSTEM
  }

  fun save(context: Context, option: LifeLoadLanguageOption) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .putString(KEY_LANGUAGE, option.storageKey)
      .apply()
  }

  fun wrapContext(base: Context): Context = localizedContext(base, load(base))

  fun localizedContext(base: Context, option: LifeLoadLanguageOption): Context {
    val locale = when (option) {
      LifeLoadLanguageOption.SYSTEM -> return base
      LifeLoadLanguageOption.ENGLISH -> Locale.ENGLISH
      LifeLoadLanguageOption.GERMAN -> Locale.GERMAN
    }
    Locale.setDefault(locale)
    val configuration = Configuration(base.resources.configuration)
    configuration.setLocale(locale)
    return base.createConfigurationContext(configuration)
  }
}

fun Context.findActivity(): Activity? =
  when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
  }
