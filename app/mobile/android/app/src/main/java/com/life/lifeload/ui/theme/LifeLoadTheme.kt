package com.life.lifeload.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight

private val LightColors = lightColorScheme(
  primary = Color(0xFF1F6959),
  onPrimary = Color(0xFFFFFDF7),
  secondary = Color(0xFF286F46),
  tertiary = Color(0xFF937016),
  background = Color(0xFFF5EFE3),
  onBackground = Color(0xFF241F18),
  surface = Color(0xFFFFFDF7),
  onSurface = Color(0xFF241F18),
  surfaceVariant = Color(0xFFF2E7D3),
  onSurfaceVariant = Color(0xFF766D61),
  outline = Color(0x804F4331),
  error = Color(0xFFA93832),
  onError = Color(0xFFFFFDF7),
)

private val DarkColors = darkColorScheme(
  primary = Color(0xFF72D6C2),
  onPrimary = Color(0xFF082C25),
  secondary = Color(0xFF7EDFA3),
  tertiary = Color(0xFFFFC766),
  background = Color(0xFF10140F),
  onBackground = Color(0xFFF4EFE5),
  surface = Color(0xFF1B2119),
  onSurface = Color(0xFFF4EFE5),
  surfaceVariant = Color(0xFF263022),
  onSurfaceVariant = Color(0xFFD5CCBE),
  outline = Color(0xFF7E8A73),
  error = Color(0xFFFF8F86),
  onError = Color(0xFF3B0806),
)

@Composable
fun LifeLoadTheme(
  darkTheme: Boolean = isSystemInDarkTheme(),
  content: @Composable () -> Unit,
) {
  MaterialTheme(
    colorScheme = if (darkTheme) DarkColors else LightColors,
    typography = MaterialTheme.typography.copy(
      titleLarge = MaterialTheme.typography.titleLarge.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
      titleMedium = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
      titleSmall = MaterialTheme.typography.titleSmall.copy(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold),
      labelMedium = MaterialTheme.typography.labelMedium.copy(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold),
    ),
    content = content,
  )
}
