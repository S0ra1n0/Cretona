package com.cretona.app.ui.navigation

import kotlinx.serialization.Serializable

/**
 * Type-safe navigation routes. Screens are added here as each phase of the
 * roadmap lands; see Cretona_Roadmap.md (P4-5 onwards).
 */
sealed interface CretonaRoute {

    @Serializable
    data object Home : CretonaRoute
}
