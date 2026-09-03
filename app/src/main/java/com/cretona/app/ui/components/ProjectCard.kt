package com.cretona.app.ui.components

import android.widget.Toast
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
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
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
    isDeleting: Boolean = false,
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
            prompt = project.prompt,
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

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
        colors = androidx.compose.material3.CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.75f),
        ),
    ) {
        Column {
            when (project.status) {
                ProjectStatus.COMPLETED -> {
                    // Completed: tappable thumbnail with play overlay and badges
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable(
                                enabled = project.videoUrl != null,
                                onClickLabel = "Play ${project.title}",
                                role = Role.Button,
                            ) {
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
                                color = Color.Black.copy(alpha = 0.65f),
                                modifier = Modifier
                                    .align(Alignment.Center)
                                    .size(52.dp),
                            ) {
                                Icon(
                                    imageVector = Icons.Default.PlayArrow,
                                    contentDescription = "Play Video",
                                    tint = Color.White,
                                    modifier = Modifier
                                        .padding(10.dp)
                                        .fillMaxSize(),
                                )
                            }
                        }

                        // Aspect ratio & duration badges overlay
                        Row(
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(8.dp),
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Surface(
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
                                color = Color.Black.copy(alpha = 0.75f),
                            ) {
                                Text(
                                    text = project.aspectRatio,
                                    color = Color.White,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                )
                            }
                            if (project.durationSeconds != null) {
                                Surface(
                                    shape = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
                                    color = Color.Black.copy(alpha = 0.75f),
                                ) {
                                    Text(
                                        text = "${project.durationSeconds}s",
                                        color = Color.White,
                                        style = MaterialTheme.typography.labelSmall,
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                    )
                                }
                            }
                        }
                    }
                }

                ProjectStatus.PENDING, ProjectStatus.GENERATING -> {
                    // In-progress: thumbnail placeholder (spinner) + progress strip
                    Box(modifier = Modifier.fillMaxWidth()) {
                        ProjectThumbnail(
                            thumbnailUrl = null,
                            title = project.title,
                            aspectRatio = project.thumbnailAspectRatio,
                            showSpinner = true,
                        )
                        // Indeterminate progress strip along the top edge
                        LinearProgressIndicator(
                            modifier = Modifier
                                .fillMaxWidth()
                                .align(Alignment.TopCenter),
                            color = MaterialTheme.colorScheme.primary,
                            trackColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.2f),
                        )
                        // Aspect ratio badge (bottom-end, not overlapping strip)
                        Surface(
                            shape = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
                            color = Color.Black.copy(alpha = 0.75f),
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(8.dp),
                        ) {
                            Text(
                                text = project.aspectRatio,
                                color = Color.White,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            )
                        }
                    }
                }

                else -> {
                    // FAILED / CANCELLED: no thumbnail, nothing to show
                }
            }

            // One column, not a title/actions Row. The action buttons carry no
            // weight, so they took their full intrinsic width first and left the
            // text column a narrow remainder -- which wrapped the title over six
            // lines and broke "Mode: text" one character per line.
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        project.title,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    ProjectStatusText(project)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        val providerLabel = when (project.provider) {
                            "kaggle" -> "🎬 Wan2.1 Kaggle"
                            "real", "cloud", "wan21" -> "🖼️ AI image + motion"
                            "local" -> "💻 Local (placeholder)"
                            "mock", "fake" -> "🎭 Demo Sample"
                            else -> "🎭 Demo Sample"
                        }
                        Text(
                            providerLabel,
                            style = MaterialTheme.typography.labelMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            color = when (project.provider) {
                                "kaggle" -> MaterialTheme.colorScheme.primary
                                "real", "cloud", "wan21" -> MaterialTheme.colorScheme.secondary
                                else -> MaterialTheme.colorScheme.outline
                            },
                        )
                        Text(
                            "Mode: ${project.mode.replace('_', '+')}",
                            style = MaterialTheme.typography.labelMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            color = MaterialTheme.colorScheme.outline,
                        )
                        if (project.imageUrl != null) {
                            Text(
                                "📷 Image-to-Video",
                                style = MaterialTheme.typography.labelSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (isDeleting) {
                        // Replaces the actions rather than sitting beside them:
                        // the row is on its way out, and leaving Remix tappable
                        // invites a second request against a deleted project.
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "Deleting…",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        return@Row
                    }

                    OutlinedButton(onClick = onRemix) {
                        Text("✨ Remix", style = MaterialTheme.typography.labelSmall)
                    }

                    if (project.status == ProjectStatus.COMPLETED && project.videoUrl != null) {
                        IconButton(
                            onClick = {
                                if (!isSharing) {
                                    isSharing = true
                                    coroutineScope.launch {
                                        val result = MediaDownloader.shareVideo(
                                            context,
                                            project.videoUrl,
                                            project.title,
                                        )
                                        isSharing = false
                                        result.exceptionOrNull()?.let { error ->
                                            Toast.makeText(
                                                context,
                                                "Share failed: ${error.message ?: "Unknown error"}",
                                                Toast.LENGTH_LONG,
                                            ).show()
                                        }
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

                    if (project.prompt != null || project.title.isNotBlank()) {
                        IconButton(
                            onClick = {
                                val textToCopy = project.prompt ?: project.title
                                val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                val clip = android.content.ClipData.newPlainText("Prompt", textToCopy)
                                clipboard.setPrimaryClip(clip)
                                Toast.makeText(context, "📋 Prompt copied to clipboard!", Toast.LENGTH_SHORT).show()
                            },
                        ) {
                            Icon(
                                imageVector = Icons.Default.ContentCopy,
                                contentDescription = "Copy prompt",
                                tint = MaterialTheme.colorScheme.outline,
                            )
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
    showSpinner: Boolean = false,
) {
    var loadState by remember(thumbnailUrl, showSpinner) {
        mutableStateOf(
            when {
                showSpinner -> ThumbnailLoadState.Loading
                thumbnailUrl == null -> ThumbnailLoadState.Unavailable
                else -> ThumbnailLoadState.Loading
            },
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
        ProjectStatus.CANCELLED -> MaterialTheme.colorScheme.onSurfaceVariant
        ProjectStatus.PENDING, ProjectStatus.GENERATING -> MaterialTheme.colorScheme.tertiary
    }
    Text(
        text = project.status.name.lowercase().replaceFirstChar(Char::uppercase),
        color = color,
        style = MaterialTheme.typography.labelLarge,
    )
}
