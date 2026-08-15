package com.cretona.app.ui.admin

import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult

enum class AdminTab(val title: String) {
    STATS("Overview"),
    USERS("Users"),
    AUDIT_LOGS("Audit Logs"),
    DIAGNOSTICS("Diagnostics"),
}

data class AdminUiState(
    val selectedTab: AdminTab = AdminTab.STATS,
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
    val diagnosticsMessage: String? = null,
)
