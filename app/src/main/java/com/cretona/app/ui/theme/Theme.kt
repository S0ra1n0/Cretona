package com.cretona.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

private val LightColors = lightColorScheme(
    primary = CretonaPurple,
    onPrimary = androidx.compose.ui.graphics.Color.White,
    primaryContainer = CretonaPurpleLight.copy(alpha = 0.3f),
    secondary = CretonaBlue,
    tertiary = CretonaPink,
    background = androidx.compose.ui.graphics.Color(0xFFF8F9FE),
    surface = androidx.compose.ui.graphics.Color.White,
    surfaceVariant = androidx.compose.ui.graphics.Color(0xFFEEF0FA),
    error = CretonaError,
)

private val DarkColors = darkColorScheme(
    primary = CretonaPurpleLight,
    onPrimary = CretonaInk,
    primaryContainer = CretonaPurpleDark,
    secondary = CretonaCyan,
    tertiary = CretonaPink,
    background = CretonaInk,
    surface = CretonaSurfaceDark,
    surfaceVariant = CretonaSurfaceCard,
    error = CretonaError,
)

@Composable
fun CretonaTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    // Material You is opt-in; the brand palette is the default so the app looks
    // the same across devices during development.
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit,
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColors
        else -> LightColors
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = CretonaTypography,
        content = content,
    )
}
