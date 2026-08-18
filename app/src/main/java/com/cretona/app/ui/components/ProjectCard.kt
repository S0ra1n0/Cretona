package com.cretona.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.graphics.Color
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.cretona.app.core.util.MediaDownloader
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.VideoProject
import kotlinx.coroutines.launch

/**
 * A finished (or failed) project, as shown in a list.
 *
 * Lives here rather than in `ui.home` because both the Home and History tabs
 * render it; a shared component importing downward from one feature package
 * into another would invert the dependency.
 */
@Composable
fun ProjectHistoryCard(
    project: VideoProject,
    onRemix: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    var showDeleteDialog by remember { mutableStateOf(false) }
    var showFullscreenPlayer by remember { mutableStateOf(false) }
    var isSharing by remember { mutableStateOf(false) }

    if (showFullscreenPlayer && project.videoUrl != null) {
        FullscreenVideoDialog(
            videoUrl = project.videoUrl,
            title = project.title,
            aspectRatioString = project.aspectRatio,
            onDismiss = { showFullscreenPlayer = false },
        )
    }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text("Delete project?") },
            text = {
                Text(
                    "\"${project.title}\" will be permanently removed. This cannot be undone.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteDialog = false
                        onDelete()
                    },
                ) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text("Cancel")
                }
            },
        )
    }

    Card(modifier = modifier.fillMaxWidth()) {
        Column {
            if (project.status == ProjectStatus.COMPLETED) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = project.videoUrl != null) {
                            showFullscreenPlayer = true
                        },
                ) {
                    ProjectThumbnail(
                        thumbnailUrl = project.thumbnailUrl,
                        title = project.title,
                        aspectRatio = project.thumbnailAspectRatio,
                    )
                    if (project.videoUrl != null) {
                        Surface(
                            shape = CircleShape,
                            color = Color.Black.copy(alpha = 0.55f),
                            modifier = Modifier
                                .align(Alignment.Center)
                                .size(48.dp),
                        ) {
                            Icon(
                                imageVector = Icons.Default.PlayArrow,
                                contentDescription = "Play Video",
                                tint = Color.White,
                                modifier = Modifier
                                    .padding(8.dp)
                                    .fillMaxSize(),
                            )
                        }
                    }
                }
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(14.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(project.title, style = MaterialTheme.typography.titleMedium)
                    ProjectStatusText(project)
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        val providerLabel = when (project.provider) {
                            "real" -> "🖼️ AI image + motion"
                            "local" -> "💻 Local (placeholder)"
                            else -> "🎭 Demo"
                        }
                        Text(
                            providerLabel,
                            style = MaterialTheme.typography.labelMedium,
                            color = if (project.provider == "real") {
                                MaterialTheme.colorScheme.secondary
                            } else {
                                MaterialTheme.colorScheme.outline
                            },
                        )
                        if (project.imageUrl != null) {
                            Text(
                                "📷 Image-to-Video",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedButton(onClick = onRemix) {
                        Text("✨ Remix", style = MaterialTheme.typography.labelSmall)
                    }

                    if (project.status == ProjectStatus.COMPLETED && project.videoUrl != null) {
                        IconButton(
                            onClick = {
                                if (!isSharing) {
                                    isSharing = true
                                    coroutineScope.launch {
                                        MediaDownloader.shareVideo(
                                            context,
                                            project.videoUrl,
                                            project.title,
                                        )
                                        isSharing = false
                                    }
                                }
                            },
                        ) {
                            if (isSharing) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(18.dp),
                                    strokeWidth = 2.dp,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                            } else {
                                Icon(
                                    imageVector = Icons.Default.Share,
                                    contentDescription = "Share video",
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                    }

                    IconButton(onClick = { showDeleteDialog = true }) {
                        Icon(
                            imageVector = Icons.Default.Delete,
                            contentDescription = "Delete project",
                            tint = MaterialTheme.colorScheme.outline,
                        )
                    }
                }
            }
        }
    }
}

@Composable
internal fun ProjectThumbnail(
    thumbnailUrl: String?,
    title: String,
    aspectRatio: Float,
) {
    var loadState by remember(thumbnailUrl) {
        mutableStateOf(
            if (thumbnailUrl == null) ThumbnailLoadState.Unavailable
            else ThumbnailLoadState.Loading,
        )
    }
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(aspectRatio)
            .background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        if (thumbnailUrl != null) {
            AsyncImage(
                model = thumbnailUrl,
                contentDescription = "Preview for $title",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
                onLoading = { loadState = ThumbnailLoadState.Loading },
                onSuccess = { loadState = ThumbnailLoadState.Loaded },
                onError = { loadState = ThumbnailLoadState.Unavailable },
            )
        }
        when (loadState) {
            ThumbnailLoadState.Loading -> CircularProgressIndicator(
                modifier = Modifier.size(28.dp),
                strokeWidth = 2.dp,
            )

            ThumbnailLoadState.Unavailable -> Text(
                "Preview unavailable",
                style = MaterialTheme.typography.bodyMedium,
            )

            ThumbnailLoadState.Loaded -> Unit
        }
    }
}

private enum class ThumbnailLoadState {
    Loading,
    Loaded,
    Unavailable,
}

@Composable
fun ProjectStatusText(project: VideoProject) {
    val color = when (project.status) {
        ProjectStatus.COMPLETED -> MaterialTheme.colorScheme.primary
        ProjectStatus.FAILED -> MaterialTheme.colorScheme.error
        ProjectStatus.PENDING, ProjectStatus.GENERATING -> MaterialTheme.colorScheme.tertiary
    }
    Text(
        text = project.status.name.lowercase().replaceFirstChar(Char::uppercase),
        color = color,
        style = MaterialTheme.typography.labelLarge,
    )
}
