package com.cretona.app.ui.history

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.ui.components.ProjectHistoryCard
import com.cretona.app.ui.components.verticalScrollbar
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Sort order for the history list. Newest-first is the default. */
enum class HistorySort(val label: String) {
    NEWEST("Newest first"),
    OLDEST("Oldest first"),
}

enum class HistoryStatusFilter(val label: String) {
    ALL("All Status"),
    COMPLETED("Completed"),
    GENERATING("In Progress"),
    FAILED("Failed"),
}

@Composable
fun HistoryScreen(
    projects: List<VideoProject>,
    onRemixProject: (VideoProject) -> Unit,
    onDeleteProject: (String) -> Unit,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(0.dp),
) {
    var searchQuery by remember { mutableStateOf("") }
    var sort by remember { mutableStateOf(HistorySort.NEWEST) }
    var statusFilter by remember { mutableStateOf(HistoryStatusFilter.ALL) }
    var ratioFilter by remember { mutableStateOf("All") }
    val listState = rememberLazyListState()

    val filteredProjects = remember(projects, sort, searchQuery, statusFilter, ratioFilter) {
        projects.asSequence()
            .filter { proj ->
                if (searchQuery.isBlank()) true
                else {
                    val query = searchQuery.trim().lowercase()
                    proj.title.lowercase().contains(query) || (proj.prompt?.lowercase()?.contains(query) == true)
                }
            }
            .filter { proj ->
                when (statusFilter) {
                    HistoryStatusFilter.ALL -> true
                    HistoryStatusFilter.COMPLETED -> proj.status == ProjectStatus.COMPLETED
                    HistoryStatusFilter.GENERATING -> proj.status == ProjectStatus.GENERATING || proj.status == ProjectStatus.PENDING
                    HistoryStatusFilter.FAILED -> proj.status == ProjectStatus.FAILED
                }
            }
            .filter { proj ->
                if (ratioFilter == "All") true else proj.aspectRatio == ratioFilter
            }
            .sortedWith(
                when (sort) {
                    HistorySort.NEWEST -> compareByDescending { it.createdAt }
                    HistorySort.OLDEST -> compareBy { it.createdAt }
                }
            )
            .toList()
    }

    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.TopCenter,
    ) {
        LazyColumn(
            state = listState,
            modifier = Modifier
                .fillMaxSize()
                .wrapContentWidth(Alignment.CenterHorizontally)
                .widthIn(max = 680.dp)
                .verticalScrollbar(
                    state = listState,
                    color = MaterialTheme.colorScheme.primary,
                )
                .padding(horizontal = 20.dp),
            contentPadding = PaddingValues(
                top = contentPadding.calculateTopPadding() + 20.dp,
                bottom = contentPadding.calculateBottomPadding() + 20.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("History", style = MaterialTheme.typography.headlineMedium)
                    OutlinedButton(onClick = onRefresh) { Text("Refresh") }
                }
            }

            // Search Bar
            item {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    placeholder = { Text("Search by prompt or title...") },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Default.Search,
                            contentDescription = "Search",
                            tint = MaterialTheme.colorScheme.outline,
                        )
                    },
                    trailingIcon = {
                        if (searchQuery.isNotEmpty()) {
                            IconButton(onClick = { searchQuery = "" }) {
                                Icon(
                                    imageVector = Icons.Default.Close,
                                    contentDescription = "Clear search",
                                    tint = MaterialTheme.colorScheme.outline,
                                )
                            }
                        }
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            // Filter Chips (Horizontally Scrollable)
            item {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // Sort order
                    HistorySort.entries.forEach { option ->
                        FilterChip(
                            selected = sort == option,
                            onClick = { sort = option },
                            label = { Text(option.label) },
                        )
                    }

                    // Status filter
                    HistoryStatusFilter.entries.filter { it != HistoryStatusFilter.ALL }.forEach { filter ->
                        FilterChip(
                            selected = statusFilter == filter,
                            onClick = {
                                statusFilter = if (statusFilter == filter) HistoryStatusFilter.ALL else filter
                            },
                            label = { Text(filter.label) },
                        )
                    }

                    // Aspect ratio filter
                    listOf("16:9", "9:16", "1:1").forEach { ratio ->
                        FilterChip(
                            selected = ratioFilter == ratio,
                            onClick = {
                                ratioFilter = if (ratioFilter == ratio) "All" else ratio
                            },
                            label = { Text(ratio) },
                        )
                    }
                }
            }

            if (projects.isEmpty()) {
                item {
                    Text(
                        "No projects yet. Your first generation will appear here.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(vertical = 24.dp),
                    )
                }
            } else if (filteredProjects.isEmpty()) {
                item {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            "No videos match your search or filters.",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = {
                                searchQuery = ""
                                statusFilter = HistoryStatusFilter.ALL
                                ratioFilter = "All"
                            }
                        ) {
                            Text("Reset Filters")
                        }
                    }
                }
            } else {
                items(filteredProjects, key = VideoProject::id) { project ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            text = project.createdAt.toDisplayDate(),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        ProjectHistoryCard(
                            project = project,
                            onRemix = { onRemixProject(project) },
                            onDelete = { onDeleteProject(project.id) },
                        )
                    }
                }
            }
        }
    }
}

private val dateFormatter = DateTimeFormatter.ofPattern("d MMM yyyy, HH:mm")

/** Falls back to the raw value rather than crashing on an unexpected format. */
private fun String.toDisplayDate(): String = runCatching {
    Instant.parse(this).atZone(ZoneId.systemDefault()).format(dateFormatter)
}.getOrDefault(this)
