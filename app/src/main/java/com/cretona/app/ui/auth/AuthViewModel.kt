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
        _state.update { it.copy(email = value, errorMessage = null) }
    }

    fun onPasswordChanged(value: String) {
        _state.update { it.copy(password = value, errorMessage = null) }
    }

    fun login() {
        val current = _state.value
        if (!current.canSubmit) return

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, errorMessage = null) }
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

    /** Consumed once the nav host has acted on it, so recomposition can't re-fire it. */
    fun consumeLoginSucceeded() {
        _state.update { it.copy(loginSucceeded = false) }
    }
}
