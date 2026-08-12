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
    ): AppResult<VideoProject> {
        createCalls += 1
        return AppResult.Success(pending.copy(prompt = prompt))
    }

    override suspend fun getProject(id: String): AppResult<VideoProject> =
        AppResult.Success(completed)

    override suspend fun listProjects(): AppResult<List<VideoProject>> =
        AppResult.Success(if (createCalls == 0) emptyList() else listOf(completed))

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
