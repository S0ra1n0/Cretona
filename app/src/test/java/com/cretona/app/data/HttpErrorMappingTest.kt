package com.cretona.app.data

import com.cretona.app.core.result.AppError
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

/**
 * The backend answers failures with `{"error": {"code", "message"}}`. That
 * message was previously thrown away, so a taken username reached the account
 * as "Request failed with HTTP 409".
 */
class HttpErrorMappingTest {
    @Test
    fun `a conflict carries the servers own wording`() {
        val error = httpError(409, """{"error":{"code":"CONFLICT","message":"That username is already taken."}}""")

        assertEquals("That username is already taken.", error.message)
    }

    @Test
    fun `a validation failure carries the servers own wording`() {
        val error = httpError(400, """{"error":{"code":"VALIDATION_ERROR","message":"birthday must be an ISO date (YYYY-MM-DD)"}}""")

        assertEquals("birthday must be an ISO date (YYYY-MM-DD)", error.message)
    }

    @Test
    fun `an unparseable body falls back to the generic line`() {
        val error = httpError(409, "<html>gateway</html>")

        assertEquals("Request failed with HTTP 409.", error.message)
    }

    @Test
    fun `an empty body falls back to the generic line`() {
        val error = httpError(418, "")

        assertEquals("Request failed with HTTP 418.", error.message)
    }

    @Test
    fun `an envelope without a message falls back to the generic line`() {
        val error = httpError(409, """{"error":{"code":"CONFLICT"}}""")

        assertEquals("Request failed with HTTP 409.", error.message)
    }

    @Test
    fun `a server fault keeps the generic line even when it explains itself`() {
        // A 5xx message is an internal detail and the caller can act on none
        // of it, so it is deliberately not surfaced.
        val error = httpError(500, """{"error":{"code":"INTERNAL","message":"psycopg pool exhausted"}}""")

        assertEquals("The server could not complete the request.", error.message)
        assertTrue(error is AppError.Server)
    }

    @Test
    fun `recognised statuses keep their own type while gaining the detail`() {
        val forbidden = httpError(403, """{"error":{"code":"FORBIDDEN","message":"You do not have access to this resource."}}""")

        assertTrue(forbidden is AppError.Forbidden)
        assertEquals("You do not have access to this resource.", forbidden.message)
    }

    @Test
    fun `a recognised status without a body keeps its default wording`() {
        val unauthorized = httpError(401, "")

        assertTrue(unauthorized is AppError.Unauthorized)
        assertEquals("Session expired", unauthorized.message)
    }
}

private fun httpError(code: Int, body: String): AppError {
    val response = Response.error<Any>(
        code,
        body.toResponseBody("application/json".toMediaType()),
    )
    return HttpException(response).toAppError()
}
