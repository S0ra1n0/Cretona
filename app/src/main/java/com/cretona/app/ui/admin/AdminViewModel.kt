package com.cretona.app.ui.admin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AdminViewModel @Inject constructor(
    private val repository: CretonaRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AdminUiState())
    val state: StateFlow<AdminUiState> = _state.asStateFlow()

    private var usersJob: Job? = null
    private var logsJob: Job? = null

    init {
        loadStats()
    }

    fun selectTab(tab: AdminTab) {
        _state.update { it.copy(selectedTab = tab) }
        when (tab) {
            AdminTab.STATS -> if (_state.value.stats == null) loadStats()
            AdminTab.USERS -> if (_state.value.users.isEmpty()) loadUsers()
            AdminTab.AUDIT_LOGS -> if (_state.value.auditLogs.isEmpty()) loadAuditLogs()
            AdminTab.DIAGNOSTICS -> {
                if (_state.value.healthResponse == null) runHealthCheck()
                if (_state.value.metrics == null) loadMetrics()
            }
        }
    }

    /**
     * A 403 from any admin endpoint is authoritative: the backend decided this
     * caller is not an admin, so the screen stops presenting itself as one.
     */
    private fun AppError.markIfForbidden() {
        if (this is AppError.Forbidden) {
            _state.update { it.copy(isForbidden = true) }
        }
    }

    fun loadStats(days: Int = 30) {
        viewModelScope.launch {
            _state.update { it.copy(isLoadingStats = true, statsError = null) }
            when (val result = repository.getAdminStats(days)) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isLoadingStats = false,
                            stats = result.data,
                            statsError = null,
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            isLoadingStats = false,
                            statsError = result.error.message,
                        )
                    }
                }
            }
        }
    }

    fun loadUsers() {
        // Cancelling the previous request is what stops a slower earlier
        // response from landing after a newer one and winning.
        usersJob?.cancel()
        usersJob = viewModelScope.launch { loadUsersNow(cursor = null, append = false) }
    }

    fun loadMoreUsers() {
        val current = _state.value
        val cursor = current.usersNextCursor
        if (!current.hasMoreUsers || cursor.isNullOrBlank() || current.isLoadingMoreUsers) {
            return
        }
        usersJob?.cancel()
        usersJob = viewModelScope.launch { loadUsersNow(cursor = cursor, append = true) }
    }

    private suspend fun loadUsersNow(cursor: String?, append: Boolean) {
        _state.update {
            it.copy(
                isLoadingUsers = !append,
                isLoadingMoreUsers = append,
                usersError = null,
                usersNextCursor = if (append) it.usersNextCursor else null,
                hasMoreUsers = if (append) it.hasMoreUsers else false,
            )
        }
        val current = _state.value
        when (
            val result = repository.getAdminUsers(
                cursor = cursor,
                query = current.userSearchQuery.ifBlank { null },
                role = current.userRoleFilter,
                isDisabled = current.userStatusFilter,
            )
        ) {
            is AppResult.Success -> {
                _state.update {
                    it.copy(
                        isLoadingUsers = false,
                        isLoadingMoreUsers = false,
                        users = if (append) {
                            (it.users + result.data.items).distinctBy(AdminUser::id)
                        } else {
                            result.data.items
                        },
                        usersNextCursor = result.data.nextCursor,
                        hasMoreUsers = result.data.hasMore,
                        usersError = null,
                    )
                }
            }
            is AppResult.Failure -> {
                result.error.markIfForbidden()
                _state.update {
                    it.copy(
                        isLoadingUsers = false,
                        isLoadingMoreUsers = false,
                        usersError = result.error.message,
                    )
                }
            }
        }
    }

    fun onSearchQueryChanged(query: String) {
        _state.update {
            it.copy(
                userSearchQuery = query,
                usersNextCursor = null,
                hasMoreUsers = false,
            )
        }
        // Debounced: a keystroke-per-request search both floods the server and
        // races itself, because responses need not arrive in send order.
        usersJob?.cancel()
        usersJob = viewModelScope.launch {
            delay(SEARCH_DEBOUNCE_MS)
            loadUsersNow(cursor = null, append = false)
        }
    }

    fun onRoleFilterChanged(role: String?) {
        _state.update { it.copy(userRoleFilter = role) }
        loadUsers()
    }

    fun onStatusFilterChanged(isDisabled: Boolean?) {
        _state.update { it.copy(userStatusFilter = isDisabled) }
        loadUsers()
    }

    fun toggleUserRole(user: AdminUser) {
        val newRole = if (user.role == "admin") "user" else "admin"
        viewModelScope.launch {
            _state.update { it.copy(updatingUserId = user.id, userActionMessage = null) }
            when (val result = repository.updateAdminUser(id = user.id, role = newRole)) {
                is AppResult.Success -> {
                    _state.update { s ->
                        s.copy(
                            updatingUserId = null,
                            users = s.users.map { if (it.id == user.id) result.data else it },
                            userActionMessage = "Updated ${user.email ?: user.username ?: user.id} to $newRole",
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            updatingUserId = null,
                            userActionMessage = "Failed: ${result.error.message}",
                        )
                    }
                }
            }
        }
    }

    fun toggleUserDisabled(user: AdminUser) {
        val newDisabled = !user.isDisabled
        viewModelScope.launch {
            _state.update { it.copy(updatingUserId = user.id, userActionMessage = null) }
            when (val result = repository.updateAdminUser(id = user.id, isDisabled = newDisabled)) {
                is AppResult.Success -> {
                    _state.update { s ->
                        s.copy(
                            updatingUserId = null,
                            users = s.users.map { if (it.id == user.id) result.data else it },
                            userActionMessage = if (newDisabled) "User disabled" else "User enabled",
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            updatingUserId = null,
                            userActionMessage = "Failed: ${result.error.message}",
                        )
                    }
                }
            }
        }
    }

    fun loadAuditLogs(action: String? = _state.value.logActionFilter) {
        logsJob?.cancel()
        logsJob = viewModelScope.launch {
            loadAuditLogsNow(action = action, cursor = null, append = false)
        }
    }

    fun loadMoreAuditLogs() {
        val current = _state.value
        val cursor = current.logsNextCursor
        if (!current.hasMoreLogs || cursor.isNullOrBlank() || current.isLoadingMoreLogs) {
            return
        }
        logsJob?.cancel()
        logsJob = viewModelScope.launch {
            loadAuditLogsNow(action = current.logActionFilter, cursor = cursor, append = true)
        }
    }

    private suspend fun loadAuditLogsNow(action: String?, cursor: String?, append: Boolean) {
        _state.update {
            it.copy(
                isLoadingLogs = !append,
                isLoadingMoreLogs = append,
                logsError = null,
                logActionFilter = action,
                logsNextCursor = if (append) it.logsNextCursor else null,
                hasMoreLogs = if (append) it.hasMoreLogs else false,
            )
        }
        when (val result = repository.getAdminAuditLogs(cursor = cursor, action = action)) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isLoadingLogs = false,
                            isLoadingMoreLogs = false,
                            auditLogs = if (append) {
                                (it.auditLogs + result.data.items).distinctBy { log -> log.id }
                            } else {
                                result.data.items
                            },
                            logsNextCursor = result.data.nextCursor,
                            hasMoreLogs = result.data.hasMore,
                            logsError = null,
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            isLoadingLogs = false,
                            isLoadingMoreLogs = false,
                            logsError = result.error.message,
                        )
                    }
                }
            }
    }

    fun onLogActionFilterChanged(action: String?) {
        loadAuditLogs(action)
    }

    fun triggerThumbnailBackfill() {
        viewModelScope.launch {
            _state.update { it.copy(isBackfilling = true, diagnosticsMessage = null) }
            when (val result = repository.backfillThumbnails()) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isBackfilling = false,
                            backfillResult = result.data,
                            diagnosticsMessage = "Backfill complete: ${result.data.backfilled} thumbnails created (${result.data.processed} processed).",
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            isBackfilling = false,
                            diagnosticsMessage = "Backfill failed: ${result.error.message}",
                        )
                    }
                }
            }
        }
    }

    private companion object {
        // Long enough to swallow a burst of typing, short enough that the list
        // still feels reactive.
        const val SEARCH_DEBOUNCE_MS = 300L
    }

    fun runHealthCheck() {
        viewModelScope.launch {
            _state.update { it.copy(isCheckingHealth = true, diagnosticsMessage = null) }
            when (val result = repository.checkHealth()) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isCheckingHealth = false,
                            healthResponse = result.data,
                            diagnosticsMessage = "Server status: ${result.data.status} (version: ${result.data.version ?: "1.0.0"})",
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            isCheckingHealth = false,
                            healthResponse = null,
                            diagnosticsMessage = "Health check failed: ${result.error.message}",
                        )
                    }
                }
            }
        }
    }

    fun loadMetrics() {
        viewModelScope.launch {
            _state.update { it.copy(isLoadingMetrics = true) }
            when (val result = repository.getAdminMetrics()) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isLoadingMetrics = false,
                            metrics = result.data,
                        )
                    }
                }
                is AppResult.Failure -> {
                    result.error.markIfForbidden()
                    _state.update {
                        it.copy(
                            isLoadingMetrics = false,
                            diagnosticsMessage = "Metrics query failed: ${result.error.message}",
                        )
                    }
                }
            }
        }
    }
}
