package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ExportImportRoundTripRegressionInstrumentedTest {
  @Test
  fun fullDebugBundleRestoresEntriesAndOutboxAfterReset() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)

    val draft = RegressionFixture.seedDraft(
      context,
      RegressionFixture.entry(RegressionFixture.mondayNormal, note = "roundtrip draft"),
    )
    val pending = RegressionFixture.seedPendingApproval(
      context,
      RegressionFixture.entry(RegressionFixture.wednesdayOverload, note = "roundtrip pending"),
    )
    val approved = RegressionFixture.seedServerApproved(
      context,
      RegressionFixture.entry(RegressionFixture.saturdayWeekend, note = "roundtrip approved"),
    )

    val fullBundle = LifeLoadLocalStore(context).use { store ->
      assertEquals(3, store.status().entryCount)
      assertEquals(2, store.status().pendingOutboxCount)
      store.exportDebugBundle(redacted = false)
    }

    RegressionFixture.resetLocalStore(context)
    AndroidTruthHelpers.assertNoEntries(context)

    LifeLoadLocalStore(context).use { store ->
      store.restoreDebugBundle(fullBundle)
      assertEquals("draft", store.getEntry(draft.date)?.state)
      assertEquals("roundtrip draft", store.getEntry(draft.date)?.entry?.diaryText)
      assertEquals("pending_approval", store.getEntry(pending.date)?.state)
      assertEquals("roundtrip pending", store.getEntry(pending.date)?.entry?.diaryText)
      assertEquals("approved", store.getEntry(approved.date)?.state)
      assertEquals("roundtrip approved", store.getEntry(approved.date)?.entry?.diaryText)
      assertEquals(3, store.status().entryCount)
      assertEquals(2, store.status().pendingOutboxCount)
      assertNotNull(store.pendingOutbox().firstOrNull { it.date == draft.date && it.operation == "draft_upsert" })
      assertNotNull(store.pendingOutbox().firstOrNull { it.date == pending.date && it.operation == "approve" })
    }
  }
}
