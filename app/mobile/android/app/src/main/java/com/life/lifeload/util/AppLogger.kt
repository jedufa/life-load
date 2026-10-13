package com.life.lifeload.util

import android.content.Context
import android.util.Log
import com.life.lifeload.BuildConfig
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.time.Instant

object AppLogger {
  private const val TAG = "LifeLoad"
  private const val LOG_FILE = "mobile_app.log"
  private const val MAX_BYTES = 1_000_000L
  private const val BACKUPS = 2
  private const val REDACTED = "[redacted]"
  private const val SENSITIVE_KEYS =
    "diary_text|diaryText|diary_summary|diarySummary|summary|draft_payload|draftPayload|entry_json|entryJson|payload_json|payloadJson|raw_json|rawJson|structured_json|structuredJson|entry|payload|health|sleep|sleep_ok|sleepOk|stress|family_stress|familyStress|garmin_email|garminEmail|garminPassword|password|token|auth[_-]?token"

  private val sensitiveKeyValuePatterns = listOf(
    Regex("(?i)\"?\\b($SENSITIVE_KEYS)\\b\"?\\s*[:=]\\s*\"(?:\\\\.|[^\"])*\""),
    Regex("(?i)\"?\\b($SENSITIVE_KEYS)\\b\"?\\s*[:=]\\s*\\{[^\\n]*?\\}"),
    Regex("(?i)\"?\\b($SENSITIVE_KEYS)\\b\"?\\s*[:=]\\s*\\[[^\\n]*?\\]"),
    Regex("(?i)\"?\\b($SENSITIVE_KEYS)\\b\"?\\s*[:=]\\s*[^,\\s}]+"),
  )
  private val emailPattern = Regex("\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b", RegexOption.IGNORE_CASE)
  private val bearerPattern = Regex("(?i)\\bBearer\\s+[A-Za-z0-9._~+/=-]+")

  @Volatile
  private var initialized = false
  @Volatile
  private var minimumLevel = if (BuildConfig.DEBUG) AppLogLevel.DEBUG else AppLogLevel.INFO
  private var logDir: File? = null

  fun init(context: Context) {
    if (initialized) return
    synchronized(this) {
      if (initialized) return
      logDir = context.filesDir
      initialized = true
      i("logger initialized")
    }
  }

  fun setMinimumLevel(level: AppLogLevel) {
    minimumLevel = level
  }

  fun t(message: String) = write(AppLogLevel.TRACE, message, null)
  fun d(message: String) = write(AppLogLevel.DEBUG, message, null)
  fun i(message: String) = write(AppLogLevel.INFO, message, null)
  fun w(message: String) = write(AppLogLevel.WARN, message, null)
  fun e(message: String, t: Throwable? = null) = write(AppLogLevel.ERROR, message, t)

  private fun write(level: AppLogLevel, message: String, t: Throwable?) {
    if (!shouldLog(level)) return
    val safeMessage = sanitizeForLog(message)
    val safeStack = t?.let { sanitizeForLog(stackTrace(it)) }
    try {
      when (level) {
        AppLogLevel.ERROR -> Log.e(TAG, appendStack(safeMessage, safeStack))
        AppLogLevel.WARN -> Log.w(TAG, appendStack(safeMessage, safeStack))
        AppLogLevel.INFO -> Log.i(TAG, appendStack(safeMessage, safeStack))
        AppLogLevel.DEBUG -> Log.d(TAG, appendStack(safeMessage, safeStack))
        AppLogLevel.TRACE -> Log.v(TAG, appendStack(safeMessage, safeStack))
      }
    } catch (_: Throwable) {
      // JVM unit tests may not have android.util.Log runtime.
    }
    val dir = logDir ?: return
    synchronized(this) {
      try {
        val log = File(dir, LOG_FILE)
        rotateIfNeeded(log)
        val line = buildLine(level.code, safeMessage, safeStack)
        log.appendText(line)
      } catch (_: Throwable) {
        // Never crash app because logging fails.
      }
    }
  }

  private fun rotateIfNeeded(log: File) {
    val cur = if (log.exists()) log.length() else 0L
    if (cur < MAX_BYTES) return
    for (i in BACKUPS downTo 1) {
      val src = if (i == 1) log else File(log.parentFile, "$LOG_FILE.${i - 1}")
      val dst = File(log.parentFile, "$LOG_FILE.$i")
      if (src.exists()) src.renameTo(dst)
    }
  }

  private fun buildLine(level: String, message: String, stack: String?): String {
    val ts = Instant.now().toString()
    val b = StringBuilder(256)
    b.append(ts).append(' ').append(level).append(' ').append(message)
    if (!stack.isNullOrBlank()) {
      b.append('\n')
      b.append(stack)
    }
    b.append('\n')
    return b.toString()
  }

  internal fun sanitizeForLog(raw: String): String {
    var sanitized = raw
    sanitized = bearerPattern.replace(sanitized, "Bearer $REDACTED")
    for (pattern in sensitiveKeyValuePatterns) {
      sanitized = pattern.replace(sanitized) { match ->
        val key = match.value.substringBefore('=').substringBefore(':').trim().trim('"')
        "$key=$REDACTED"
      }
    }
    sanitized = emailPattern.replace(sanitized, REDACTED)
    return sanitized
  }

  internal fun shouldLog(level: AppLogLevel): Boolean = level.priority >= minimumLevel.priority

  private fun appendStack(message: String, stack: String?): String {
    if (stack.isNullOrBlank()) return message
    return "$message\n$stack"
  }

  private fun stackTrace(t: Throwable): String {
    val sw = StringWriter()
    val pw = PrintWriter(sw)
    t.printStackTrace(pw)
    pw.flush()
    return sw.toString()
  }
}

enum class AppLogLevel(internal val priority: Int, internal val code: String) {
  TRACE(0, "T"),
  DEBUG(1, "D"),
  INFO(2, "I"),
  WARN(3, "W"),
  ERROR(4, "E"),
}
