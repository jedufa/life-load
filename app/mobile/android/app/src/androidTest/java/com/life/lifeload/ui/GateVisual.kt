package com.life.lifeload.ui

import androidx.test.platform.app.InstrumentationRegistry

object GateVisual {
  private val args = InstrumentationRegistry.getArguments()

  val enabled: Boolean =
    args.getString("visual_observable", "true")
      ?.lowercase()
      ?.let { it != "0" && it != "false" && it != "no" }
      ?: true

  private val delayMs: Long =
    args.getString("visual_delay_ms", "650")?.toLongOrNull()?.coerceAtLeast(0L) ?: 650L

  fun pause() {
    if (enabled && delayMs > 0L) {
      Thread.sleep(delayMs)
    }
  }
}
