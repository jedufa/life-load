package com.life.lifeload.ui.regression

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import com.life.lifeload.ui.regression.closeKeyboard
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.life.lifeload.BuildConfig
import com.life.lifeload.MainActivity
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.rules.RuleChain
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SettingsRegressionInstrumentedTest {
  private val variantRule = UiVariantRule(LifeLoadUiVariant.Classic)
  private val compose = createAndroidComposeRule<MainActivity>()

  @get:Rule
  val rules: RuleChain = RuleChain.outerRule(variantRule).around(compose)

  private val robot by lazy { ComposeRobot(compose) }

  @Test
  fun settingsGarminAndServerControlsAreReachableAndServerConfigPersists() {
    val context = compose.activity.applicationContext
    RegressionFixture.resetAppState(context)

    robot.waitForText("Guidance")
    robot.navigateDrawer("drawer_daily", "Check-in")
    robot.navigateDrawer("drawer_settings", "Settings")

    robot.scrollToTag("settings_garmin_active")
    compose.onNodeWithTag("settings_garmin_active").performClick()
    compose.onNodeWithTag("settings_garmin_auto_import").performClick()
    robot.scrollToTag("settings_garmin_email")
    compose.onNodeWithTag("settings_garmin_email").performTextInput("synthetic@example.test")
    closeKeyboard()
    robot.scrollToTag("settings_garmin_password")
    compose.onNodeWithTag("settings_garmin_password").performTextInput("synthetic-password")
    closeKeyboard()
    tap("settings_garmin_auto_import_days_14")
    compose.onNodeWithTag("settings_garmin_save").assertIsDisplayed()

    tap("settings_default_date_today")
    tap("settings_cache_days_14")
    tap("settings_formula_profile_protective")
    tap("settings_show_formula_button")
    tap("settings_show_formula_button")

    val testServerUrl = "http://127.0.0.1:1"
    repeat(3) { attempt ->
      if (ServerConfig.resolveBaseUrl(context) == testServerUrl) return@repeat
      robot.scrollToTag("settings_server_url")
      compose.onNodeWithTag("settings_server_url").performClick()
      compose.onNodeWithTag("settings_server_url").performTextReplacement(testServerUrl)
      compose.onNodeWithTag("settings_server_url").assertTextContains(testServerUrl)
      compose.waitForIdle()
      closeKeyboard()
      robot.scrollToTag("settings_server_apply")
      compose.onNodeWithTag("settings_server_apply").performClick()
      val saved = runCatching {
        compose.waitUntil(5_000) {
          ServerConfig.resolveBaseUrl(context) == testServerUrl
        }
      }.isSuccess
      if (!saved && attempt == 2) {
        assertEquals(testServerUrl, ServerConfig.resolveBaseUrl(context))
      }
    }
    assertEquals(testServerUrl, ServerConfig.resolveBaseUrl(context))

    robot.scrollToTag("settings_server_default")
    compose.onNodeWithTag("settings_server_default").performClick()
    compose.waitUntil(5_000) {
      ServerConfig.resolveBaseUrl(context) == ServerConfig.normalizeBaseUrl(BuildConfig.SERVER_BASE_URL)
    }
    assertEquals(ServerConfig.normalizeBaseUrl(BuildConfig.SERVER_BASE_URL), ServerConfig.resolveBaseUrl(context))
  }

  private fun tap(tag: String) {
    robot.scrollTo(hasTestTag(tag))
    compose.onNodeWithTag(tag).performClick()
  }
}
