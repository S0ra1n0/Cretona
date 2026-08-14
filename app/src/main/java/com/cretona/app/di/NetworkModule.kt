package com.cretona.app.di

import com.cretona.app.BuildConfig
import com.cretona.app.data.remote.CretonaApi
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val requestBuilder = chain.request().newBuilder()
            requestBuilder.header("X-Debug-User-Id", "00000000-0000-4000-8000-000000000001")
            requestBuilder.header(
                "Authorization",
                "Bearer eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiMGYyY2EyNmQtYzBjYy00MDkzLTljODAtYzQwNDYwMTc2ZDgzIiwgImF1ZCI6ICJhdXRoZW50aWNhdGVkIiwgInJvbGUiOiAiYXV0aGVudGljYXRlZCIsICJpc3MiOiAiaHR0cHM6Ly9maXNud2R6aHl1aWl1cnNsamJsdy5zdXBhYmFzZS5jby9hdXRoL3YxIiwgImlhdCI6IDE3ODY2OTM1NTUsICJleHAiOiAyMTAyMDUzNTU1LCAiZW1haWwiOiAidXNlckBjcmV0b25hLnRlc3QifQ.jR8N8QAwB8CzulImrW0kTtM_HYt-j_3s-mwAXZrX-5E",
            )
            chain.proceed(requestBuilder.build())
        }
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        level = HttpLoggingInterceptor.Level.BODY
                        // Auth headers must never reach logcat.
                        redactHeader("Authorization")
                    },
                )
            }
        }
        .build()

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient, json: Json): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides
    @Singleton
    fun provideCretonaApi(retrofit: Retrofit): CretonaApi = retrofit.create(CretonaApi::class.java)
}
