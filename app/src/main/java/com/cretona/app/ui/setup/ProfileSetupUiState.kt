package com.cretona.app.ui.setup

import android.net.Uri

/** Username rules, enforced here so the field can explain itself as you type. */
object UsernameRules {
    const val MIN_LENGTH = 3
    const val MAX_LENGTH = 25

    // Letters, digits and underscore only. The backend pins the same character
    // class (^[A-Za-z0-9_]+$); it allows up to 30, so this 25 is the stricter
    // of the two and will never be rejected on length by the server.
    private val ALLOWED = Regex("^[A-Za-z0-9_]+$")

    /** The reason [value] is unusable, or null when it is fine. */
    fun validate(value: String): String? = when {
        value.isEmpty() -> null // Nothing typed yet is not an error to show.
        value.length < MIN_LENGTH -> "At least $MIN_LENGTH characters."
        value.length > MAX_LENGTH -> "At most $MAX_LENGTH characters."
        !ALLOWED.matches(value) -> "Letters, numbers and underscore only."
        else -> null
    }

    fun isValid(value: String): Boolean =
        value.length in MIN_LENGTH..MAX_LENGTH && ALLOWED.matches(value)
}

data class ProfileSetupUiState(
    val username: String = "",
    val avatarUri: Uri? = null,
    // The avatar already stored on the account, shown until a new one is
    // picked. Distinct from avatarUri so "keep what I have" and "replace it"
    // stay distinguishable.
    val existingAvatarUrl: String? = null,
    val isSubmitting: Boolean = false,
    val errorMessage: String? = null,
    val isComplete: Boolean = false,
) {
    val usernameError: String? get() = UsernameRules.validate(username)

    // The avatar is optional; only the username gates submission.
    val canSubmit: Boolean get() = UsernameRules.isValid(username) && !isSubmitting
}
