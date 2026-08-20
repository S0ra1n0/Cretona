package com.cretona.app.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.AuthRepository
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import javax.inject.Inject

enum class RestoredDestination { AUTH, PROFILE_SETUP, MAIN }

data class SessionRestoreUiState(
    val isLoading: Boolean = true,
    val destination: RestoredDestination? = null,
    val errorMessage: String? = null,
)

@HiltViewModel
class SessionRestoreViewModel @Inject constructor(
    private val auth: AuthRepository,
    private val profiles: CretonaRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(SessionRestoreUiState())
    val state = _state.asStateFlow()
    private var restoreJob: Job? = null

    init {
        restore()
    }

    fun restore() {
        if (restoreJob?.isActive == true) return

        restoreJob = viewModelScope.launch {
            _state.value = SessionRestoreUiState(isLoading = true)
            when (val restored = auth.restoreSession()) {
                is AppResult.Failure -> _state.value = SessionRestoreUiState(
                    isLoading = false,
                    errorMessage = restored.error.message,
                )
                is AppResult.Success -> {
                    if (!restored.data) {
                        _state.value = SessionRestoreUiState(
                            isLoading = false,
                            destination = RestoredDestination.AUTH,
                        )
                        return@launch
                    }
                    val destination = when (val profile = profiles.getCurrentUser()) {
                        is AppResult.Success -> if (profile.data.needsProfileSetup) {
                            RestoredDestination.PROFILE_SETUP
                        } else {
                            RestoredDestination.MAIN
                        }
                        // A valid restored session should not be destroyed by a
                        // transient FastAPI failure. Main already owns retry UI.
                        is AppResult.Failure -> RestoredDestination.MAIN
                    }
                    _state.value = SessionRestoreUiState(
                        isLoading = false,
                        destination = destination,
                    )
                }
            }
        }
    }
}
