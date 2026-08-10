package com.cretona.app.domain.model

enum class ProjectStatus {
    PENDING,
    GENERATING,
    COMPLETED,
    FAILED,
}

data class VideoProject(
    val id: String,
    val title: String,
    val prompt: String?,
    val videoUrl: String?,
    val status: ProjectStatus,
    val provider: String,
    val errorMessage: String?,
    val durationSeconds: Int?,
    val createdAt: String,
) {
    val isTerminal: Boolean
        get() = status == ProjectStatus.COMPLETED || status == ProjectStatus.FAILED
}

data class EnhancedPrompt(
    val text: String,
    val provider: String,
    val usedFallback: Boolean,
)
