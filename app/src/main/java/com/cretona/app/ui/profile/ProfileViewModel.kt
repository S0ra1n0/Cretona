package com.cretona.app.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {
    private val _signOutState = MutableStateFlow(ProfileSignOutState())
    val signOutState = _signOutState.asStateFlow()

    fun signOut(onSignedOut: () -> Unit) {
        if (_signOutState.value.isSigningOut) return
        viewModelScope.launch {
            _signOutState.update { it.copy(isSigningOut = true, errorMessage = null) }
            when (val result = auth.signOut()) {
                is AppResult.Success -> {
                    _signOutState.value = ProfileSignOutState()
                    onSignedOut()
                }
                is AppResult.Failure -> _signOutState.value = ProfileSignOutState(
                    errorMessage = result.error.message,
                )
            }
        }
    }
}

data class ProfileSignOutState(
    val isSigningOut: Boolean = false,
    val errorMessage: String? = null,
)
