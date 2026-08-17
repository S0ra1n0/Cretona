package com.cretona.app.data.remote

import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Backend contract. Endpoints are added as the API is built out; the wire
 * shapes are specified in docs/API_CONTRACT.md.
 */
interface CretonaApi {

    @GET("health")
    suspend fun health(): HealthResponse

    @GET("me")
    suspend fun getCurrentUser(): MeDto

    @retrofit2.http.PATCH("me")
    suspend fun updateProfile(@Body request: MeUpdateRequest): MeDto

    @POST("prompts/enhance")
    suspend fun enhancePrompt(@Body request: PromptEnhanceRequest): PromptEnhanceResponse

    @retrofit2.http.Multipart
    @POST("uploads")
    suspend fun uploadImage(
        @retrofit2.http.Part file: okhttp3.MultipartBody.Part,
    ): UploadResponseDto

    @POST("uploads/sign")
    suspend fun signUpload(
        @Body request: UploadSignRequestDto,
    ): UploadSignResponseDto

    @POST("projects")
    suspend fun createProject(
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body request: ProjectCreateRequest,
    ): ProjectDto


    @POST("projects/{id}/cancel")
    suspend fun cancelProject(@Path("id") id: String): ProjectCancelResponseDto

    @retrofit2.http.DELETE("projects/{id}")
    suspend fun deleteProject(@Path("id") id: String): retrofit2.Response<Unit>

    @GET("projects/{id}")
    suspend fun getProject(@Path("id") id: String): ProjectDto

    @GET("projects")
    suspend fun listProjects(): ProjectPageDto

    @GET("admin/stats")
    suspend fun getAdminStats(
        @retrofit2.http.Query("days") days: Int = 30,
    ): AdminStatsDto

    @GET("admin/users")
    suspend fun getAdminUsers(
        @retrofit2.http.Query("limit") limit: Int = 50,
        @retrofit2.http.Query("cursor") cursor: String? = null,
        @retrofit2.http.Query("q") query: String? = null,
        @retrofit2.http.Query("role") role: String? = null,
        @retrofit2.http.Query("isDisabled") isDisabled: Boolean? = null,
    ): AdminUserPageDto

    @retrofit2.http.PATCH("admin/users/{id}")
    suspend fun updateAdminUser(
        @Path("id") id: String,
        @Body request: AdminUserUpdateRequestDto,
    ): AdminUserDto

    @GET("admin/audit-logs")
    suspend fun getAdminAuditLogs(
        @retrofit2.http.Query("limit") limit: Int = 50,
        @retrofit2.http.Query("cursor") cursor: String? = null,
        @retrofit2.http.Query("action") action: String? = null,
        @retrofit2.http.Query("actorId") actorId: String? = null,
    ): AdminAuditLogPageDto

    @POST("admin/thumbnails/backfill")
    suspend fun backfillThumbnails(): BackfillResponseDto
}

@Serializable
data class HealthResponse(
    val status: String,
    val version: String? = null,
)

@Serializable
data class PromptEnhanceRequest(
    val prompt: String,
    val aspectRatio: String = "16:9",
)

@Serializable
data class PromptEnhanceResponse(
    val originalPrompt: String,
    val enhancedPrompt: String,
    val provider: String,
    val usedFallback: Boolean,
)

@Serializable
data class MeUpdateRequest(
    val username: String?,
    // Storage object key from POST /uploads, never a URL. Omitted entirely
    // when unchanged: sending an explicit null clears the existing avatar.
    val avatarPath: String? = null,
)

@Serializable
data class MeDto(
    val id: String,
    val email: String? = null,
    val username: String? = null,
    val avatarUrl: String? = null,
    val role: String,
    val isDisabled: Boolean,
    val createdAt: String,
    val quota: QuotaDto,
)

@Serializable
data class QuotaDto(
    val limit: Int,
    val used: Int,
    val remaining: Int,
    val resetsAt: String? = null,
)

@Serializable
data class ProjectCreateRequest(
    val prompt: String? = null,
    val imagePath: String? = null,
    val provider: String = "fake",
    val options: GenerationOptionsDto = GenerationOptionsDto(),
)

@Serializable
data class UploadResponseDto(
    val storagePath: String,
    val imageUrl: String? = null,
)

@Serializable
data class UploadSignRequestDto(
    val contentType: String,
    val sizeBytes: Long,
)

@Serializable
data class UploadSignResponseDto(
    val uploadUrl: String,
    val storagePath: String,
    val token: String,
    val expiresAt: String,
)

@Serializable
data class GenerationOptionsDto(
    val durationSeconds: Int = 5,
    val aspectRatio: String = "16:9",
    val stylePreset: String? = null,
    val cameraMotion: String? = null,
)

@Serializable
data class ProjectDto(
    val id: String,
    val title: String,
    val prompt: String? = null,
    val imageUrl: String? = null,
    val videoUrl: String? = null,
    val thumbnailUrl: String? = null,
    val status: String,
    val provider: String,
    val errorMessage: String? = null,
    val progressPercent: Int? = 0,
    val stepMessage: String? = null,
    val durationSeconds: Int? = null,
    val aspectRatio: String = "16:9",
    val createdAt: String,
    val updatedAt: String,
    val completedAt: String? = null,
)

@Serializable
data class ProjectCancelResponseDto(
    val cancelled: Boolean,
    val projectId: String,
    val quotaRefunded: Boolean,
)

@Serializable
data class ProjectPageDto(
    val items: List<ProjectDto>,
    val page: PageInfoDto,
)

@Serializable
data class PageInfoDto(
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
)

@Serializable
data class AdminStatsDto(
    val totals: AdminTotalsDto,
    val failureRate: Double = 0.0,
    val projectsByStatus: Map<String, Int> = emptyMap(),
    val projectsByProvider: Map<String, Int> = emptyMap(),
    val daily: List<DailyStatsDto> = emptyList(),
)

@Serializable
data class AdminTotalsDto(
    val users: Int = 0,
    val activeUsers: Int = 0,
    val projects: Int = 0,
)

@Serializable
data class DailyStatsDto(
    val date: String,
    val created: Int = 0,
    val completed: Int = 0,
    val failed: Int = 0,
)

@Serializable
data class AdminUserDto(
    val id: String,
    val email: String? = null,
    val username: String? = null,
    val role: String,
    val isDisabled: Boolean,
    val createdAt: String,
    val projectCount: Int = 0,
)

@Serializable
data class AdminUserPageDto(
    val items: List<AdminUserDto>,
    val page: PageInfoDto,
)

@Serializable
data class AdminUserUpdateRequestDto(
    val role: String? = null,
    val isDisabled: Boolean? = null,
)

@Serializable
data class AdminAuditLogDto(
    val id: String,
    val actorId: String,
    val action: String,
    val targetType: String,
    val targetId: String? = null,
    val createdAt: String,
)

@Serializable
data class AdminAuditLogPageDto(
    val items: List<AdminAuditLogDto>,
    val page: PageInfoDto,
)

@Serializable
data class BackfillResponseDto(
    val backfilled: Int,
    val processed: Int,
)

