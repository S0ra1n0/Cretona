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
        val session = SessionManager()

        val request = executeAndCapture(NetworkModule.provideOkHttpClient(session))

        assertEquals("00000000-0000-4000-8000-000000000001", request.header("X-Debug-User-Id"))
        assertNull(request.header("Authorization"))
    }

    @Test
    fun `signed-in requests use only the Supabase access token`() {
        val session = SessionManager().apply { setSession("test-access-token") }

        val request = executeAndCapture(NetworkModule.provideOkHttpClient(session))

        assertEquals("Bearer test-access-token", request.header("Authorization"))
        assertNull(request.header("X-Debug-User-Id"))
    }

    @Test
    fun `debug HTTP logging never records request or response bodies`() {
        val backendClient = NetworkModule.provideOkHttpClient(SessionManager())
        val supabaseClient = NetworkModule.provideSupabaseOkHttpClient()

        listOf(backendClient, supabaseClient).forEach { client ->
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
