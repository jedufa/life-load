package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.BuildConfig
import com.life.lifeload.data.ServerConfig
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ServerUrlNormalizationRegressionInstrumentedTest {
  @Test
  fun serverUrlNormalizationHandlesQuotesWhitespacePortsAndDefaults() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    val defaultUrl = ServerConfig.normalizeBaseUrl(BuildConfig.SERVER_BASE_URL)

    assertEquals(
      "http://192.0.2.1:8765/projects/life-load/app",
      ServerConfig.normalizeBaseUrl(" 192.0.2.1:8765/projects/life-load/app/ "),
    )
    assertEquals(
      "http://192.0.2.1:8765/projects/life-load/app",
      ServerConfig.normalizeBaseUrl("192.0.2.1'8765/projects/life-load/app"),
    )
    assertEquals("https://example.test/api", ServerConfig.normalizeBaseUrl(" https://example.test/api/ "))
    assertEquals(defaultUrl, ServerConfig.normalizeBaseUrl(""))
    assertEquals(defaultUrl, ServerConfig.normalizeBaseUrl(null))

    ServerConfig.saveBaseUrl(context, " 192.0.2.1:8765/projects/life-load/app/ ")
    assertEquals("http://192.0.2.1:8765/projects/life-load/app", ServerConfig.resolveBaseUrl(context))
    ServerConfig.resetBaseUrl(context)
    assertEquals(defaultUrl, ServerConfig.resolveBaseUrl(context))
  }
}
