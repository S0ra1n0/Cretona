package com.cretona.app.domain.model

import androidx.compose.runtime.Immutable

@Immutable
data class UserProfile(
    val id: String,
    val email: String?,
    val username: String?,
    val avatarUrl: String? = null,
    val role: String,
    val isDisabled: Boolean,
    val createdAt: String,
    val quota: GenerationQuota,
) {
    val displayName: String
        get() = username ?: email ?: "Cretona user"

    /** A new account has no username until profile setup completes. */
    val needsProfileSetup: Boolean
        get() = username.isNullOrBlank()
}

@Immutable
data class GenerationQuota(
    val limit: Int,
    val used: Int,
    val remaining: Int,
    val resetsAt: String?,
)
