package com.cretona.app.ui.admin

import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult

import com.cretona.app.domain.model.AdminMetrics

enum class AdminTab(val title: String) {
    STATS("Overview"),
    USERS("Users"),
    AUDIT_LOGS("Audit Logs"),
    DIAGNOSTICS("Diagnostics"),
}

data class AdminUiState(
    val selectedTab: AdminTab = AdminTab.STATS,
    // Set when the backend answers any admin call with 403. Hiding the entry
    // button is presentation, not authorization -- this is what makes the
    // screen itself refuse a non-admin who reaches it by some other route.
    val isForbidden: Boolean = false,
    // Stats Tab
    val stats: AdminStats? = null,
    val isLoadingStats: Boolean = false,
    val statsError: String? = null,
    // Users Tab
    val users: List<AdminUser> = emptyList(),
    val isLoadingUsers: Boolean = false,
    val usersError: String? = null,
    val userSearchQuery: String = "",
    val userRoleFilter: String? = null,
    val userStatusFilter: Boolean? = null,
    val updatingUserId: String? = null,
    val userActionMessage: String? = null,
    // Audit Logs Tab
    val auditLogs: List<AdminAuditLog> = emptyList(),
    val isLoadingLogs: Boolean = false,
    val logsError: String? = null,
    val logActionFilter: String? = null,
    // Diagnostics Tab
    val isBackfilling: Boolean = false,
    val backfillResult: BackfillResult? = null,
    val isCheckingHealth: Boolean = false,
    val healthResponse: HealthResponse? = null,
    val isLoadingMetrics: Boolean = false,
    val metrics: AdminMetrics? = null,
    val diagnosticsMessage: String? = null,
)
