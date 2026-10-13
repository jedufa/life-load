package com.life.lifeload.ui.regression

import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
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
class CompassEditReapproveRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Compass)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  @Test
  fun compassEditReapproveReplacesCoreTruth() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)
    waitForTag("compass-content")
    compose.onNodeWithTag("nav-today").performClick()
    waitForTag("today-hero-card")

    enterCore(note = "compass first truth", sleep = "daily-core-sleep_yes", nutrition = "daily-core-nutrition_yes", alcohol = "daily-core-alcohol_none", binge = "daily-core-binge_no")
    approveAndWaitForPending(fixtureDate, approveCount = 1)

    enterCore(note = "compass replacement truth", sleep = "daily-core-sleep_no", nutrition = "daily-core-nutrition_no", alcohol = "daily-core-alcohol_home", binge = "daily-core-binge_yes")
    approveAndWaitForPending(fixtureDate, approveCount = 2)

    LifeLoadLocalStore(context).use { store ->
      val record = store.getEntry(fixtureDate)
      assertEquals("pending_approval", record?.state)
      assertEquals("compass replacement truth", record?.entry?.diaryText)
      assertEquals(false, record?.entry?.sleepOk)
      assertEquals(false, record?.entry?.nutritionOk)
      assertEquals("home", record?.entry?.alcohol)
      assertEquals(true, record?.entry?.binge)
      assertEquals(2, store.pendingOutbox().count { it.date == fixtureDate && it.operation == "approve" })
    }
  }

  private fun enterCore(note: String, sleep: String, nutrition: String, alcohol: String, binge: String) {
    replaceTextAndAssert(compose, "daily-diary-input", note)
    closeKeyboard()
    compose.onNodeWithTag(sleep).performClick()
    compose.onNodeWithTag(nutrition).performClick()
    compose.onNodeWithTag(alcohol).performClick()
    compose.onNodeWithTag(binge).performClick()
  }

  private fun approveAndWaitForPending(fixtureDate: String, approveCount: Int) {
    compose.onNodeWithTag("compass-content").performScrollToNode(hasTestTag("daily-approve-button"))
    compose.onNodeWithTag("daily-approve-button").performClick()
    compose.waitUntil(20_000) {
      LifeLoadLocalStore(compose.activity.applicationContext).use { store ->
        store.getEntry(fixtureDate)?.state == "pending_approval" &&
          store.pendingOutbox().count { it.date == fixtureDate && it.operation == "approve" } >= approveCount
      }
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
