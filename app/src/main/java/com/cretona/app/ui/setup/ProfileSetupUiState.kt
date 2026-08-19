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

/**
 * The gender choices, in the order the form offers them.
 *
 * [stored] is what the backend keeps and validates against; [label] is what
 * the form shows. Kept together so the two cannot drift apart.
 */
enum class GenderOption(val stored: String, val label: String) {
    MALE("male", "Male"),
    FEMALE("female", "Female"),
    OTHER("other", "Other"),
    ;

    companion object {
        /** The option matching a stored value, or null if none does. */
        fun fromStored(value: String?): GenderOption? =
            entries.firstOrNull { it.stored.equals(value?.trim(), ignoreCase = true) }
    }
}

/** Birthday rules, enforced here so the field can explain itself. */
object BirthdayRules {
    /**
     * The wire and storage format, matching the backend's ISO date check.
     * Chosen over a localised format so what is typed is what is stored.
     */
    private val ISO_DATE = Regex("""^\d{4}-\d{2}-\d{2}$""")

    /** The reason [value] is unusable, or null when it is fine. */
    fun validate(value: String): String? = when {
        value.isEmpty() -> null // Optional: nothing chosen is not an error.
        !ISO_DATE.matches(value) -> "Use the date picker, or type YYYY-MM-DD."
        else -> null
    }

    fun isValid(value: String): Boolean = value.isEmpty() || ISO_DATE.matches(value)
}

data class ProfileSetupUiState(
    val username: String = "",
    // Both optional and both empty when unanswered. Empty is also what the
    // save sends to clear a value that was chosen before.
    val gender: String = "",
    val birthday: String = "",
    val showDatePicker: Boolean = false,
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

    val birthdayError: String? get() = BirthdayRules.validate(birthday)

    /** The chosen option, or null while the account has not answered. */
    val selectedGender: GenderOption? get() = GenderOption.fromStored(gender)

    // The avatar, gender and birthday are all optional, so only the username
    // gates submission -- a malformed birthday is the one exception, since
    // saving it would fail at the backend anyway.
    val canSubmit: Boolean
        get() = UsernameRules.isValid(username) &&
            BirthdayRules.isValid(birthday) &&
            !isSubmitting
}
