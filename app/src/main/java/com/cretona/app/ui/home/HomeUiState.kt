package com.cretona.app.ui.home

import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.model.UserProfile

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
) {
    val isQuotaExhausted: Boolean
        get() = account?.quota?.remaining == 0
}
