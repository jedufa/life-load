package com.life.lifeload.ui.regression

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.rules.ActivityScenarioRule
import com.life.lifeload.ui.GateVisual
import org.junit.Assert.assertTrue

class ComposeRobot<A : ComponentActivity>(
  private val compose: AndroidComposeTestRule<ActivityScenarioRule<A>, A>,
) {
  fun waitForText(text: String, substring: Boolean = false, timeoutMs: Long = 20_000) {
    compose.waitUntil(timeoutMs) {
      val nodes = compose.onAllNodesWithText(text, substring = substring).fetchSemanticsNodes()
      nodes.indices.any { index ->
        runCatching {
          compose.onAllNodesWithText(text, substring = substring)[index].assertIsDisplayed()
          true
        }.getOrDefault(false)
      }
    }
    GateVisual.pause()
  }

  fun openDrawer() {
    scrollTo(hasContentDescription("Open navigation"))
    compose.onNodeWithContentDescription("Open navigation").performClick()
    compose.waitForIdle()
    GateVisual.pause()
  }

  fun navigateDrawer(tag: String, expectedTitle: String) {
    openDrawer()
    compose.onNodeWithTag(tag).performClick()
    waitForText(expectedTitle, substring = true)
    assertAppForeground()
  }

  fun scrollTo(matcher: SemanticsMatcher) {
    compose.onNodeWithTag("life_load_content").performScrollToNode(matcher)
  }

  fun scrollToTag(tag: String) {
    scrollTo(hasTestTag(tag))
  }

  fun waitForEnabledTag(tag: String, timeoutMs: Long = 20_000) {
    compose.waitUntil(timeoutMs) {
      runCatching {
        compose.onNodeWithTag(tag).assertIsEnabled()
        true
      }.getOrDefault(false)
    }
    GateVisual.pause()
  }

  fun assertAppForeground() {
    assertTrue(compose.activity.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED))
  }
}
