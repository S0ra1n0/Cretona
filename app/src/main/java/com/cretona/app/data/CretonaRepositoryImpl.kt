package com.cretona.app.data

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.CretonaApi
import com.cretona.app.data.remote.MeDto
import com.cretona.app.data.remote.MeUpdateRequest
import com.cretona.app.data.remote.ProjectCreateRequest
import com.cretona.app.data.remote.ProjectDto
import com.cretona.app.data.remote.PromptEnhanceRequest
import com.cretona.app.data.remote.AdminAuditLogDto
import com.cretona.app.data.remote.AdminMetricsDto
import com.cretona.app.data.remote.AdminStatsDto
import com.cretona.app.data.remote.AdminUserDto
import com.cretona.app.data.remote.AdminUserUpdateRequestDto
import com.cretona.app.data.remote.BackfillResponseDto
import com.cretona.app.data.remote.DailyStatsDto
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminMetrics
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.DailyStats
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.GenerationQuota
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
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

    override suspend fun updateProfile(
        username: String,
        avatarPath: String?,
        gender: String,
        birthday: String,
    ): AppResult<UserProfile> = apiCall {
        api.updateProfile(
            MeUpdateRequest(
                username = username,
                avatarPath = avatarPath,
                gender = gender,
                birthday = birthday,
            ),
        ).toDomain()
    }

    override suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt> = apiCall {
        val response = api.enhancePrompt(PromptEnhanceRequest(prompt = prompt))
        EnhancedPrompt(
            text = response.enhancedPrompt,
            provider = response.provider,
            usedFallback = response.usedFallback,
        )
    }

    override suspend fun uploadImage(
        bytes: ByteArray,
        mimeType: String,
        fileName: String,
    ): AppResult<String> = apiCall {
        val mediaType = mimeType.toMediaTypeOrNull()
        val requestBody = bytes.toRequestBody(mediaType, 0, bytes.size)
        val part = MultipartBody.Part.createFormData("file", fileName, requestBody)
        val response = api.uploadImage(part)
        response.storagePath
    }

    override suspend fun createProject(
        prompt: String?,
        imagePath: String?,
        idempotencyKey: String,
        provider: String,
        aspectRatio: String,
        stylePreset: String?,
        cameraMotion: String?,
    ): AppResult<VideoProject> = apiCall {
        api.createProject(
            idempotencyKey = idempotencyKey,
            request = ProjectCreateRequest(
                prompt = prompt,
                imagePath = imagePath,
                provider = provider,
                options = com.cretona.app.data.remote.GenerationOptionsDto(
                    aspectRatio = aspectRatio,
                    stylePreset = stylePreset,
                    cameraMotion = cameraMotion,
                ),
            ),
        ).toDomain()
    }

    override suspend fun getProject(id: String): AppResult<VideoProject> = apiCall {
        api.getProject(id).toDomain()
    }

    override suspend fun cancelProject(id: String): AppResult<Unit> = apiCall {
        api.cancelProject(id).run {
            check(cancelled && projectId == id) {
                "Cancel response did not confirm project '$id'."
            }
        }
    }

    override suspend fun deleteProject(id: String): AppResult<Unit> = apiCall {
        api.deleteProject(id)
    }

    override suspend fun listProjects(): AppResult<List<VideoProject>> = apiCall {
        api.listProjects().items.map(ProjectDto::toDomain)
    }

    override suspend fun getAdminStats(days: Int): AppResult<AdminStats> = apiCall {
        api.getAdminStats(days).toDomain()
    }

    override suspend fun getAdminUsers(
        limit: Int,
        cursor: String?,
        query: String?,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<List<AdminUser>> = apiCall {
        api.getAdminUsers(
            limit = limit,
            cursor = cursor,
            query = query,
            role = role,
            isDisabled = isDisabled,
        ).items.map(AdminUserDto::toDomain)
    }

    override suspend fun updateAdminUser(
        id: String,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<AdminUser> = apiCall {
        api.updateAdminUser(
            id = id,
            request = AdminUserUpdateRequestDto(role = role, isDisabled = isDisabled),
        ).toDomain()
    }

    override suspend fun getAdminAuditLogs(
        limit: Int,
        cursor: String?,
        action: String?,
        actorId: String?,
    ): AppResult<List<AdminAuditLog>> = apiCall {
        api.getAdminAuditLogs(
            limit = limit,
            cursor = cursor,
            action = action,
            actorId = actorId,
        ).items.map(AdminAuditLogDto::toDomain)
    }

    override suspend fun backfillThumbnails(): AppResult<BackfillResult> = apiCall {
        val res = api.backfillThumbnails()
        BackfillResult(backfilled = res.backfilled, processed = res.processed)
    }

    override suspend fun checkHealth(): AppResult<HealthResponse> = apiCall {
        api.health()
    }

    override suspend fun getAdminMetrics(): AppResult<AdminMetrics> = apiCall {
        api.getAdminMetrics().toDomain()
    }

    private suspend fun <T> apiCall(block: suspend () -> T): AppResult<T> = try {
        AppResult.Success(block())
    } catch (cancellation: CancellationException) {
        // Must be rethrown, and must come before the catch-all below.
        // CancellationException is an Exception, so swallowing it turns a
        // deliberate cancel into a user-visible error and leaves the coroutine
        // running instead of unwinding.
        throw cancellation
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
    imageUrl = imageUrl,
    videoUrl = videoUrl,
    thumbnailUrl = thumbnailUrl,
    status = when (status) {
        "pending" -> ProjectStatus.PENDING
        "generating" -> ProjectStatus.GENERATING
        "completed" -> ProjectStatus.COMPLETED
        "failed" -> ProjectStatus.FAILED
        else -> ProjectStatus.FAILED
    },
    provider = provider,
    errorMessage = errorMessage ?: if (status in knownStatuses) null else "Unknown job status.",
    progressPercent = progressPercent ?: 0,
    stepMessage = stepMessage,
    durationSeconds = durationSeconds,
    aspectRatio = aspectRatio,
    createdAt = createdAt,
)

internal fun MeDto.toDomain(): UserProfile = UserProfile(
    id = id,
    email = email,
    username = username,
    avatarUrl = avatarUrl,
    gender = gender,
    birthday = birthday,
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

internal fun AdminStatsDto.toDomain(): AdminStats = AdminStats(
    totalUsers = totals.users,
    activeUsers = totals.activeUsers,
    totalProjects = totals.projects,
    failureRate = failureRate,
    projectsByStatus = projectsByStatus,
    projectsByProvider = projectsByProvider,
    daily = daily.map {
        DailyStats(
            date = it.date,
            created = it.created,
            completed = it.completed,
            failed = it.failed,
        )
    },
)

internal fun AdminUserDto.toDomain(): AdminUser = AdminUser(
    id = id,
    email = email,
    username = username,
    role = role,
    isDisabled = isDisabled,
    createdAt = createdAt,
    projectCount = projectCount,
)

internal fun AdminAuditLogDto.toDomain(): AdminAuditLog = AdminAuditLog(
    id = id,
    actorId = actorId,
    action = action,
    targetType = targetType,
    targetId = targetId,
    createdAt = createdAt,
)

internal fun AdminMetricsDto.toDomain(): AdminMetrics = AdminMetrics(
    uptimeSeconds = uptimeSeconds,
    activeJobs = activeJobs,
    completedJobs = completedJobs,
    failedJobs = failedJobs,
    memoryRssMb = memoryRssMb,
    databaseBackend = databaseBackend,
    databaseStatus = databaseStatus,
    storageBackend = storageBackend,
)

private val knownStatuses = setOf("pending", "generating", "completed", "failed")

/** The backend's error envelope: `{"error": {"code", "message"}, "requestId"}`. */
@Serializable
private data class ApiErrorEnvelope(val error: ApiErrorBody? = null)

@Serializable
private data class ApiErrorBody(val code: String? = null, val message: String? = null)

// Local to the mapper rather than injected: this only ever decodes the one
// shape above, and a failure to parse must never replace the real failure.
private val errorJson = Json { ignoreUnknownKeys = true; explicitNulls = false }

/**
 * The message the backend sent, or null when there is not a usable one.
 *
 * Reads the body at most once -- `errorBody().string()` consumes the stream.
 */
private fun HttpException.serverMessage(): String? = runCatching {
    response()?.errorBody()?.string()
        ?.takeIf { it.isNotBlank() }
        ?.let { errorJson.decodeFromString(ApiErrorEnvelope.serializer(), it).error?.message }
}.getOrNull()?.takeIf { it.isNotBlank() }

/**
 * Translates a failed call, preferring the backend's own wording.
 *
 * The envelope was previously discarded, so every 4xx the app does not
 * special-case surfaced as "Request failed with HTTP 409" -- which told the
 * account nothing about a username already being taken, or which field of a
 * profile save the server actually rejected.
 *
 * 5xx keeps the generic line on purpose: a server fault's message is an
 * internal detail, and the caller can do nothing with it either way.
 */
internal fun HttpException.toAppError(): AppError {
    val detail = serverMessage()
    return when (code()) {
        401 -> detail?.let(AppError::Unauthorized) ?: AppError.Unauthorized()
        403 -> detail?.let(AppError::Forbidden) ?: AppError.Forbidden()
        404 -> detail?.let(AppError::NotFound) ?: AppError.NotFound()
        in 500..599 -> AppError.Server(code(), "The server could not complete the request.")
        else -> AppError.Server(code(), detail ?: "Request failed with HTTP ${code()}.")
    }
}

