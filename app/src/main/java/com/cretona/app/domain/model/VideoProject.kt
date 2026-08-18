package com.cretona.app.domain.model

import androidx.compose.runtime.Immutable

enum class ProjectStatus {
    PENDING,
    GENERATING,
    COMPLETED,
    FAILED,
}

@Immutable
data class VideoProject(
    val id: String,
    val title: String,
    val prompt: String?,
    val imageUrl: String? = null,
    val videoUrl: String?,
    val thumbnailUrl: String?,
    val status: ProjectStatus,
    val provider: String,
    val errorMessage: String?,
    val progressPercent: Int = 0,
    val stepMessage: String? = null,
    val durationSeconds: Int?,
    val aspectRatio: String,
    val createdAt: String,
) {
    val isTerminal: Boolean
        get() = status == ProjectStatus.COMPLETED || status == ProjectStatus.FAILED

    val thumbnailAspectRatio: Float
        get() = when (aspectRatio) {
            "9:16" -> 9f / 16f
            "1:1" -> 1f
            else -> 16f / 9f
        }
}

@Immutable
data class EnhancedPrompt(
    val text: String,
    val provider: String,
    val usedFallback: Boolean,
)
