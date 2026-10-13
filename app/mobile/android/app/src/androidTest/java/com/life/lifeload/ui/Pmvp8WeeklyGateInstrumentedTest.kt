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
import com.life.lifeload.ui.regression.RegressionFixture
import com.life.lifeload.ui.regression.UiVariantRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class Pmvp8WeeklyGateInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun approvedDailyEntryFeedsWeeklyReviewSnapshot() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val diaryText = "pmvp8 weekly gate project spillover late phone"

    ServerConfig.resetBaseUrl(context)
    RegressionFixture.resetAppState(context)
    LifeLoadLocalStore(context).use { store -> store.resetLocalData() }

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
    compose.onNodeWithTag("sleep_ok_no").performClick()
    compose.onNodeWithTag("nutrition_ok_no").performClick()
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      LifeLoadLocalStore(context).use { store ->
        store.getEntry(fixtureDate)?.state == "approved"
      }
    }
    LifeLoadLocalStore(context).use { store ->
      assertEquals("approved", store.getEntry(fixtureDate)?.state)
    }

    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.onAllNodesWithText("Guidance")[0].performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Weekly review", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    compose.onNodeWithTag("life_load_content").performScrollToNode(hasTestTag("weekly_review_snapshot"))
    compose.onNodeWithTag("weekly_review_snapshot").fetchSemanticsNode()
    compose.onAllNodesWithText("One correction:", substring = true).fetchSemanticsNodes().also { nodes ->
      org.junit.Assert.assertTrue(nodes.isNotEmpty())
    }
  }
}
