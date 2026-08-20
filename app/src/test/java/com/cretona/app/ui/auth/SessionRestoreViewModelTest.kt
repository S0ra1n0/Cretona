package com.cretona.app.ui.auth

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.AuthSignUpResult
import com.cretona.app.domain.repository.AuthRepository
import com.cretona.app.ui.home.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SessionRestoreViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `missing saved session routes to auth`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = SessionRestoreViewModel(
            FakeRestoreAuthRepository(restored = AppResult.Success(false)),
            FakeCretonaRepository(),
        )

        advanceUntilIdle()

        assertEquals(RestoredDestination.AUTH, viewModel.state.value.destination)
        assertFalse(viewModel.state.value.isLoading)
    }

    @Test
    fun `restored incomplete profile routes to setup`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = SessionRestoreViewModel(
            FakeRestoreAuthRepository(restored = AppResult.Success(true)),
            FakeCretonaRepository(),
        )

        advanceUntilIdle()

        assertEquals(RestoredDestination.PROFILE_SETUP, viewModel.state.value.destination)
    }

    @Test
    fun `temporary profile failure keeps restored session and routes to main`() =
        runTest(mainDispatcherRule.dispatcher) {
            val viewModel = SessionRestoreViewModel(
                FakeRestoreAuthRepository(restored = AppResult.Success(true)),
                FakeCretonaRepository().apply { shouldFailCurrentUser = true },
            )

            advanceUntilIdle()

            assertEquals(RestoredDestination.MAIN, viewModel.state.value.destination)
            assertNull(viewModel.state.value.errorMessage)
        }

    @Test
    fun `restore failure stays on retry screen`() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = SessionRestoreViewModel(
            FakeRestoreAuthRepository(
                restored = AppResult.Failure(AppError.Network("Auth is offline.")),
            ),
            FakeCretonaRepository(),
        )

        advanceUntilIdle()

        assertNull(viewModel.state.value.destination)
        assertEquals("Auth is offline.", viewModel.state.value.errorMessage)
        assertFalse(viewModel.state.value.isLoading)
    }
}

private class FakeRestoreAuthRepository(
    private val restored: AppResult<Boolean>,
) : AuthRepository {
    override val canUseLocalDemo: Boolean = false
    override suspend fun restoreSession(): AppResult<Boolean> = restored
    override suspend fun signIn(email: String, password: String): AppResult<Unit> = AppResult.Success(Unit)
    override suspend fun signUp(email: String, password: String): AppResult<AuthSignUpResult> =
        AppResult.Success(AuthSignUpResult(sessionCreated = false))
    override suspend fun signOut(): AppResult<Unit> = AppResult.Success(Unit)
}
