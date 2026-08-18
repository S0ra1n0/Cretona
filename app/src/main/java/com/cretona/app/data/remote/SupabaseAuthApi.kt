package com.cretona.app.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * Direct Supabase Auth calls (ADR-002: the app authenticates directly with
 * Supabase Auth; the backend only verifies the resulting JWT). A separate
 * base URL and client from CretonaApi -- this is a different service, hit
 * with the anon key, not the app's own bearer token.
 */
interface SupabaseAuthApi {
    @POST("auth/v1/token")
    suspend fun signInWithPassword(
        @Query("grant_type") grantType: String,
        @Header("apikey") apiKey: String,
        @Header("Authorization") authorization: String,
        @Body request: SupabaseSignInRequest,
    ): SupabaseSignInResponse

    @POST("auth/v1/signup")
    suspend fun signUpWithPassword(
        @Header("apikey") apiKey: String,
        @Header("Authorization") authorization: String,
        @Body request: SupabaseSignUpRequest,
    ): SupabaseSignUpResponse
}

@Serializable
data class SupabaseSignInRequest(
    val email: String,
    val password: String,
)

@Serializable
data class SupabaseSignInResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String? = null,
    @SerialName("expires_in") val expiresIn: Long? = null,
    @SerialName("refresh_token") val refreshToken: String? = null,
)

@Serializable
data class SupabaseSignUpRequest(
    val email: String,
    val password: String,
)

@Serializable
data class SupabaseSignUpResponse(
    val id: String? = null,
    @SerialName("access_token") val accessToken: String? = null,
    @SerialName("token_type") val tokenType: String? = null,
    @SerialName("expires_in") val expiresIn: Long? = null,
    @SerialName("refresh_token") val refreshToken: String? = null,
    val email: String? = null,
)

/**
 * Supabase's GoTrue error body. Fields vary by version/failure mode, so every
 * field is optional and the caller picks whichever is present.
 */
@Serializable
data class SupabaseErrorResponse(
    val error: String? = null,
    @SerialName("error_description") val errorDescription: String? = null,
    @SerialName("error_code") val errorCode: String? = null,
    val msg: String? = null,
)
