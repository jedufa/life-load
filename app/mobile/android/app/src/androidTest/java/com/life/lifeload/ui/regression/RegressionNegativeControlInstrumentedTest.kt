package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.local.LifeLoadLocalStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RegressionNegativeControlInstrumentedTest {
  @Test
  fun localStoreTruthAssertionsFailOnWrongDiaryExpectation() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    val entry = RegressionFixture.seedPendingApproval(
      context,
      RegressionFixture.entry(RegressionFixture.mondayNormal, note = "known local truth"),
    )

    assertThrows(AssertionError::class.java) {
      AndroidTruthHelpers.assertApprovedOrPendingEntry(context, entry.date, "wrong expected note")
    }
    AndroidTruthHelpers.assertApprovedOrPendingEntry(context, entry.date, "known local truth")
  }

  @Test
  fun outboxAssertionsFailOnWrongPendingCount() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    RegressionFixture.seedDraft(context)
    RegressionFixture.seedPendingApproval(context)

    assertThrows(AssertionError::class.java) {
      LifeLoadLocalStore(context).use { store ->
        assertEquals("negative control must catch wrong outbox count", 0, store.status().pendingOutboxCount)
      }
    }
    LifeLoadLocalStore(context).use { store ->
      assertEquals(2, store.status().pendingOutboxCount)
    }
  }

  @Test
  fun redactionAssertionsFailIfSecretAppearsInRedactedBundle() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    RegressionFixture.resetAppState(context)
    RegressionFixture.seedPendingApproval(
      context,
      RegressionFixture.entry(RegressionFixture.mondayNormal, note = RegressionFixture.privacySecret),
    )

    LifeLoadLocalStore(context).use { store ->
      val fullBundle = store.exportDebugBundle(redacted = false)
      val redactedBundle = store.exportDebugBundle(redacted = true)
      assertTrue(fullBundle.contains(RegressionFixture.privacySecret))
      assertThrows(AssertionError::class.java) {
        assertTrue("negative control must fail when expecting secret in redacted bundle", redactedBundle.contains(RegressionFixture.privacySecret))
      }
    }
  }
}
