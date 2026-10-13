package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.BuildConfig
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class TestHarnessSelfCheckInstrumentedTest {
  @Test
  fun fixtureResetBackendUnavailableAndExportCleanupBehaveAsExpected() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    val exportDir = File(context.filesDir, "life_load_exports")
    val exportFile = File(exportDir, "self_check_export.json")

    RegressionFixture.resetAppState(context)
    RegressionFixture.seedDraft(context)
    exportDir.mkdirs()
    exportFile.writeText("synthetic export", Charsets.UTF_8)

    LifeLoadLocalStore(context).use { store ->
      assertEquals(1, store.status().entryCount)
      assertTrue(exportFile.exists())
    }

    RegressionFixture.forceBackendUnavailable(context)
    assertEquals("http://127.0.0.1:1", ServerConfig.resolveBaseUrl(context))

    RegressionFixture.resetAppState(context)
    assertEquals(ServerConfig.normalizeBaseUrl(BuildConfig.SERVER_BASE_URL), ServerConfig.resolveBaseUrl(context))
    assertFalse(exportFile.exists())
    AndroidTruthHelpers.assertNoEntries(context)
  }
}
