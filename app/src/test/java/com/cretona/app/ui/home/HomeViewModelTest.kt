package com.cretona.app.ui.home

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.GenerationQuota
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `generate drives pending project to completed`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeRepository()
        val viewModel = HomeViewModel(repository)

        viewModel.onPromptChanged("A paper dragon over a lantern city")
        viewModel.generateVideo()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertEquals(ProjectStatus.COMPLETED, state.currentProject?.status)
        assertNotNull(state.currentProject?.videoUrl)
        assertFalse(state.isSubmitting)
        assertEquals(1, state.projects.size)
        assertEquals(2, repository.accountCalls)
    }

    @Test
    fun `enhancement exposes fallback evidence`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = HomeViewModel(FakeRepository())
        viewModel.onPromptChanged("cat astronaut")

        viewModel.enhancePrompt()
        advanceUntilIdle()

        assertEquals("Enhanced cat astronaut", viewModel.state.value.prompt)
        assertEquals(
            "Deterministic fallback (no live LLM)",
            viewModel.state.value.enhancementNote,
        )
    }

    @Test
    fun `blank prompt is rejected before repository call`() {
        val repository = FakeRepository()
        val viewModel = HomeViewModel(repository)

        viewModel.generateVideo()

        assertEquals("Enter a prompt before generating.", viewModel.state.value.errorMessage)
        assertEquals(0, repository.createCalls)
    }

    @Test
    fun `opening home loads current quota`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = HomeViewModel(FakeRepository(quotaRemaining = 7))

        advanceUntilIdle()

        assertEquals(7, viewModel.state.value.account?.quota?.remaining)
        assertFalse(viewModel.state.value.isAccountLoading)
    }

    @Test
    fun `confirmed exhausted quota blocks generation before repository call`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = FakeRepository(quotaRemaining = 0)
            val viewModel = HomeViewModel(repository)
            advanceUntilIdle()
            viewModel.onPromptChanged("A paper dragon over a lantern city")

            viewModel.generateVideo()
            advanceUntilIdle()

            assertEquals(0, repository.createCalls)
            assertEquals(
                "Generation quota is exhausted. Try again after it resets.",
                viewModel.state.value.errorMessage,
            )
        }

    @Test
    fun `quota failure is recoverable and does not block server-side verification`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = FakeRepository(accountFailure = true)
            val viewModel = HomeViewModel(repository)
            advanceUntilIdle()

            assertFalse(viewModel.state.value.isAccountLoading)
            assertEquals(
                "Cannot load quota.",
                viewModel.state.value.accountErrorMessage,
            )

            viewModel.onPromptChanged("A recoverable request")
            viewModel.generateVideo()
            advanceUntilIdle()

            assertEquals(1, repository.createCalls)
        }

    @Test
    fun `provider selection updates state`() {
        val viewModel = HomeViewModel(FakeRepository())
        assertEquals("real", viewModel.state.value.selectedProvider)

        viewModel.onProviderSelected("wan21")
        assertEquals("wan21", viewModel.state.value.selectedProvider)
    }
}

private class FakeRepository(
    private val quotaRemaining: Int = 7,
    private val accountFailure: Boolean = false,
) : CretonaRepository {
    private val pending = project(ProjectStatus.PENDING)
    private val completed = project(
        status = ProjectStatus.COMPLETED,
        videoUrl = "http://example.test/media/demo-output.mp4",
    )
    var createCalls = 0
    var accountCalls = 0

    override suspend fun getCurrentUser(): AppResult<UserProfile> {
        accountCalls += 1
        if (accountFailure) return AppResult.Failure(AppError.Network("Cannot load quota."))
        return AppResult.Success(
            UserProfile(
                id = "user-1",
                email = "student@example.com",
                username = "bruce",
                role = "user",
                isDisabled = false,
                createdAt = "2026-08-01T00:00:00Z",
                quota = GenerationQuota(
                    limit = 10,
                    used = 10 - quotaRemaining,
                    remaining = quotaRemaining,
                    resetsAt = "2026-08-13T12:00:00Z",
                ),
            ),
        )
    }

    override suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt> =
        AppResult.Success(
            EnhancedPrompt(
                text = "Enhanced $prompt",
                provider = "deterministic",
                usedFallback = true,
            ),
        )

    override suspend fun createProject(
        prompt: String,
        idempotencyKey: String,
        provider: String,
    ): AppResult<VideoProject> {
        createCalls += 1
        return AppResult.Success(pending.copy(prompt = prompt, provider = provider))
    }

    override suspend fun getProject(id: String): AppResult<VideoProject> =
        AppResult.Success(completed)

    override suspend fun listProjects(): AppResult<List<VideoProject>> =
        AppResult.Success(if (createCalls == 0) emptyList() else listOf(completed))

    override suspend fun getAdminStats(days: Int): AppResult<com.cretona.app.domain.model.AdminStats> =
        AppResult.Success(
            com.cretona.app.domain.model.AdminStats(
                totalUsers = 10,
                activeUsers = 8,
                totalProjects = 25,
                failureRate = 0.1,
                projectsByStatus = mapOf("completed" to 20, "failed" to 5),
                projectsByProvider = mapOf("fake" to 20, "real" to 5),
                daily = emptyList(),
            ),
        )

    override suspend fun getAdminUsers(
        limit: Int,
        cursor: String?,
        query: String?,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<List<com.cretona.app.domain.model.AdminUser>> = AppResult.Success(emptyList())

    override suspend fun updateAdminUser(
        id: String,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<com.cretona.app.domain.model.AdminUser> = AppResult.Success(
        com.cretona.app.domain.model.AdminUser(
            id = id,
            email = "user@example.com",
            username = "user",
            role = role ?: "user",
            isDisabled = isDisabled ?: false,
            createdAt = "2026-08-01T00:00:00Z",
            projectCount = 3,
        ),
    )

    override suspend fun getAdminAuditLogs(
        limit: Int,
        cursor: String?,
        action: String?,
        actorId: String?,
    ): AppResult<List<com.cretona.app.domain.model.AdminAuditLog>> = AppResult.Success(emptyList())

    override suspend fun backfillThumbnails(): AppResult<com.cretona.app.domain.model.BackfillResult> =
        AppResult.Success(com.cretona.app.domain.model.BackfillResult(backfilled = 2, processed = 5))

    override suspend fun checkHealth(): AppResult<com.cretona.app.data.remote.HealthResponse> =
        AppResult.Success(com.cretona.app.data.remote.HealthResponse(status = "healthy", version = "1.0.0"))


    private companion object {
        fun project(
            status: ProjectStatus,
            videoUrl: String? = null,
        ) = VideoProject(
            id = "project-1",
            title = "Paper dragon",
            prompt = "A paper dragon",
            videoUrl = videoUrl,
            thumbnailUrl = null,
            status = status,
            provider = "fake",
            errorMessage = null,
            durationSeconds = 5,
            aspectRatio = "16:9",
            createdAt = "2026-08-10T00:00:00Z",
        )
    }
}
