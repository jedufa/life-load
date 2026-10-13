package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RegressionFixtureSeedingInstrumentedTest {
  @Test
  fun fixtureCanSeedDraftPendingAndServerApprovedRows() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)

    val draft = RegressionFixture.seedDraft(
      context,
      RegressionFixture.entry(RegressionFixture.mondayNormal, note = "draft fixture"),
    )
    val pending = RegressionFixture.seedPendingApproval(
      context,
      RegressionFixture.entry(RegressionFixture.wednesdayOverload, note = "pending fixture"),
    )
    val approved = RegressionFixture.seedServerApproved(
      context,
      RegressionFixture.entry(RegressionFixture.saturdayWeekend, note = "approved fixture"),
    )

    LifeLoadLocalStore(context).use { store ->
      assertEquals("draft", store.getEntry(draft.date)?.state)
      assertEquals("pending_approval", store.getEntry(pending.date)?.state)
      assertEquals("approved", store.getEntry(approved.date)?.state)
      assertEquals(3, store.status().entryCount)
      assertEquals(2, store.status().pendingOutboxCount)
      assertNotNull(store.pendingOutbox().firstOrNull { it.date == draft.date && it.operation == "draft_upsert" })
      assertNotNull(store.pendingOutbox().firstOrNull { it.date == pending.date && it.operation == "approve" })
    }
  }

  @Test
  fun pendingLocalWriteProtectsAgainstStaleServerOverwrite() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)

    val local = RegressionFixture.seedPendingApproval(
      context,
      RegressionFixture.entry(RegressionFixture.wednesdayOverload, note = "local pending truth"),
    )
    RegressionFixture.seedServerApproved(
      context,
      RegressionFixture.entry(RegressionFixture.wednesdayOverload, note = "stale server truth"),
    )

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(local.date)
      assertEquals("pending_approval", record?.state)
      assertEquals("local pending truth", record?.entry?.diaryText)
    }
  }
}
