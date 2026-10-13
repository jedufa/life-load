package com.life.lifeload.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class LifeLoadReminderReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent?) {
    LifeLoadReminderScheduler.onReminderAlarm(context)
  }
}
