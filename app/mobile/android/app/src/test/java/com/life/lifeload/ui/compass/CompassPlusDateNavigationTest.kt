package com.life.lifeload.ui.compass

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class CompassPlusDateNavigationTest {
  @Test
  fun nextArrowStaysEnabledForPastDaysUntilToday() {
    val today = LocalDate.parse("2026-05-10")

    assertTrue(compassPlusCanGoNext(selected = today.minusDays(2), today = today))
    assertTrue(compassPlusCanGoNext(selected = today.minusDays(1), today = today))
    assertFalse(compassPlusCanGoNext(selected = today, today = today))
    assertFalse(compassPlusCanGoNext(selected = today.plusDays(1), today = today))
  }
}
