package com.cretona.app.ui.admin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.AdminEventDraft
import com.cretona.app.domain.model.AdminPackageDraft
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
        loadCurrentUser()
    }

    /** Needed before the user list renders so self-targeting controls start disabled. */
    private fun loadCurrentUser() {
        viewModelScope.launch {
            when (val result = repository.getCurrentUser()) {
                is AppResult.Success -> _state.update { it.copy(currentUserId = result.data.id) }
                // A failure here only costs the client-side guard; the backend
                // still rejects the request, so it is not worth an error banner.
                is AppResult.Failure -> Unit
            }
        }
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
            AdminTab.VIDEOS -> if (_state.value.adminProjects.isEmpty()) loadAdminProjects()
            AdminTab.CREDITS -> if (_state.value.creditTransactions.isEmpty()) loadCreditTransactions()
            AdminTab.EVENTS -> if (_state.value.events.isEmpty()) loadEvents()
            AdminTab.PACKAGES -> if (_state.value.packages.isEmpty()) loadPackages()
            AdminTab.SETTINGS -> if (_state.value.settings == null) loadSettings()
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
        if (isSelf(user)) {
            _state.update {
                it.copy(userActionMessage = "You cannot change your own role.")
            }
            return
        }
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
        if (isSelf(user)) {
            _state.update {
                it.copy(userActionMessage = "You cannot disable your own account.")
            }
            return
        }
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

    /** True when the row targets the signed-in admin.
     *
     * Locking yourself out is unrecoverable from inside the app: a demoted or
     * disabled admin can no longer reach the console to undo it.
     */
    private fun isSelf(user: AdminUser): Boolean {
        val me = _state.value.currentUserId ?: return false
        return me == user.id
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

    fun onProjectStatusFilterChanged(status: String?) {
        _state.update { it.copy(projectStatusFilter = status) }
        loadAdminProjects()
    }

    fun onProjectOwnerFilterChanged(owner: String) {
        _state.update { it.copy(projectOwnerFilter = owner) }
    }

    fun loadAdminProjects(append: Boolean = false) {
        val current = state.value
        if (append && (current.projectsNextCursor == null || current.isLoadingMoreManagement)) return
        viewModelScope.launch {
            _state.update {
                it.copy(
                    isLoadingManagement = !append,
                    isLoadingMoreManagement = append,
                    managementError = null,
                )
            }
            when (
                val result = repository.getAdminProjects(
                    status = current.projectStatusFilter,
                    userId = current.projectOwnerFilter.trim().ifBlank { null },
                    cursor = if (append) current.projectsNextCursor else null,
                )
            ) {
                is AppResult.Success -> _state.update {
                    it.copy(
                        adminProjects = if (append) {
                            (it.adminProjects + result.data.items).distinctBy { project -> project.id }
                        } else {
                            result.data.items
                        },
                        projectsNextCursor = result.data.nextCursor,
                        isLoadingManagement = false,
                        isLoadingMoreManagement = false,
                    )
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun onCreditFiltersChanged(userId: String, reason: String?) {
        _state.update { it.copy(creditUserFilter = userId, creditReasonFilter = reason) }
    }

    fun loadCreditTransactions(append: Boolean = false) {
        val current = state.value
        if (append && (current.creditTransactionsNextCursor == null || current.isLoadingMoreManagement)) return
        viewModelScope.launch {
            _state.update {
                it.copy(
                    isLoadingManagement = !append,
                    isLoadingMoreManagement = append,
                    managementError = null,
                )
            }
            when (
                val result = repository.getAdminCreditTransactions(
                    userId = current.creditUserFilter.trim().ifBlank { null },
                    reason = current.creditReasonFilter,
                    cursor = if (append) current.creditTransactionsNextCursor else null,
                )
            ) {
                is AppResult.Success -> _state.update {
                    it.copy(
                        creditTransactions = if (append) {
                            (it.creditTransactions + result.data.items).distinctBy { tx -> tx.id }
                        } else {
                            result.data.items
                        },
                        creditTransactionsNextCursor = result.data.nextCursor,
                        isLoadingManagement = false,
                        isLoadingMoreManagement = false,
                    )
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun adjustCredits(userId: String, delta: Int?, note: String) {
        if (userId.isBlank() || delta == null || delta == 0 || note.isBlank()) {
            _state.update { it.copy(managementError = "User ID, a non-zero delta, and a note are required.") }
            return
        }
        viewModelScope.launch {
            saving()
            when (val result = repository.adjustAdminCredits(userId.trim(), delta, note.trim())) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(
                            isSavingManagement = false,
                            managementMessage = "Balance is now ${result.data.balance} credits.",
                        )
                    }
                    loadCreditTransactions()
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun loadPackages() {
        viewModelScope.launch {
            loadingManagement()
            when (val result = repository.getAdminPackages()) {
                is AppResult.Success -> _state.update {
                    it.copy(packages = result.data, isLoadingManagement = false)
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun savePackage(id: String?, draft: AdminPackageDraft) {
        if (draft.name.isBlank() || draft.credits <= 0 || draft.priceVnd < 0) {
            _state.update { it.copy(managementError = "Package name, positive credits, and a non-negative price are required.") }
            return
        }
        viewModelScope.launch {
            saving()
            val result = if (id == null) {
                repository.createAdminPackage(draft)
            } else {
                repository.updateAdminPackage(id, draft)
            }
            when (result) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(isSavingManagement = false, managementMessage = "Package saved.")
                    }
                    loadPackages()
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun loadEvents() {
        viewModelScope.launch {
            loadingManagement()
            when (val result = repository.getAdminEvents()) {
                is AppResult.Success -> _state.update {
                    it.copy(events = result.data, isLoadingManagement = false)
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun saveEvent(id: String?, draft: AdminEventDraft) {
        val value = draft.bonusCredits ?: draft.discountPercent
        if (
            draft.code.isBlank() || draft.name.isBlank() || draft.startsAt.isBlank() ||
            draft.endsAt.isBlank() || value == null || value <= 0
        ) {
            _state.update { it.copy(managementError = "Code, name, window, and the grant/discount value are required.") }
            return
        }
        viewModelScope.launch {
            saving()
            val result = if (id == null) {
                repository.createAdminEvent(draft)
            } else {
                repository.updateAdminEvent(id, draft)
            }
            when (result) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(isSavingManagement = false, managementMessage = "Event saved.")
                    }
                    loadEvents()
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun loadSettings() {
        viewModelScope.launch {
            loadingManagement()
            when (val result = repository.getAdminSettings()) {
                is AppResult.Success -> _state.update {
                    it.copy(settings = result.data, isLoadingManagement = false)
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun updateGenerationCost(cost: Int?) {
        if (cost == null || cost !in 1..1000) {
            _state.update { it.copy(managementError = "Generation cost must be between 1 and 1000 credits.") }
            return
        }
        viewModelScope.launch {
            saving()
            when (val result = repository.updateAdminSettings(cost)) {
                is AppResult.Success -> _state.update {
                    it.copy(
                        settings = result.data,
                        isSavingManagement = false,
                        managementMessage = "Generation cost updated.",
                    )
                }
                is AppResult.Failure -> managementFailure(result.error)
            }
        }
    }

    fun clearManagementMessage() {
        _state.update { it.copy(managementMessage = null, managementError = null) }
    }

    private fun loadingManagement() {
        _state.update { it.copy(isLoadingManagement = true, managementError = null) }
    }

    private fun saving() {
        _state.update {
            it.copy(isSavingManagement = true, managementError = null, managementMessage = null)
        }
    }

    private fun managementFailure(error: AppError) {
        error.markIfForbidden()
        _state.update {
            it.copy(
                isLoadingManagement = false,
                isLoadingMoreManagement = false,
                isSavingManagement = false,
                managementError = error.message,
            )
        }
    }
}
