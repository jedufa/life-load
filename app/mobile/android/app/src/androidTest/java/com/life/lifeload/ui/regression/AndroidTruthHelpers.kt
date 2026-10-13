package com.life.lifeload.ui.regression

import android.content.Context
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue

object AndroidTruthHelpers {
  fun assertNoEntries(context: Context) {
    LifeLoadLocalStore(context).use { store ->
      val status = store.status()
      assertEquals(0, status.entryCount)
      assertEquals(0, status.pendingOutboxCount)
    }
  }

  fun assertApprovedOrPendingEntry(context: Context, date: String, diaryText: String) {
    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(date)
      assertNotNull(record)
      assertTrue(record?.state == "approved" || record?.state == "pending_approval")
      assertEquals(diaryText, record?.entry?.diaryText)
    }
  }
}
