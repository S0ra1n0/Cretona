package com.cretona.app.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.AuthRepository
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repository: AuthRepository,
    private val profiles: CretonaRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(AuthUiState())
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    fun onEmailChanged(value: String) {
        _state.update { it.copy(email = value, errorMessage = null, successNotice = null) }
    }

    fun onPasswordChanged(value: String) {
        _state.update { it.copy(password = value, errorMessage = null, successNotice = null) }
    }

    fun onConfirmPasswordChanged(value: String) {
        _state.update { it.copy(confirmPassword = value, errorMessage = null, successNotice = null) }
    }

    fun toggleMode() {
        _state.update {
            it.copy(
                isSignUpMode = !it.isSignUpMode,
                errorMessage = null,
                successNotice = null,
            )
        }
    }

    fun setSignUpMode(isSignUp: Boolean) {
        _state.update {
            it.copy(
                isSignUpMode = isSignUp,
                errorMessage = null,
                successNotice = null,
            )
        }
    }

    fun submit() {
        val current = _state.value
        if (!current.canSubmit) return

        if (current.isSignUpMode) {
            signUp()
        } else {
            login()
        }
    }

    fun login() {
        val current = _state.value
        if (current.email.isBlank() || current.password.isBlank()) return

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, errorMessage = null, successNotice = null) }
            when (val result = repository.signIn(current.email, current.password)) {
                is AppResult.Success -> {
                    // A profile with no username has not completed setup. If
                    // this lookup fails, fall through to Home rather than
                    // trapping the user in setup on a transient error -- Home
                    // surfaces the failure and offers a retry.
                    val needsSetup = when (val me = profiles.getCurrentUser()) {
                        is AppResult.Success -> me.data.needsProfileSetup
                        is AppResult.Failure -> false
                    }
                    _state.update {
                        it.copy(
                            isLoading = false,
                            loginSucceeded = true,
                            needsProfileSetup = needsSetup,
                        )
                    }
                }

                is AppResult.Failure -> _state.update {
                    it.copy(isLoading = false, errorMessage = result.error.message)
                }
            }
        }
    }

    fun signUp() {
        val current = _state.value
        if (current.email.isBlank() || current.password.isBlank()) return

        if (current.password.length < 6) {
            _state.update { it.copy(errorMessage = "Password must be at least 6 characters.") }
            return
        }
        if (current.password != current.confirmPassword) {
            _state.update { it.copy(errorMessage = "Passwords do not match.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, errorMessage = null, successNotice = null) }
            when (val result = repository.signUp(current.email, current.password)) {
                is AppResult.Success -> {
                    // Check if signed in automatically or needs email verification
                    when (val me = profiles.getCurrentUser()) {
                        is AppResult.Success -> {
                            _state.update {
                                it.copy(
                                    isLoading = false,
                                    loginSucceeded = true,
                                    needsProfileSetup = true, // Fresh account always needs profile setup!
                                )
                            }
                        }
                        is AppResult.Failure -> {
                            // Account created; if confirmation required, guide user to login
                            _state.update {
                                it.copy(
                                    isLoading = false,
                                    isSignUpMode = false,
                                    successNotice = "Account created successfully! Please sign in.",
                                )
                            }
                        }
                    }
                }

                is AppResult.Failure -> _state.update {
                    it.copy(isLoading = false, errorMessage = result.error.message)
                }
            }
        }
    }

    /** Consumed once the nav host has acted on it, so recomposition can't re-fire it. */
    fun consumeLoginSucceeded() {
        _state.update { it.copy(loginSucceeded = false) }
    }
}
