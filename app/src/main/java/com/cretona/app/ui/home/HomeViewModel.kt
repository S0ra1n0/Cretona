package com.cretona.app.ui.home

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.core.result.AppError
import com.cretona.app.core.util.ImageCompressor
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID
import javax.inject.Inject

import com.cretona.app.core.network.NetworkMonitor

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val repository: CretonaRepository,
    @param:dagger.hilt.android.qualifiers.ApplicationContext private val applicationContext: android.content.Context? = null,
    private val networkMonitor: NetworkMonitor? = null,
) : ViewModel() {
    var ioDispatcher: CoroutineDispatcher = Dispatchers.IO
    internal var imageCompressor: (ByteArray, String) -> Pair<ByteArray, String> =
        ImageCompressor::compress

    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    private var pollingJob: Job? = null
    private var historyVersion: Long = 0
    private var pendingGenerationKey: String? = null
    private var pendingImagePath: String? = null

    init {
        refreshAccount()
        refreshHistory()

        networkMonitor?.let { monitor ->
            viewModelScope.launch {
                var wasOffline = false
                monitor.isOnline.collect { online ->
                    _state.update { it.copy(isOnline = online) }
                    if (online && wasOffline) {
                        refreshAccount()
                        refreshHistory()
                    }
                    wasOffline = !online
                }
            }
        }
    }

    fun refreshAccount() {
        viewModelScope.launch { refreshAccountInternal() }
    }

    private suspend fun refreshAccountInternal() {
        _state.update { it.copy(isAccountLoading = true, accountErrorMessage = null) }
        when (val result = repository.getCurrentUser()) {
            is AppResult.Success -> _state.update {
                it.copy(
                    account = result.data,
                    isAccountLoading = false,
                    accountErrorMessage = null,
                )
            }

            is AppResult.Failure -> _state.update {
                it.copy(
                    isAccountLoading = false,
                    accountErrorMessage = result.error.message,
                )
            }
        }
    }

    fun onPromptChanged(prompt: String) {
        resetGenerationIntent()
        _state.update { it.copy(prompt = prompt, errorMessage = null) }
    }

    fun onImageSelected(uri: Uri?, bytes: ByteArray, mimeType: String, fileName: String) {
        resetGenerationIntent()
        viewModelScope.launch {
            // Compress on IO thread so the main thread stays responsive
            val (compressedBytes, finalMime) = withContext(ioDispatcher) {
                imageCompressor(bytes, mimeType)
            }
            _state.update {
                it.copy(
                    selectedImageUri = uri,
                    selectedImageBytes = compressedBytes,
                    selectedImageMimeType = finalMime,
                    selectedImageFileName = fileName,
                    errorMessage = null,
                )
            }
        }
    }

    fun onImageCleared() {
        resetGenerationIntent()
        _state.update {
            it.copy(
                selectedImageUri = null,
                selectedImageBytes = null,
                selectedImageMimeType = null,
                selectedImageFileName = null,
                errorMessage = null,
            )
        }
    }

    fun enhancePrompt() {
        val current = state.value.prompt.trim()
        if (current.isEmpty()) {
            _state.update { it.copy(errorMessage = "Enter an idea before enhancing it.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isEnhancing = true, errorMessage = null) }
            when (val result = repository.enhancePrompt(current)) {
                is AppResult.Success -> {
                    resetGenerationIntent()
                    _state.update {
                        val source = if (result.data.usedFallback) {
                            "Deterministic fallback (no live LLM)"
                        } else {
                            "Enhanced by ${result.data.provider}"
                        }
                        it.copy(
                            prompt = result.data.text,
                            previousPrompt = current,
                            isEnhancing = false,
                            enhancementNote = source,
                        )
                    }
                }

                is AppResult.Failure -> _state.update {
                    it.copy(isEnhancing = false, errorMessage = result.error.message)
                }
            }
        }
    }

    fun revertPrompt() {
        val prev = state.value.previousPrompt ?: return
        resetGenerationIntent()
        _state.update {
            it.copy(
                prompt = prev,
                previousPrompt = null,
                enhancementNote = null,
                errorMessage = null,
            )
        }
    }

    fun onSelectPromptIdea(idea: String) {
        resetGenerationIntent()
        _state.update {
            it.copy(
                prompt = idea,
                previousPrompt = null,
                enhancementNote = null,
                errorMessage = null,
            )
        }
    }

    fun onProviderSelected(provider: String) {
        resetGenerationIntent()
        _state.update { it.copy(selectedProvider = provider, errorMessage = null) }
    }

    fun onStylePresetSelected(preset: String?) {
        resetGenerationIntent()
        _state.update {
            val next = if (it.selectedStylePreset == preset) null else preset
            it.copy(selectedStylePreset = next, errorMessage = null)
        }
    }

    fun onCameraMotionSelected(motion: String?) {
        resetGenerationIntent()
        _state.update {
            val next = if (it.selectedCameraMotion == motion) null else motion
            it.copy(selectedCameraMotion = next, errorMessage = null)
        }
    }

    fun onAspectRatioSelected(ratio: String) {
        resetGenerationIntent()
        _state.update { it.copy(selectedAspectRatio = ratio, errorMessage = null) }
    }

    fun onDurationSelected(seconds: Int) {
        if (seconds !in 2..5) return
        resetGenerationIntent()
        _state.update { it.copy(selectedDurationSeconds = seconds, errorMessage = null) }
    }

    fun remixProject(project: VideoProject) {
        resetGenerationIntent()
        _state.update {
            it.copy(
                prompt = project.prompt ?: it.prompt,
                selectedAspectRatio = project.aspectRatio,
                selectedDurationSeconds = project.durationSeconds ?: it.selectedDurationSeconds,
                selectedProvider = project.provider,
                errorMessage = null,
                enhancementNote = "Remixing: ${project.title}",
            )
        }
    }

    fun generateVideo() {
        val current = state.value
        val prompt = current.prompt.trim()
        val currentImageBytes = current.selectedImageBytes
        val hasImage = currentImageBytes != null
        if (prompt.isEmpty() && !hasImage) {
            _state.update { it.copy(errorMessage = "Enter a prompt or select a reference image.") }
            return
        }
        if (current.isQuotaExhausted) {
            _state.update {
                it.copy(
                    errorMessage = "Generation quota is exhausted. Try again after it resets.",
                )
            }
            return
        }

        val currentProvider = current.selectedProvider
        val currentDurationSeconds = current.selectedDurationSeconds
        val currentAspectRatio = current.selectedAspectRatio
        val currentStylePreset = current.selectedStylePreset
        val currentCameraMotion = current.selectedCameraMotion
        val currentImageMimeType = current.selectedImageMimeType ?: "image/jpeg"
        val currentImageFileName = current.selectedImageFileName ?: "reference.jpg"
        val idempotencyKey = pendingGenerationKey
            ?: UUID.randomUUID().toString().also { pendingGenerationKey = it }

        pollingJob?.cancel()
        viewModelScope.launch {
            _state.update { it.copy(isSubmitting = true, errorMessage = null) }

            var imagePath = pendingImagePath
            if (currentImageBytes != null && imagePath == null) {
                _state.update { it.copy(isUploadingImage = true) }
                when (
                    val uploadResult = repository.uploadImage(
                        currentImageBytes,
                        currentImageMimeType,
                        currentImageFileName,
                    )
                ) {
                    is AppResult.Success -> {
                        imagePath = uploadResult.data
                        pendingImagePath = uploadResult.data
                        _state.update { it.copy(isUploadingImage = false) }
                    }
                    is AppResult.Failure -> {
                        _state.update {
                            it.copy(
                                isSubmitting = false,
                                isUploadingImage = false,
                                errorMessage = "Image upload failed: ${uploadResult.error.message}",
                            )
                        }
                        return@launch
                    }
                }
            }

            when (
                val result = repository.createProject(
                    prompt = prompt.ifBlank { null },
                    imagePath = imagePath,
                    idempotencyKey = idempotencyKey,
                    provider = currentProvider,
                    durationSeconds = currentDurationSeconds,
                    aspectRatio = currentAspectRatio,
                    stylePreset = currentStylePreset,
                    cameraMotion = currentCameraMotion,
                )
            ) {
                is AppResult.Success -> {
                    resetGenerationIntent()
                    _state.update {
                        it.copy(
                            isSubmitting = false,
                            currentProject = result.data,
                            selectedImageUri = null,
                            selectedImageBytes = null,
                            selectedImageMimeType = null,
                            selectedImageFileName = null,
                        )
                    }
                    refreshHistoryInternal()
                    refreshAccountInternal()
                    poll(result.data)
                }

                is AppResult.Failure -> _state.update {
                    val apiCode = (result.error as? AppError.Server)?.apiCode
                    val needsCredits = apiCode == "INSUFFICIENT_CREDITS"
                    it.copy(
                        isSubmitting = false,
                        creditActionRequired = needsCredits,
                        errorMessage = when {
                            needsCredits -> null
                            hasImage && apiCode == "PROVIDER_ERROR" ->
                                "Image-to-video is not available for this provider yet. " +
                                    "Remove the image or choose an image-capable provider."
                            else -> result.error.message
                        },
                    )
                }
            }
        }
    }

    fun consumeCreditAction() {
        _state.update { it.copy(creditActionRequired = false) }
    }

    private fun resetGenerationIntent() {
        pendingGenerationKey = null
        pendingImagePath = null
    }

    fun refreshHistory() {
        viewModelScope.launch { refreshHistoryInternal() }
    }

    fun loadMoreHistory() {
        val current = _state.value
        val cursor = current.projectsNextCursor
        if (
            !current.hasMoreProjects ||
            cursor.isNullOrBlank() ||
            current.isRefreshingProjects ||
            current.isLoadingMoreProjects
        ) {
            return
        }

        val requestVersion = historyVersion
        _state.update { it.copy(isLoadingMoreProjects = true) }
        viewModelScope.launch {
            when (val result = repository.listProjects(cursor = cursor)) {
                is AppResult.Success -> {
                    if (requestVersion != historyVersion) return@launch
                    _state.update {
                        it.copy(
                            projects = (it.projects + result.data.items).distinctBy(VideoProject::id),
                            projectsNextCursor = result.data.nextCursor,
                            hasMoreProjects = result.data.hasMore,
                            isLoadingMoreProjects = false,
                            errorMessage = if (it.errorMessage == it.historyErrorMessage) {
                                null
                            } else {
                                it.errorMessage
                            },
                            historyErrorMessage = null,
                        )
                    }
                }

                is AppResult.Failure -> {
                    if (requestVersion != historyVersion) return@launch
                    _state.update {
                        it.copy(
                            isLoadingMoreProjects = false,
                            errorMessage = result.error.message,
                            historyErrorMessage = result.error.message,
                        )
                    }
                }
            }
        }
    }

    fun dismissErrorMessage() {
        _state.update { it.copy(errorMessage = null, historyErrorMessage = null) }
    }

    private suspend fun refreshHistoryInternal() {
        val requestVersion = ++historyVersion
        _state.update {
            it.copy(
                isRefreshingProjects = true,
                isLoadingMoreProjects = false,
            )
        }
        when (val result = repository.listProjects()) {
            is AppResult.Success -> {
                if (requestVersion != historyVersion) return
                _state.update {
                    it.copy(
                        projects = result.data.items,
                        projectsNextCursor = result.data.nextCursor,
                        hasMoreProjects = result.data.hasMore,
                        isRefreshingProjects = false,
                        isLoadingMoreProjects = false,
                        errorMessage = if (it.errorMessage == it.historyErrorMessage) {
                            null
                        } else {
                            it.errorMessage
                        },
                        historyErrorMessage = null,
                    )
                }
            }

            is AppResult.Failure -> {
                if (requestVersion != historyVersion) return
                _state.update {
                    it.copy(
                        errorMessage = result.error.message,
                        historyErrorMessage = result.error.message,
                        isRefreshingProjects = false,
                        isLoadingMoreProjects = false,
                    )
                }
            }
        }
    }

    fun onImageSelectionFailed(message: String) {
        _state.update { it.copy(errorMessage = message) }
    }

    private fun poll(initial: VideoProject) {
        pollingJob = viewModelScope.launch {
            var project = initial
            repeat(MAX_POLLS) { pollIndex ->
                if (project.isTerminal) {
                    refreshHistoryInternal()
                    return@launch
                }
                delay(
                    if (pollIndex < FAST_POLL_COUNT) {
                        FAST_POLL_INTERVAL_MS
                    } else {
                        SLOW_POLL_INTERVAL_MS
                    },
                )
                when (val result = repository.getProject(project.id)) {
                    is AppResult.Success -> {
                        project = result.data
                        _state.update { it.copy(currentProject = project) }
                        // Checked here rather than only at the top of the next
                        // iteration: a project that finishes on the final poll
                        // would otherwise fall through to the "still running"
                        // message despite having succeeded.
                        if (project.isTerminal) {
                            if (project.status == com.cretona.app.domain.model.ProjectStatus.COMPLETED) {
                                applicationContext?.let { ctx ->
                                    com.cretona.app.core.notification.CretonaNotificationManager.notifyVideoCompleted(
                                        ctx,
                                        project.id,
                                        project.title,
                                    )
                                }
                            }
                            refreshHistoryInternal()
                            return@launch
                        }
                    }

                    is AppResult.Failure -> {
                        _state.update { it.copy(errorMessage = result.error.message) }
                        return@launch
                    }
                }
            }
            _state.update {
                it.copy(errorMessage = "Generation is still running. Refresh history later.")
            }
        }
    }

    fun cancelCurrentProject() {
        val current = state.value.currentProject ?: return
        if (current.isTerminal) return

        pollingJob?.cancel()
        viewModelScope.launch {
            when (val res = repository.cancelProject(current.id)) {
                is AppResult.Success -> {
                    when (val updatedRes = repository.getProject(current.id)) {
                        is AppResult.Success -> _state.update { it.copy(currentProject = updatedRes.data) }
                        is AppResult.Failure -> Unit
                    }
                    refreshAccountInternal()
                    refreshHistoryInternal()
                }
                is AppResult.Failure -> {
                    _state.update { it.copy(errorMessage = "Could not cancel: ${res.error.message}") }
                }
            }
        }
    }

    fun deleteProject(projectId: String) {
        viewModelScope.launch {
            when (val res = repository.deleteProject(projectId)) {
                is AppResult.Success -> {
                    if (state.value.currentProject?.id == projectId) {
                        _state.update { it.copy(currentProject = null) }
                    }
                    refreshHistoryInternal()
                }
                is AppResult.Failure -> {
                    _state.update { it.copy(errorMessage = "Could not delete: ${res.error.message}") }
                }
            }
        }
    }

    override fun onCleared() {
        pollingJob?.cancel()
    }

    private companion object {
        const val FAST_POLL_INTERVAL_MS = 5_000L
        const val SLOW_POLL_INTERVAL_MS = 15_000L
        const val FAST_POLL_COUNT = 12
        const val MAX_POLLS = 48
    }
}
