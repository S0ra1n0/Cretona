package com.cretona.app.domain.model

/**
 * Credits, events and packages.
 *
 * Wire shapes are specified in `docs/API_CONTRACT.md` Part II. These are the
 * domain types the UI binds to; the DTOs in `data/remote/CreditsDto.kt` map
 * onto them so a wire change does not reach a Composable.
 */

/**
 * What the Credits screen and the Create screen both need.
 *
 * [generationCost] is the configured base price. [effectiveCost] is what the
 * next generation will actually cost after any running discount, and is the
 * number to show — a user told "1 credit" and charged 2 has been misled.
 */
data class CreditBalance(
    val balance: Int,
    val generationCost: Int,
    val effectiveCost: Int,
    val activeDiscount: ActiveDiscount?,
    val lifetimeGranted: Int,
    val lifetimeSpent: Int,
)

data class ActiveDiscount(
    val eventId: String,
    val name: String,
    val discountPercent: Int,
    val endsAt: String,
)

/**
 * One row of the ledger.
 *
 * [reason] stays a String rather than an enum on purpose: the server may add a
 * reason before the app ships again, and an unknown value must render as
 * itself rather than crash a screen. [CreditReason] holds the known values for
 * mapping to a label and an icon.
 */
data class CreditTransaction(
    val id: String,
    val delta: Int,
    val balanceAfter: Int,
    val reason: String,
    val refType: String?,
    val refId: String?,
    val note: String?,
    val createdAt: String,
) {
    val isCredit: Boolean get() = delta > 0
}

object CreditReason {
    const val SIGNUP_BONUS = "signup_bonus"
    const val EVENT_GRANT = "event_grant"
    const val PURCHASE = "purchase"
    const val GENERATION = "generation"
    const val REFUND = "refund"
    const val ADMIN_ADJUSTMENT = "admin_adjustment"

    /** A human label, falling back to the raw value for anything unrecognised. */
    fun label(reason: String): String = when (reason) {
        SIGNUP_BONUS -> "Welcome bonus"
        EVENT_GRANT -> "Event reward"
        PURCHASE -> "Credits purchased"
        GENERATION -> "Video generated"
        REFUND -> "Refunded"
        ADMIN_ADJUSTMENT -> "Adjusted by admin"
        else -> reason
    }
}

data class CreditPackage(
    val id: String,
    val name: String,
    val credits: Int,
    val priceVnd: Int,
    val sortOrder: Int,
)

data class PaymentReceipt(
    val id: String,
    val status: String,
    val packageId: String,
    val amountVnd: Int,
    val creditsGranted: Int,
    val balance: Int,
    val method: String,
    val createdAt: String,
    val completedAt: String?,
)

/**
 * A promotion. One shape covers both kinds:
 *
 *  - `grant` gives credits and is claimed with a button,
 *  - `discount` reduces the generation cost and applies by itself.
 *
 * [claimable] is computed by the server and is **the only thing the button
 * should bind to**. Re-deriving it here from the window, the cap and the claim
 * history would put the rule in two places, and the one that gives away
 * credits when they disagree is this one.
 */
data class PromoEvent(
    val id: String,
    val code: String,
    val name: String,
    val description: String?,
    val kind: String,
    val bonusCredits: Int?,
    val discountPercent: Int?,
    val recurrence: String,
    val isActiveNow: Boolean,
    val activeUntil: String?,
    val nextActiveAt: String?,
    val claimable: Boolean,
    val claimedThisPeriod: Boolean,
    val remainingSlots: Int?,
) {
    val isGrant: Boolean get() = kind == EventKind.GRANT
    val isDiscount: Boolean get() = kind == EventKind.DISCOUNT
}

object EventKind {
    const val GRANT = "grant"
    const val DISCOUNT = "discount"
}

data class EventClaimResult(
    val creditsGranted: Int,
    val balance: Int,
    val transactionId: String,
)

/** A cursor-paged slice. `nextCursor == null` means the last page. */
data class Page<T>(
    val items: List<T>,
    val nextCursor: String?,
)
