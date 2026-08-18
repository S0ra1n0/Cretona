package com.cretona.app.domain.repository

import com.cretona.app.core.result.AppResult

/**
 * Kept separate from CretonaRepository: this talks to Supabase Auth directly,
 * not through the FastAPI backend, and conflating the two would blur that
 * boundary (see ADR-002).
 */
interface AuthRepository {
    suspend fun signIn(email: String, password: String): AppResult<Unit>
    suspend fun signUp(email: String, password: String): AppResult<Unit>
}
