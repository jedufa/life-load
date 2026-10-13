package com.life.lifeload.util

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppLoggerTest {
  @Test
  fun sanitizeForLogRedactsSensitivePayloadFields() {
    val message = """
      payload={"diary_text":"I had a private family conflict","diarySummary":"raw summary"}
      entry_json={"diary_text":"Raw local diary","family_stress":8,"sleep_ok":false}
      payload_json={"entry":{"stress":9,"health":"private"}}
      garminPassword="secret" token=abc123 garminEmail=operator@example.test
    """.trimIndent()

    val sanitized = AppLogger.sanitizeForLog(message)

    assertFalse(sanitized.contains("private family conflict"))
    assertFalse(sanitized.contains("raw summary"))
    assertFalse(sanitized.contains("Raw local diary"))
    assertFalse(sanitized.contains("private"))
    assertFalse(sanitized.contains("operator@example.test"))
    assertFalse(sanitized.contains("secret"))
    assertFalse(sanitized.contains("abc123"))
    assertTrue(sanitized.contains("[redacted]"))
  }

  @Test
  fun sanitizeForLogRedactsEmailsAndBearerTokens() {
    val sanitized = AppLogger.sanitizeForLog(
      "request failed for subs@example.test Authorization: Bearer super-secret-token",
    )

    assertFalse(sanitized.contains("subs@example.test"))
    assertFalse(sanitized.contains("super-secret-token"))
    assertTrue(sanitized.contains("Bearer [redacted]"))
  }

  @Test
  fun minimumLevelFiltersLowerPriorityLogs() {
    AppLogger.setMinimumLevel(AppLogLevel.WARN)

    assertFalse(AppLogger.shouldLog(AppLogLevel.TRACE))
    assertFalse(AppLogger.shouldLog(AppLogLevel.DEBUG))
    assertFalse(AppLogger.shouldLog(AppLogLevel.INFO))
    assertTrue(AppLogger.shouldLog(AppLogLevel.WARN))
    assertTrue(AppLogger.shouldLog(AppLogLevel.ERROR))

    AppLogger.setMinimumLevel(AppLogLevel.DEBUG)
  }
}
