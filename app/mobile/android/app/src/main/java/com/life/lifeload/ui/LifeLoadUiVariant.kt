package com.life.lifeload.ui

import android.content.Context
import androidx.compose.runtime.Composable
import com.life.lifeload.BuildConfig
import com.life.lifeload.ui.compass.CompassPlusRoot
import com.life.lifeload.ui.compass.CompassRoot

enum class LifeLoadUiVariant(
  val id: String,
  val label: String,
  val description: String,
) {
  Classic(
    id = "classic",
    label = "Classic",
    description = "Current compact daily-first Android UI.",
  ),
  Compass(
    id = "compass",
    label = "Compass",
    description = "Decision-first progressive UI with Simple, Detailed, and Operator depth.",
  ),
  CompassPlus(
    id = "compass_plus",
    label = "Compass Plus",
    description = "Floating premium shell for Guidance-first daily use.",
  ),
}

object LifeLoadUiVariantRegistry {
  val all: List<LifeLoadUiVariant> = LifeLoadUiVariant.entries
  val default: LifeLoadUiVariant = LifeLoadUiVariant.CompassPlus

  fun fromId(id: String?): LifeLoadUiVariant =
    all.firstOrNull { it.id == id } ?: default
}

object DebugUiVariantStore {
  private const val PREFS_NAME = "debug_ui_variant"
  private const val KEY_VARIANT = "variant"

  fun resolve(context: Context): LifeLoadUiVariant {
    if (!BuildConfig.DEBUG) return LifeLoadUiVariantRegistry.default
    val stored = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getString(KEY_VARIANT, null)
    return LifeLoadUiVariantRegistry.fromId(stored)
  }

  fun save(context: Context, variant: LifeLoadUiVariant) {
    if (!BuildConfig.DEBUG) return
    context
      .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .putString(KEY_VARIANT, variant.id)
      .apply()
  }
}

@Composable
internal fun LifeLoadVariantHost(
  state: LifeLoadUiState,
  actions: LifeLoadUiActions,
  selectedVariant: LifeLoadUiVariant,
  onVariantSelected: (LifeLoadUiVariant) -> Unit,
) {
  when (selectedVariant) {
    LifeLoadUiVariant.Classic -> LifeLoadClassicScreen(
      state = state,
      actions = actions,
      selectedVariant = selectedVariant,
      onVariantSelected = onVariantSelected,
    )
    LifeLoadUiVariant.Compass -> CompassRoot(
      state = state,
      actions = actions,
      selectedVariant = selectedVariant,
      onVariantSelected = onVariantSelected,
    )
    LifeLoadUiVariant.CompassPlus -> CompassPlusRoot(
      state = state,
      actions = actions,
      selectedVariant = selectedVariant,
      onVariantSelected = onVariantSelected,
    )
  }
}
