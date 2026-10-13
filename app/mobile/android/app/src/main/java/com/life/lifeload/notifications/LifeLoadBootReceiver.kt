package com.life.lifeload.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class LifeLoadBootReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent?) {
    if (intent?.action == Intent.ACTION_BOOT_COMPLETED) {
      LifeLoadReminderScheduler.rescheduleFromLocalSettings(context)
    }
  }
}
