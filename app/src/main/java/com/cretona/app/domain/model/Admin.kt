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
)

@Immutable
data class DailyStats(
    val date: String,
    val created: Int,
    val completed: Int,
    val failed: Int,
)

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
