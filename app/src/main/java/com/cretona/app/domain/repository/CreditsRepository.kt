package com.cretona.app.domain.repository

import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.CreditTransaction
import com.cretona.app.domain.model.EventClaimResult
import com.cretona.app.domain.model.Page
import com.cretona.app.domain.model.PaymentReceipt
import com.cretona.app.domain.model.PromoEvent

/**
 * Credits, events and packages.
 *
 * Split from [CretonaRepository] rather than added to it: the screens that use
 * this are new, the ones that use the other are not, and a fake of this one
 * can stand in for the whole feature while the backend is being written.
 *
 * Contract: `docs/API_CONTRACT.md` Part II.
 */
interface CreditsRepository {

    /** Balance, base cost, and what the next generation actually costs now. */
    suspend fun getBalance(): AppResult<CreditBalance>

    /** The ledger, newest first. Pass the previous page's cursor to continue. */
    suspend fun getTransactions(
        limit: Int = 20,
        cursor: String? = null,
    ): AppResult<Page<CreditTransaction>>

    suspend fun getPackages(): AppResult<List<CreditPackage>>

    /**
     * Buys a package. No real money moves — see `ADR-010`.
     *
     * [idempotencyKey] must be generated once per user intent and reused across
     * retries of that same intent. Generating a fresh one on retry is the same
     * as having none.
     */
    suspend fun purchase(
        packageId: String,
        idempotencyKey: String,
    ): AppResult<PaymentReceipt>

    /** Live and upcoming events, with this caller's claim state on each. */
    suspend fun getEvents(cursor: String? = null): AppResult<Page<PromoEvent>>

    /**
     * Claims a `grant` event.
     *
     * Only call this when [PromoEvent.claimable] is true. The server enforces
     * the window, the cap and one-claim-per-period regardless, returning
     * `EVENT_NOT_ACTIVE`, `EVENT_FULL` or `EVENT_ALREADY_CLAIMED` — but a UI
     * that offers a button it knows will fail is a UI that looks broken.
     */
    suspend fun claimEvent(
        eventId: String,
        idempotencyKey: String,
    ): AppResult<EventClaimResult>
}
