package com.cretona.app.data

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.ActiveDiscount
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.CreditReason
import com.cretona.app.domain.model.CreditTransaction
import com.cretona.app.domain.model.EventClaimResult
import com.cretona.app.domain.model.EventKind
import com.cretona.app.domain.model.Page
import com.cretona.app.domain.model.PaymentReceipt
import com.cretona.app.domain.model.PromoEvent
import com.cretona.app.domain.repository.CreditsRepository
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * An in-memory stand-in for the credits backend (B-02).
 *
 * Its whole purpose is to unblock the Android lane: the Credits, Buy and
 * Events screens can be built, previewed and demoed today, against the shapes
 * agreed in `docs/API_CONTRACT.md` Part II, while the endpoints are still
 * being written. Swap the Hilt binding to the real implementation and the
 * screens do not change.
 *
 * It reproduces the behaviours a screen must actually handle, rather than
 * always succeeding:
 *
 *  - a purchase or claim replayed with the same idempotency key does not grant
 *    twice, so retry logic can be tested;
 *  - a charge beyond the balance fails the way the server fails it;
 *  - claiming a `discount` event is refused, because discounts apply by
 *    themselves and should never have offered a button.
 *
 * Delays are deliberate: a screen built against instant responses hides every
 * missing loading state.
 */
@Singleton
class FakeCreditsRepository @Inject constructor() : CreditsRepository {

    private val mutex = Mutex()

    private var balance = 15
    private var lifetimeGranted = 20
    private var lifetimeSpent = 5

    private val ledger = mutableListOf(
        CreditTransaction(
            id = "tx-3", delta = -1, balanceAfter = 15, reason = CreditReason.GENERATION,
            refType = "project", refId = "demo-3", note = "Hot Hours -50%",
            createdAt = "2026-08-28T13:20:11Z",
        ),
        CreditTransaction(
            id = "tx-2", delta = 10, balanceAfter = 16, reason = CreditReason.EVENT_GRANT,
            refType = "event", refId = "evt-weekend", note = "Weekend Gift",
            createdAt = "2026-08-23T02:00:00Z",
        ),
        CreditTransaction(
            id = "tx-1", delta = 5, balanceAfter = 6, reason = CreditReason.SIGNUP_BONUS,
            refType = null, refId = null, note = null,
            createdAt = "2026-08-20T08:12:44Z",
        ),
    )

    private val packages = listOf(
        CreditPackage("pkg-1", "Starter", credits = 10, priceVnd = 20_000, sortOrder = 1),
        CreditPackage("pkg-2", "Creator", credits = 50, priceVnd = 90_000, sortOrder = 2),
        CreditPackage("pkg-3", "Studio", credits = 150, priceVnd = 250_000, sortOrder = 3),
    )

    private val events = mutableListOf(
        PromoEvent(
            id = "evt-hot", code = "HOT_HOURS", name = "Hot Hours",
            description = "Half price on every generation, 20:00-22:00 daily.",
            kind = EventKind.DISCOUNT, bonusCredits = null, discountPercent = 50,
            recurrence = "daily", isActiveNow = true,
            activeUntil = "2026-08-28T15:00:00Z", nextActiveAt = null,
            // Discounts are never claimable: they apply on their own.
            claimable = false, claimedThisPeriod = false, remainingSlots = null,
        ),
        PromoEvent(
            id = "evt-weekend", code = "WEEKEND_GIFT", name = "Weekend Gift",
            description = "+10 credits every weekend.",
            kind = EventKind.GRANT, bonusCredits = 10, discountPercent = null,
            recurrence = "weekly", isActiveNow = true,
            activeUntil = "2026-08-31T17:00:00Z", nextActiveAt = null,
            claimable = true, claimedThisPeriod = false, remainingSlots = 463,
        ),
        PromoEvent(
            id = "evt-national", code = "NATIONAL_DAY", name = "Quoc khanh 2/9",
            description = "Twenty credits to celebrate National Day.",
            kind = EventKind.GRANT, bonusCredits = 20, discountPercent = null,
            recurrence = "once", isActiveNow = false,
            activeUntil = null, nextActiveAt = "2026-09-01T17:00:00Z",
            // Upcoming, so not yet claimable. The card shows a countdown.
            claimable = false, claimedThisPeriod = false, remainingSlots = 1000,
        ),
        PromoEvent(
            id = "evt-surprise", code = "WELCOME_BACK", name = "Surprise drop",
            description = "A thank-you from the Cretona team.",
            kind = EventKind.GRANT, bonusCredits = 15, discountPercent = null,
            recurrence = "once", isActiveNow = true,
            activeUntil = "2026-09-30T17:00:00Z", nextActiveAt = null,
            // Already taken: the button reads "Claimed" and is disabled.
            claimable = false, claimedThisPeriod = true, remainingSlots = 0,
        ),
    )

    /** Idempotency keys already honoured, mapped to what they returned. */
    private val seenKeys = mutableMapOf<String, Any>()

