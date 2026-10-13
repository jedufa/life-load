package com.life.lifeload.ui.regression

import androidx.test.platform.app.InstrumentationRegistry
import com.life.lifeload.ui.DebugUiVariantStore
import com.life.lifeload.ui.LifeLoadUiVariant
import org.junit.rules.TestRule
import org.junit.runner.Description
import org.junit.runners.model.Statement

class UiVariantRule(
  private val variant: LifeLoadUiVariant,
) : TestRule {
  override fun apply(base: Statement, description: Description): Statement =
    object : Statement() {
      override fun evaluate() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        DebugUiVariantStore.save(context, variant)
        base.evaluate()
      }
    }
}
