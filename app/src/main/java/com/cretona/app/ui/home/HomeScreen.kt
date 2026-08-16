package com.cretona.app.ui.home

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn as AndroidxOptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Share
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
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.focus.FocusManager
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.compose.PlayerSurface
import coil3.compose.AsyncImage
import com.cretona.app.domain.model.GenerationQuota
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.ui.theme.CretonaTheme
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@Composable
fun HomeScreen(
    modifier: Modifier = Modifier,
    onNavigateToAdmin: () -> Unit = {},
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current
    val context = LocalContext.current

    val photoPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
        onResult = { uri ->
            if (uri != null) {
                try {
                    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
                    val fileName = uri.lastPathSegment ?: "reference.jpg"
                    if (bytes != null) {
                        viewModel.onImageSelected(uri, bytes, mime, fileName)
                    }
                } catch (_: Exception) {}
            }
        },
    )

    HomeContent(
        state = state,
        onPromptChanged = viewModel::onPromptChanged,
        onProviderSelected = viewModel::onProviderSelected,
        onPickImage = {
            photoPickerLauncher.launch(
                PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
            )
        },
        onClearImage = viewModel::onImageCleared,
        onEnhance = {
            hideKeyboard(focusManager, keyboardController)
            viewModel.enhancePrompt()
        },
        onRevertPrompt = viewModel::revertPrompt,
        onSelectPromptIdea = viewModel::onSelectPromptIdea,
        onStylePresetSelected = viewModel::onStylePresetSelected,
        onCameraMotionSelected = viewModel::onCameraMotionSelected,
        onAspectRatioSelected = viewModel::onAspectRatioSelected,
        onRemixProject = viewModel::remixProject,
        onGenerate = {
            hideKeyboard(focusManager, keyboardController)
            viewModel.generateVideo()
        },
        onCancelCurrent = viewModel::cancelCurrentProject,
        onDeleteProject = viewModel::deleteProject,
        onRefreshAccount = viewModel::refreshAccount,
        onRefresh = viewModel::refreshHistory,
        onNavigateToAdmin = onNavigateToAdmin,
        modifier = modifier,
    )
}

