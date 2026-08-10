package com.cretona.app.ui.home

import com.cretona.app.domain.model.VideoProject

data class HomeUiState(
    val prompt: String = "",
    val isEnhancing: Boolean = false,
    val isSubmitting: Boolean = false,
    val currentProject: VideoProject? = null,
    val projects: List<VideoProject> = emptyList(),
    val enhancementNote: String? = null,
    val errorMessage: String? = null,
)
