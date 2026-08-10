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

    @POST("prompts/enhance")
    suspend fun enhancePrompt(@Body request: PromptEnhanceRequest): PromptEnhanceResponse

    @POST("projects")
    suspend fun createProject(
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body request: ProjectCreateRequest,
    ): ProjectDto

    @GET("projects/{id}")
    suspend fun getProject(@Path("id") id: String): ProjectDto

    @GET("projects")
    suspend fun listProjects(): ProjectPageDto
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
data class ProjectCreateRequest(
    val prompt: String,
    val provider: String = "fake",
    val options: GenerationOptionsDto = GenerationOptionsDto(),
)

@Serializable
data class GenerationOptionsDto(
    val durationSeconds: Int = 5,
    val aspectRatio: String = "16:9",
)

@Serializable
data class ProjectDto(
    val id: String,
    val title: String,
    val prompt: String? = null,
    val videoUrl: String? = null,
    val status: String,
    val provider: String,
    val errorMessage: String? = null,
    val durationSeconds: Int? = null,
    val aspectRatio: String = "16:9",
    val createdAt: String,
    val updatedAt: String,
    val completedAt: String? = null,
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
