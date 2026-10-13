package com.life.lifeload.notifications

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.life.lifeload.MainActivity
import com.life.lifeload.R
import com.life.lifeload.domain.LifeLoadReminderSettings
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZonedDateTime

object LifeLoadReminderScheduler {
  private const val CHANNEL_ID = "life_load_daily_checkin"
  private const val NOTIFICATION_ID = 4101
  private const val REQUEST_CODE = 4101
  private const val PREFS = "life_load_reminder"
  private const val KEY_ENABLED = "enabled"
  private const val KEY_HOUR = "hour"
  private const val KEY_MINUTE = "minute"

  fun apply(context: Context, settings: LifeLoadReminderSettings) {
    val appContext = context.applicationContext
    ensureNotificationChannel(appContext)
    saveLocalSettings(appContext, settings)
    if (settings.enabled) {
      schedule(appContext, settings)
    } else {
      cancel(appContext)
    }
  }

  fun rescheduleFromLocalSettings(context: Context) {
    val settings = loadLocalSettings(context.applicationContext)
    if (settings.enabled) schedule(context.applicationContext, settings)
  }

  fun onReminderAlarm(context: Context) {
    val appContext = context.applicationContext
    postReminder(appContext)
    rescheduleFromLocalSettings(appContext)
  }

  fun postReminder(context: Context) {
    val appContext = context.applicationContext
    ensureNotificationChannel(appContext)
    if (
      Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
      ContextCompat.checkSelfPermission(appContext, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
    ) {
      return
    }
    val openAppIntent = Intent(appContext, MainActivity::class.java)
      .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
    val contentIntent = PendingIntent.getActivity(
      appContext,
      REQUEST_CODE,
      openAppIntent,
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
    val notification = NotificationCompat.Builder(appContext, CHANNEL_ID)
      .setSmallIcon(R.drawable.ll_ic_compass_mark)
      .setContentTitle(appContext.getString(R.string.reminder_notification_title))
      .setContentText(appContext.getString(R.string.reminder_notification_body))
      .setContentIntent(contentIntent)
      .setAutoCancel(true)
      .setPriority(NotificationCompat.PRIORITY_DEFAULT)
      .build()
    try {
      NotificationManagerCompat.from(appContext).notify(NOTIFICATION_ID, notification)
    } catch (_: SecurityException) {
      // Permission can still be revoked between the check and notify call.
    }
  }

  private fun schedule(context: Context, settings: LifeLoadReminderSettings) {
    val alarmManager = context.getSystemService(AlarmManager::class.java)
    alarmManager.setAndAllowWhileIdle(
      AlarmManager.RTC_WAKEUP,
      nextTriggerMillis(settings),
      reminderPendingIntent(context),
    )
  }

  private fun cancel(context: Context) {
    val alarmManager = context.getSystemService(AlarmManager::class.java)
    alarmManager.cancel(reminderPendingIntent(context))
  }

  private fun reminderPendingIntent(context: Context): PendingIntent =
    PendingIntent.getBroadcast(
      context,
      REQUEST_CODE,
      Intent(context, LifeLoadReminderReceiver::class.java),
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

  private fun nextTriggerMillis(settings: LifeLoadReminderSettings): Long {
    val zone = ZoneId.systemDefault()
    val now = ZonedDateTime.now(zone)
    var trigger = LocalDateTime.of(
      now.toLocalDate(),
      java.time.LocalTime.of(settings.hour.coerceIn(0, 23), settings.minute.coerceIn(0, 59)),
    ).atZone(zone)
    if (!trigger.isAfter(now)) trigger = trigger.plusDays(1)
    return trigger.toInstant().toEpochMilli()
  }

  private fun ensureNotificationChannel(context: Context) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val manager = context.getSystemService(NotificationManager::class.java)
    val channel = NotificationChannel(CHANNEL_ID, context.getString(R.string.reminder_notification_channel_name), NotificationManager.IMPORTANCE_DEFAULT).apply {
      description = context.getString(R.string.reminder_notification_channel_description)
    }
    manager.createNotificationChannel(channel)
  }

  private fun saveLocalSettings(context: Context, settings: LifeLoadReminderSettings) {
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
      .edit()
      .putBoolean(KEY_ENABLED, settings.enabled)
      .putInt(KEY_HOUR, settings.hour.coerceIn(0, 23))
      .putInt(KEY_MINUTE, settings.minute.coerceIn(0, 59))
      .apply()
  }

  private fun loadLocalSettings(context: Context): LifeLoadReminderSettings {
    val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    return LifeLoadReminderSettings(
      enabled = prefs.getBoolean(KEY_ENABLED, false),
      hour = prefs.getInt(KEY_HOUR, 21).coerceIn(0, 23),
      minute = prefs.getInt(KEY_MINUTE, 30).coerceIn(0, 59),
    )
  }
}
