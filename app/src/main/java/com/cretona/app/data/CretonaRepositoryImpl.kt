package com.cretona.app.data

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.CretonaApi
import com.cretona.app.data.remote.MeDto
import com.cretona.app.data.remote.ProjectCreateRequest
import com.cretona.app.data.remote.ProjectDto
import com.cretona.app.data.remote.PromptEnhanceRequest
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.GenerationQuota
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import retrofit2.HttpException
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CretonaRepositoryImpl @Inject constructor(
    private val api: CretonaApi,
) : CretonaRepository {
    override suspend fun getCurrentUser(): AppResult<UserProfile> = apiCall {
        api.getCurrentUser().toDomain()
    }

    override suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt> = apiCall {
        val response = api.enhancePrompt(PromptEnhanceRequest(prompt = prompt))
        EnhancedPrompt(
            text = response.enhancedPrompt,
            provider = response.provider,
            usedFallback = response.usedFallback,
        )
    }

    override suspend fun createProject(
        prompt: String,
        idempotencyKey: String,
    ): AppResult<VideoProject> = apiCall {
        api.createProject(
            idempotencyKey = idempotencyKey,
            request = ProjectCreateRequest(prompt = prompt),
        ).toDomain()
    }

    override suspend fun getProject(id: String): AppResult<VideoProject> = apiCall {
        api.getProject(id).toDomain()
    }

    override suspend fun listProjects(): AppResult<List<VideoProject>> = apiCall {
        api.listProjects().items.map(ProjectDto::toDomain)
    }

    private suspend fun <T> apiCall(block: suspend () -> T): AppResult<T> = try {
        AppResult.Success(block())
    } catch (error: HttpException) {
        AppResult.Failure(error.toAppError())
    } catch (_: IOException) {
        AppResult.Failure(AppError.Network("Cannot reach the FastAPI server."))
    } catch (_: Exception) {
        AppResult.Failure(AppError.Unknown())
    }
}

internal fun ProjectDto.toDomain(): VideoProject = VideoProject(
    id = id,
    title = title,
    prompt = prompt,
    videoUrl = videoUrl,
    status = when (status) {
        "pending" -> ProjectStatus.PENDING
        "generating" -> ProjectStatus.GENERATING
        "completed" -> ProjectStatus.COMPLETED
        "failed" -> ProjectStatus.FAILED
        else -> ProjectStatus.FAILED
    },
    provider = provider,
    errorMessage = errorMessage ?: if (status in knownStatuses) null else "Unknown job status.",
    durationSeconds = durationSeconds,
    createdAt = createdAt,
)

internal fun MeDto.toDomain(): UserProfile = UserProfile(
    id = id,
    email = email,
    username = username,
    role = role,
    isDisabled = isDisabled,
    createdAt = createdAt,
    quota = GenerationQuota(
        limit = quota.limit,
        used = quota.used,
        remaining = quota.remaining,
        resetsAt = quota.resetsAt,
    ),
)

private val knownStatuses = setOf("pending", "generating", "completed", "failed")

private fun HttpException.toAppError(): AppError = when (code()) {
    401 -> AppError.Unauthorized()
    403 -> AppError.Forbidden()
    404 -> AppError.NotFound()
    in 500..599 -> AppError.Server(code(), "The server could not complete the request.")
    else -> AppError.Server(code(), "Request failed with HTTP ${code()}.")
}
