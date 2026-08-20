package com.cretona.app.data

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.CretonaApi
import com.cretona.app.data.remote.ProjectCancelResponseDto
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class CretonaRepositoryMutationTest {
    private val api = mockk<CretonaApi>()
    private val repository = CretonaRepositoryImpl(api)

    @Test
    fun `cancel succeeds only when the response confirms the requested project`() = runTest {
        coEvery { api.cancelProject("project-1") } returns ProjectCancelResponseDto(
            cancelled = true,
            projectId = "project-1",
            quotaRefunded = true,
        )

        assertEquals(AppResult.Success(Unit), repository.cancelProject("project-1"))
        coVerify(exactly = 1) { api.cancelProject("project-1") }
    }

    @Test
    fun `cancel rejects a mismatched response instead of reporting success`() = runTest {
        coEvery { api.cancelProject("project-1") } returns ProjectCancelResponseDto(
            cancelled = true,
            projectId = "different-project",
            quotaRefunded = true,
        )

        val result = repository.cancelProject("project-1")

        assertTrue(result is AppResult.Failure && result.error is AppError.Unknown)
    }

    @Test
    fun `delete returns success after a successful empty response`() = runTest {
        coEvery { api.deleteProject("project-1") } returns Unit

        assertEquals(AppResult.Success(Unit), repository.deleteProject("project-1"))
        coVerify(exactly = 1) { api.deleteProject("project-1") }
    }

    @Test
    fun `delete maps an HTTP failure instead of reporting success`() = runTest {
        val body = """{"error":{"code":"CONFLICT","message":"A generating project cannot be deleted."}}"""
            .toResponseBody("application/json".toMediaType())
        coEvery { api.deleteProject("project-1") } throws HttpException(
            Response.error<Unit>(409, body),
        )

        val result = repository.deleteProject("project-1")

        assertTrue(result is AppResult.Failure)
        assertEquals(
            AppError.Server(409, "A generating project cannot be deleted."),
            (result as AppResult.Failure).error,
        )
    }
}
