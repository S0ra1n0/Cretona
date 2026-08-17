package com.cretona.app.core.auth

import javax.inject.Inject
import javax.inject.Singleton

/**
 * Holds the access token from a real Supabase sign-in, in memory only.
 *
 * Does not survive process death by design -- every fresh launch starts at
 * the login screen rather than silently resuming a session, which is the
 * simplest correct behaviour until real session persistence is asked for.
 *
 * NetworkModule's interceptor reads [accessToken] and falls back to the fixed
 * local dev identity when nobody has signed in, which is what keeps dev-mode
 * backend testing (scripts/run-dev-backend.ps1) working unchanged.
 */
@Singleton
class SessionManager @Inject constructor() {
    @Volatile
    var accessToken: String? = null
        private set

    fun setSession(token: String) {
        accessToken = token
    }

    fun clear() {
        accessToken = null
    }
}
