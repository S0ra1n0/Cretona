package com.cretona.app.ui.auth

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.GenerationQuota
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.AuthRepository
import com.cretona.app.domain.repository.CretonaRepository
import com.cretona.app.ui.home.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `initial state has empty fields and login mode`() {
        val authRepo = FakeAuthRepository()
        val cretonaRepo = FakeCretonaRepository()
        val viewModel = AuthViewModel(authRepo, cretonaRepo)

        val state = viewModel.state.value
        assertEquals("", state.email)
        assertEquals("", state.password)
        assertEquals("", state.confirmPassword)
        assertFalse(state.isSignUpMode)
        assertFalse(state.isLoading)
        assertNull(state.errorMessage)
    }

    @Test
    fun `toggleMode switches between login and sign up modes`() {
        val authRepo = FakeAuthRepository()
        val cretonaRepo = FakeCretonaRepository()
        val viewModel = AuthViewModel(authRepo, cretonaRepo)

        viewModel.toggleMode()
        assertTrue(viewModel.state.value.isSignUpMode)

        viewModel.toggleMode()
        assertFalse(viewModel.state.value.isSignUpMode)
    }

    @Test
    fun `login success triggers loginSucceeded`() = runTest(mainDispatcherRule.dispatcher) {
        val authRepo = FakeAuthRepository()
        val cretonaRepo = FakeCretonaRepository()
        val viewModel = AuthViewModel(authRepo, cretonaRepo)

        viewModel.onEmailChanged("user@cretona.test")
        viewModel.onPasswordChanged("password123")
        viewModel.login()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertTrue(state.loginSucceeded)
        assertNull(state.errorMessage)
    }

    @Test
    fun `signUp with mismatched passwords sets error`() = runTest(mainDispatcherRule.dispatcher) {
        val authRepo = FakeAuthRepository()
        val cretonaRepo = FakeCretonaRepository()
        val viewModel = AuthViewModel(authRepo, cretonaRepo)

        viewModel.setSignUpMode(true)
        viewModel.onEmailChanged("newuser@cretona.test")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("different123")
        viewModel.submit()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertEquals("Passwords do not match.", state.errorMessage)
        assertFalse(state.loginSucceeded)
    }

    @Test
    fun `signUp with valid input succeeds and flags needsProfileSetup`() = runTest(mainDispatcherRule.dispatcher) {
        val authRepo = FakeAuthRepository()
        val cretonaRepo = FakeCretonaRepository()
        val viewModel = AuthViewModel(authRepo, cretonaRepo)

        viewModel.setSignUpMode(true)
        viewModel.onEmailChanged("newuser@cretona.test")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("password123")
        viewModel.submit()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertTrue(state.loginSucceeded)
        assertTrue(state.needsProfileSetup)
        assertNull(state.errorMessage)
    }
}

private class FakeAuthRepository : AuthRepository {
    var shouldFail: Boolean = false

    override suspend fun signIn(email: String, password: String): AppResult<Unit> {
        if (shouldFail) return AppResult.Failure(AppError.Unauthorized("Incorrect email or password."))
        return AppResult.Success(Unit)
    }

    override suspend fun signUp(email: String, password: String): AppResult<Unit> {
        if (shouldFail) return AppResult.Failure(AppError.Unauthorized("Sign up failed."))
        return AppResult.Success(Unit)
    }
}

private class FakeCretonaRepository : CretonaRepository {
    override suspend fun getCurrentUser(): AppResult<UserProfile> =
        AppResult.Success(
            UserProfile(
                id = "user_123",
                email = "user@cretona.test",
                username = null,
                avatarUrl = null,
                role = "user",
                isDisabled = false,
                createdAt = "2026-01-01T00:00:00Z",
                quota = GenerationQuota(limit = 10, used = 0, remaining = 10, resetsAt = null),
            ),
        )

    override suspend fun updateProfile(username: String, avatarPath: String?): AppResult<UserProfile> =
        AppResult.Success(
            UserProfile(
                id = "user_123",
                email = "user@cretona.test",
                username = username,
                avatarUrl = null,
                role = "user",
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
        aspectRatio: String,
        stylePreset: String?,
        cameraMotion: String?,
    ): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun getProject(id: String): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun cancelProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun deleteProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun listProjects(): AppResult<List<VideoProject>> = throw NotImplementedError()
    override suspend fun getAdminStats(days: Int): AppResult<AdminStats> = throw NotImplementedError()
    override suspend fun getAdminUsers(limit: Int, cursor: String?, query: String?, role: String?, isDisabled: Boolean?): AppResult<List<AdminUser>> = throw NotImplementedError()
    override suspend fun updateAdminUser(id: String, role: String?, isDisabled: Boolean?): AppResult<AdminUser> = throw NotImplementedError()
    override suspend fun getAdminAuditLogs(limit: Int, cursor: String?, action: String?, actorId: String?): AppResult<List<AdminAuditLog>> = throw NotImplementedError()
    override suspend fun backfillThumbnails(): AppResult<BackfillResult> = throw NotImplementedError()
    override suspend fun checkHealth(): AppResult<HealthResponse> = throw NotImplementedError()
}
