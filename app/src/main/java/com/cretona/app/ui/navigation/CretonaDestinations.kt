package com.cretona.app.ui.navigation

import kotlinx.serialization.Serializable

/**
 * Type-safe navigation routes. Screens are added here as each phase of the
 * roadmap lands; see Cretona_Roadmap.md (P4-5 onwards).
 */
sealed interface CretonaRoute {

    @Serializable
    data object Auth : CretonaRoute

    /**
     * Avatar and username. [isEdit] distinguishes first-run setup, which has
     * no way back, from editing an existing profile, which can be cancelled.
     */
    @Serializable
    data class ProfileSetup(val isEdit: Boolean = false) : CretonaRoute

    /** The signed-in shell: Home, History and Profile behind one bottom bar. */
    @Serializable
    data object Main : CretonaRoute

    @Serializable
    data object Admin : CretonaRoute
}

