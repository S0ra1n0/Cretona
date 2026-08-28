package com.cretona.app.ui.admin

import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult

import com.cretona.app.domain.model.AdminMetrics
import com.cretona.app.domain.model.AdminCreditTransaction
import com.cretona.app.domain.model.AdminEvent
import com.cretona.app.domain.model.AdminPackage
import com.cretona.app.domain.model.AdminSettings
import com.cretona.app.domain.model.VideoProject

enum class AdminTab(val title: String) {
    STATS("Overview"),
    USERS("Users"),
    AUDIT_LOGS("Audit Logs"),
    DIAGNOSTICS("Diagnostics"),
    VIDEOS("Videos"),
    CREDITS("Credits & Transactions"),
    EVENTS("Events"),
    PACKAGES("Credit Packages"),
    SETTINGS("Settings"),
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
    val isLoadingMoreUsers: Boolean = false,
    val usersNextCursor: String? = null,
    val hasMoreUsers: Boolean = false,
    val usersError: String? = null,
    val userSearchQuery: String = "",
    val userRoleFilter: String? = null,
    val userStatusFilter: Boolean? = null,
    val updatingUserId: String? = null,
    val userActionMessage: String? = null,
    // Audit Logs Tab
    val auditLogs: List<AdminAuditLog> = emptyList(),
    val isLoadingLogs: Boolean = false,
    val isLoadingMoreLogs: Boolean = false,
    val logsNextCursor: String? = null,
    val hasMoreLogs: Boolean = false,
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
    // Manage screens
    val adminProjects: List<VideoProject> = emptyList(),
    val projectsNextCursor: String? = null,
    val projectStatusFilter: String? = null,
    val projectOwnerFilter: String = "",
    val creditTransactions: List<AdminCreditTransaction> = emptyList(),
    val creditTransactionsNextCursor: String? = null,
    val creditUserFilter: String = "",
    val creditReasonFilter: String? = null,
    val packages: List<AdminPackage> = emptyList(),
    val events: List<AdminEvent> = emptyList(),
    val settings: AdminSettings? = null,
    val isLoadingManagement: Boolean = false,
    val isLoadingMoreManagement: Boolean = false,
    val isSavingManagement: Boolean = false,
    val managementError: String? = null,
    val managementMessage: String? = null,
)
