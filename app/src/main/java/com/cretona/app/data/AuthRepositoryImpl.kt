package com.cretona.app.data

import com.cretona.app.BuildConfig
import com.cretona.app.core.auth.SessionManager
import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.SupabaseAuthApi
import com.cretona.app.data.remote.SupabaseErrorResponse
import com.cretona.app.data.remote.SupabaseSignInRequest
import com.cretona.app.domain.repository.AuthRepository
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.Json
import retrofit2.HttpException
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val api: SupabaseAuthApi,
    private val session: SessionManager,
    private val json: Json,
) : AuthRepository {
    override suspend fun signIn(email: String, password: String): AppResult<Unit> = try {
        val response = api.signInWithPassword(
            grantType = "password",
            apiKey = BuildConfig.SUPABASE_ANON_KEY,
            authorization = "Bearer ${BuildConfig.SUPABASE_ANON_KEY}",
            request = SupabaseSignInRequest(email = email.trim(), password = password),
        )
        session.setSession(response.accessToken)
        AppResult.Success(Unit)
    } catch (cancellation: CancellationException) {
        // Must be rethrown ahead of the catch-all below, or a deliberate
        // cancel turns into a user-visible error.
        throw cancellation
    } catch (error: HttpException) {
        AppResult.Failure(error.toAuthError(json))
    } catch (_: IOException) {
        AppResult.Failure(AppError.Network("Cannot reach the authentication server."))
    } catch (_: Exception) {
        AppResult.Failure(AppError.Unknown())
    }

    private fun HttpException.toAuthError(json: Json): AppError {
        val parsed = response()?.errorBody()?.string()?.let { body ->
            runCatching { json.decodeFromString(SupabaseErrorResponse.serializer(), body) }.getOrNull()
        }
        val detail = parsed?.errorDescription ?: parsed?.msg

        return when {
            // GoTrue answers wrong credentials with 400, not 401.
            code() == 400 || code() == 401 -> AppError.Unauthorized(detail ?: "Incorrect email or password.")
            code() in 500..599 ->
                AppError.Server(code(), "The authentication service had a problem. Try again.")
            else -> AppError.Server(code(), detail ?: "Sign-in failed.")
        }
    }
}
