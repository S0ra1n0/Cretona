package com.cretona.app.ui.auth

data class AuthUiState(
    val email: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    val isSignUpMode: Boolean = false,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val successNotice: String? = null,
    val loginSucceeded: Boolean = false,
    // An account with no username has not been through profile setup yet.
    val needsProfileSetup: Boolean = false,
) {
    val canSubmit: Boolean
        get() = if (isSignUpMode) {
            email.isNotBlank() &&
                password.length >= 6 &&
                confirmPassword.isNotBlank() &&
                !isLoading
        } else {
            email.isNotBlank() && password.isNotBlank() && !isLoading
        }
}
