package com.cretona.app.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

val CretonaPurple = Color(0xFF7C3AED)
val CretonaPurpleDark = Color(0xFF5B21B6)
val CretonaPurpleLight = Color(0xFFA78BFA)
val CretonaBlue = Color(0xFF2563EB)
val CretonaCyan = Color(0xFF06B6D4)
val CretonaPink = Color(0xFFEC4899)
val CretonaAmber = Color(0xFFF59E0B)
val CretonaEmerald = Color(0xFF10B981)

val CretonaInk = Color(0xFF0F0B1E)
val CretonaSurfaceDark = Color(0xFF181232)
val CretonaSurfaceCard = Color(0xFF201844)
val CretonaSurfaceCardLight = Color(0xFF2A2058)
val CretonaError = Color(0xFFEF4444)

// Galaxy gradient: blue fading into purple, used on the auth screen
// background and its bright accent (wordmark, primary button).
val GalaxyDeepBlue = Color(0xFF0B0726)
val GalaxyIndigo = Color(0xFF1E1452)
val GalaxyViolet = Color(0xFF7C3AED)
val GalaxyBrightAccent = Color(0xFFC084FC)

val PrimaryGradient = Brush.horizontalGradient(
    listOf(Color(0xFF7C3AED), Color(0xFF3B82F6))
)
val AccentGradient = Brush.horizontalGradient(
    listOf(Color(0xFFEC4899), Color(0xFF8B5CF6))
)
val CardGradient = Brush.verticalGradient(
    listOf(Color(0xFF231A4C), Color(0xFF171035))
)
