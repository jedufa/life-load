package com.life.lifeload.data

import android.content.Context

data class LifeLoadAuthSession(
  val email: String = "",
  val userId: String = "",
  val deviceId: String = "",
  val sessionToken: String = "",
) {
  val isSignedIn: Boolean get() = sessionToken.isNotBlank()
}

object AuthConfig {
  private const val PREFS_NAME = "auth_config"
  private const val KEY_EMAIL = "email"
  private const val KEY_USER_ID = "user_id"
  private const val KEY_DEVICE_ID = "device_id"
  private const val KEY_SESSION_TOKEN = "session_token"

  fun resolve(context: Context): LifeLoadAuthSession {
    val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    return LifeLoadAuthSession(
      email = prefs.getString(KEY_EMAIL, "").orEmpty(),
      userId = prefs.getString(KEY_USER_ID, "").orEmpty(),
      deviceId = prefs.getString(KEY_DEVICE_ID, "").orEmpty(),
      sessionToken = prefs.getString(KEY_SESSION_TOKEN, "").orEmpty(),
    )
  }

  fun save(context: Context, session: LifeLoadAuthSession) {
    context
      .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .putString(KEY_EMAIL, session.email)
      .putString(KEY_USER_ID, session.userId)
      .putString(KEY_DEVICE_ID, session.deviceId)
      .putString(KEY_SESSION_TOKEN, session.sessionToken)
      .apply()
  }

  fun clear(context: Context) {
    context
      .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .clear()
      .apply()
  }
}
