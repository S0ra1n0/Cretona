package com.cretona.app.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val repository: CretonaRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    private var pollingJob: Job? = null

    init {
        refreshHistory()
    }

    fun onPromptChanged(prompt: String) {
        _state.update { it.copy(prompt = prompt, errorMessage = null, enhancementNote = null) }
    }

    fun enhancePrompt() {
        val prompt = state.value.prompt.trim()
        if (prompt.isEmpty()) {
            _state.update { it.copy(errorMessage = "Enter an idea before enhancing it.") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(isEnhancing = true, errorMessage = null) }
            when (val result = repository.enhancePrompt(prompt)) {
                is AppResult.Success -> _state.update {
                    val source = if (result.data.usedFallback) {
                        "Deterministic fallback (no live LLM)"
                    } else {
                        "Enhanced by ${result.data.provider}"
                    }
                    it.copy(
                        prompt = result.data.text,
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

    fun generateVideo() {
        val prompt = state.value.prompt.trim()
        if (prompt.isEmpty()) {
            _state.update { it.copy(errorMessage = "Enter a prompt before generating.") }
            return
        }

        pollingJob?.cancel()
        viewModelScope.launch {
            _state.update { it.copy(isSubmitting = true, errorMessage = null) }
            when (
                val result = repository.createProject(
                    prompt = prompt,
                    idempotencyKey = UUID.randomUUID().toString(),
                )
            ) {
                is AppResult.Success -> {
                    _state.update {
                        it.copy(isSubmitting = false, currentProject = result.data)
                    }
                    refreshHistoryInternal()
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

    private suspend fun refreshHistoryInternal() {
        when (val result = repository.listProjects()) {
            is AppResult.Success -> _state.update { it.copy(projects = result.data) }
            is AppResult.Failure -> _state.update { it.copy(errorMessage = result.error.message) }
        }
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
