package com.cretona.app.data.remote

import kotlinx.serialization.Serializable
import retrofit2.http.GET

/**
 * Backend contract. Endpoints are added as the API is built out; the wire
 * shapes are specified in docs/API_CONTRACT.md.
 */
interface CretonaApi {

    @GET("health")
    suspend fun health(): HealthResponse
}

@Serializable
data class HealthResponse(
    val status: String,
    val version: String? = null,
)
