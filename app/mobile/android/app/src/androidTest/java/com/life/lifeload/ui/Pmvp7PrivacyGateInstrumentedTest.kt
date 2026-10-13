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
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.regression.UiVariantRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class Pmvp7PrivacyGateInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun privacyControlsExportAndDeleteLocalDataFromSettings() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val diaryText = "pmvp7 privacy gate local export note"

    File(context.filesDir, "life_load_exports").deleteRecursively()
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }
    ServerConfig.saveBaseUrl(context, "http://127.0.0.1:1")

    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Guidance").fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onAllNodesWithText("Check-in")[0].performClick()
    compose.onNodeWithContentDescription("Refresh").performClick()
    compose.waitForIdle()

    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag("daily_diary_text").assertIsEnabled()
        true
      }.getOrDefault(false)
    }
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onAllNodesWithText("Settings")[0].performClick()
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("privacy_controls_card"))
    compose.onNodeWithTag("privacy_export_local").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Exported", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    val exportFile = File(context.filesDir, "life_load_exports/life_load_local_export.json")
    assertTrue(exportFile.exists())
    val exportText = exportFile.readText(Charsets.UTF_8)
    assertTrue(exportText.contains("\"redaction\":\"full_local_only\""))
    assertTrue(exportText.contains(diaryText))

    LifeLoadLocalStore(context).use { store ->
      assertEquals("pending_approval", store.getEntry(fixtureDate)?.state)
      assertTrue(store.pendingOutbox().any { it.date == fixtureDate && it.operation == "approve" })
    }

    compose.onNodeWithTag("privacy_delete_local").performClick()
    compose.onNodeWithTag("privacy_delete_confirm").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Local data deleted", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    LifeLoadLocalStore(context).use { store ->
      assertEquals(0, store.status().entryCount)
      assertEquals(0, store.status().pendingOutboxCount)
    }
    assertFalse(exportFile.exists())
  }
}
