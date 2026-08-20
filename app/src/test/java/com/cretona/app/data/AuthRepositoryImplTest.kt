package com.cretona.app.data

import com.cretona.app.core.auth.AuthNotConfiguredException
import com.cretona.app.core.auth.SessionManager
import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class AuthRepositoryImplTest {
    @Test
    fun `local demo is exposed only when Supabase is unconfigured`() {
        assertTrue(AuthRepositoryImpl(FakeSdkSessionManager(isConfigured = false)).canUseLocalDemo)
        assertFalse(AuthRepositoryImpl(FakeSdkSessionManager(isConfigured = true)).canUseLocalDemo)
    }

    @Test
    fun `restore waits for SDK initialization and reports a saved session`() = runTest {
        val session = FakeSdkSessionManager(hasSession = true)

        val result = AuthRepositoryImpl(session).restoreSession()

        assertEquals(AppResult.Success(true), result)
        assertTrue(session.awaitedInitialization)
    }

    @Test
    fun `sign in trims email but preserves password`() = runTest {
        val session = FakeSdkSessionManager()

        assertEquals(
            AppResult.Success(Unit),
            AuthRepositoryImpl(session).signIn("  user@example.test  ", " password "),
        )
        assertEquals("user@example.test", session.signedInEmail)
        assertEquals(" password ", session.signedInPassword)
    }

    @Test
    fun `sign up exposes whether Supabase created a session`() = runTest {
        val session = FakeSdkSessionManager(signUpCreatesSession = false)

        val result = AuthRepositoryImpl(session).signUp("user@example.test", "password")

        assertTrue(result is AppResult.Success && !result.data.sessionCreated)
    }

    @Test
    fun `unconfigured auth returns actionable failure`() = runTest {
        val session = FakeSdkSessionManager(signInFailure = AuthNotConfiguredException())

        val result = AuthRepositoryImpl(session).signIn("user@example.test", "password")

        assertTrue(result is AppResult.Failure)
        assertTrue((result as AppResult.Failure).error.message.contains("not configured"))
    }

    @Test
    fun `network failure maps without exposing provider internals`() = runTest {
        val session = FakeSdkSessionManager(signInFailure = IOException("secret transport detail"))

        val result = AuthRepositoryImpl(session).signIn("user@example.test", "password")

        assertEquals(
            AppError.Network("Cannot reach the authentication server."),
            (result as AppResult.Failure).error,
        )
        assertFalse(result.error.message.contains("secret"))
    }

    @Test(expected = CancellationException::class)
    fun `auth cancellation is never converted to a UI error`() = runTest {
        val session = FakeSdkSessionManager(signInFailure = CancellationException("cancelled"))
        AuthRepositoryImpl(session).signIn("user@example.test", "password")
    }
}

private class FakeSdkSessionManager(
    override val isConfigured: Boolean = true,
    override val hasSession: Boolean = false,
    private val signUpCreatesSession: Boolean = true,
    private val signInFailure: Exception? = null,
) : SessionManager {
    override val accessToken: String? = null
    var awaitedInitialization = false
    var signedInEmail: String? = null
    var signedInPassword: String? = null

    override suspend fun awaitInitialization() {
        awaitedInitialization = true
    }

    override suspend fun signIn(email: String, password: String) {
        signInFailure?.let { throw it }
        signedInEmail = email
        signedInPassword = password
    }

    override suspend fun signUp(email: String, password: String): Boolean = signUpCreatesSession
    override suspend fun signOut() = Unit
}
