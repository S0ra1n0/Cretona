package com.cretona.app.ui.home

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn as AndroidxOptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Image
import androidx.compose.material3.Button
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
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
        onGenerate = {
            hideKeyboard(focusManager, keyboardController)
            viewModel.generateVideo()
        },
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
    onGenerate: () -> Unit,
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
                                else "Fake video provider - zero-spend demo",
                        )
                    },
                )
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Model:", style = MaterialTheme.typography.bodyMedium)
                    FilterChip(
                        selected = state.selectedProvider == "fake",
                        onClick = { onProviderSelected("fake") },
                        label = { Text("🎭 Fake") },
                    )
                    FilterChip(
                        selected = state.selectedProvider == "real",
                        onClick = { onProviderSelected("real") },
                        label = { Text("🤖 Real AI") },
                    )
                    FilterChip(
                        selected = state.selectedProvider == "wan21",
                        onClick = { onProviderSelected("wan21") },
                        label = { Text("⚡ Wan 2.1") },
                    )
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
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
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
                            Text("Generate")
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
                item { CurrentProjectCard(project) }
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
                    HistoryCard(project)
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
private fun CurrentProjectCard(project: VideoProject) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(project.title, style = MaterialTheme.typography.titleLarge)
            StatusText(project)
            project.errorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            if (project.status == ProjectStatus.COMPLETED && project.videoUrl != null) {
                VideoPlayer(project.videoUrl)
            }
        }
    }
}

@Composable
private fun HistoryCard(project: VideoProject) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column {
            if (project.status == ProjectStatus.COMPLETED) {
                ProjectThumbnail(
                    thumbnailUrl = project.thumbnailUrl,
                    title = project.title,
                    aspectRatio = project.thumbnailAspectRatio,
                )
            }
            Column(
                modifier = Modifier.padding(14.dp),
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

    LaunchedEffect(videoUrl) {
        player.setMediaItem(MediaItem.fromUri(videoUrl))
        player.prepare()
        player.playWhenReady = true
    }
    DisposableEffect(player) {
        onDispose(player::release)
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .background(Color.Black),
        ) {
            PlayerSurface(player = player, modifier = Modifier.fillMaxSize())
        }
        OutlinedButton(onClick = { if (player.isPlaying) player.pause() else player.play() }) {
            Text("Play / pause")
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
            onGenerate = {},
            onRefreshAccount = {},
            onRefresh = {},
            onNavigateToAdmin = {},
        )
    }
}

