package com.life.lifeload.data

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@Config(sdk = [34])
@RunWith(RobolectricTestRunner::class)
class AuthConfigTest {
  @Test
  fun saveResolveAndClearSession() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    AuthConfig.clear(context)

    assertFalse(AuthConfig.resolve(context).isSignedIn)

    AuthConfig.save(
      context,
      LifeLoadAuthSession(
        email = "alpha@example.invalid",
        userId = "usr_alpha",
        deviceId = "dev_alpha",
        sessionToken = "session_alpha",
      ),
    )

    val saved = AuthConfig.resolve(context)
    assertTrue(saved.isSignedIn)
    assertEquals("alpha@example.invalid", saved.email)
    assertEquals("usr_alpha", saved.userId)
    assertEquals("dev_alpha", saved.deviceId)
    assertEquals("session_alpha", saved.sessionToken)

    AuthConfig.clear(context)
    assertFalse(AuthConfig.resolve(context).isSignedIn)
  }
}
