package com.life.lifeload.ui.regression

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class CompassDailyApprovalRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun compassCoreApprovalWritesPendingLocalEntry() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()
    val diaryText = "compass approval neutral note"

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    waitForTag("compass-content")
    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")

    replaceTextAndAssert(compose, "daily-diary-input", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("daily-core-sleep_yes").performClick()
    compose.onNodeWithTag("daily-core-nutrition_yes").performClick()
    compose.onNodeWithTag("daily-core-alcohol_none").performClick()
    compose.onNodeWithTag("daily-core-binge_no").performClick()
    compose.onNodeWithTag("daily-approve-button").performClick()

    compose.waitUntil(20_000) {
      LifeLoadLocalStore(context).use { store ->
        store.getEntry(fixtureDate)?.state == "pending_approval"
      }
    }
    compose.onNodeWithText("Done").assertExists()
    compose.onNodeWithTag("daily-approve-button").assertTextContains("Update check-in")
    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      assertEquals("pending_approval", record?.state)
      assertEquals(diaryText, record?.entry?.diaryText)
      assertEquals(true, record?.entry?.sleepOk)
      assertEquals(true, record?.entry?.nutritionOk)
      assertEquals("none", record?.entry?.alcohol)
      assertEquals(false, record?.entry?.binge)
      assertEquals(1, store.pendingOutbox().count { it.date == fixtureDate && it.operation == "approve" })
    }
  }

  private fun waitForTag(tag: String) {
    compose.waitUntil(20_000) {
      runCatching {
        compose.onNodeWithTag(tag).fetchSemanticsNode()
        true
      }.getOrDefault(false)
    }
    compose.waitForIdle()
  }
}
