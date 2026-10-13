package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject

@RunWith(AndroidJUnit4::class)
class ImportSafetyRegressionInstrumentedTest {
  @Test
  fun redactedDebugBundleCannotRestoreLocalData() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    RegressionFixture.seedPendingApproval(context)

    val redactedBundle = LifeLoadLocalStore(context).use { it.exportDebugBundle(redacted = true) }

    RegressionFixture.resetLocalStore(context)
    LifeLoadLocalStore(context).use { store ->
      assertThrows(IllegalArgumentException::class.java) {
        store.restoreDebugBundle(redactedBundle)
      }
      assertEquals(0, store.status().entryCount)
      assertEquals(0, store.status().pendingOutboxCount)
    }
  }

  @Test
  fun malformedDebugBundleCannotPartiallyRestoreLocalData() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    val malformed = JSONObject()
      .put("schema_version", "unexpected_schema")
      .put("redaction", "full_local_only")
      .put("entries", emptyList<String>())
      .put("outbox", emptyList<String>())
      .toString()

    LifeLoadLocalStore(context).use { store ->
      assertThrows(IllegalArgumentException::class.java) {
        store.restoreDebugBundle(malformed)
      }
      assertEquals(0, store.status().entryCount)
      assertEquals(0, store.status().pendingOutboxCount)
    }
  }
}
