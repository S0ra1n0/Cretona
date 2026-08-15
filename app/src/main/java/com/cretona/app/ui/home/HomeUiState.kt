package com.cretona.app.ui.home

import android.net.Uri
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject

data class HomeUiState(
    val prompt: String = "",
    val account: UserProfile? = null,
    val isAccountLoading: Boolean = true,
    val accountErrorMessage: String? = null,
    val isEnhancing: Boolean = false,
    val isSubmitting: Boolean = false,
    val currentProject: VideoProject? = null,
    val projects: List<VideoProject> = emptyList(),
    val selectedProvider: String = "real",
    val enhancementNote: String? = null,
    val errorMessage: String? = null,
    val selectedImageUri: Uri? = null,
    val selectedImageBytes: ByteArray? = null,
    val selectedImageMimeType: String? = null,
    val selectedImageFileName: String? = null,
    val isUploadingImage: Boolean = false,
) {
    val isQuotaExhausted: Boolean
        get() = account?.quota?.remaining == 0

    val isImageToVideo: Boolean
        get() = selectedImageBytes != null
}
