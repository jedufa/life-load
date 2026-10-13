package com.life.lifeload.ui.regression

import android.app.Activity
import android.content.Context
import android.view.inputmethod.InputMethodManager
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextReplacement
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage

fun closeKeyboard() {
  val instrumentation = InstrumentationRegistry.getInstrumentation()
  instrumentation.runOnMainSync {
    val activity = resumedActivity()
    val view = activity?.currentFocus ?: activity?.window?.decorView
    val imm = activity?.getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
    if (view != null) {
      view.clearFocus()
      imm?.hideSoftInputFromWindow(view.windowToken, 0)
    }
  }
  instrumentation.waitForIdleSync()
}

fun <A : ComponentActivity> replaceTextAndAssert(
  compose: AndroidComposeTestRule<ActivityScenarioRule<A>, A>,
  tag: String,
  text: String,
) {
  var lastFailure: Throwable? = null
  repeat(3) {
    runCatching {
      compose.onNodeWithTag(tag).performClick()
      compose.onNodeWithTag(tag).performTextReplacement("")
      compose.onNodeWithTag(tag).performTextReplacement(text)
      compose.waitForIdle()
      compose.onNodeWithTag(tag).assertTextContains(text)
    }.onSuccess {
      return
    }.onFailure {
      lastFailure = it
    }
  }
  throw AssertionError("Failed to replace text for $tag", lastFailure)
}

private fun resumedActivity(): Activity? =
  ActivityLifecycleMonitorRegistry
    .getInstance()
    .getActivitiesInStage(Stage.RESUMED)
    .filterIsInstance<Activity>()
    .firstOrNull()
