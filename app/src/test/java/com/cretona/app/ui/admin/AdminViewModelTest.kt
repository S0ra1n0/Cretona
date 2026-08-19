package com.cretona.app.ui.admin

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminMetrics
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import com.cretona.app.ui.home.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AdminViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `init loads platform stats successfully`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isLoadingStats)
        assertNotNull(state.stats)
        assertEquals(10, state.stats?.totalUsers)
        assertEquals(25, state.stats?.totalProjects)
    }

    @Test
    fun `selecting users tab loads users list`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        advanceUntilIdle()

        viewModel.selectTab(AdminTab.USERS)
        advanceUntilIdle()

        val state = viewModel.state.value
        assertEquals(AdminTab.USERS, state.selectedTab)
        assertEquals(2, state.users.size)
        assertEquals("admin@example.com", state.users[0].email)
    }

    @Test
    fun `promoting user updates role in state`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        viewModel.selectTab(AdminTab.USERS)
        advanceUntilIdle()

        val normalUser = viewModel.state.value.users[1]
        assertEquals("user", normalUser.role)

        viewModel.toggleUserRole(normalUser)
        advanceUntilIdle()

        val updatedUser = viewModel.state.value.users.first { it.id == normalUser.id }
        assertEquals("admin", updatedUser.role)
    }

    @Test
    fun `toggling disabled status updates state`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        viewModel.selectTab(AdminTab.USERS)
        advanceUntilIdle()

        val normalUser = viewModel.state.value.users[1]
        assertFalse(normalUser.isDisabled)

        viewModel.toggleUserDisabled(normalUser)
        advanceUntilIdle()

        val updatedUser = viewModel.state.value.users.first { it.id == normalUser.id }
        assertTrue(updatedUser.isDisabled)
    }

    @Test
    fun `triggering backfill updates backfill result in state`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        viewModel.selectTab(AdminTab.DIAGNOSTICS)
        advanceUntilIdle()

        viewModel.triggerThumbnailBackfill()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isBackfilling)
        assertNotNull(state.backfillResult)
        assertEquals(3, state.backfillResult?.backfilled)
    }

    @Test
    fun `health check updates health response in state`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        viewModel.runHealthCheck()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isCheckingHealth)
        assertNotNull(state.healthResponse)
        assertEquals("healthy", state.healthResponse?.status)
    }

    @Test
    fun `load metrics populates telemetry in state`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository()
        val viewModel = AdminViewModel(repository)
        viewModel.loadMetrics()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isLoadingMetrics)
        assertNotNull(state.metrics)
        assertEquals(0, state.metrics?.activeJobs)
        assertEquals("sqlite", state.metrics?.databaseBackend)
    }
}

private class FakeAdminRepository : CretonaRepository {
    private var users = mutableListOf(
        AdminUser(
            id = "admin-1",
            email = "admin@example.com",
            username = "admin",
            role = "admin",
            isDisabled = false,
            createdAt = "2026-08-01T00:00:00Z",
            projectCount = 5,
        ),
        AdminUser(
            id = "user-2",
            email = "alice@example.com",
            username = "alice",
            role = "user",
            isDisabled = false,
            createdAt = "2026-08-02T00:00:00Z",
            projectCount = 2,
        ),
    )

    override suspend fun updateProfile(
        username: String,
        avatarPath: String?,
        gender: String,
        birthday: String,
    ): AppResult<UserProfile> = AppResult.Failure(AppError.Unknown("not used in this test"))

    override suspend fun getCurrentUser(): AppResult<UserProfile> = throw NotImplementedError()
    override suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt> = throw NotImplementedError()
    override suspend fun uploadImage(bytes: ByteArray, mimeType: String, fileName: String): AppResult<String> = throw NotImplementedError()
    override suspend fun createProject(
        prompt: String?,
        imagePath: String?,
        idempotencyKey: String,
        provider: String,
        aspectRatio: String,
        stylePreset: String?,
        cameraMotion: String?,
    ): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun getProject(id: String): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun cancelProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun deleteProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun listProjects(): AppResult<List<VideoProject>> = throw NotImplementedError()

    override suspend fun getAdminStats(days: Int): AppResult<AdminStats> =
        AppResult.Success(
            AdminStats(
                totalUsers = 10,
                activeUsers = 9,
                totalProjects = 25,
                failureRate = 0.04,
                projectsByStatus = mapOf("completed" to 24, "failed" to 1),
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
    ): AppResult<List<AdminUser>> = AppResult.Success(users)

    override suspend fun updateAdminUser(
        id: String,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<AdminUser> {
        val index = users.indexOfFirst { it.id == id }
        val current = users[index]
        val updated = current.copy(
            role = role ?: current.role,
            isDisabled = isDisabled ?: current.isDisabled,
        )
        users[index] = updated
        return AppResult.Success(updated)
    }

    override suspend fun getAdminAuditLogs(
        limit: Int,
        cursor: String?,
        action: String?,
        actorId: String?,
    ): AppResult<List<AdminAuditLog>> =
        AppResult.Success(
            listOf(
                AdminAuditLog(
                    id = "log-1",
                    actorId = "admin-1",
                    action = "user_updated",
                    targetType = "user",
                    targetId = "user-2",
                    createdAt = "2026-08-14T10:00:00Z",
                ),
            ),
        )

    override suspend fun backfillThumbnails(): AppResult<BackfillResult> =
        AppResult.Success(BackfillResult(backfilled = 3, processed = 5))

    override suspend fun checkHealth(): AppResult<HealthResponse> =
        AppResult.Success(HealthResponse(status = "healthy", version = "1.0.0"))

    override suspend fun getAdminMetrics(): AppResult<AdminMetrics> =
        AppResult.Success(
            AdminMetrics(
                uptimeSeconds = 120.5f,
                activeJobs = 0,
                completedJobs = 10,
                failedJobs = 1,
                memoryRssMb = 42.5f,
                databaseBackend = "sqlite",
                databaseStatus = "healthy",
                storageBackend = "local",
            ),
        )
}
