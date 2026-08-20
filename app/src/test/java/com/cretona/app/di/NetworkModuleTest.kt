package com.cretona.app.di

import com.cretona.app.core.auth.SessionManager
import okhttp3.Interceptor
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.logging.HttpLoggingInterceptor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NetworkModuleTest {
    @Test
    fun `signed-out requests use only the local debug identity`() {
        val session = FakeSessionManager(isConfigured = false)

        val request = executeAndCapture(NetworkModule.provideOkHttpClient(session))

        assertEquals("00000000-0000-4000-8000-000000000001", request.header("X-Debug-User-Id"))
        assertNull(request.header("Authorization"))
    }

    @Test
    fun `signed-in requests use only the Supabase access token`() {
        val session = FakeSessionManager(
            isConfigured = true,
            accessToken = "test-access-token",
        )

        val request = executeAndCapture(NetworkModule.provideOkHttpClient(session))

        assertEquals("Bearer test-access-token", request.header("Authorization"))
        assertNull(request.header("X-Debug-User-Id"))
    }

    @Test
    fun `configured signed-out requests never impersonate the dev user`() {
        val request = executeAndCapture(
            NetworkModule.provideOkHttpClient(FakeSessionManager(isConfigured = true)),
        )

        assertNull(request.header("Authorization"))
        assertNull(request.header("X-Debug-User-Id"))
    }

    @Test
    fun `release requests never use the local debug identity`() {
        val builder = Request.Builder().url("https://example.test/")
        applyBackendIdentity(
            request = builder,
            session = FakeSessionManager(isConfigured = false),
            isDebug = false,
        )

        val request = builder.build()
        assertNull(request.header("Authorization"))
        assertNull(request.header("X-Debug-User-Id"))
    }

    @Test
    fun `debug HTTP logging never records request or response bodies`() {
        val backendClient = NetworkModule.provideOkHttpClient(FakeSessionManager(isConfigured = false))

        listOf(backendClient).forEach { client ->
            val loggers = client.interceptors.filterIsInstance<HttpLoggingInterceptor>()
            assertTrue(loggers.isNotEmpty())
            assertTrue(loggers.all { it.level == HttpLoggingInterceptor.Level.BASIC })
            assertFalse(loggers.any { it.level == HttpLoggingInterceptor.Level.BODY })
        }
    }

    private fun executeAndCapture(client: okhttp3.OkHttpClient): Request {
        var captured: Request? = null
        val terminal = Interceptor { chain ->
            captured = chain.request()
            Response.Builder()
                .request(chain.request())
                .protocol(Protocol.HTTP_1_1)
                .code(200)
                .message("OK")
                .body("{}".toResponseBody())
                .build()
        }
        val testClient = client.newBuilder().addInterceptor(terminal).build()

        testClient.newCall(Request.Builder().url("https://example.test/").build()).execute().use {
            assertEquals(200, it.code)
        }
        return requireNotNull(captured)
    }
}

private class FakeSessionManager(
    override val isConfigured: Boolean,
    override val accessToken: String? = null,
) : SessionManager {
    override val hasSession: Boolean = accessToken != null
    override suspend fun awaitInitialization() = Unit
    override suspend fun signIn(email: String, password: String) = Unit
    override suspend fun signUp(email: String, password: String): Boolean = true
    override suspend fun signOut() = Unit
}
