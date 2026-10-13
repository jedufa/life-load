package com.life.lifeload.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LifeLoadUiVariantTest {
  @Test
  fun registryDefaultsUnknownVariantToCompassPlus() {
    assertEquals(LifeLoadUiVariant.CompassPlus, LifeLoadUiVariantRegistry.default)
    assertEquals(LifeLoadUiVariant.CompassPlus, LifeLoadUiVariantRegistry.fromId("missing"))
    assertEquals(LifeLoadUiVariant.CompassPlus, LifeLoadUiVariantRegistry.fromId(null))
  }

  @Test
  fun variantIdsAreStableAndUnique() {
    val ids = LifeLoadUiVariantRegistry.all.map { it.id }
    assertTrue(ids.contains("classic"))
    assertTrue(ids.contains("compass"))
    assertTrue(ids.contains("compass_plus"))
    assertEquals(ids.toSet().size, ids.size)
  }
}
