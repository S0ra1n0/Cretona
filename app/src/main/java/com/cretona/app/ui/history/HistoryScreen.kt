package com.cretona.app.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
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

@Composable
fun HistoryScreen(
    projects: List<VideoProject>,
    onRemixProject: (VideoProject) -> Unit,
    onDeleteProject: (String) -> Unit,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(0.dp),
) {
    var sort by remember { mutableStateOf(HistorySort.NEWEST) }
    val listState = rememberLazyListState()

    // createdAt is an ISO-8601 instant from the API, so lexicographic ordering
    // matches chronological ordering -- no parsing needed to sort correctly.
    val sorted = remember(projects, sort) {
        when (sort) {
            HistorySort.NEWEST -> projects.sortedByDescending { it.createdAt }
            HistorySort.OLDEST -> projects.sortedBy { it.createdAt }
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        LazyColumn(
            state = listState,
            modifier = Modifier
                .fillMaxSize()
                .verticalScrollbar(
                    state = listState,
                    color = MaterialTheme.colorScheme.primary,
                )
                .padding(horizontal = 20.dp),
            // Matches Home: spacing added to the Scaffold's insets, not instead
            // of them, so the list still scrolls under the bars.
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

            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HistorySort.entries.forEach { option ->
                        FilterChip(
                            selected = sort == option,
                            onClick = { sort = option },
                            label = { Text(option.label) },
                        )
                    }
                }
            }

            if (sorted.isEmpty()) {
                item {
                    Text(
                        "No projects yet. Your first generation will appear here.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(vertical = 24.dp),
                    )
                }
            } else {
                items(sorted, key = VideoProject::id) { project ->
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
