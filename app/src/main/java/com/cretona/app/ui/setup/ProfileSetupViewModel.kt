package com.cretona.app.ui.setup

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ProfileSetupViewModel @Inject constructor(
    private val repository: CretonaRepository,
) : ViewModel() {
    var ioDispatcher: CoroutineDispatcher = Dispatchers.IO

    private val _state = MutableStateFlow(ProfileSetupUiState())
    val state: StateFlow<ProfileSetupUiState> = _state.asStateFlow()

    // Held until submit so a picked-then-changed avatar is only uploaded once,
    // and never at all if the user backs out.
    private var pendingAvatar: PendingAvatar? = null

    private data class PendingAvatar(
        val bytes: ByteArray,
        val mimeType: String,
        val fileName: String,
    )

    private var prefilled = false

    /**
     * Seeds the form from the account being edited.
     *
     * Reads the profile here rather than taking it as a navigation argument:
     * the avatar is a signed URL that would be unwieldy and short-lived in a
     * route, and fetching means the form always opens on current values.
     *
     * Guarded so recomposition cannot overwrite what the user has typed.
     */
    fun startEdit() {
        if (prefilled) return
        prefilled = true
        viewModelScope.launch {
            when (val result = repository.getCurrentUser()) {
                is AppResult.Success -> _state.update {
                    it.copy(
                        username = result.data.username.orEmpty(),
                        // Empty for a detail never answered, so the form opens
                        // with nothing selected rather than a default the
                        // account did not choose.
                        gender = result.data.gender.orEmpty(),
                        birthday = result.data.birthday.orEmpty(),
                        existingAvatarUrl = result.data.avatarUrl,
                    )
                }
                // An empty form is still usable; the save will report any real
                // problem. Blocking the screen on this read would be worse.
                is AppResult.Failure -> Unit
            }
        }
    }

    fun onUsernameChanged(value: String) {
        _state.update { it.copy(username = value, errorMessage = null) }
    }

    /**
     * Selects a gender, or clears it by picking the one already selected.
     *
     * Re-tapping is the only way back to "prefer not to say" once an answer
     * has been given; a form with no clear affordance would trap the account
     * in whichever option it first touched.
     */
    fun onGenderSelected(option: GenderOption) {
        _state.update {
            val next = if (it.selectedGender == option) "" else option.stored
            it.copy(gender = next, errorMessage = null)
        }
    }

    fun onBirthdayChanged(value: String) {
        _state.update { it.copy(birthday = value.trim(), errorMessage = null) }
    }

    fun onBirthdayCleared() {
        _state.update { it.copy(birthday = "", errorMessage = null) }
    }

    fun onDatePickerRequested() {
        _state.update { it.copy(showDatePicker = true) }
    }

    fun onDatePickerDismissed() {
        _state.update { it.copy(showDatePicker = false) }
    }

    /** Accepts the picker's choice, already formatted as an ISO date. */
    fun onBirthdayPicked(isoDate: String) {
        _state.update {
            it.copy(birthday = isoDate, showDatePicker = false, errorMessage = null)
        }
    }

    fun onAvatarSelected(uri: Uri, bytes: ByteArray, mimeType: String, fileName: String) {
        pendingAvatar = PendingAvatar(bytes, mimeType, fileName)
        _state.update { it.copy(avatarUri = uri, errorMessage = null) }
    }

    fun onAvatarCleared() {
        pendingAvatar = null
        // Clears the existing picture too, so "Remove" means removed rather
        // than "discard the new pick and silently keep the old one".
        _state.update { it.copy(avatarUri = null, existingAvatarUrl = null) }
    }

    fun submit() {
        val current = _state.value
        if (!current.canSubmit) return

        viewModelScope.launch {
            _state.update { it.copy(isSubmitting = true, errorMessage = null) }

            // Upload first: the profile write stores the object key the upload
            // returns, so a failed upload must not leave a username saved
            // against an avatar that does not exist.
            var avatarPath: String? = null
            val avatar = pendingAvatar
            if (avatar != null) {
                when (val upload = repository.uploadImage(
                    bytes = avatar.bytes,
                    mimeType = avatar.mimeType,
                    fileName = avatar.fileName,
                )) {
                    is AppResult.Success -> avatarPath = upload.data
                    is AppResult.Failure -> {
                        _state.update {
                            it.copy(
                                isSubmitting = false,
                                errorMessage = "Could not upload the picture: ${upload.error.message}",
                            )
                        }
                        return@launch
                    }
                }
            }

            // Both details are sent on every save, empty included: empty is
            // how a value chosen before is taken back, and omitting the field
            // would instead mean "leave whatever is stored".
            when (
                val result = repository.updateProfile(
                    username = current.username,
                    avatarPath = avatarPath,
                    gender = current.gender,
                    birthday = current.birthday,
                )
            ) {
                is AppResult.Success -> _state.update {
                    it.copy(isSubmitting = false, isComplete = true)
                }

                is AppResult.Failure -> _state.update {
                    it.copy(isSubmitting = false, errorMessage = result.error.message)
                }
            }
        }
    }

    /** Consumed once navigation has acted on it, so it cannot re-fire. */
    fun consumeCompletion() {
        _state.update { it.copy(isComplete = false) }
    }
}
