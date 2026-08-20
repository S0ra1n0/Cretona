package com.cretona.app.ui.profile

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.AuthRepository
import com.cretona.app.domain.repository.AuthSignUpResult
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
class ProfileViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `successful sign out navigates only after SDK completion`() =
        runTest(mainDispatcherRule.dispatcher) {
            val auth = FakeProfileAuthRepository()
            val viewModel = ProfileViewModel(auth)
            var navigated = false

            viewModel.signOut { navigated = true }
            assertFalse(navigated)
            advanceUntilIdle()

            assertTrue(auth.signOutCalled)
            assertTrue(navigated)
            assertFalse(viewModel.signOutState.value.isSigningOut)
            assertNull(viewModel.signOutState.value.errorMessage)
        }

    @Test
    fun `failed sign out keeps the user in place and exposes the error`() =
        runTest(mainDispatcherRule.dispatcher) {
            val auth = FakeProfileAuthRepository(
                signOutResult = AppResult.Failure(AppError.Network("Auth is offline.")),
            )
            val viewModel = ProfileViewModel(auth)
            var navigated = false

            viewModel.signOut { navigated = true }
            advanceUntilIdle()

            assertFalse(navigated)
            assertEquals("Auth is offline.", viewModel.signOutState.value.errorMessage)
        }
}

private class FakeProfileAuthRepository(
    private val signOutResult: AppResult<Unit> = AppResult.Success(Unit),
) : AuthRepository {
    override val canUseLocalDemo: Boolean = false
    var signOutCalled = false
    override suspend fun restoreSession(): AppResult<Boolean> = AppResult.Success(false)
    override suspend fun signIn(email: String, password: String): AppResult<Unit> = AppResult.Success(Unit)
    override suspend fun signUp(email: String, password: String): AppResult<AuthSignUpResult> =
        AppResult.Success(AuthSignUpResult(false))
    override suspend fun signOut(): AppResult<Unit> {
        signOutCalled = true
        return signOutResult
    }
}
