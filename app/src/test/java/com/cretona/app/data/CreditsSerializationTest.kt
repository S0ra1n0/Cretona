package com.cretona.app.data

import com.cretona.app.data.remote.CreditBalanceDto
import com.cretona.app.data.remote.CreditTransactionPageDto
import com.cretona.app.data.remote.EventPageDto
import com.cretona.app.data.remote.PaymentCreateRequest
import com.cretona.app.data.remote.toDomain
import com.cretona.app.di.NetworkModule
import com.cretona.app.domain.model.CreditReason
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Credit wire shapes, encoded and decoded with the real app JSON config.
 *
 * The request half of this exists because of a bug that already shipped once:
 * `encodeDefaults = false` drops any property still equal to its declared
 * default, so an optional field with a default never reaches the server. On
 * `MeUpdateRequest` that turned every "clear my gender" into "leave it alone".
 * On a payment it would drop the package id and the purchase would fail
 * validation for no visible reason.
 */
class CreditsSerializationTest {
    private val json = NetworkModule.provideJson()

    // --- requests ------------------------------------------------------------

    @Test
    fun `payment request always sends the package id`() {
        val body = json.encodeToString(
            PaymentCreateRequest.serializer(),
            PaymentCreateRequest(packageId = "pkg-1"),
        )

        assertTrue("packageId missing from $body", body.contains("\"packageId\":\"pkg-1\""))
    }

    @Test
    fun `payment request has no defaulted fields to drop`() {
        // A regression guard rather than a behaviour test: if someone adds
        // `= null` or `= ""` to a field here, encodeDefaults = false will drop
        // it and this catches that at the declaration, before it reaches an API.
        val descriptor = PaymentCreateRequest.serializer().descriptor
        for (index in 0 until descriptor.elementsCount) {
            assertFalse(
                "${descriptor.getElementName(index)} has a default and will be " +
                    "dropped from the request body",
                descriptor.isElementOptional(index),
            )
        }
    }

    // --- responses -----------------------------------------------------------

    @Test
    fun `balance decodes with a discount running`() {
        val payload = """
            {
              "balance": 25,
              "generationCost": 2,
              "effectiveCost": 1,
              "activeDiscount": {
                "eventId": "evt-hot", "name": "Hot Hours",
                "discountPercent": 50, "endsAt": "2026-08-28T15:00:00Z"
              },
              "lifetimeGranted": 35,
              "lifetimeSpent": 10
            }
        """.trimIndent()

        val balance = json.decodeFromString(CreditBalanceDto.serializer(), payload).toDomain()

        assertEquals(25, balance.balance)
        assertEquals(2, balance.generationCost)
        assertEquals(1, balance.effectiveCost)
        assertEquals(50, balance.activeDiscount?.discountPercent)
    }

    @Test
    fun `balance decodes with no discount`() {
        val payload = """
            {"balance": 3, "generationCost": 1, "effectiveCost": 1, "activeDiscount": null}
        """.trimIndent()

        val balance = json.decodeFromString(CreditBalanceDto.serializer(), payload).toDomain()

        assertNull(balance.activeDiscount)
        assertEquals(0, balance.lifetimeGranted)
    }

    @Test
    fun `an unknown transaction reason survives decoding`() {
        // The server may add a reason before the app ships again. Rendering the
        // raw value is acceptable; crashing a screen is not, which is why
        // `reason` is a String and not an enum.
        val payload = """
            {"items": [{
              "id": "tx-1", "delta": 4, "balanceAfter": 9,
              "reason": "loyalty_bonus", "createdAt": "2026-08-28T13:20:11Z"
            }], "nextCursor": null}
        """.trimIndent()

        val page = json.decodeFromString(CreditTransactionPageDto.serializer(), payload).toDomain()

        assertEquals(1, page.items.size)
        assertEquals("loyalty_bonus", page.items[0].reason)
        // Falls back to showing the raw value rather than an empty label.
        assertEquals("loyalty_bonus", CreditReason.label("loyalty_bonus"))
        assertTrue(page.items[0].isCredit)
    }

    @Test
    fun `known reasons get human labels`() {
        assertEquals("Welcome bonus", CreditReason.label(CreditReason.SIGNUP_BONUS))
        assertEquals("Video generated", CreditReason.label(CreditReason.GENERATION))
        assertEquals("Refunded", CreditReason.label(CreditReason.REFUND))
    }

    @Test
    fun `an unexpected response field does not break decoding`() {
        // ignoreUnknownKeys: the server adding a field must not break a shipped
        // app, which is the whole reason additive API changes are safe.
        val payload = """
            {"balance": 1, "generationCost": 1, "effectiveCost": 1, "somethingNew": true}
        """.trimIndent()

        val balance = json.decodeFromString(CreditBalanceDto.serializer(), payload)

        assertEquals(1, balance.balance)
    }

    @Test
    fun `events decode both kinds`() {
        val payload = """
            {"items": [
              {"id": "e1", "code": "HOT_HOURS", "name": "Hot Hours", "kind": "discount",
               "discountPercent": 50, "recurrence": "daily", "isActiveNow": true,
               "claimable": false},
              {"id": "e2", "code": "WEEKEND_GIFT", "name": "Weekend Gift", "kind": "grant",
               "bonusCredits": 10, "recurrence": "weekly", "isActiveNow": true,
               "claimable": true, "remainingSlots": 463}
            ], "nextCursor": null}
        """.trimIndent()

        val page = json.decodeFromString(EventPageDto.serializer(), payload).toDomain()

        val discount = page.items[0]
        val grant = page.items[1]

        assertTrue(discount.isDiscount)
        // A discount is never claimable: it applies on its own, and a button
        // here would be a button that always fails.
        assertFalse(discount.claimable)
        assertNull(discount.bonusCredits)

        assertTrue(grant.isGrant)
        assertTrue(grant.claimable)
        assertEquals(10, grant.bonusCredits)
        assertEquals(463, grant.remainingSlots)
    }

    @Test
    fun `an uncapped event decodes remainingSlots as null`() {
        val payload = """
            {"items": [{"id": "e1", "code": "C", "name": "N", "kind": "grant",
             "bonusCredits": 5, "recurrence": "once"}], "nextCursor": null}
        """.trimIndent()

        val page = json.decodeFromString(EventPageDto.serializer(), payload).toDomain()

        assertNull(page.items[0].remainingSlots)
        assertFalse(page.items[0].claimable)
    }
}
