package com.cretona.app.ui.admin

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdminScreen(
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: AdminViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Admin Panel") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = {
                            when (state.selectedTab) {
                                AdminTab.STATS -> viewModel.loadStats()
                                AdminTab.USERS -> viewModel.loadUsers()
                                AdminTab.AUDIT_LOGS -> viewModel.loadAuditLogs()
                                AdminTab.DIAGNOSTICS -> viewModel.runHealthCheck()
                            }
                        },
                    ) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                        )
                    }
                },
            )
        },
        modifier = modifier,
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
        ) {
            PrimaryTabRow(selectedTabIndex = state.selectedTab.ordinal) {
                AdminTab.entries.forEach { tab ->
                    Tab(
                        selected = state.selectedTab == tab,
                        onClick = { viewModel.selectTab(tab) },
                        text = { Text(tab.title) },
                    )
                }
            }

            if (state.isForbidden) {
                // Defence in depth. The button that opens this screen is
                // already gated on role, and every endpoint behind it is gated
                // server-side -- this is the third layer, so a non-admin who
                // arrives here by any future route gets a plain refusal
                // instead of four tabs of confusing permission errors.
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            "Admin access required",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            "This account does not have administrator permissions.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(onClick = onNavigateBack) { Text("Go back") }
                    }
                }
                return@Column
            }

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .wrapContentWidth(Alignment.CenterHorizontally)
                    .widthIn(max = 760.dp),
                contentAlignment = Alignment.TopCenter,
            ) {
                when (state.selectedTab) {
                    AdminTab.STATS -> StatsTabContent(
                        state = state,
                        onRefresh = viewModel::loadStats,
                    )
                    AdminTab.USERS -> UsersTabContent(
                        state = state,
                        onSearch = viewModel::onSearchQueryChanged,
                        onRoleFilter = viewModel::onRoleFilterChanged,
                        onStatusFilter = viewModel::onStatusFilterChanged,
                        onToggleRole = viewModel::toggleUserRole,
                        onToggleDisabled = viewModel::toggleUserDisabled,
                    )
                    AdminTab.AUDIT_LOGS -> AuditLogsTabContent(
                        state = state,
                        onActionFilter = viewModel::onLogActionFilterChanged,
                    )
                    AdminTab.DIAGNOSTICS -> DiagnosticsTabContent(
                        state = state,
                        onBackfill = viewModel::triggerThumbnailBackfill,
                        onCheckHealth = viewModel::runHealthCheck,
                        onLoadMetrics = viewModel::loadMetrics,
                    )
                }
            }
        }
    }
}

