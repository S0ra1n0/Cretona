package com.cretona.app.data

import com.cretona.app.data.remote.AdminCreditAdjustRequest
import com.cretona.app.data.remote.AdminEventCreateRequest
import com.cretona.app.data.remote.AdminStatsDto
import com.cretona.app.data.remote.toUpdateRequest
import com.cretona.app.domain.model.AdminEventDraft
import com.cretona.app.di.NetworkModule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.serialization.json.JsonNull

class AdminCreditsSerializationTest {
    private val json = NetworkModule.provideJson()

    @Test
    fun `credit adjustment always sends delta and audit note`() {
        val body = json.encodeToString(
            AdminCreditAdjustRequest.serializer(),
            AdminCreditAdjustRequest(delta = -5, note = "Duplicate demo grant"),
        )

        assertTrue(body.contains("\"delta\":-5"))
        assertTrue(body.contains("\"note\":\"Duplicate demo grant\""))
    }

    @Test
    fun `event create sends the complete scheduling contract`() {
        val body = json.encodeToString(
            AdminEventCreateRequest.serializer(),
            AdminEventCreateRequest(
                code = "HOT_HOURS",
                name = "Hot Hours",
                kind = "discount",
                discountPercent = 50,
                recurrence = "daily",
                activeDays = "mon,tue,wed,thu,fri",
                activeFromMinute = 1200,
                activeToMinute = 1320,
                startsAt = "2026-08-28T00:00:00Z",
                endsAt = "2026-09-05T00:00:00Z",
                maxClaims = 100,
                autoGrant = false,
            ),
        )

        for (field in listOf("code", "kind", "discountPercent", "recurrence", "activeDays", "activeFromMinute", "activeToMinute", "startsAt", "endsAt", "maxClaims")) {
            assertTrue("$field missing from $body", body.contains("\"$field\""))
        }
    }

    @Test
    fun `extended stats retain zeros and unlimited event slots`() {
        val payload = """
            {
              "totals": {"users": 2, "activeUsers": 2, "projects": 0,
                "creditsGranted": 0, "creditsUsed": 0, "revenueVnd": 0},
              "projectsByStatus": {}, "projectsByProvider": {}, "failureRate": 0,
              "daily": [{"date":"2026-08-28","created":0,"completed":0,"failed":0,
                "newUsers":0,"creditsGranted":0,"creditsUsed":0,"revenueVnd":0}],
              "events": [{"eventId":"evt-1","code":"OPEN","name":"Open",
                "claims":0,"creditsGranted":0,"remainingSlots":null}]
            }
        """.trimIndent()

        val stats = json.decodeFromString(AdminStatsDto.serializer(), payload).toDomain()

        assertEquals(0, stats.creditsGranted)
        assertEquals(0, stats.daily.single().newUsers)
        assertNull(stats.events.single().remainingSlots)
    }

    @Test
    fun `event update sends explicit nulls when an admin clears optional fields`() {
        val body = AdminEventDraft(
            code = "WEEKEND",
            name = "Weekend",
            description = null,
            kind = "grant",
            bonusCredits = 10,
            discountPercent = null,
            recurrence = "weekly",
            activeDays = null,
            activeFromMinute = null,
            activeToMinute = null,
            startsAt = "2026-08-28T00:00:00Z",
            endsAt = "2026-09-05T00:00:00Z",
            maxClaims = null,
            autoGrant = false,
        ).toUpdateRequest()

        assertEquals(JsonNull, body["maxClaims"])
        assertEquals(JsonNull, body["activeDays"])
        assertEquals(JsonNull, body["activeFromMinute"])
    }
}
