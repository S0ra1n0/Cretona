package com.cretona.app.domain.repository

import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject

interface CretonaRepository {
    suspend fun getCurrentUser(): AppResult<UserProfile>

    suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt>

    suspend fun createProject(prompt: String, idempotencyKey: String): AppResult<VideoProject>

    suspend fun getProject(id: String): AppResult<VideoProject>

    suspend fun listProjects(): AppResult<List<VideoProject>>
}
