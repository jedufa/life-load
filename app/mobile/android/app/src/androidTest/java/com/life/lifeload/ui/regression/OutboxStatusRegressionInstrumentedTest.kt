package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OutboxStatusRegressionInstrumentedTest {
  @Test
  fun outboxFailureConflictAndUploadedStatesAffectStatusCounts() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    RegressionFixture.seedDraft(context, RegressionFixture.entry(RegressionFixture.mondayNormal, note = "draft outbox"))
    RegressionFixture.seedPendingApproval(context, RegressionFixture.entry(RegressionFixture.wednesdayOverload, note = "approval outbox"))

    LifeLoadLocalStore(context).use { store ->
      val rows = store.pendingOutbox()
      assertEquals(2, rows.size)

      store.markOutboxFailed(rows[0].id, "temporary backend failure")
      assertEquals(2, store.status().pendingOutboxCount)
      assertEquals("temporary backend failure", store.pendingOutbox().first { it.id == rows[0].id }.lastError)

      store.markOutboxConflict(rows[0].id, "server has newer truth")
      assertEquals(1, store.status().pendingOutboxCount)
      assertEquals(1, store.status().conflictOutboxCount)

      store.markOutboxUploaded(rows[1].id)
      assertEquals(0, store.status().pendingOutboxCount)
      assertEquals(1, store.status().conflictOutboxCount)

      val bundle = JSONObject(store.exportDebugBundle(redacted = true))
      assertEquals(0, bundle.getJSONObject("status").getInt("pending_outbox_count"))
      assertEquals(1, bundle.getJSONObject("status").getInt("conflict_outbox_count"))
      assertTrue(bundle.getJSONArray("outbox").length() >= 2)
    }
  }
}
