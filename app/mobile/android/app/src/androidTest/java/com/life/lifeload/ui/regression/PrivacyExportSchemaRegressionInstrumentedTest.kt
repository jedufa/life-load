package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.local.LIFE_LOAD_DEBUG_BUNDLE_VERSION
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PrivacyExportSchemaRegressionInstrumentedTest {
  @Test
  fun fullAndRedactedDebugBundlesKeepSchemaAndRedactionContract() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    RegressionFixture.seedPendingApproval(
      context,
      RegressionFixture.entry(RegressionFixture.mondayNormal, note = RegressionFixture.privacySecret),
    )

    LifeLoadLocalStore(context).use { store ->
      val full = store.exportDebugBundle(redacted = false)
      val redacted = store.exportDebugBundle(redacted = true)
      val fullJson = JSONObject(full)
      val redactedJson = JSONObject(redacted)

      assertEquals(LIFE_LOAD_DEBUG_BUNDLE_VERSION, fullJson.getString("schema_version"))
      assertEquals("full_local_only", fullJson.getString("redaction"))
      assertEquals("redacted", redactedJson.getString("redaction"))
      assertEquals(1, fullJson.getJSONObject("counts").getInt("entries"))
      assertEquals(1, fullJson.getJSONObject("counts").getInt("outbox"))
      assertTrue(full.contains(RegressionFixture.privacySecret))
      assertFalse(redacted.contains(RegressionFixture.privacySecret))
      assertTrue(redactedJson.getJSONArray("entries").getJSONObject(0).getJSONObject("entry_json").getBoolean("redacted"))
      assertTrue(redactedJson.getJSONArray("outbox").getJSONObject(0).getJSONObject("payload_json").getBoolean("redacted"))
    }
  }
}