    override suspend fun getBalance(): AppResult<CreditBalance> = mutex.withLock {
        delay(FAKE_LATENCY_MS)
        val discount = events.firstOrNull { it.isDiscount && it.isActiveNow }
        AppResult.Success(
            CreditBalance(
                balance = balance,
                generationCost = BASE_COST,
                effectiveCost = effectiveCost(discount?.discountPercent),
                activeDiscount = discount?.let {
                    ActiveDiscount(
                        eventId = it.id,
                        name = it.name,
                        discountPercent = it.discountPercent ?: 0,
                        endsAt = it.activeUntil.orEmpty(),
                    )
                },
                lifetimeGranted = lifetimeGranted,
                lifetimeSpent = lifetimeSpent,
            ),
        )
    }

    override suspend fun getTransactions(
        limit: Int,
        cursor: String?,
    ): AppResult<Page<CreditTransaction>> = mutex.withLock {
        delay(FAKE_LATENCY_MS)
        // Cursor is the index of the first item on the next page. Opaque to the
        // caller, exactly like the real one.
        val start = cursor?.toIntOrNull() ?: 0
        val slice = ledger.drop(start).take(limit)
        val next = (start + limit).takeIf { it < ledger.size }?.toString()
        AppResult.Success(Page(slice, next))
    }

    override suspend fun getPackages(): AppResult<List<CreditPackage>> = mutex.withLock {
        delay(FAKE_LATENCY_MS)
        AppResult.Success(packages.sortedBy { it.sortOrder })
    }

    override suspend fun purchase(
        packageId: String,
        idempotencyKey: String,
    ): AppResult<PaymentReceipt> = mutex.withLock {
        delay(FAKE_LATENCY_MS * 2)

        (seenKeys[idempotencyKey] as? PaymentReceipt)?.let {
            return AppResult.Success(it)
        }

        val chosen = packages.firstOrNull { it.id == packageId }
            ?: return AppResult.Failure(AppError.NotFound("That package is no longer available."))

        balance += chosen.credits
        lifetimeGranted += chosen.credits
        val receipt = PaymentReceipt(
            id = "pay-${UUID.randomUUID()}",
            status = "completed",
            packageId = chosen.id,
            amountVnd = chosen.priceVnd,
            creditsGranted = chosen.credits,
            balance = balance,
            method = "simulated",
            createdAt = "2026-08-28T14:00:00Z",
            completedAt = "2026-08-28T14:00:00Z",
        )
        ledger.add(
            0,
            CreditTransaction(
                id = "tx-${UUID.randomUUID()}",
                delta = chosen.credits,
                balanceAfter = balance,
                reason = CreditReason.PURCHASE,
                refType = "payment",
                refId = receipt.id,
                note = chosen.name,
                createdAt = receipt.createdAt,
            ),
        )
        seenKeys[idempotencyKey] = receipt
        AppResult.Success(receipt)
    }

    override suspend fun getEvents(cursor: String?): AppResult<Page<PromoEvent>> =
        mutex.withLock {
            delay(FAKE_LATENCY_MS)
            AppResult.Success(Page(events.toList(), null))
        }

    override suspend fun claimEvent(
        eventId: String,
        idempotencyKey: String,
    ): AppResult<EventClaimResult> = mutex.withLock {
        delay(FAKE_LATENCY_MS)

        (seenKeys[idempotencyKey] as? EventClaimResult)?.let {
            return AppResult.Success(it)
        }

        val index = events.indexOfFirst { it.id == eventId }
        if (index < 0) {
            return AppResult.Failure(AppError.NotFound("That event no longer exists."))
        }
        val event = events[index]

        // Mirrors the server's refusals so the screen has to handle them.
        if (event.isDiscount) {
            return AppResult.Failure(
                AppError.Server(409, "This discount applies automatically."),
            )
        }
        if (event.claimedThisPeriod) {
            return AppResult.Failure(
                AppError.Server(409, "You have already claimed this one."),
            )
        }
        if (!event.isActiveNow) {
            return AppResult.Failure(AppError.Server(409, "This event is not running."))
        }
        if (event.remainingSlots != null && event.remainingSlots <= 0) {
            return AppResult.Failure(AppError.Server(409, "This event is fully claimed."))
        }

        val granted = event.bonusCredits ?: 0
        balance += granted
        lifetimeGranted += granted
        events[index] = event.copy(
            claimable = false,
            claimedThisPeriod = true,
            remainingSlots = event.remainingSlots?.minus(1),
        )
        val transactionId = "tx-${UUID.randomUUID()}"
        ledger.add(
            0,
            CreditTransaction(
                id = transactionId,
                delta = granted,
                balanceAfter = balance,
                reason = CreditReason.EVENT_GRANT,
                refType = "event",
                refId = event.id,
                note = event.name,
                createdAt = "2026-08-28T14:05:00Z",
            ),
        )
        val result = EventClaimResult(granted, balance, transactionId)
        seenKeys[idempotencyKey] = result
        AppResult.Success(result)
    }

    private fun effectiveCost(discountPercent: Int?): Int {
        if (discountPercent == null || discountPercent == 0) return BASE_COST
        val remaining = Math.round(BASE_COST * (100 - discountPercent) / 100.0).toInt()
        return maxOf(1, remaining)
    }

    private companion object {
        const val BASE_COST = 2
        const val FAKE_LATENCY_MS = 350L
    }
}
