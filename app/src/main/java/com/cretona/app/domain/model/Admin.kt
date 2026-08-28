package com.cretona.app.domain.model

import androidx.compose.runtime.Immutable

@Immutable
data class AdminStats(
    val totalUsers: Int,
    val activeUsers: Int,
    val totalProjects: Int,
    val failureRate: Double,
    val projectsByStatus: Map<String, Int>,
    val projectsByProvider: Map<String, Int>,
    val daily: List<DailyStats>,
    val creditsGranted: Int = 0,
    val creditsUsed: Int = 0,
    val revenueVnd: Int = 0,
    val events: List<AdminEventStat> = emptyList(),
)

@Immutable
data class DailyStats(
    val date: String,
    val created: Int,
    val completed: Int,
    val failed: Int,
    val newUsers: Int = 0,
    val creditsGranted: Int = 0,
    val creditsUsed: Int = 0,
    val revenueVnd: Int = 0,
)

@Immutable
data class AdminEventStat(
    val eventId: String,
    val code: String,
    val name: String,
    val claims: Int,
    val creditsGranted: Int,
    val remainingSlots: Int?,
)

@Immutable
data class AdminCreditTransaction(
    val id: String,
    val userId: String,
    val delta: Int,
    val balanceAfter: Int,
    val reason: String,
    val note: String?,
    val createdAt: String,
)

@Immutable
data class AdminCreditAdjustment(
    val userId: String,
    val delta: Int,
    val balance: Int,
    val transactionId: String,
)

@Immutable
data class AdminPackage(
    val id: String,
    val name: String,
    val credits: Int,
    val priceVnd: Int,
    val sortOrder: Int,
    val isActive: Boolean,
)

data class AdminPackageDraft(
    val name: String,
    val credits: Int,
    val priceVnd: Int,
    val sortOrder: Int,
    val isActive: Boolean = true,
)

@Immutable
data class AdminEvent(
    val id: String,
    val code: String,
    val name: String,
    val description: String?,
    val kind: String,
    val bonusCredits: Int?,
    val discountPercent: Int?,
    val recurrence: String,
    val activeDays: String?,
    val activeFromMinute: Int?,
    val activeToMinute: Int?,
    val startsAt: String,
    val endsAt: String,
    val maxClaims: Int?,
    val autoGrant: Boolean,
    val isActive: Boolean,
)

data class AdminEventDraft(
    val code: String,
    val name: String,
    val description: String?,
    val kind: String,
    val bonusCredits: Int?,
    val discountPercent: Int?,
    val recurrence: String,
    val activeDays: String?,
    val activeFromMinute: Int?,
    val activeToMinute: Int?,
    val startsAt: String,
    val endsAt: String,
    val maxClaims: Int?,
    val autoGrant: Boolean,
    val isActive: Boolean = true,
)

@Immutable
data class AdminSettings(val generationCostCredits: Int)

@Immutable
data class AdminUser(
    val id: String,
    val email: String?,
    val username: String?,
    val role: String,
    val isDisabled: Boolean,
    val createdAt: String,
    val projectCount: Int,
)

@Immutable
data class AdminAuditLog(
    val id: String,
    val actorId: String,
    val action: String,
    val targetType: String,
    val targetId: String?,
    val createdAt: String,
)

@Immutable
data class BackfillResult(
    val backfilled: Int,
    val processed: Int,
)

@Immutable
data class AdminMetrics(
    val uptimeSeconds: Float,
    val activeJobs: Int,
    val completedJobs: Int,
    val failedJobs: Int,
    val memoryRssMb: Float,
    val databaseBackend: String,
    val databaseStatus: String,
    val storageBackend: String,
)
