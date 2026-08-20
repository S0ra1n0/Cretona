package com.cretona.app.core.auth

import io.github.jan.supabase.SupabaseClient
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.auth.providers.builtin.Email

/**
 * App-owned boundary around Supabase Auth. The SDK remains the sole owner of
 * access/refresh rotation and persisted sessions.
 */
interface SessionManager {
    val isConfigured: Boolean
    val accessToken: String?
    val hasSession: Boolean

    suspend fun awaitInitialization()
    suspend fun signIn(email: String, password: String)
    suspend fun signUp(email: String, password: String): Boolean
    suspend fun signOut()
}

internal class SupabaseSessionManager(
    private val client: SupabaseClient,
) : SessionManager {
    override val isConfigured: Boolean = true
    override val accessToken: String?
        get() = client.auth.currentAccessTokenOrNull()
    override val hasSession: Boolean
        get() = client.auth.currentSessionOrNull() != null

    override suspend fun awaitInitialization() {
        client.auth.awaitInitialization()
    }

    override suspend fun signIn(email: String, password: String) {
        client.auth.signInWith(Email) {
            this.email = email
            this.password = password
        }
    }

    override suspend fun signUp(email: String, password: String): Boolean {
        client.auth.signUpWith(Email) {
            this.email = email
            this.password = password
        }
        return hasSession
    }

    override suspend fun signOut() {
        if (hasSession) {
            client.auth.signOut()
        } else {
            client.auth.clearSession()
        }
    }
}

internal class UnconfiguredSessionManager : SessionManager {
    override val isConfigured: Boolean = false
    override val accessToken: String? = null
    override val hasSession: Boolean = false

    override suspend fun awaitInitialization() = Unit

    override suspend fun signIn(email: String, password: String): Nothing =
        throw AuthNotConfiguredException()

    override suspend fun signUp(email: String, password: String): Nothing =
        throw AuthNotConfiguredException()

    override suspend fun signOut() = Unit
}

class AuthNotConfiguredException : IllegalStateException(
    "Supabase Auth is not configured for this build. Use Dev Login or configure local.properties.",
)
