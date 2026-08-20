package com.cretona.app.ui.home

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
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
        _state.update { it.copy(prompt = prompt, errorMessage = null) }
    }

    fun onImageSelected(uri: Uri?, bytes: ByteArray, mimeType: String, fileName: String) {
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
                is AppResult.Success -> _state.update {
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

                is AppResult.Failure -> _state.update {
                    it.copy(isEnhancing = false, errorMessage = result.error.message)
                }
            }
        }
    }

    fun revertPrompt() {
        val prev = state.value.previousPrompt ?: return
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
        _state.update { it.copy(selectedProvider = provider, errorMessage = null) }
    }

    fun onStylePresetSelected(preset: String?) {
        _state.update {
            val next = if (it.selectedStylePreset == preset) null else preset
            it.copy(selectedStylePreset = next, errorMessage = null)
        }
    }

    fun onCameraMotionSelected(motion: String?) {
        _state.update {
            val next = if (it.selectedCameraMotion == motion) null else motion
            it.copy(selectedCameraMotion = next, errorMessage = null)
        }
    }

    fun onAspectRatioSelected(ratio: String) {
        _state.update { it.copy(selectedAspectRatio = ratio, errorMessage = null) }
    }

    fun remixProject(project: VideoProject) {
        _state.update {
            it.copy(
                prompt = project.prompt ?: it.prompt,
                selectedAspectRatio = project.aspectRatio,
                selectedProvider = project.provider,
                errorMessage = null,
                enhancementNote = "Remixing: ${project.title}",
            )
        }
    }

    fun generateVideo() {
        val prompt = state.value.prompt.trim()
        val hasImage = state.value.selectedImageBytes != null
        if (prompt.isEmpty() && !hasImage) {
            _state.update { it.copy(errorMessage = "Enter a prompt before generating.") }
            return
        }
        if (state.value.isQuotaExhausted) {
            _state.update {
                it.copy(
                    errorMessage = "Generation quota is exhausted. Try again after it resets.",
                )
            }
            return
        }

        val currentAspectRatio = state.value.selectedAspectRatio
        val currentStylePreset = state.value.selectedStylePreset
        val currentCameraMotion = state.value.selectedCameraMotion

        pollingJob?.cancel()
        viewModelScope.launch {
            _state.update { it.copy(isSubmitting = true, errorMessage = null) }

            var imagePath: String? = null
            val currentImageBytes = state.value.selectedImageBytes
            if (currentImageBytes != null) {
                _state.update { it.copy(isUploadingImage = true) }
                val mime = state.value.selectedImageMimeType ?: "image/jpeg"
                val name = state.value.selectedImageFileName ?: "reference.jpg"
                when (val uploadResult = repository.uploadImage(currentImageBytes, mime, name)) {
                    is AppResult.Success -> {
                        imagePath = uploadResult.data
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
                    idempotencyKey = UUID.randomUUID().toString(),
                    provider = state.value.selectedProvider,
                    aspectRatio = currentAspectRatio,
                    stylePreset = currentStylePreset,
                    cameraMotion = currentCameraMotion,
                )
            ) {
                is AppResult.Success -> {
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
                    it.copy(isSubmitting = false, errorMessage = result.error.message)
                }
            }
        }
    }

    fun refreshHistory() {
        viewModelScope.launch { refreshHistoryInternal() }
    }

    fun dismissErrorMessage() {
        _state.update { it.copy(errorMessage = null, historyErrorMessage = null) }
    }

    private suspend fun refreshHistoryInternal() {
        when (val result = repository.listProjects()) {
            is AppResult.Success -> _state.update {
                it.copy(
                    projects = result.data,
                    errorMessage = if (it.errorMessage == it.historyErrorMessage) {
                        null
                    } else {
                        it.errorMessage
                    },
                    historyErrorMessage = null,
                )
            }

            is AppResult.Failure -> _state.update {
                it.copy(
                    errorMessage = result.error.message,
                    historyErrorMessage = result.error.message,
                )
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
        super.onCleared()
    }

    private companion object {
        const val FAST_POLL_INTERVAL_MS = 5_000L
        const val SLOW_POLL_INTERVAL_MS = 15_000L
        const val FAST_POLL_COUNT = 12
        const val MAX_POLLS = 48
    }
}
