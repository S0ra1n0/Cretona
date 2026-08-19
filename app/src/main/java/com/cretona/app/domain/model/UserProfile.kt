package com.cretona.app.domain.model

import androidx.compose.runtime.Immutable

@Immutable
data class UserProfile(
    val id: String,
    val email: String?,
    val username: String?,
    val avatarUrl: String? = null,
    /** "male", "female" or "other"; null until the account chooses one. */
    val gender: String? = null,
    /** ISO calendar date, "YYYY-MM-DD"; null until the account chooses one. */
    val birthday: String? = null,
    val role: String,
    val isDisabled: Boolean,
    val createdAt: String,
    val quota: GenerationQuota,
) {
    val displayName: String
        get() = username ?: email ?: "Cretona user"

    /**
     * A new account has no username until profile setup completes.
     *
     * Gender and birthday are deliberately not part of this: they are
     * optional, so an account that skipped them is still fully set up.
     */
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
