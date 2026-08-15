package com.cretona.app.domain.repository

import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject

interface CretonaRepository {
    suspend fun getCurrentUser(): AppResult<UserProfile>

    suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt>

    suspend fun uploadImage(
        bytes: ByteArray,
        mimeType: String,
        fileName: String,
    ): AppResult<String>

    suspend fun createProject(
        prompt: String?,
        imagePath: String? = null,
        idempotencyKey: String,
        provider: String = "fake",
    ): AppResult<VideoProject>


    suspend fun getProject(id: String): AppResult<VideoProject>

    suspend fun listProjects(): AppResult<List<VideoProject>>

    suspend fun getAdminStats(days: Int = 30): AppResult<AdminStats>

    suspend fun getAdminUsers(
        limit: Int = 50,
        cursor: String? = null,
        query: String? = null,
        role: String? = null,
        isDisabled: Boolean? = null,
    ): AppResult<List<AdminUser>>

    suspend fun updateAdminUser(
        id: String,
        role: String? = null,
        isDisabled: Boolean? = null,
    ): AppResult<AdminUser>

    suspend fun getAdminAuditLogs(
        limit: Int = 50,
        cursor: String? = null,
        action: String? = null,
        actorId: String? = null,
    ): AppResult<List<AdminAuditLog>>

    suspend fun backfillThumbnails(): AppResult<BackfillResult>

    suspend fun checkHealth(): AppResult<HealthResponse>
}

