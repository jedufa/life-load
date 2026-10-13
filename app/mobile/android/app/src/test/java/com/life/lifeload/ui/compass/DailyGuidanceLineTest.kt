package com.life.lifeload.ui.compass

import org.junit.Assert.assertEquals
import org.junit.Test

class DailyGuidanceLineTest {
  @Test
  fun dailyGuidanceLinesSeparatesBulletMarkerFromLinkedText() {
    val lines = dailyGuidanceLines("• Sleep first.\n• Reduce optional load.")

    assertEquals(
      listOf(
        DailyGuidanceLine("Sleep first.", bulleted = true),
        DailyGuidanceLine("Reduce optional load.", bulleted = true),
      ),
      lines,
    )
  }

  @Test
  fun dailyGuidanceLinesPreservesPlainRecommendationText() {
    assertEquals(
      listOf(DailyGuidanceLine("Keep steady.", bulleted = false)),
      dailyGuidanceLines("Keep steady."),
    )
  }
}
