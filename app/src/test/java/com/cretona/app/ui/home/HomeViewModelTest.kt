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
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
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
        assertEquals("cat astronaut", viewModel.state.value.previousPrompt)
        assertEquals(
            "Deterministic fallback (no live LLM)",
            viewModel.state.value.enhancementNote,
        )
    }

    @Test
    fun `revertPrompt restores previous prompt before enhancement`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = HomeViewModel(FakeRepository())
        viewModel.onPromptChanged("cat astronaut")

        viewModel.enhancePrompt()
        advanceUntilIdle()

        assertEquals("Enhanced cat astronaut", viewModel.state.value.prompt)
        assertEquals("cat astronaut", viewModel.state.value.previousPrompt)

        viewModel.revertPrompt()
        assertEquals("cat astronaut", viewModel.state.value.prompt)
        org.junit.Assert.assertNull(viewModel.state.value.previousPrompt)
    }

    @Test
    fun `onSelectPromptIdea updates prompt`() {
        val viewModel = HomeViewModel(FakeRepository())
        viewModel.onSelectPromptIdea("🐉 Rồng bay trên núi")
        assertEquals("🐉 Rồng bay trên núi", viewModel.state.value.prompt)
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
        assertEquals("mock", viewModel.state.value.selectedProvider)

        viewModel.onProviderSelected("cloud")
        assertEquals("cloud", viewModel.state.value.selectedProvider)

        viewModel.onProviderSelected("local")
        assertEquals("local", viewModel.state.value.selectedProvider)
    }

    @Test
    fun `style preset and camera motion selection toggles state`() {
        val viewModel = HomeViewModel(FakeRepository())
        org.junit.Assert.assertNull(viewModel.state.value.selectedStylePreset)
        org.junit.Assert.assertNull(viewModel.state.value.selectedCameraMotion)

        viewModel.onStylePresetSelected("anime")
        assertEquals("anime", viewModel.state.value.selectedStylePreset)
        viewModel.onStylePresetSelected("anime") // toggle off
        org.junit.Assert.assertNull(viewModel.state.value.selectedStylePreset)

        viewModel.onCameraMotionSelected("dolly_zoom")
        assertEquals("dolly_zoom", viewModel.state.value.selectedCameraMotion)
        viewModel.onCameraMotionSelected("dolly_zoom") // toggle off
        org.junit.Assert.assertNull(viewModel.state.value.selectedCameraMotion)
    }

    @Test
    fun `aspect ratio selection updates state`() {
        val viewModel = HomeViewModel(FakeRepository())
        assertEquals("16:9", viewModel.state.value.selectedAspectRatio)

        viewModel.onAspectRatioSelected("9:16")
        assertEquals("9:16", viewModel.state.value.selectedAspectRatio)
    }

    @Test
    fun `remixProject pre-fills prompt, ratio and provider`() {
        val viewModel = HomeViewModel(FakeRepository())
        val completedProject = VideoProject(
            id = "proj-1",
            title = "A cyberpunk city",
            prompt = "A cyberpunk city in rain",
            imageUrl = null,
            videoUrl = "http://example.test/video.mp4",
            thumbnailUrl = null,
            status = com.cretona.app.domain.model.ProjectStatus.COMPLETED,
            provider = "wan21",
            errorMessage = null,
            progressPercent = 100,
            stepMessage = "Complete",
            durationSeconds = 5,
            aspectRatio = "9:16",
            createdAt = "2026-08-15T00:00:00Z",
        )

        viewModel.remixProject(completedProject)

        val state = viewModel.state.value
        assertEquals("A cyberpunk city in rain", state.prompt)
        assertEquals("9:16", state.selectedAspectRatio)
        assertEquals("wan21", state.selectedProvider)
        assertEquals("Remixing: A cyberpunk city", state.enhancementNote)
    }

    @Test
    fun `generate passes aspect ratio, style preset and camera motion to repository`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = FakeRepository()
            val viewModel = HomeViewModel(repository)

            viewModel.onPromptChanged("A majestic dragon")
            viewModel.onAspectRatioSelected("9:16")
            viewModel.onStylePresetSelected("anime")
            viewModel.onCameraMotionSelected("orbit")

            viewModel.generateVideo()
            advanceUntilIdle()

            assertEquals(1, repository.createCalls)
            assertEquals("9:16", repository.lastAspectRatio)
            assertEquals("anime", repository.lastStylePreset)
            assertEquals("orbit", repository.lastCameraMotion)
        }

    @Test
    fun `selecting and clearing image updates state`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = HomeViewModel(FakeRepository()).apply {
            ioDispatcher = mainDispatcherRule.dispatcher
        }

        viewModel.onImageSelected(
            uri = null,
            bytes = byteArrayOf(1, 2, 3),
            mimeType = "image/png",
            fileName = "sample.png",
        )
        advanceUntilIdle() // wait for async compression coroutine

        val stateWithImage = viewModel.state.value
        assertEquals("image/png", stateWithImage.selectedImageMimeType)
        assertEquals("sample.png", stateWithImage.selectedImageFileName)
        org.junit.Assert.assertTrue(stateWithImage.isImageToVideo)

        viewModel.onImageCleared()
        val stateAfterClear = viewModel.state.value
        org.junit.Assert.assertNull(stateAfterClear.selectedImageUri)
        org.junit.Assert.assertNull(stateAfterClear.selectedImageBytes)
        org.junit.Assert.assertFalse(stateAfterClear.isImageToVideo)
    }

    @Test
    fun `generate with image uploads image and creates image-to-video project`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeRepository()
        val viewModel = HomeViewModel(repository).apply {
            ioDispatcher = mainDispatcherRule.dispatcher
        }

        viewModel.onImageSelected(
            uri = null,
            bytes = byteArrayOf(10, 20, 30),
            mimeType = "image/jpeg",
            fileName = "portrait.jpg",
        )
        advanceUntilIdle() // wait for async compression coroutine
        viewModel.onPromptChanged("Make the portrait smile and wave")
        viewModel.generateVideo()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertEquals(1, repository.uploadCalls)
        assertEquals(1, repository.createCalls)
        assertEquals("dev-user/sample.jpg", repository.lastCreatedImagePath)
        org.junit.Assert.assertNull(state.selectedImageUri)
        org.junit.Assert.assertFalse(state.isSubmitting)
    }

    @Test
    fun cancelCurrentProject_cancels_and_refreshes() = runTest {
        val repository = FakeRepository()
        val viewModel = HomeViewModel(repository)

        viewModel.onPromptChanged("Slow motion fireworks")
        viewModel.generateVideo()
        // Advance just enough for createProject to finish, but NOT the 5 000 ms poll delay
        advanceTimeBy(100)

        // currentProject is now the pending project from createProject, not yet terminal
        viewModel.cancelCurrentProject()
        advanceUntilIdle()

        assertEquals(1, repository.cancelCalls)
    }

    @Test
    fun deleteProject_calls_repository_and_refreshes() = runTest {
        val repository = FakeRepository()
        val viewModel = HomeViewModel(repository)

        viewModel.deleteProject("test-proj-id")
        advanceUntilIdle()

        assertEquals(1, repository.deleteCalls)
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
    var uploadCalls = 0
    var cancelCalls = 0
    var deleteCalls = 0
    var lastCreatedImagePath: String? = null
    var lastAspectRatio: String? = null
    var lastStylePreset: String? = null
    var lastCameraMotion: String? = null

    override suspend fun updateProfile(
        username: String,
        avatarPath: String?,
    ): AppResult<UserProfile> = AppResult.Failure(AppError.Unknown("not used in this test"))

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

    override suspend fun uploadImage(
        bytes: ByteArray,
        mimeType: String,
        fileName: String,
    ): AppResult<String> {
        uploadCalls += 1
        return AppResult.Success("dev-user/sample.jpg")
    }

    override suspend fun createProject(
        prompt: String?,
        imagePath: String?,
        idempotencyKey: String,
        provider: String,
        aspectRatio: String,
        stylePreset: String?,
        cameraMotion: String?,
    ): AppResult<VideoProject> {
        createCalls += 1
        lastCreatedImagePath = imagePath
        lastAspectRatio = aspectRatio
        lastStylePreset = stylePreset
        lastCameraMotion = cameraMotion
        return AppResult.Success(
            pending.copy(
                prompt = prompt,
                provider = provider,
                aspectRatio = aspectRatio,
                imageUrl = imagePath?.let { "http://example.test/media/$it" },
            ),
        )
    }


    override suspend fun getProject(id: String): AppResult<VideoProject> =
        AppResult.Success(completed)

    override suspend fun cancelProject(id: String): AppResult<Unit> {
        cancelCalls += 1
        return AppResult.Success(Unit)
    }

    override suspend fun deleteProject(id: String): AppResult<Unit> {
        deleteCalls += 1
        return AppResult.Success(Unit)
    }

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

    override suspend fun getAdminMetrics(): AppResult<com.cretona.app.domain.model.AdminMetrics> =
        AppResult.Success(
            com.cretona.app.domain.model.AdminMetrics(
                uptimeSeconds = 100f,
                activeJobs = 0,
                completedJobs = 5,
                failedJobs = 0,
                memoryRssMb = 30f,
                databaseBackend = "sqlite",
                databaseStatus = "healthy",
                storageBackend = "local",
            ),
        )


    private companion object {
        fun project(
            status: ProjectStatus,
            videoUrl: String? = null,
            imageUrl: String? = null,
        ) = VideoProject(
            id = "project-1",
            title = "Paper dragon",
            prompt = "A paper dragon",
            imageUrl = imageUrl,
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
