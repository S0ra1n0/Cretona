package com.cretona.app.ui.admin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
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

    init {
        loadStats()
    }

    fun selectTab(tab: AdminTab) {
        _state.update { it.copy(selectedTab = tab) }
        when (tab) {
            AdminTab.STATS -> if (_state.value.stats == null) loadStats()
            AdminTab.USERS -> if (_state.value.users.isEmpty()) loadUsers()
            AdminTab.AUDIT_LOGS -> if (_state.value.auditLogs.isEmpty()) loadAuditLogs()
            AdminTab.DIAGNOSTICS -> if (_state.value.healthResponse == null) runHealthCheck()
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
        viewModelScope.launch {
            _state.update { it.copy(isLoadingUsers = true, usersError = null) }
            val current = _state.value
            when (val result = repository.getAdminUsers(
                query = current.userSearchQuery.ifBlank { null },
                role = current.userRoleFilter,
                isDisabled = current.userStatusFilter,
            )) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isLoadingUsers = false,
                            users = result.data,
                            usersError = null,
                        )
                    }
                }
                is AppResult.Failure -> {
                    _state.update {
                        it.copy(
                            isLoadingUsers = false,
                            usersError = result.error.message,
                        )
                    }
                }
            }
        }
    }

    fun onSearchQueryChanged(query: String) {
        _state.update { it.copy(userSearchQuery = query) }
        loadUsers()
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

    fun loadAuditLogs(action: String? = null) {
        viewModelScope.launch {
            _state.update { it.copy(isLoadingLogs = true, logsError = null, logActionFilter = action) }
            when (val result = repository.getAdminAuditLogs(action = action)) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isLoadingLogs = false,
                            auditLogs = result.data,
                            logsError = null,
                        )
                    }
                }
                is AppResult.Failure -> {
                    _state.update {
                        it.copy(
                            isLoadingLogs = false,
                            logsError = result.error.message,
                        )
                    }
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
}
