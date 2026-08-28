package com.cretona.app.ui.home

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import androidx.annotation.OptIn as AndroidxOptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeMute
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Surface
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
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.ProjectStatus
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.core.util.ImageCompressor
import com.cretona.app.ui.components.FullscreenVideoDialog
import com.cretona.app.ui.components.ProjectStatusText
import com.cretona.app.ui.components.verticalScrollbar
import com.cretona.app.ui.theme.CretonaTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@Composable
fun HomeScreen(
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(0.dp),
    viewModel: HomeViewModel = hiltViewModel(),
    creditBalance: CreditBalance? = null,
    isCreditLoading: Boolean = false,
    creditError: String? = null,
    onRefreshCredits: () -> Unit = {},
    onOpenCredits: () -> Unit = {},
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current
    val context = LocalContext.current
    val imagePickerScope = rememberCoroutineScope()

    // Both the gallery picker and the camera end at the same place: a content
    // URI to read, compress and hand to the view model. Shared so a fix to the
    // read path cannot apply to one source and not the other.
    val readImage: (Uri, String) -> Unit = { uri, fallbackName ->
        imagePickerScope.launch {
            try {
                val selection = withContext(Dispatchers.IO) {
                    val bytes = context.contentResolver.openInputStream(uri)?.use {
                        ImageCompressor.readBounded(it)
                    } ?: throw IllegalStateException("The selected image could not be opened.")
                    val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
                    val fileName = uri.lastPathSegment ?: fallbackName
                    Triple(bytes, mime, fileName)
                }
                viewModel.onImageSelected(
                    uri,
                    selection.first,
                    selection.second,
                    selection.third,
                )
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                viewModel.onImageSelectionFailed(
                    error.message ?: "The selected image could not be read.",
                )
            }
        }
    }

    val photoPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
        onResult = { uri -> if (uri != null) readImage(uri, "reference.jpg") },
    )

    // TakePicture writes into a URI we supply, so the destination has to exist
    // before the camera opens and has to survive the activity being recreated
    // while the camera app is in front. remember + a cache file does both.
    var pendingCaptureUri by remember { mutableStateOf<Uri?>(null) }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture(),
        onResult = { saved ->
            val uri = pendingCaptureUri
            pendingCaptureUri = null
            // `saved` is false when the user backs out of the camera. That is
            // a cancellation, not a failure, so it reports nothing.
            if (saved && uri != null) readImage(uri, "capture.jpg")
        },
    )

    val launchCamera: () -> Unit = {
        try {
            val directory = File(context.cacheDir, "captures").apply { mkdirs() }
            val file = File(directory, "capture-${System.currentTimeMillis()}.jpg")
            val uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file,
            )
            pendingCaptureUri = uri
            cameraLauncher.launch(uri)
        } catch (error: Exception) {
            viewModel.onImageSelectionFailed(
                error.message ?: "The camera could not be opened.",
            )
        }
    }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
        onResult = { granted ->
            if (granted) {
                launchCamera()
            } else {
                viewModel.onImageSelectionFailed(
                    "Camera permission is needed to take a photo. " +
                        "You can still choose one from your gallery.",
                )
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
        onCaptureImage = {
            // Asking every time would nag; checking first means the system
            // dialog appears once and never again after it is granted.
            val alreadyGranted = ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.CAMERA,
            ) == PackageManager.PERMISSION_GRANTED

            if (alreadyGranted) {
                launchCamera()
            } else {
                cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
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
        onDismissError = viewModel::dismissErrorMessage,
        creditBalance = creditBalance,
        isCreditLoading = isCreditLoading,
        creditError = creditError,
        onRefreshCredits = onRefreshCredits,
        onOpenCredits = onOpenCredits,
        contentPadding = contentPadding,
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
    onCaptureImage: () -> Unit,
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
    onDismissError: () -> Unit,
    creditBalance: CreditBalance?,
    isCreditLoading: Boolean,
    creditError: String?,
    onRefreshCredits: () -> Unit,
    onOpenCredits: () -> Unit,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(0.dp),
) {
    // The app bar and bottom navigation live in MainScreen, which hosts this
    // tab; duplicating a Scaffold here would nest two of each.
    val listState = rememberLazyListState()
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
            // Breathing room under the app bar and above the navigation bar,
            // added to the Scaffold's insets rather than replacing them.
            contentPadding = PaddingValues(
                top = contentPadding.calculateTopPadding() + 20.dp,
                bottom = contentPadding.calculateBottomPadding() + 20.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = "✨ AI Video Studio",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "Create cinematic video clips from text or reference images",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            item {
                CreditsCard(
                    account = state.account,
                    balance = creditBalance,
                    isLoading = isCreditLoading,
                    errorMessage = creditError,
                    onRetry = onRefreshCredits,
                    onOpenCredits = onOpenCredits,
                )
            }

            item {
                Card(
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            text = "Prompt Studio",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.primary,
                        )

                        OutlinedTextField(
                            value = state.prompt,
                            onValueChange = onPromptChanged,
                            modifier = Modifier.fillMaxWidth(),
                            minLines = 3,
                            maxLines = 6,
                            placeholder = { Text("Describe the cinematic scene in detail...") },
                            shape = RoundedCornerShape(12.dp),
                            supportingText = {
                                Text(
                                    state.enhancementNote
                                        ?: when (state.selectedProvider) {
                                            "cloud", "real", "wan21" -> "AI image + motion pan"
                                            "local" -> "Local placeholder"
                                            else -> "Instant demo sample"
                                        },
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            },
                        )

                        if (state.prompt.isBlank()) {
                            val ideas = listOf(
                                "🐉 Rồng bay đỉnh núi tuyết",
                                "🌆 Cyberpunk neon Tokyo",
                                "🌊 Hoàng hôn trên biển",
                                "🐱 Phi hành gia mèo vũ trụ",
                                "🎆 Pháo hoa rực rỡ đêm giao thừa",
                            )
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(
                                    "💡 Gợi ý ý tưởng:",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .horizontalScroll(rememberScrollState()),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                ) {
                                    ideas.forEach { idea ->
                                        FilterChip(
                                            selected = false,
                                            onClick = { onSelectPromptIdea(idea) },
                                            label = { Text(idea, style = MaterialTheme.typography.labelSmall) },
                                        )
                                    }
                                }
                            }
                        }

                        // Enhance & Revert actions directly under prompt
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.End,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            if (state.previousPrompt != null) {
                                OutlinedButton(
                                    onClick = onRevertPrompt,
                                    enabled = !state.isEnhancing && !state.isSubmitting,
                                    modifier = Modifier.padding(end = 8.dp),
                                ) {
                                    Text("↩️ Revert")
                                }
                            }
                            OutlinedButton(
                                onClick = onEnhance,
                                enabled = !state.isEnhancing && !state.isSubmitting && state.prompt.isNotBlank(),
                            ) {
                                if (state.isEnhancing) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(16.dp),
                                        strokeWidth = 2.dp,
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text("Enhancing...")
                                } else {
                                    Text("✨ AI Enhance")
                                }
                            }
                        }
                    }
                }
            }

            // Creative Controls Group Card
            item {
                Card(
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f),
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        // Aspect ratio
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Aspect Ratio:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                listOf("9:16" to "📱 9:16", "16:9" to "📺 16:9", "1:1" to "🔲 1:1").forEach { (ratio, label) ->
                                    FilterChip(
                                        selected = state.selectedAspectRatio == ratio,
                                        onClick = { onAspectRatioSelected(ratio) },
                                        label = { Text(label) },
                                    )
                                }
                            }
                        }

                        // Style Preset
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Visual Style:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
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

                        // Camera Motion
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Camera Motion:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
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

                        // Model / Engine
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Engine Tier:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
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
                                    label = { Text("🎭 Demo Sample") },
                                )
                                FilterChip(
                                    selected = state.selectedProvider == "cloud" || state.selectedProvider == "real" || state.selectedProvider == "wan21",
                                    onClick = { onProviderSelected("cloud") },
                                    label = { Text("🖼️ AI image + motion") },
                                )
                                FilterChip(
                                    selected = state.selectedProvider == "local",
                                    onClick = { onProviderSelected("local") },
                                    label = { Text("💻 Local") },
                                )
                                FilterChip(
                                    selected = state.selectedProvider == "kaggle",
                                    onClick = { onProviderSelected("kaggle") },
                                    label = { Text("🎬 Wan2.1 Kaggle") },
                                )
                            }
                        }
                    }
                }
            }

            item {
                ImageReferencePicker(
                    selectedImageUri = state.selectedImageUri,
                    onPickImage = onPickImage,
                    onCaptureImage = onCaptureImage,
                    onClearImage = onClearImage,
                )
            }

            item {
                val creditCost = creditBalance?.effectiveCost
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Button(
                        onClick = onGenerate,
                        enabled = !state.isSubmitting &&
                            !state.isEnhancing &&
                            !state.isAccountLoading &&
                            !state.isQuotaExhausted &&
                            (state.prompt.isNotBlank() || state.selectedImageUri != null),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                    ) {
                        if (state.isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Starting Generation...")
                        } else {
                            Text(
                                "🚀 Generate AI Video" +
                                    (creditCost?.let { " (-$it credits)" } ?: ""),
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }

                    if (state.isAccountLoading) {
                        Text(
                            "Checking account and credit limits before generation.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    } else if (state.isQuotaExhausted) {
                        Text(
                            "The rolling generation limit is exhausted. Credits and rate limits are separate.",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }

            state.errorMessage?.let { message ->
                item {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer,
                        ),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = message,
                                modifier = Modifier
                                    .weight(1f)
                                    .padding(16.dp),
                                color = MaterialTheme.colorScheme.onErrorContainer,
                            )
                            IconButton(onClick = onDismissError) {
                                Icon(
                                    imageVector = Icons.Default.Close,
                                    contentDescription = "Dismiss error",
                                    tint = MaterialTheme.colorScheme.onErrorContainer,
                                )
                            }
                        }
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

            // Past projects now live on the History tab; keeping a second copy
            // here would mean two lists to keep in sync for no added reach.
        }
    }
}

@Composable
private fun CreditsCard(
    account: UserProfile?,
    balance: CreditBalance?,
    isLoading: Boolean,
    errorMessage: String?,
    onRetry: () -> Unit,
    onOpenCredits: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.85f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Credit Wallet",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                )
                if (account != null) {
                    val roleLabel = if (account.role == "admin") "👑 Admin Tier" else "⚡ Pro Creator"
                    Box(
                        modifier = Modifier
                            .background(
                                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f),
                                shape = CircleShape,
                            )
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                    ) {
                        Text(
                            text = roleLabel,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }

            when {
                isLoading -> Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Checking credit balance...", style = MaterialTheme.typography.bodySmall)
                }

                errorMessage != null -> {
                    Text("Credits unavailable: $errorMessage", style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = onRetry) { Text("Retry") }
                }

                balance != null -> {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.Bottom,
                    ) {
                        Text(
                            "⚡ ${balance.balance} credits",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                        )
                        account?.let {
                            Text(it.displayName, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    Text(
                        "Next generation costs ${balance.effectiveCost} credits" +
                            balance.activeDiscount?.let { " · ${it.discountPercent}% off (${it.name})" }.orEmpty(),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    account?.quota?.let {
                        Text(
                            "Rolling safety limit: ${it.remaining}/${it.limit} remaining",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                    OutlinedButton(onClick = onOpenCredits) { Text("Manage credits") }
                }
            }
        }
    }
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
            ProjectStatusText(project)
            Text("Mode: ${project.mode.replace('_', '+')}", style = MaterialTheme.typography.labelMedium)

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
                var showFullscreen by remember { mutableStateOf(false) }

                if (showFullscreen) {
                    FullscreenVideoDialog(
                        videoUrl = project.videoUrl,
                        title = project.title,
                        prompt = project.prompt,
                        aspectRatioString = project.aspectRatio,
                        onDismiss = { showFullscreen = false },
                    )
                }

                VideoPlayer(project.videoUrl)

                val context = LocalContext.current
                val coroutineScope = androidx.compose.runtime.rememberCoroutineScope()
                var isSharing by remember { mutableStateOf(false) }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Button(
                        onClick = { showFullscreen = true },
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("⛶ Fullscreen")
                    }

                    OutlinedButton(
                        onClick = {
                            if (!isSharing) {
                                isSharing = true
                                coroutineScope.launch {
                                    val result = com.cretona.app.core.util.MediaDownloader.shareVideo(
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
                        modifier = Modifier.weight(1f),
                    ) {
                        if (isSharing) {
                            CircularProgressIndicator(modifier = Modifier.size(16.dp), color = MaterialTheme.colorScheme.primary, strokeWidth = 2.dp)
                        } else {
                            Text("📤 Share")
                        }
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
    onCaptureImage: () -> Unit,
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
        // Two sources, side by side, because section 2.2 of the brief asks for
        // both: "chon hoac chup hinh anh tu thiet bi".
        Row(
            modifier = modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedButton(
                onClick = onPickImage,
                modifier = Modifier.weight(1f),
            ) {
                Icon(
                    imageVector = Icons.Default.Image,
                    contentDescription = null,
                    modifier = Modifier.padding(end = 8.dp),
                )
                Text("Choose")
            }
            OutlinedButton(
                onClick = onCaptureImage,
                modifier = Modifier.weight(1f),
            ) {
                Icon(
                    imageVector = Icons.Default.PhotoCamera,
                    contentDescription = null,
                    modifier = Modifier.padding(end = 8.dp),
                )
                Text("Take photo")
            }
        }
    }
}

@AndroidxOptIn(UnstableApi::class)
@Composable
private fun VideoPlayer(videoUrl: String) {
    val context = LocalContext.current
    val player = remember(videoUrl) {
        ExoPlayer.Builder(context)
            .setMediaSourceFactory(com.cretona.app.core.media.VideoCacheManager.createMediaSourceFactory(context))
            .build()
    }
    var isPlaying by remember { mutableStateOf(true) }
    var currentPositionMs by remember { mutableLongStateOf(0L) }
    var durationMs by remember { mutableLongStateOf(0L) }
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
                    imageVector = if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
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
                Icon(
                    imageVector = if (isMuted) Icons.AutoMirrored.Filled.VolumeMute else Icons.AutoMirrored.Filled.VolumeUp,
                    contentDescription = if (isMuted) "Unmute" else "Mute",
                )
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
            onCaptureImage = {},
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
            onDismissError = {},
            creditBalance = CreditBalance(
                balance = 15,
                generationCost = 2,
                effectiveCost = 1,
                activeDiscount = null,
                lifetimeGranted = 20,
                lifetimeSpent = 5,
            ),
            isCreditLoading = false,
            creditError = null,
            onRefreshCredits = {},
            onOpenCredits = {},
        )
    }
}