@Composable
private fun StatsTabContent(
    state: AdminUiState,
    onRefresh: () -> Unit,
) {
    if (state.isLoadingStats) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    if (state.statsError != null) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(state.statsError, color = MaterialTheme.colorScheme.error)
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = onRefresh) { Text("Retry") }
            }
        }
        return
    }

    val stats = state.stats ?: return

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text(
                text = "Key Metrics",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                MetricCard(
                    title = "Total Users",
                    value = "${stats.totalUsers}",
                    subtitle = "${stats.activeUsers} active",
                    modifier = Modifier.weight(1f),
                )
                MetricCard(
                    title = "Total Projects",
                    value = "${stats.totalProjects}",
                    subtitle = "All time",
                    modifier = Modifier.weight(1f),
                )
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                MetricCard(
                    title = "Failure Rate",
                    value = "${(stats.failureRate * 100).toInt()}%",
                    subtitle = "Finished jobs",
                    modifier = Modifier.weight(1f),
                )
                MetricCard(
                    title = "Active Users",
                    value = "${stats.activeUsers}",
                    subtitle = "Non-disabled",
                    modifier = Modifier.weight(1f),
                )
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Projects by Status",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    stats.projectsByStatus.forEach { (status, count) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(status.replaceFirstChar { it.uppercase() })
                            Text("$count", fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Projects by Provider",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    stats.projectsByProvider.forEach { (provider, count) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(provider.uppercase())
                            Text("$count", fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "System Volume Distribution",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    val primaryColor = MaterialTheme.colorScheme.primary
                    val secondaryColor = MaterialTheme.colorScheme.secondary
                    val tertiaryColor = MaterialTheme.colorScheme.tertiary
                    val surfaceColor = MaterialTheme.colorScheme.surface

                    androidx.compose.foundation.Canvas(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(120.dp),
                    ) {
                        val barWidth = size.width / 5f
                        val maxVal = maxOf(stats.totalProjects, stats.totalUsers, 1).toFloat()

                        val bars = listOf(
                            Triple("Users", stats.totalUsers.toFloat(), primaryColor),
                            Triple("Active", stats.activeUsers.toFloat(), secondaryColor),
                            Triple("Projects", stats.totalProjects.toFloat(), tertiaryColor),
                        )

                        bars.forEachIndexed { index, (_, value, color) ->
                            val barHeight = (value / maxVal) * (size.height - 20f)
                            val x = index * (barWidth + 24f) + 16f
                            val y = size.height - barHeight - 10f

                            drawRect(
                                color = color,
                                topLeft = androidx.compose.ui.geometry.Offset(x, y),
                                size = androidx.compose.ui.geometry.Size(barWidth, barHeight),
                            )
                        }
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceAround,
                    ) {
                        Text("Users (${stats.totalUsers})", style = MaterialTheme.typography.labelSmall)
                        Text("Active (${stats.activeUsers})", style = MaterialTheme.typography.labelSmall)
                        Text("Projects (${stats.totalProjects})", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

@Composable
private fun MetricCard(
    title: String,
    value: String,
    subtitle: String,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = title, style = MaterialTheme.typography.labelMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private sealed interface AdminConfirmAction {
    data class ToggleRole(val user: AdminUser) : AdminConfirmAction
    data class ToggleDisabled(val user: AdminUser) : AdminConfirmAction
}

@Composable
private fun UsersTabContent(
    state: AdminUiState,
    onSearch: (String) -> Unit,
    onRoleFilter: (String?) -> Unit,
    onStatusFilter: (Boolean?) -> Unit,
    onToggleRole: (AdminUser) -> Unit,
    onToggleDisabled: (AdminUser) -> Unit,
) {
    var confirmAction by remember { mutableStateOf<AdminConfirmAction?>(null) }

    confirmAction?.let { action ->
        when (action) {
            is AdminConfirmAction.ToggleRole -> {
                val nextRole = if (action.user.role == "admin") "standard user" else "administrator"
                AlertDialog(
                    onDismissRequest = { confirmAction = null },
                    title = { Text("Confirm Role Change") },
                    text = {
                        Text(
                            "Are you sure you want to change ${action.user.email ?: action.user.username ?: action.user.id}'s role to $nextRole?",
                        )
                    },
                    confirmButton = {
                        TextButton(
                            onClick = {
                                confirmAction = null
                                onToggleRole(action.user)
                            },
                        ) {
                            Text("Confirm")
                        }
                    },
                    dismissButton = {
                        TextButton(onClick = { confirmAction = null }) {
                            Text("Cancel")
                        }
                    },
                )
            }

            is AdminConfirmAction.ToggleDisabled -> {
                val actionVerb = if (action.user.isDisabled) "enable" else "disable"
                AlertDialog(
                    onDismissRequest = { confirmAction = null },
                    title = { Text("Confirm Account Action") },
                    text = {
                        Text(
                            "Are you sure you want to $actionVerb the account for ${action.user.email ?: action.user.username ?: action.user.id}?",
                        )
                    },
                    confirmButton = {
                        TextButton(
                            onClick = {
                                confirmAction = null
                                onToggleDisabled(action.user)
                            },
                        ) {
                            Text("Confirm")
                        }
                    },
                    dismissButton = {
                        TextButton(onClick = { confirmAction = null }) {
                            Text("Cancel")
                        }
                    },
                )
            }
        }
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            OutlinedTextField(
                value = state.userSearchQuery,
                onValueChange = onSearch,
                label = { Text("Search users by email or username") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilterChip(
                    selected = state.userRoleFilter == null,
                    onClick = { onRoleFilter(null) },
                    label = { Text("All Roles") },
                )
                FilterChip(
                    selected = state.userRoleFilter == "admin",
                    onClick = { onRoleFilter(if (state.userRoleFilter == "admin") null else "admin") },
                    label = { Text("Admins") },
                )
                FilterChip(
                    selected = state.userRoleFilter == "user",
                    onClick = { onRoleFilter(if (state.userRoleFilter == "user") null else "user") },
                    label = { Text("Standard") },
                )
            }
        }

        if (state.userActionMessage != null) {
            item {
                Text(
                    text = state.userActionMessage,
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }

        if (state.isLoadingUsers) {
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
        } else if (state.users.isEmpty()) {
            item {
                Text(
                    text = "No users found.",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(16.dp),
                )
            }
        } else {
            items(state.users, key = { it.id }) { user ->
                UserCard(
                    user = user,
                    isUpdating = state.updatingUserId == user.id,
                    onToggleRole = { confirmAction = AdminConfirmAction.ToggleRole(user) },
                    onToggleDisabled = { confirmAction = AdminConfirmAction.ToggleDisabled(user) },
                )
            }
        }
    }
}

@Composable
private fun UserCard(
    user: AdminUser,
    isUpdating: Boolean,
    onToggleRole: () -> Unit,
    onToggleDisabled: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = user.email ?: user.username ?: "User ${user.id.take(8)}",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    Text(
                        text = "ID: ${user.id.take(12)}... • Projects: ${user.projectCount}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = user.role.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = if (user.role == "admin") {
                            MaterialTheme.colorScheme.primary
                        } else {
                            // Theme-driven, so the label stays legible in dark mode.
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    )
                    if (user.isDisabled) {
                        Text(
                            text = "(DISABLED)",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            if (isUpdating) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    OutlinedButton(
                        onClick = onToggleRole,
                        modifier = Modifier.padding(end = 8.dp),
                    ) {
                        Text(if (user.role == "admin") "Demote to User" else "Promote to Admin")
                    }
                    Button(
                        onClick = onToggleDisabled,
                        colors = if (user.isDisabled) ButtonDefaults.buttonColors() else ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                    ) {
                        Text(if (user.isDisabled) "Enable" else "Disable")
                    }
                }
            }
        }
    }
}

@Composable
private fun AuditLogsTabContent(
    state: AdminUiState,
    onActionFilter: (String?) -> Unit,
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilterChip(
                    selected = state.logActionFilter == null,
                    onClick = { onActionFilter(null) },
                    label = { Text("All Actions") },
                )
                FilterChip(
                    selected = state.logActionFilter == "user_updated",
                    onClick = { onActionFilter(if (state.logActionFilter == "user_updated") null else "user_updated") },
                    label = { Text("User Updates") },
                )
                FilterChip(
                    selected = state.logActionFilter == "thumbnails_backfilled",
                    onClick = { onActionFilter(if (state.logActionFilter == "thumbnails_backfilled") null else "thumbnails_backfilled") },
                    label = { Text("Thumbnails") },
                )
            }
        }

        if (state.isLoadingLogs) {
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
        } else if (state.auditLogs.isEmpty()) {
            item {
                Text(
                    text = "No audit log entries.",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(16.dp),
                )
            }
        } else {
            items(state.auditLogs, key = { it.id }) { log ->
                AuditLogCard(log = log)
            }
        }
    }
}

@Composable
private fun AuditLogCard(log: AdminAuditLog) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = log.action,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    text = log.createdAt.take(19).replace("T", " "),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Target: ${log.targetType} (${log.targetId ?: "all"})",
                style = MaterialTheme.typography.bodySmall,
            )
            Text(
                text = "Actor: ${log.actorId.take(8)}...",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DiagnosticsTabContent(
    state: AdminUiState,
    onBackfill: () -> Unit,
    onCheckHealth: () -> Unit,
    onLoadMetrics: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "📊 Backend Telemetry & Metrics",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        IconButton(
                            onClick = onLoadMetrics,
                            enabled = !state.isLoadingMetrics,
                        ) {
                            if (state.isLoadingMetrics) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    strokeWidth = 2.dp,
                                )
                            } else {
                                Icon(
                                    imageVector = Icons.Default.Refresh,
                                    contentDescription = "Refresh Metrics",
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    if (state.metrics != null) {
                        val m = state.metrics
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text("Uptime:", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    text = formatUptime(m.uptimeSeconds),
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text("Process Memory (RSS):", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    text = "${String.format(Locale.ROOT, "%.1f", m.memoryRssMb)} MB",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text("Active Jobs:", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    text = "${m.activeJobs} running",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = if (m.activeJobs > 0) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.onSurface,
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text("Completed / Failed:", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    text = "${m.completedJobs} / ${m.failedJobs}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text("Database:", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    text = "${m.databaseBackend.uppercase()} (${m.databaseStatus})",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = if (m.databaseStatus == "healthy") MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text("Storage Backend:", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    text = m.storageBackend.uppercase(),
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                    } else {
                        Text(
                            text = "Tap refresh to query real-time server telemetry.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "System Health & Status",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = if (state.healthResponse != null) {
                            "FastAPI Backend: ${state.healthResponse.status.uppercase()} (v${state.healthResponse.version ?: "1.0.0"})"
                        } else {
                            "Status not checked yet."
                        },
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = onCheckHealth,
                        enabled = !state.isCheckingHealth,
                    ) {
                        if (state.isCheckingHealth) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                        }
                        Text("Ping Server Health")
                    }
                }
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Thumbnail Maintenance",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Scan completed projects missing video thumbnails and backfill them on storage.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = onBackfill,
                        enabled = !state.isBackfilling,
                    ) {
                        if (state.isBackfilling) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                // The spinner sits on a filled Button, so it takes the
                                // container's own contrast colour rather than a fixed white.
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                        }
                        Text("Backfill Missing Thumbnails")
                    }
                }
            }
        }

        if (state.diagnosticsMessage != null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                ) {
                    Text(
                        text = state.diagnosticsMessage,
                        modifier = Modifier.padding(16.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                }
            }
        }
    }
}

private fun formatUptime(seconds: Float): String {
    val sec = seconds.toLong()
    val hours = sec / 3600
    val minutes = (sec % 3600) / 60
    val remSec = sec % 60
    return when {
        hours > 0 -> "${hours}h ${minutes}m ${remSec}s"
        minutes > 0 -> "${minutes}m ${remSec}s"
        else -> String.format(Locale.ROOT, "%.1fs", seconds)
    }
}
