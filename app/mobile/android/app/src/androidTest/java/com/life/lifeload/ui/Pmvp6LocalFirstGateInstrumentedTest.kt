package com.life.lifeload.ui

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import com.life.lifeload.ui.regression.closeKeyboard
import com.life.lifeload.ui.regression.replaceTextAndAssert
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.regression.RegressionFixture
import com.life.lifeload.ui.regression.UiVariantRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class Pmvp6LocalFirstGateInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun backendUnavailableApprovalQueuesAndroidLocalOutbox() {
    GateVisual.pause()
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val diaryText = "pmvp6 local first gate note"
    val onlineServerUrl = ServerConfig.resolveBaseUrl(context)
    val offlineOnly = InstrumentationRegistry.getArguments().getString("backend_mode") == "offline-only"
    RegressionFixture.resetAppState(context)

    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }

    compose.onNodeWithContentDescription("Open navigation").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("drawer_settings").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("local_diagnostics_card"))
    GateVisual.pause()
    compose.onNodeWithTag("local_history_import_7d").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Imported", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    GateVisual.pause()
    LifeLoadLocalStore(context).use { store ->
      assertTrue(store.status().entryCount >= 1)
    }
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("settings_close_button"))
    compose.onNodeWithTag("settings_close_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onNodeWithTag("drawer_daily").performClick()
    GateVisual.pause()

    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")
    compose.onNodeWithContentDescription("Refresh").performClick()
    compose.waitForIdle()
    GateVisual.pause()

    compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    GateVisual.pause()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    GateVisual.pause()
    compose.onNodeWithTag("daily_approve_button").assertIsEnabled().performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    GateVisual.pause()
    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onNodeWithTag("drawer_settings").performClick()
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("local_diagnostics_card"))
    compose.onNodeWithTag("local_diagnostics_card").fetchSemanticsNode()
    GateVisual.pause()
    compose.onNodeWithTag("local_diagnostics_refresh").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Redacted diagnostics loaded.", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    GateVisual.pause()

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      val outbox = store.pendingOutbox()
      assertEquals("pending_approval", record?.state)
      assertEquals(diaryText, record?.entry?.diaryText)
      assertTrue(outbox.any { it.date == fixtureDate && it.operation == "approve" })
    }

    val expectedState: String
    val expectedPendingOutboxCount: Int
    if (offlineOnly) {
      expectedState = "pending_approval"
      expectedPendingOutboxCount = LifeLoadLocalStore(context).use { store -> store.status().pendingOutboxCount }
    } else {
      ServerConfig.saveBaseUrl(context, onlineServerUrl)
      compose.onNodeWithTag("local_outbox_sync").performClick()
      compose.waitUntil(20_000) {
        compose.onAllNodesWithText("Synced", substring = true).fetchSemanticsNodes().isNotEmpty()
      }
      GateVisual.pause()
      compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("settings_close_button"))
      compose.onNodeWithTag("settings_close_button").performClick()
      compose.waitUntil(20_000) {
        LifeLoadLocalStore(context).use { store ->
          store.getEntry(fixtureDate)?.state == "approved"
        }
      }
      expectedState = "approved"
      expectedPendingOutboxCount = 0
    }
    GateVisual.pause()
    if (!offlineOnly) {
      compose.onNodeWithContentDescription("Open navigation").performClick()
      compose.onNodeWithTag("drawer_settings").performClick()
    }
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("local_diagnostics_card"))
    GateVisual.pause()
    if (!offlineOnly) {
      compose.onNodeWithTag("local_debug_mirror").performClick()
      compose.waitUntil(20_000) {
        compose.onAllNodesWithText("Mirrored", substring = true).fetchSemanticsNodes().isNotEmpty()
      }
    }
    GateVisual.pause()

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      assertEquals(expectedState, record?.state)
      assertEquals(diaryText, record?.entry?.diaryText)
      assertEquals(expectedPendingOutboxCount, store.status().pendingOutboxCount)

      val redactedBundle = store.exportDebugBundle(redacted = true)
      assertTrue(redactedBundle.contains("\"redaction\":\"redacted\""))
      assertTrue(!redactedBundle.contains(diaryText))
      val fullBundle = store.exportDebugBundle(redacted = false)
      store.resetLocalData()
      assertEquals(0, store.status().entryCount)
      assertEquals(0, store.status().pendingOutboxCount)
      store.restoreDebugBundle(fullBundle)
      assertEquals(expectedState, store.getEntry(fixtureDate)?.state)
      assertEquals(expectedPendingOutboxCount, store.status().pendingOutboxCount)
    }
  }
}
