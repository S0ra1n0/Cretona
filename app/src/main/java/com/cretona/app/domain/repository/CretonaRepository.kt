package com.cretona.app.domain.repository

import com.cretona.app.core.result.AppResult
import com.cretona.app.core.result.AppError
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminCreditAdjustment
import com.cretona.app.domain.model.AdminCreditTransaction
import com.cretona.app.domain.model.AdminEvent
import com.cretona.app.domain.model.AdminEventDraft
import com.cretona.app.domain.model.AdminMetrics
import com.cretona.app.domain.model.AdminPackage
import com.cretona.app.domain.model.AdminPackageDraft
import com.cretona.app.domain.model.AdminSettings
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.CursorPage
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject

interface CretonaRepository {
    suspend fun getCurrentUser(): AppResult<UserProfile>

    /**
     * Completes or edits the profile. [avatarPath] is the storage key returned
     * by [uploadImage]; null leaves the existing avatar untouched.
     *
     * [gender] and [birthday] are optional details: an empty string clears
     * whatever is stored, which is how a value chosen once can be taken back.
     */
    suspend fun updateProfile(
        username: String,
        avatarPath: String? = null,
        gender: String = "",
        birthday: String = "",
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

    suspend fun listProjects(
        limit: Int = 20,
        cursor: String? = null,
    ): AppResult<CursorPage<VideoProject>>

    suspend fun getAdminStats(days: Int = 30): AppResult<AdminStats>

    suspend fun getAdminUsers(
        limit: Int = 50,
        cursor: String? = null,
        query: String? = null,
        role: String? = null,
        isDisabled: Boolean? = null,
    ): AppResult<CursorPage<AdminUser>>

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
    ): AppResult<CursorPage<AdminAuditLog>>

    suspend fun backfillThumbnails(): AppResult<BackfillResult>

    suspend fun checkHealth(): AppResult<HealthResponse>

    suspend fun getAdminMetrics(): AppResult<AdminMetrics>

    suspend fun getAdminProjects(
        status: String? = null,
        userId: String? = null,
        limit: Int = 20,
        cursor: String? = null,
    ): AppResult<CursorPage<VideoProject>> = unsupportedAdminCall()

    suspend fun adjustAdminCredits(
        userId: String,
        delta: Int,
        note: String,
    ): AppResult<AdminCreditAdjustment> = unsupportedAdminCall()

    suspend fun getAdminCreditTransactions(
        userId: String? = null,
        reason: String? = null,
        limit: Int = 20,
        cursor: String? = null,
    ): AppResult<CursorPage<AdminCreditTransaction>> = unsupportedAdminCall()

    suspend fun getAdminSettings(): AppResult<AdminSettings> = unsupportedAdminCall()
    suspend fun updateAdminSettings(generationCostCredits: Int): AppResult<AdminSettings> = unsupportedAdminCall()
    suspend fun getAdminPackages(): AppResult<List<AdminPackage>> = unsupportedAdminCall()
    suspend fun createAdminPackage(draft: AdminPackageDraft): AppResult<AdminPackage> = unsupportedAdminCall()
    suspend fun updateAdminPackage(id: String, draft: AdminPackageDraft): AppResult<AdminPackage> = unsupportedAdminCall()
    suspend fun getAdminEvents(): AppResult<List<AdminEvent>> = unsupportedAdminCall()
    suspend fun createAdminEvent(draft: AdminEventDraft): AppResult<AdminEvent> = unsupportedAdminCall()
    suspend fun updateAdminEvent(id: String, draft: AdminEventDraft): AppResult<AdminEvent> = unsupportedAdminCall()
}

private fun <T> unsupportedAdminCall(): AppResult<T> =
    AppResult.Failure(AppError.Unknown("This repository does not implement admin commerce."))

