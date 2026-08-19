package com.cretona.app.data

import com.cretona.app.data.remote.MeUpdateRequest
import com.cretona.app.di.NetworkModule
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The body the backend actually receives, encoded with the real app config.
 *
 * `gender` and `birthday` use empty string to mean "clear this", and the
 * backend decides intent from which fields were sent. That only works if an
 * empty string is actually written to the wire -- kotlinx omits any property
 * still equal to its declared default unless told otherwise, which silently
 * turned every "clear" into "leave as is".
 */
class MeUpdateRequestSerializationTest {
    private val json = NetworkModule.provideJson()

    private fun encode(request: MeUpdateRequest): String =
        json.encodeToString(MeUpdateRequest.serializer(), request)

    @Test
    fun `clearing both details still sends both fields`() {
        val body = encode(MeUpdateRequest(username = "someone", gender = "", birthday = ""))

        assertTrue("gender missing from $body", body.contains("\"gender\":\"\""))
        assertTrue("birthday missing from $body", body.contains("\"birthday\":\"\""))
    }

    @Test
    fun `clearing only the gender leaves the birthday sent too`() {
        val body = encode(
            MeUpdateRequest(username = "someone", gender = "", birthday = "1998-04-17"),
        )

        assertTrue("gender missing from $body", body.contains("\"gender\":\"\""))
        assertTrue("birthday missing from $body", body.contains("\"birthday\":\"1998-04-17\""))
    }

    @Test
    fun `chosen values are sent`() {
        val body = encode(
            MeUpdateRequest(username = "someone", gender = "male", birthday = "1998-04-17"),
        )

        assertTrue(body.contains("\"gender\":\"male\""))
        assertTrue(body.contains("\"birthday\":\"1998-04-17\""))
    }

    @Test
    fun `an untouched avatar is still omitted`() {
        val body = encode(MeUpdateRequest(username = "someone", gender = "", birthday = ""))

        // Unlike the details, a null avatarPath must stay absent: absent is
        // what tells the backend to leave the existing picture alone.
        assertFalse("avatarPath should not be sent: $body", body.contains("avatarPath"))
    }
}
