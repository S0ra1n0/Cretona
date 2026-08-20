package com.cretona.app.core.auth

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.jan.supabase.auth.exception.NoSessionFoundException
import io.github.jan.supabase.auth.user.UserSession
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EncryptedAuthSessionStoreInstrumentedTest {
    @Test
    fun sessionRoundTripsThroughAndroidKeystoreAndCanBeDeleted() = runBlocking {
        val store = EncryptedAuthSessionStore(
            context = ApplicationProvider.getApplicationContext(),
            json = Json { ignoreUnknownKeys = true; explicitNulls = false },
        )
        val expected = UserSession(
            accessToken = "access-token",
            refreshToken = "refresh-token",
            expiresIn = 3600,
            tokenType = "bearer",
        )

        try {
            store.deleteSession()
            store.saveSession(expected)
            assertEquals(expected, store.loadSession())
            store.deleteSession()
            assertThrows(NoSessionFoundException::class.java) {
                runBlocking { store.loadSession() }
            }
        } finally {
            store.deleteSession()
        }
    }
}