@kotlin.OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HomeContent(
    state: HomeUiState,
    onPromptChanged: (String) -> Unit,
    onProviderSelected: (String) -> Unit,
    onPickImage: () -> Unit,
    onClearImage: () -> Unit,
    onEnhance: () -> Unit,
    onRevertPrompt: () -> Unit,
    onSelectPromptIdea: (String) -> Unit,
    onStylePresetSelected: (String?) -> Unit,
    onCameraMotionSelected: (String?) -> Unit,
    onAspectRatioSelected: (String) -> Unit,
    onRemixProject: (VideoProject) -> Unit,
    onGenerate: () -> Unit,
    onCancelCurrent: () -> Unit,
    onDeleteProject: (String) -> Unit,
    onRefreshAccount: () -> Unit,
    onRefresh: () -> Unit,
    onNavigateToAdmin: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = { Text("Cretona") },
                actions = {
                    if (state.account?.role == "admin") {
                        Button(
                            onClick = onNavigateToAdmin,
                            modifier = Modifier.padding(end = 8.dp),
                        ) {
                            Text("Admin Panel")
                        }
                    }
                },
            )
        },
    ) { innerPadding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Create an AI video", style = MaterialTheme.typography.headlineMedium)
                    Text(
                        "FastAPI owns prompt enhancement and the video job lifecycle.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            item {
                QuotaCard(
                    account = state.account,
                    isLoading = state.isAccountLoading,
                    errorMessage = state.accountErrorMessage,
                    onRetry = onRefreshAccount,
                )
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = state.prompt,
                        onValueChange = onPromptChanged,
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 4,
                        maxLines = 8,
                        label = { Text("Describe the video") },
                        supportingText = {
                            Text(
                                state.enhancementNote
                                    ?: if (state.selectedProvider == "real") "Real AI video provider - model AI"
                                    else if (state.selectedProvider == "wan21") "Wan 2.1 video provider"
                                    else "Fake video provider - zero-spend demo",
                            )
                        },
                    )

                    if (state.prompt.isBlank()) {
                        val ideas = listOf(
                            "🐉 Rồng bay trên núi",
                            "🌆 Cyberpunk city",
                            "🌊 Hoàng hôn trên biển",
                            "🐱 Mèo trong vũ trụ",
                            "🎆 Fireworks celebration",
                        )
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            ideas.take(3).forEach { idea ->
                                FilterChip(
                                    selected = false,
                                    onClick = { onSelectPromptIdea(idea) },
                                    label = { Text(idea, style = MaterialTheme.typography.labelSmall) },
                                )
                            }
                        }
                    }
                }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Model / Engine:", style = MaterialTheme.typography.bodyMedium)
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        FilterChip(
                            selected = state.selectedProvider == "mock" || state.selectedProvider == "fake",
                            onClick = { onProviderSelected("mock") },
                            label = { Text("🎭 Mock / Dev") },
                        )
                        FilterChip(
                            selected = state.selectedProvider == "cloud" || state.selectedProvider == "real" || state.selectedProvider == "wan21",
                            onClick = { onProviderSelected("cloud") },
                            label = { Text("☁️ Cloud AI (Wan 2.1 / LTX)") },
                        )
                        FilterChip(
                            selected = state.selectedProvider == "local",
                            onClick = { onProviderSelected("local") },
                            label = { Text("💻 Local Model (LTX-Video)") },
                        )
                    }
                    val modelDesc = when (state.selectedProvider) {
                        "mock", "fake" -> "⚡ Instant zero-cost simulation (best for UI testing & demo)"
                        "cloud", "real", "wan21" -> "🌐 Live Cloud AI generation via GPU cluster"
                        "local" -> "🖥️ Runs local model weights on PC (Ollama / LTX)"
                        else -> ""
                    }
                    if (modelDesc.isNotEmpty()) {
                        Text(
                            modelDesc,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Ratio:", style = MaterialTheme.typography.bodyMedium)
                    listOf("9:16" to "📱 9:16", "16:9" to "📺 16:9", "1:1" to "🔲 1:1").forEach { (ratio, label) ->
                        FilterChip(
                            selected = state.selectedAspectRatio == ratio,
                            onClick = { onAspectRatioSelected(ratio) },
                            label = { Text(label) },
                        )
                    }
                }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Style Preset:", style = MaterialTheme.typography.bodyMedium)
                    val styles = listOf(
                        "anime" to "🌸 Anime",
                        "cyberpunk" to "🌆 Cyberpunk",
                        "3d_pixar" to "🧸 3D Pixar",
                        "vintage_film" to "🎞️ Vintage Film",
                        "photorealistic" to "🌿 8K Realistic",
                    )
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        styles.forEach { (key, label) ->
                            FilterChip(
                                selected = state.selectedStylePreset == key,
                                onClick = { onStylePresetSelected(key) },
                                label = { Text(label) },
                            )
                        }
                    }
                }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Camera Motion:", style = MaterialTheme.typography.bodyMedium)
                    val motions = listOf(
                        "pan_left" to "⬅️ Pan Left",
                        "pan_right" to "➡️ Pan Right",
                        "zoom_in" to "🔍 Zoom In",
                        "zoom_out" to "🔭 Zoom Out",
                        "dolly_zoom" to "🌀 Dolly Zoom",
                        "orbit" to "🔄 Orbit 360",
                    )
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        motions.forEach { (key, label) ->
                            FilterChip(
                                selected = state.selectedCameraMotion == key,
                                onClick = { onCameraMotionSelected(key) },
                                label = { Text(label) },
                            )
                        }
                    }
                }
            }

            item {
                ImageReferencePicker(
                    selectedImageUri = state.selectedImageUri,
                    onPickImage = onPickImage,
                    onClearImage = onClearImage,
                )
            }

            item {
                val quotaCost = if (state.selectedProvider in listOf("real", "wan21")) 2 else 1
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    if (state.previousPrompt != null) {
                        OutlinedButton(
                            onClick = onRevertPrompt,
                            enabled = !state.isEnhancing && !state.isSubmitting,
                        ) {
                            Text("Revert")
                        }
                    }
                    OutlinedButton(
                        onClick = onEnhance,
                        enabled = !state.isEnhancing && !state.isSubmitting,
                        modifier = Modifier.weight(1f),
                    ) {
                        if (state.isEnhancing) {
                            CircularProgressIndicator(modifier = Modifier.padding(2.dp))
                        } else {
                            Text("Enhance")
                        }
                    }
                    Button(
                        onClick = onGenerate,
                        enabled = !state.isSubmitting &&
                            !state.isEnhancing &&
                            !state.isAccountLoading &&
                            !state.isQuotaExhausted,
                        modifier = Modifier.weight(1f),
                    ) {
                        if (state.isSubmitting) {
                            CircularProgressIndicator(modifier = Modifier.padding(2.dp))
                        } else {
                            Text("Generate (-$quotaCost Quota)")
                        }
                    }
                }
                if (state.isAccountLoading) {
                    Text(
                        "Checking quota before generation.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                } else if (state.isQuotaExhausted) {
                    Text(
                        "Generation is unavailable until your quota resets.",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }

            state.errorMessage?.let { message ->
                item {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer,
                        ),
                    ) {
                        Text(
                            text = message,
                            modifier = Modifier.padding(16.dp),
                            color = MaterialTheme.colorScheme.onErrorContainer,
                        )
                    }
                }
            }

            state.currentProject?.let { project ->
                item {
                    CurrentProjectCard(
                        project = project,
                        onCancel = onCancelCurrent,
                    )
                }
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text("Recent projects", style = MaterialTheme.typography.titleLarge)
                    OutlinedButton(onClick = onRefresh) { Text("Refresh") }
                }
            }

            if (state.projects.isEmpty()) {
                item { Text("No projects yet. Your first generation will appear here.") }
            } else {
                items(state.projects, key = VideoProject::id) { project ->
                    HistoryCard(
                        project = project,
                        onRemix = { onRemixProject(project) },
                        onDelete = { onDeleteProject(project.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun QuotaCard(
    account: UserProfile?,
    isLoading: Boolean,
    errorMessage: String?,
    onRetry: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer,
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Generation quota", style = MaterialTheme.typography.titleMedium)
            when {
                isLoading -> Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Checking remaining generations...")
                }

                errorMessage != null -> {
                    Text("Quota unavailable. $errorMessage")
                    Text(
                        "Retry now, or continue after the server verifies quota at submission.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    OutlinedButton(onClick = onRetry) { Text("Retry quota") }
                }

                account != null -> QuotaDetails(account)
            }
        }
    }
}

@Composable
private fun QuotaDetails(account: UserProfile) {
    val quota = account.quota
    val fraction = if (quota.limit == 0) 0f else quota.remaining.toFloat() / quota.limit
    Text("Signed in as ${account.displayName}", style = MaterialTheme.typography.bodySmall)
    Text(
        "${quota.remaining} of ${quota.limit} generations remaining",
        style = MaterialTheme.typography.titleLarge,
    )
    LinearProgressIndicator(
        progress = { fraction.coerceIn(0f, 1f) },
        modifier = Modifier.fillMaxWidth(),
    )
    Text(
        if (quota.remaining == 0) {
            resetCopy(quota)
        } else {
            "${quota.used} used in the current rolling window."
        },
        color = if (quota.remaining == 0) {
            MaterialTheme.colorScheme.error
        } else {
            MaterialTheme.colorScheme.onSecondaryContainer
        },
        style = MaterialTheme.typography.bodyMedium,
    )
}

private fun resetCopy(quota: GenerationQuota): String {
    val formatted = quota.resetsAt?.let { value ->
        runCatching {
            DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .format(Instant.parse(value).atZone(ZoneId.systemDefault()))
        }.getOrNull()
    }
    return formatted?.let { "Quota used. Next generation becomes available after $it." }
        ?: "Quota used. Refresh later to check when a generation becomes available."
}

private fun hideKeyboard(
    focusManager: FocusManager,
    keyboardController: androidx.compose.ui.platform.SoftwareKeyboardController?,
) {
    focusManager.clearFocus()
    keyboardController?.hide()
}

@Composable
private fun CurrentProjectCard(
    project: VideoProject,
    onCancel: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(project.title, style = MaterialTheme.typography.titleLarge)
            StatusText(project)

            if (project.status == ProjectStatus.PENDING || project.status == ProjectStatus.GENERATING) {
                val progressFraction = (project.progressPercent.coerceIn(0, 100)) / 100f
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = project.stepMessage ?: "Generating video...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = "${project.progressPercent}%",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                LinearProgressIndicator(
                    progress = { progressFraction },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedButton(
                    onClick = onCancel,
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.error,
                    ),
                    modifier = Modifier.align(Alignment.End),
                ) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "Cancel",
                        modifier = Modifier.size(16.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text("Cancel Generation")
                }
            }

            project.errorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            if (project.status == ProjectStatus.COMPLETED && project.videoUrl != null) {
                VideoPlayer(project.videoUrl)

                val context = LocalContext.current
                val coroutineScope = androidx.compose.runtime.rememberCoroutineScope()
                var isSaving by remember { mutableStateOf(false) }
                var saveFeedback by remember { mutableStateOf<String?>(null) }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Button(
                        onClick = {
                            coroutineScope.launch {
                                isSaving = true
                                val result = com.cretona.app.core.util.MediaDownloader.saveVideoToGallery(
                                    context,
                                    project.videoUrl,
                                    project.title,
                                )
                                isSaving = false
                                saveFeedback = if (result.isSuccess) "Saved to Gallery (Movies/Cretona)!" else "Failed to save video"
                            }
                        },
                        enabled = !isSaving,
                        modifier = Modifier.weight(1f),
                    ) {
                        if (isSaving) {
                            CircularProgressIndicator(modifier = Modifier.padding(2.dp), color = MaterialTheme.colorScheme.onPrimary)
                        } else {
                            Text("📥 Save to Gallery")
                        }
                    }

                    OutlinedButton(
                        onClick = {
                            coroutineScope.launch {
                                com.cretona.app.core.util.MediaDownloader.shareVideo(
                                    context,
                                    project.videoUrl,
                                    project.title,
                                )
                            }
                        },
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("📤 Share")
                    }
                }

                saveFeedback?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
    }
}

@Composable
private fun HistoryCard(
    project: VideoProject,
    onRemix: () -> Unit,
    onDelete: () -> Unit,
) {
    val context = LocalContext.current
    val coroutineScope = androidx.compose.runtime.rememberCoroutineScope()
    var showDeleteDialog by remember { mutableStateOf(false) }

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

    Card(modifier = Modifier.fillMaxWidth()) {
        Column {
            if (project.status == ProjectStatus.COMPLETED) {
                ProjectThumbnail(
                    thumbnailUrl = project.thumbnailUrl,
                    title = project.title,
                    aspectRatio = project.thumbnailAspectRatio,
                )
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
                    StatusText(project)
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        val providerLabel = when (project.provider) {
                            "real" -> "🤖 Model AI (Real)"
                            "wan21" -> "⚡ Wan 2.1"
                            else -> "🎭 Fake Demo"
                        }
                        Text(
                            providerLabel,
                            style = MaterialTheme.typography.labelMedium,
                            color = if (project.provider in listOf("real", "wan21")) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.outline,
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
                    OutlinedButton(
                        onClick = onRemix,
                    ) {
                        Text("✨ Remix", style = MaterialTheme.typography.labelSmall)
                    }

                    if (project.status == ProjectStatus.COMPLETED && project.videoUrl != null) {
                        IconButton(
                            onClick = {
                                coroutineScope.launch {
                                    com.cretona.app.core.util.MediaDownloader.shareVideo(
                                        context,
                                        project.videoUrl,
                                        project.title,
                                    )
                                }
                            },
                        ) {
                            Icon(
                                imageVector = Icons.Default.Share,
                                contentDescription = "Share video",
                                tint = MaterialTheme.colorScheme.primary,
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
private fun ImageReferencePicker(
    selectedImageUri: android.net.Uri?,
    onPickImage: () -> Unit,
    onClearImage: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (selectedImageUri != null) {
        Card(
            modifier = modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    modifier = Modifier.weight(1f),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    AsyncImage(
                        model = selectedImageUri,
                        contentDescription = "Reference Image",
                        modifier = Modifier
                            .size(56.dp)
                            .aspectRatio(1f),
                        contentScale = ContentScale.Crop,
                    )
                    Column {
                        Text(
                            text = "Reference Image Attached",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = "Mode: Image-to-Video",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }

                IconButton(onClick = onClearImage) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "Remove image",
                    )
                }
            }
        }
    } else {
        OutlinedButton(
            onClick = onPickImage,
            modifier = modifier.fillMaxWidth(),
        ) {
            Icon(
                imageVector = Icons.Default.Image,
                contentDescription = null,
                modifier = Modifier.padding(end = 8.dp),
            )
            Text("Attach Reference Image (Image-to-Video)")
        }
    }
}

@Composable
private fun ProjectThumbnail(
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
private fun StatusText(project: VideoProject) {
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

@AndroidxOptIn(UnstableApi::class)
@Composable
private fun VideoPlayer(videoUrl: String) {
    val context = LocalContext.current
    val player = remember { ExoPlayer.Builder(context).build() }
    var isPlaying by remember { mutableStateOf(true) }
    var currentPositionMs by remember { mutableStateOf(0L) }
    var durationMs by remember { mutableStateOf(0L) }
    var isMuted by remember { mutableStateOf(false) }

    LaunchedEffect(videoUrl) {
        player.setMediaItem(MediaItem.fromUri(videoUrl))
        player.prepare()
        player.playWhenReady = true
    }

    LaunchedEffect(player) {
        while (true) {
            currentPositionMs = player.currentPosition.coerceAtLeast(0L)
            durationMs = player.duration.coerceAtLeast(0L)
            isPlaying = player.isPlaying
            kotlinx.coroutines.delay(200)
        }
    }

    DisposableEffect(player) {
        onDispose(player::release)
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(8.dp),
            )
            .padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .background(Color.Black, shape = RoundedCornerShape(6.dp)),
        ) {
            PlayerSurface(player = player, modifier = Modifier.fillMaxSize())
        }

        // Scrubbing & Controls Bar
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            IconButton(
                onClick = {
                    if (player.isPlaying) {
                        player.pause()
                        isPlaying = false
                    } else {
                        if (player.playbackState == androidx.media3.common.Player.STATE_ENDED) {
                            player.seekTo(0)
                        }
                        player.play()
                        isPlaying = true
                    }
                },
                modifier = Modifier.size(36.dp),
            ) {
                Icon(
                    imageVector = if (isPlaying) Icons.Default.Close else Icons.Default.PlayArrow,
                    contentDescription = if (isPlaying) "Pause" else "Play",
                )
            }

            val curSec = currentPositionMs / 1000
            val durSec = if (durationMs > 0) durationMs / 1000 else 5
            Text(
                text = String.format(
                    java.util.Locale.US,
                    "%02d:%02d / %02d:%02d",
                    curSec / 60,
                    curSec % 60,
                    durSec / 60,
                    durSec % 60,
                ),
                style = MaterialTheme.typography.labelSmall,
            )

            Slider(
                value = if (durationMs > 0) (currentPositionMs.toFloat() / durationMs).coerceIn(0f, 1f) else 0f,
                onValueChange = { fraction ->
                    if (durationMs > 0) {
                        player.seekTo((fraction * durationMs).toLong())
                    }
                },
                modifier = Modifier.weight(1f),
            )

            IconButton(
                onClick = {
                    isMuted = !isMuted
                    player.volume = if (isMuted) 0f else 1f
                },
                modifier = Modifier.size(36.dp),
            ) {
                Text(if (isMuted) "🔇" else "🔊", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun HomeScreenPreview() {
    CretonaTheme {
        HomeContent(
            state = HomeUiState(
                prompt = "A paper dragon flying over a lantern city",
                account = UserProfile(
                    id = "preview-user",
                    email = "student@example.com",
                    username = "bruce",
                    role = "user",
                    isDisabled = false,
                    createdAt = "2026-08-01T00:00:00Z",
                    quota = GenerationQuota(
                        limit = 10,
                        used = 3,
                        remaining = 7,
                        resetsAt = "2026-08-13T12:00:00Z",
                    ),
                ),
                isAccountLoading = false,
            ),
            onPromptChanged = {},
            onProviderSelected = {},
            onPickImage = {},
            onClearImage = {},
            onEnhance = {},
            onRevertPrompt = {},
            onSelectPromptIdea = {},
            onStylePresetSelected = {},
            onCameraMotionSelected = {},
            onAspectRatioSelected = {},
            onRemixProject = {},
            onGenerate = {},
            onCancelCurrent = {},
            onDeleteProject = {},
            onRefreshAccount = {},
            onRefresh = {},
            onNavigateToAdmin = {},
        )
    }
}

