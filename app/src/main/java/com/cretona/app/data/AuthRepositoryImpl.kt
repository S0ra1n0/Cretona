package com.cretona.app.data

import com.cretona.app.core.auth.AuthNotConfiguredException
import com.cretona.app.core.auth.SessionManager
import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.repository.AuthSignUpResult
import com.cretona.app.domain.repository.AuthRepository
import io.github.jan.supabase.exceptions.HttpRequestException
import io.github.jan.supabase.exceptions.RestException
import io.ktor.client.plugins.HttpRequestTimeoutException
import kotlinx.coroutines.CancellationException
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val session: SessionManager,
) : AuthRepository {
    override val canUseLocalDemo: Boolean
        get() = !session.isConfigured

    override suspend fun restoreSession(): AppResult<Boolean> = authCall {
        session.awaitInitialization()
        session.hasSession
    }

    override suspend fun signIn(email: String, password: String): AppResult<Unit> = authCall {
        session.signIn(email.trim(), password)
    }

    override suspend fun signUp(email: String, password: String): AppResult<AuthSignUpResult> = authCall {
        AuthSignUpResult(sessionCreated = session.signUp(email.trim(), password))
    }

    override suspend fun signOut(): AppResult<Unit> = authCall {
        session.signOut()
    }

    private suspend fun <T> authCall(block: suspend () -> T): AppResult<T> = try {
        AppResult.Success(block())
    } catch (cancellation: CancellationException) {
        throw cancellation
    } catch (error: AuthNotConfiguredException) {
        AppResult.Failure(AppError.Unknown(error.message.orEmpty()))
    } catch (_: HttpRequestTimeoutException) {
        AppResult.Failure(AppError.Network("The authentication server timed out."))
    } catch (_: HttpRequestException) {
        AppResult.Failure(AppError.Network("Cannot reach the authentication server."))
    } catch (_: IOException) {
        AppResult.Failure(AppError.Network("Cannot reach the authentication server."))
    } catch (_: RestException) {
        // Do not surface provider response bodies: auth errors can include
        // account details that enable enumeration. The actionable copy is the
        // same for sign-in, sign-up and expired/revoked restore attempts.
        AppResult.Failure(AppError.Unauthorized("Authentication failed. Check your input or sign in again."))
    } catch (_: Exception) {
        AppResult.Failure(AppError.Unknown("Authentication could not be completed."))
    }
}
