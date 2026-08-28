package com.cretona.app.data.remote

import com.cretona.app.domain.model.AdminCreditAdjustment
import com.cretona.app.domain.model.AdminCreditTransaction
import com.cretona.app.domain.model.AdminEvent
import com.cretona.app.domain.model.AdminEventDraft
import com.cretona.app.domain.model.AdminPackage
import com.cretona.app.domain.model.AdminPackageDraft
import com.cretona.app.domain.model.AdminSettings
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

@Serializable
data class AdminCreditAdjustRequest(val delta: Int, val note: String? = null)

@Serializable
data class AdminCreditAdjustDto(
    val userId: String,
    val delta: Int,
    val balance: Int,
    val transactionId: String,
)

@Serializable
data class AdminCreditTransactionDto(
    val id: String,
    val userId: String,
    val delta: Int,
    val balanceAfter: Int,
    val reason: String,
    val note: String? = null,
    val createdAt: String,
)

@Serializable
data class AdminCreditTransactionPageDto(
    val items: List<AdminCreditTransactionDto> = emptyList(),
    val nextCursor: String? = null,
)

@Serializable
data class AdminSettingsDto(val generationCostCredits: Int)

@Serializable
data class AdminSettingsUpdateRequest(val generationCostCredits: Int)

@Serializable
data class AdminPackageDto(
    val id: String,
    val name: String,
    val credits: Int,
    val priceVnd: Int,
    val sortOrder: Int,
    val isActive: Boolean,
)

@Serializable
data class AdminPackageListDto(val items: List<AdminPackageDto> = emptyList())

@Serializable
data class AdminPackageCreateRequest(
    val name: String,
    val credits: Int,
    val priceVnd: Int,
    val sortOrder: Int,
)

@Serializable
data class AdminPackageUpdateRequest(
    val name: String? = null,
    val credits: Int? = null,
    val priceVnd: Int? = null,
    val sortOrder: Int? = null,
    val isActive: Boolean? = null,
)

@Serializable
data class AdminEventDto(
    val id: String,
    val code: String,
    val name: String,
    val description: String? = null,
    val kind: String,
    val bonusCredits: Int? = null,
    val discountPercent: Int? = null,
    val recurrence: String,
    val activeDays: String? = null,
    val activeFromMinute: Int? = null,
    val activeToMinute: Int? = null,
    val startsAt: String,
    val endsAt: String,
    val maxClaims: Int? = null,
    val autoGrant: Boolean,
    val isActive: Boolean,
)

@Serializable
data class AdminEventListDto(val items: List<AdminEventDto> = emptyList())

@Serializable
data class AdminEventCreateRequest(
    val code: String,
    val name: String,
    val description: String? = null,
    val kind: String,
    val bonusCredits: Int? = null,
    val discountPercent: Int? = null,
    val recurrence: String,
    val activeDays: String? = null,
    val activeFromMinute: Int? = null,
    val activeToMinute: Int? = null,
    val startsAt: String,
    val endsAt: String,
    val maxClaims: Int? = null,
    val autoGrant: Boolean = false,
)

fun AdminCreditAdjustDto.toDomain() = AdminCreditAdjustment(userId, delta, balance, transactionId)

fun AdminCreditTransactionDto.toDomain() = AdminCreditTransaction(
    id, userId, delta, balanceAfter, reason, note, createdAt,
)

fun AdminSettingsDto.toDomain() = AdminSettings(generationCostCredits)

fun AdminPackageDto.toDomain() = AdminPackage(id, name, credits, priceVnd, sortOrder, isActive)

fun AdminEventDto.toDomain() = AdminEvent(
    id = id,
    code = code,
    name = name,
    description = description,
    kind = kind,
    bonusCredits = bonusCredits,
    discountPercent = discountPercent,
    recurrence = recurrence,
    activeDays = activeDays,
    activeFromMinute = activeFromMinute,
    activeToMinute = activeToMinute,
    startsAt = startsAt,
    endsAt = endsAt,
    maxClaims = maxClaims,
    autoGrant = autoGrant,
    isActive = isActive,
)

fun AdminPackageDraft.toCreateRequest() = AdminPackageCreateRequest(name, credits, priceVnd, sortOrder)

fun AdminPackageDraft.toUpdateRequest() = AdminPackageUpdateRequest(
    name, credits, priceVnd, sortOrder, isActive,
)

fun AdminEventDraft.toCreateRequest() = AdminEventCreateRequest(
    code = code,
    name = name,
    description = description,
    kind = kind,
    bonusCredits = bonusCredits,
    discountPercent = discountPercent,
    recurrence = recurrence,
    activeDays = activeDays,
    activeFromMinute = activeFromMinute,
    activeToMinute = activeToMinute,
    startsAt = startsAt,
    endsAt = endsAt,
    maxClaims = maxClaims,
    autoGrant = autoGrant,
)

fun AdminEventDraft.toUpdateRequest(): JsonObject = buildJsonObject {
    put("name", name)
    put("description", description?.let(::JsonPrimitive) ?: JsonNull)
    put("bonusCredits", bonusCredits?.let(::JsonPrimitive) ?: JsonNull)
    put("discountPercent", discountPercent?.let(::JsonPrimitive) ?: JsonNull)
    put("activeDays", activeDays?.let(::JsonPrimitive) ?: JsonNull)
    put("activeFromMinute", activeFromMinute?.let(::JsonPrimitive) ?: JsonNull)
    put("activeToMinute", activeToMinute?.let(::JsonPrimitive) ?: JsonNull)
    put("startsAt", startsAt)
    put("endsAt", endsAt)
    put("maxClaims", maxClaims?.let(::JsonPrimitive) ?: JsonNull)
    put("isActive", isActive)
}
