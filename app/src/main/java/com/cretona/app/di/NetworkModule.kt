package com.cretona.app.di

import com.cretona.app.BuildConfig
import com.cretona.app.core.auth.SessionManager
import com.cretona.app.data.remote.CretonaApi
import com.cretona.app.data.remote.SupabaseAuthApi
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
import javax.inject.Qualifier
import javax.inject.Singleton

/** Distinguishes the Supabase-facing OkHttpClient/Retrofit from the backend's own. */
@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class SupabaseHttpClient

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class SupabaseRetrofit

// Fixed local dev identity (app/config.py's dev_user_id default). Used only
// when nobody has signed in yet, so credential-free local testing keeps
// working. Production rejects this header before it reaches repository code.
private const val DEV_USER_ID = "00000000-0000-4000-8000-000000000001"

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
    fun provideOkHttpClient(session: SessionManager): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val requestBuilder = chain.request().newBuilder()
            val token = session.accessToken

            if (token != null) {
                // Signed in for real: send only the Supabase token. Sending
                // X-Debug-User-Id alongside it would pin every request to the
                // fixed dev identity on a dev-mode backend, so whoever signed
                // in would still be served another account's profile, quota
                // and role.
                requestBuilder.header("Authorization", "Bearer $token")
            } else {
                // Nobody has signed in: fall back to the fixed local identity
                // so the credential-free dev backend still works.
                requestBuilder.header("X-Debug-User-Id", DEV_USER_ID)
            }
            chain.proceed(requestBuilder.build())
        }
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        // BASIC records method, URL and status only. BODY would
                        // leak prompts, signed media URLs and upload payloads.
                        level = HttpLoggingInterceptor.Level.BASIC
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

    @Provides
    @Singleton
    @SupabaseHttpClient
    fun provideSupabaseOkHttpClient(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        // Supabase Auth bodies contain plaintext passwords.
                        level = HttpLoggingInterceptor.Level.BASIC
                    },
                )
            }
        }
        .build()

    @Provides
    @Singleton
    @SupabaseRetrofit
    fun provideSupabaseRetrofit(
        @SupabaseHttpClient client: OkHttpClient,
        json: Json,
    ): Retrofit = Retrofit.Builder()
        // BuildConfig.SUPABASE_URL has no trailing slash; Retrofit requires one.
        .baseUrl("${BuildConfig.SUPABASE_URL}/")
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides
    @Singleton
    fun provideSupabaseAuthApi(@SupabaseRetrofit retrofit: Retrofit): SupabaseAuthApi =
        retrofit.create(SupabaseAuthApi::class.java)
}
