package com.life.lifeload.ui.regression

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.data.HttpLifeLoadApi
import com.life.lifeload.data.LifeLoadRepository
import com.life.lifeload.data.ServerConfig
import com.life.lifeload.data.local.LifeLoadLocalStore
import com.life.lifeload.domain.LifeLoadEntry
import com.life.lifeload.domain.LifeLoadFormulaSettings
import com.life.lifeload.domain.LifeLoadScore
import com.life.lifeload.domain.LifeLoadSettings
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

@RunWith(AndroidJUnit4::class)
class FormulaExpectedResultsRegressionInstrumentedTest {
  private val context = InstrumentationRegistry.getInstrumentation().targetContext
  private lateinit var store: LifeLoadLocalStore
  private lateinit var repository: LifeLoadRepository
  private var originalSettings: LifeLoadSettings? = null

  @Before
  fun setUp() {
    RegressionFixture.resetLocalStore(context)
    ServerConfig.resetBaseUrl(context)
    store = LifeLoadLocalStore(context)
    repository = LifeLoadRepository(
      api = HttpLifeLoadApi(serverBaseUrlProvider = { ServerConfig.resolveBaseUrl(context) }),
      localStore = store,
    )
    runBlocking {
      originalSettings = repository.loadSettings()
    }
  }

  @After
  fun tearDown() {
    runBlocking {
      originalSettings?.let { runCatching { repository.saveSettings(it) } }
    }
    store.close()
  }

  @Test
  fun protectiveModifierProducesExpectedScoreThresholdsAndProvenance() = runBlocking {
    repository.saveSettings(settingsWithProfileModifiers("protective"))

    val score = approveAndReadScore(
      LifeLoadEntry(
        date = "2032-02-02",
        diaryText = "formula regression protective fixture",
        sleepOk = true,
        nutritionOk = true,
        alcohol = "none",
        binge = false,
        shutdownDone = false,
        afterWorkDecompressionDone = false,
        phoneAfter21 = true,
        projectOverrun = true,
        stress = 7,
        energy = 6,
      ),
    )

    assertScoreEquals(18.4, score.baseScore)
    assertScoreEquals(20.4, score.profileAdjustedScore)
    assertScoreEquals(20.4, score.lifeLoadScore)
    assertScoreEquals(20.4, score.strainScore)
    assertScoreEquals(6.4, score.recoveryScore)
    assertEquals("red", score.zone)
    assertEquals(32, score.guidanceMediumThreshold)
    assertEquals(65, score.guidanceHighThreshold)
    assertEquals(listOf("protective"), score.profileModifiers)
    assertTrue(score.profileEffects.contains("protective lowered medium-risk threshold to 32"))
    assertTrue(score.profileEffects.contains("protective lowered high-risk threshold to 65"))
    assertTrue(score.profileEffects.contains("protective increased late-phone strain"))
    assertTrue(score.profileEffects.contains("protective increased project-overrun strain"))
    assertTrue(score.profileEffects.contains("protective increased shutdown-missed strain"))
    assertTrue(score.profileEffects.contains("protective increased after-work decompression strain"))
  }

  @Test
  fun sportsLightModifierSoftensOnlyEligibleTrainingLoad() = runBlocking {
    repository.saveSettings(settingsWithProfileModifiers("sports_light"))

    val eligible = approveAndReadScore(
      LifeLoadEntry(
        date = "2032-02-03",
        diaryText = "formula regression sports-light eligible fixture",
        sleepOk = true,
        nutritionOk = true,
        alcohol = "none",
        binge = false,
        energy = 6,
        footPain = 0,
        shoulderPain = 0,
        primaryActivityType = "run",
        activityTypes = listOf("run"),
        activityDurationMin = 60,
      ),
    )
    assertScoreEquals(6.0, eligible.baseScore)
    assertScoreEquals(5.6, eligible.profileAdjustedScore)
    assertScoreEquals(4.0, eligible.trainingLoad)
    assertEquals("yellow", eligible.zone)
    assertEquals(listOf("sports_light"), eligible.profileModifiers)
    assertEquals(listOf("sports_light softened training spike penalty"), eligible.profileEffects)

    val painBlocked = approveAndReadScore(
      LifeLoadEntry(
        date = "2032-02-04",
        diaryText = "formula regression sports-light pain-blocked fixture",
        sleepOk = true,
        nutritionOk = true,
        alcohol = "none",
        binge = false,
        energy = 6,
        footPain = 5,
        shoulderPain = 0,
        primaryActivityType = "run",
        activityTypes = listOf("run"),
        activityDurationMin = 60,
      ),
    )
    assertScoreEquals(8.5, painBlocked.profileAdjustedScore)
    assertScoreEquals(4.0, painBlocked.trainingLoad)
    assertEquals("yellow", painBlocked.zone)
    assertEquals(listOf("sports_light not applied because pain >= 5"), painBlocked.profileEffects)
  }

  private suspend fun approveAndReadScore(entry: LifeLoadEntry): LifeLoadScore {
    repository.saveDraft(entry)
    val payload = repository.approve(entry)
    assertEquals("approved", payload.entryState)
    val storedScore = store.getEntry(entry.date)?.score
    requireNotNull(storedScore) { "No local score stored for ${entry.date}" }
    return storedScore
  }

  private fun settingsWithProfileModifiers(vararg modifiers: String): LifeLoadSettings {
    val settings = originalSettings ?: LifeLoadSettings()
    return settings.copy(
      formula = settings.formula.withExpectedResultToggles(
        profile = "balanced",
        profileModifiers = modifiers.toSet(),
      ),
    )
  }

  private fun LifeLoadFormulaSettings.withExpectedResultToggles(
    profile: String,
    profileModifiers: Set<String>,
  ): LifeLoadFormulaSettings =
    copy(
      profile = profile,
      profileModifiers = profileModifiers,
      includeTrainingTrendBrake = true,
      includeGarminRecovery = true,
      includeRelationshipStress = true,
      includeAloneHome = true,
      includeAfterWorkDecompression = true,
      includeProjectOverrun = true,
      includeLatePhone = true,
      includeHomeOffice = true,
    )

  private fun assertScoreEquals(expected: Double, actual: Double) {
    assertTrue("expected <$expected> but was <$actual>", abs(expected - actual) < 0.001)
  }
}
