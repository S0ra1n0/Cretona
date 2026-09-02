package com.cretona.app.ui.admin

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminMetrics
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.CursorPage
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.GenerationQuota
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
    fun `an admin cannot change their own role`() = runTest(mainDispatcherRule.dispatcher) {
        // The signed-in admin is the "admin-1" fixture row here, so the guard
        // is the only thing standing between the console and a locked-out user.
        val repository = FakeAdminRepository(currentUserId = "admin-1")
        val viewModel = AdminViewModel(repository)
        viewModel.selectTab(AdminTab.USERS)
        advanceUntilIdle()

        val self = viewModel.state.value.users.first { it.id == "admin-1" }
        assertEquals("admin", self.role)

        viewModel.toggleUserRole(self)
        advanceUntilIdle()

        assertEquals("admin", viewModel.state.value.users.first { it.id == "admin-1" }.role)
        assertEquals(
            "You cannot change your own role.",
            viewModel.state.value.userActionMessage,
        )
    }

    @Test
    fun `an admin cannot disable their own account`() = runTest(mainDispatcherRule.dispatcher) {
        val repository = FakeAdminRepository(currentUserId = "admin-1")
        val viewModel = AdminViewModel(repository)
        viewModel.selectTab(AdminTab.USERS)
        advanceUntilIdle()

        val self = viewModel.state.value.users.first { it.id == "admin-1" }
        viewModel.toggleUserDisabled(self)
        advanceUntilIdle()

        assertFalse(viewModel.state.value.users.first { it.id == "admin-1" }.isDisabled)
        assertEquals(
            "You cannot disable your own account.",
            viewModel.state.value.userActionMessage,
        )
    }

    @Test
    fun `another admin can still be demoted`() = runTest(mainDispatcherRule.dispatcher) {
        // The guard must be scoped to self, not to admins in general.
        val repository = FakeAdminRepository(currentUserId = "someone-else")
        val viewModel = AdminViewModel(repository)
        viewModel.selectTab(AdminTab.USERS)
        advanceUntilIdle()

        viewModel.toggleUserRole(viewModel.state.value.users.first { it.id == "admin-1" })
        advanceUntilIdle()

        assertEquals("user", viewModel.state.value.users.first { it.id == "admin-1" }.role)
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

    @Test
    fun `user pagination forwards cursor appends uniquely and filter restarts`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = FakeAdminRepository(paginatedCollections = true)
            val viewModel = AdminViewModel(repository)
            advanceUntilIdle()

            viewModel.selectTab(AdminTab.USERS)
            advanceUntilIdle()
            assertEquals(1, viewModel.state.value.users.size)
            assertTrue(viewModel.state.value.hasMoreUsers)

            viewModel.loadMoreUsers()
            advanceUntilIdle()
            assertEquals(listOf(null, "users-page-2"), repository.userCursors)
            assertEquals(listOf("admin-1", "user-2"), viewModel.state.value.users.map { it.id })

            viewModel.onRoleFilterChanged("admin")
            advanceUntilIdle()
            assertEquals(null, repository.userCursors.last())
        }

    @Test
    fun `audit pagination forwards cursor and appends uniquely`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = FakeAdminRepository(paginatedCollections = true)
            val viewModel = AdminViewModel(repository)
            advanceUntilIdle()

            viewModel.selectTab(AdminTab.AUDIT_LOGS)
            advanceUntilIdle()
            assertTrue(viewModel.state.value.hasMoreLogs)

            viewModel.loadMoreAuditLogs()
            advanceUntilIdle()

            assertEquals(listOf(null, "logs-page-2"), repository.logCursors)
            assertEquals(listOf("log-1", "log-2"), viewModel.state.value.auditLogs.map { it.id })
            assertFalse(viewModel.state.value.hasMoreLogs)
        }

    @Test
    fun `credit adjustment requires an audit note before calling the repository`() =
        runTest(mainDispatcherRule.dispatcher) {
            val viewModel = AdminViewModel(FakeAdminRepository())
            advanceUntilIdle()

            viewModel.adjustCredits("user-1", 10, "")

            assertEquals(
                "User ID, a non-zero delta, and a note are required.",
                viewModel.state.value.managementError,
            )
        }
}

private class FakeAdminRepository(
    private val paginatedCollections: Boolean = false,
    private val currentUserId: String = "signed-in-admin",
) : CretonaRepository {
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
    val userCursors = mutableListOf<String?>()
    val logCursors = mutableListOf<String?>()

    override suspend fun updateProfile(
        username: String,
        avatarPath: String?,
        gender: String,
        birthday: String,
    ): AppResult<UserProfile> = AppResult.Failure(AppError.Unknown("not used in this test"))

    /** The signed-in admin. Defaults to an id no fixture user shares, so the
     *  self-targeting guard stays out of the way unless a test opts into it. */
    override suspend fun getCurrentUser(): AppResult<UserProfile> = AppResult.Success(
        UserProfile(
            id = currentUserId,
            email = "signed-in@example.com",
            username = "signedin",
            role = "admin",
            isDisabled = false,
            createdAt = "2026-01-01T00:00:00Z",
            quota = GenerationQuota(limit = 10, used = 0, remaining = 10, resetsAt = null),
        ),
    )
    override suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt> = throw NotImplementedError()
    override suspend fun uploadImage(bytes: ByteArray, mimeType: String, fileName: String): AppResult<String> = throw NotImplementedError()
    override suspend fun createProject(
        prompt: String?,
        imagePath: String?,
        idempotencyKey: String,
        provider: String,
        durationSeconds: Int,
        aspectRatio: String,
        stylePreset: String?,
        cameraMotion: String?,
    ): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun getProject(id: String): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun cancelProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun deleteProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun listProjects(limit: Int, cursor: String?): AppResult<CursorPage<VideoProject>> = throw NotImplementedError()

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
    ): AppResult<CursorPage<AdminUser>> {
        userCursors += cursor
        return if (paginatedCollections && cursor == null) {
            AppResult.Success(
                CursorPage(
                    items = listOf(users[0]),
                    nextCursor = "users-page-2",
                    hasMore = true,
                ),
            )
        } else if (paginatedCollections) {
            AppResult.Success(CursorPage(items = listOf(users[0], users[1])))
        } else {
            AppResult.Success(CursorPage(items = users))
        }
    }

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
    ): AppResult<CursorPage<AdminAuditLog>> {
        logCursors += cursor
        val first = AdminAuditLog(
            id = "log-1",
            actorId = "admin-1",
            action = "user_updated",
            targetType = "user",
            targetId = "user-2",
            createdAt = "2026-08-14T10:00:00Z",
        )
        return if (paginatedCollections && cursor == null) {
            AppResult.Success(
                CursorPage(
                    items = listOf(first),
                    nextCursor = "logs-page-2",
                    hasMore = true,
                ),
            )
        } else if (paginatedCollections) {
            AppResult.Success(
                CursorPage(
                    items = listOf(
                        first,
                        AdminAuditLog(
                            id = "log-2",
                            actorId = "admin-1",
                            action = "thumbnails_backfilled",
                            targetType = "project",
                            targetId = null,
                            createdAt = "2026-08-14T11:00:00Z",
                        ),
                    ),
                ),
            )
        } else {
            AppResult.Success(CursorPage(items = listOf(first)))
        }
    }

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
