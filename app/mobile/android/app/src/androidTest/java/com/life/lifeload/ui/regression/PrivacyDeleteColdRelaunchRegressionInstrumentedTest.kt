package com.life.lifeload.ui.regression

import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.MainActivity
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate
import java.time.ZoneId

@RunWith(AndroidJUnit4::class)
class PrivacyDeleteColdRelaunchRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val composeRule = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(composeRule)

  private val compose = composeRule
  private val robot by lazy { ComposeRobot(composeRule) }

  @Test
  fun deleteLocalDataClearsStoreExportsAndSurvivesActivityRecreate() {
    val context = compose.activity.applicationContext
    val fixtureDate = LocalDate.now(ZoneId.of("Europe/Vienna")).minusDays(1).toString()

    RegressionFixture.resetAppState(context)
    RegressionFixture.forceBackendUnavailable(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.waitForEnabledTag("daily_diary_text")
    val diaryText = "privacy delete cold relaunch neutral note"
    replaceTextAndAssert(compose, "daily_diary_text", diaryText)
    closeKeyboard()
    compose.onNodeWithTag("sleep_ok_yes").performClick()
    compose.onNodeWithTag("nutrition_ok_yes").performClick()
    compose.onNodeWithTag("daily_approve_button").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Check-in saved locally", substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    robot.navigateDrawer("drawer_settings", "Settings")
    robot.scrollTo(hasTestTag("privacy_controls_card"))
    compose.onNodeWithTag("privacy_export_local").performClick()
    compose.waitUntil(20_000) {
      compose.onAllNodesWithText("Exported", substring = true).fetchSemanticsNodes().isNotEmpty()
    }
    val exportFile = File(context.filesDir, "life_load_exports/life_load_local_export.json")

    compose.onNodeWithTag("privacy_delete_local").performClick()
    compose.onNodeWithTag("privacy_delete_confirm").performClick()
    robot.waitForText("Local data deleted", substring = true)

    compose.activityRule.scenario.recreate()
    robot.assertAppForeground()

    LifeLoadLocalStore(context).use { store ->
      assertEquals(0, store.status().entryCount)
      assertEquals(0, store.status().pendingOutboxCount)
      assertNull(store.getEntry(fixtureDate))
    }
    assertEquals(false, exportFile.exists())
  }
}
