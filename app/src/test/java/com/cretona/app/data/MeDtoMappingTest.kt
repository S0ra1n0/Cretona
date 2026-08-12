package com.cretona.app.data

import com.cretona.app.data.remote.MeDto
import com.cretona.app.data.remote.QuotaDto
import org.junit.Assert.assertEquals
import org.junit.Test

class MeDtoMappingTest {
    @Test
    fun `me DTO maps identity and quota without losing reset time`() {
        val user = MeDto(
            id = "user-1",
            email = "student@example.com",
            username = "bruce",
            role = "user",
            isDisabled = false,
            createdAt = "2026-08-01T00:00:00Z",
            quota = QuotaDto(
                limit = 10,
                used = 3,
                remaining = 7,
                resetsAt = "2026-08-13T12:00:00Z",
            ),
        ).toDomain()

        assertEquals("bruce", user.displayName)
        assertEquals(10, user.quota.limit)
        assertEquals(3, user.quota.used)
        assertEquals(7, user.quota.remaining)
        assertEquals("2026-08-13T12:00:00Z", user.quota.resetsAt)
    }

    @Test
    fun `email is the display fallback when username is absent`() {
        val user = MeDto(
            id = "user-2",
            email = "fallback@example.com",
            username = null,
            role = "user",
            isDisabled = false,
            createdAt = "2026-08-01T00:00:00Z",
            quota = QuotaDto(limit = 10, used = 0, remaining = 10, resetsAt = null),
        ).toDomain()

        assertEquals("fallback@example.com", user.displayName)
    }
}
