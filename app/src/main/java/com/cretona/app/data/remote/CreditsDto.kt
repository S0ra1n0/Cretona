package com.cretona.app.data.remote

import com.cretona.app.domain.model.ActiveDiscount
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.CreditTransaction
import com.cretona.app.domain.model.EventClaimResult
import com.cretona.app.domain.model.Page
import com.cretona.app.domain.model.PaymentReceipt
import com.cretona.app.domain.model.PromoEvent
import kotlinx.serialization.Serializable

/**
 * Wire types for credits, events and packages.
 * Contract: `docs/API_CONTRACT.md` Part II §6, §7, §8.
 *
 * **Request models must not give optional fields a default value.** The JSON
 * configuration uses `encodeDefaults = false`, so a field still equal to its
 * default is dropped from the body entirely and the server never sees it. That
 * is the bug `gender`/`birthday` hit; `CreditsSerializationTest` pins it here.
 */

// --- responses ---------------------------------------------------------------

@Serializable
data class CreditBalanceDto(
    val balance: Int,
    val generationCost: Int,
    val effectiveCost: Int,
    val activeDiscount: ActiveDiscountDto? = null,
    val lifetimeGranted: Int = 0,
    val lifetimeSpent: Int = 0,
)

@Serializable
data class ActiveDiscountDto(
    val eventId: String,
    val name: String,
    val discountPercent: Int,
    val endsAt: String,
)

@Serializable
data class CreditTransactionDto(
    val id: String,
    val delta: Int,
    val balanceAfter: Int,
    val reason: String,
    val refType: String? = null,
    val refId: String? = null,
    val note: String? = null,
    val createdAt: String,
)

@Serializable
data class CreditTransactionPageDto(
    val items: List<CreditTransactionDto> = emptyList(),
    val nextCursor: String? = null,
)

@Serializable
data class CreditPackageDto(
    val id: String,
    val name: String,
    val credits: Int,
    val priceVnd: Int,
    val sortOrder: Int = 0,
)

@Serializable
data class CreditPackageListDto(
    val items: List<CreditPackageDto> = emptyList(),
)

@Serializable
data class PaymentDto(
    val id: String,
    val status: String,
    val packageId: String,
    val amountVnd: Int,
    val creditsGranted: Int,
    val balance: Int,
    val method: String = "simulated",
    val createdAt: String,
    val completedAt: String? = null,
)

@Serializable
data class EventDto(
    val id: String,
    val code: String,
    val name: String,
    val description: String? = null,
    val kind: String,
    val bonusCredits: Int? = null,
    val discountPercent: Int? = null,
    val recurrence: String,
    val isActiveNow: Boolean = false,
    val activeUntil: String? = null,
    val nextActiveAt: String? = null,
    val claimable: Boolean = false,
    val claimedThisPeriod: Boolean = false,
    val remainingSlots: Int? = null,
)

@Serializable
data class EventPageDto(
    val items: List<EventDto> = emptyList(),
    val nextCursor: String? = null,
)

@Serializable
data class EventClaimDto(
    val creditsGranted: Int,
    val balance: Int,
    val transactionId: String,
)

// --- requests ----------------------------------------------------------------

/**
 * No default on [packageId]: see the file header. A defaulted field is dropped
 * from the request body and the server rejects the call as invalid.
 */
@Serializable
data class PaymentCreateRequest(
    val packageId: String,
)

// --- mappers -----------------------------------------------------------------

fun CreditBalanceDto.toDomain(): CreditBalance = CreditBalance(
    balance = balance,
    generationCost = generationCost,
    effectiveCost = effectiveCost,
    activeDiscount = activeDiscount?.toDomain(),
    lifetimeGranted = lifetimeGranted,
    lifetimeSpent = lifetimeSpent,
)

fun ActiveDiscountDto.toDomain(): ActiveDiscount = ActiveDiscount(
    eventId = eventId,
    name = name,
    discountPercent = discountPercent,
    endsAt = endsAt,
)

fun CreditTransactionDto.toDomain(): CreditTransaction = CreditTransaction(
    id = id,
    delta = delta,
    balanceAfter = balanceAfter,
    reason = reason,
    refType = refType,
    refId = refId,
    note = note,
    createdAt = createdAt,
)

fun CreditTransactionPageDto.toDomain(): Page<CreditTransaction> =
    Page(items.map { it.toDomain() }, nextCursor)

fun CreditPackageDto.toDomain(): CreditPackage = CreditPackage(
    id = id,
    name = name,
    credits = credits,
    priceVnd = priceVnd,
    sortOrder = sortOrder,
)

fun PaymentDto.toDomain(): PaymentReceipt = PaymentReceipt(
    id = id,
    status = status,
    packageId = packageId,
    amountVnd = amountVnd,
    creditsGranted = creditsGranted,
    balance = balance,
    method = method,
    createdAt = createdAt,
    completedAt = completedAt,
)

fun EventDto.toDomain(): PromoEvent = PromoEvent(
    id = id,
    code = code,
    name = name,
    description = description,
    kind = kind,
    bonusCredits = bonusCredits,
    discountPercent = discountPercent,
    recurrence = recurrence,
    isActiveNow = isActiveNow,
    activeUntil = activeUntil,
    nextActiveAt = nextActiveAt,
    claimable = claimable,
    claimedThisPeriod = claimedThisPeriod,
    remainingSlots = remainingSlots,
)

fun EventPageDto.toDomain(): Page<PromoEvent> =
    Page(items.map { it.toDomain() }, nextCursor)

fun EventClaimDto.toDomain(): EventClaimResult = EventClaimResult(
    creditsGranted = creditsGranted,
    balance = balance,
    transactionId = transactionId,
)
