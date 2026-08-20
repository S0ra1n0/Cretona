package com.cretona.app.di

import com.cretona.app.BuildConfig
import com.cretona.app.core.auth.EncryptedAuthSessionStore
import com.cretona.app.core.auth.SessionManager
import com.cretona.app.core.auth.SupabaseSessionManager
import com.cretona.app.core.auth.UnconfiguredSessionManager
import com.cretona.app.data.remote.CretonaApi
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import io.github.jan.supabase.createSupabaseClient
import io.github.jan.supabase.auth.Auth
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

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
    fun provideSessionManager(store: EncryptedAuthSessionStore): SessionManager {
        val url = BuildConfig.SUPABASE_URL.trimEnd('/')
        val key = BuildConfig.SUPABASE_ANON_KEY
        if (url.isBlank() || key.isBlank()) return UnconfiguredSessionManager()

        val client = createSupabaseClient(
            supabaseUrl = url,
            supabaseKey = key,
        ) {
            install(Auth) {
                sessionManager = store
                alwaysAutoRefresh = true
                autoLoadFromStorage = true
                autoSaveToStorage = true
            }
        }
        return SupabaseSessionManager(client)
    }

    @Provides
    @Singleton
    fun provideOkHttpClient(session: SessionManager): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val requestBuilder = chain.request().newBuilder()
            applyBackendIdentity(requestBuilder, session, BuildConfig.DEBUG)
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
}

/**
 * Real tokens and the local dev identity are mutually exclusive. The debug
 * identity exists only for credential-free local builds with Auth unconfigured;
 * a signed-out production or Supabase-configured build sends neither header.
 */
internal fun applyBackendIdentity(
    request: okhttp3.Request.Builder,
    session: SessionManager,
    isDebug: Boolean,
) {
    val token = session.accessToken
    when {
        token != null -> request.header("Authorization", "Bearer $token")
        isDebug && !session.isConfigured -> request.header("X-Debug-User-Id", DEV_USER_ID)
    }
}
