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

    /**
     * Completes or edits the profile. [avatarPath] is the storage key returned
     * by [uploadImage]; null leaves the existing avatar untouched.
     */
    suspend fun updateProfile(
        username: String,
        avatarPath: String? = null,
    ): AppResult<UserProfile>

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
        aspectRatio: String = "16:9",
        stylePreset: String? = null,
        cameraMotion: String? = null,
    ): AppResult<VideoProject>


    suspend fun getProject(id: String): AppResult<VideoProject>

    suspend fun cancelProject(id: String): AppResult<Unit>

    suspend fun deleteProject(id: String): AppResult<Unit>

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

