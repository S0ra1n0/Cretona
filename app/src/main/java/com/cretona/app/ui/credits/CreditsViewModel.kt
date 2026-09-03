package com.cretona.app.ui.credits

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.repository.CreditsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class CreditsViewModel @Inject constructor(
    private val repository: CreditsRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(CreditsUiState())
    val state: StateFlow<CreditsUiState> = _state.asStateFlow()

    private var purchaseKey: String? = null
    private val claimKeys = mutableMapOf<String, String>()

    init {
        refreshAll()
    }

    fun selectSection(section: CreditsSection) {
        _state.update { it.copy(section = section) }
    }

    fun refreshAll() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, errorMessage = null) }
            loadBalance()
            loadTransactions()
            loadPackages()
            loadEvents()
            _state.update { it.copy(isLoading = false) }
        }
    }

    fun refreshBalance() {
        viewModelScope.launch { loadBalance() }
    }

    fun loadMoreTransactions() {
        val cursor = state.value.transactionsNextCursor ?: return
        if (state.value.isLoadingMore) return
        viewModelScope.launch {
            _state.update { it.copy(isLoadingMore = true) }
            when (val result = repository.getTransactions(cursor = cursor)) {
                is AppResult.Success -> _state.update {
                    it.copy(
                        transactions = (it.transactions + result.data.items)
                            .distinctBy { transaction -> transaction.id },
                        transactionsNextCursor = result.data.nextCursor,
                        isLoadingMore = false,
                    )
                }
                is AppResult.Failure -> _state.update {
                    it.copy(isLoadingMore = false, errorMessage = result.error.message)
                }
            }
        }
    }

    fun selectPackage(packageItem: CreditPackage) {
        purchaseKey = UUID.randomUUID().toString()
        _state.update {
            it.copy(selectedPackage = packageItem, purchaseError = null, message = null)
        }
    }

    fun dismissPurchase() {
        if (state.value.isPurchasing) return
        purchaseKey = null
        _state.update { it.copy(selectedPackage = null, purchaseError = null) }
    }

    fun confirmPurchase() {
        val packageItem = state.value.selectedPackage ?: return
        val key = purchaseKey ?: UUID.randomUUID().toString().also { purchaseKey = it }
        if (state.value.isPurchasing) return

        viewModelScope.launch {
            _state.update { it.copy(isPurchasing = true, purchaseError = null) }
            when (val result = repository.purchase(packageItem.id, key)) {
                is AppResult.Success -> {
                    purchaseKey = null
                    val receipt = result.data
                    _state.update {
                        it.copy(
                            selectedPackage = null,
                            isPurchasing = false,
                            message = "Added ${receipt.creditsGranted} credits.",
                            // Same reason as claimEvent: show the balance the
                            // server just returned rather than the pre-purchase
                            // one until the refetch lands.
                            balance = it.balance?.copy(balance = receipt.balance),
                        )
                    }
                    reloadCreditData()
                }
                is AppResult.Failure -> {
                    if (result.error.apiCode == "PACKAGE_INACTIVE") {
                        purchaseKey = null
                        _state.update {
                            it.copy(
                                selectedPackage = null,
                                isPurchasing = false,
                                message = "That package is no longer available. The list was refreshed.",
                            )
                        }
                        loadPackages()
                    } else {
                        // Keep both package and key: tapping Retry is the same
                        // user intent and must never create a second payment.
                        _state.update {
                            it.copy(isPurchasing = false, purchaseError = result.error.message)
                        }
                    }
                }
            }
        }
    }

    fun claimEvent(eventId: String) {
        if (state.value.claimingEventId != null) return
        val event = state.value.events.firstOrNull { it.id == eventId } ?: return
        if (!event.claimable) return
        val key = claimKeys.getOrPut(eventId) { UUID.randomUUID().toString() }

        viewModelScope.launch {
            _state.update { it.copy(claimingEventId = eventId, message = null) }
            when (val result = repository.claimEvent(eventId, key)) {
                is AppResult.Success -> {
                    claimKeys.remove(eventId)
                    val claim = result.data
                    // Apply what the server just confirmed before re-fetching, so
                    // the card flips to "Claimed" and the wallet moves on the same
                    // frame as the message. This is not the client re-deriving
                    // `claimable`: the grant already happened, and the edit only
                    // ever disables the button, so a disagreement with the next
                    // fetch cannot hand out a second claim.
                    _state.update { current ->
                        current.copy(
                            claimingEventId = null,
                            message = "Claimed ${claim.creditsGranted} credits.",
                            balance = current.balance?.copy(balance = claim.balance),
                            events = current.events.map { event ->
                                if (event.id != eventId) {
                                    event
                                } else {
                                    event.copy(
                                        claimable = false,
                                        claimedThisPeriod = true,
                                        remainingSlots = event.remainingSlots
                                            ?.minus(1)
                                            ?.coerceAtLeast(0),
                                    )
                                }
                            },
                        )
                    }
                    // Then reconcile: the server owns the next period, the ledger
                    // row and any cap shared with other users.
                    reloadCreditData()
                    loadEvents()
                }
                is AppResult.Failure -> {
                    val contractMessage = when (result.error.apiCode) {
                        "EVENT_NOT_ACTIVE" -> "This event is not active."
                        "EVENT_ALREADY_CLAIMED" -> "Already claimed for this period."
                        "EVENT_FULL" -> "This event is fully claimed."
                        else -> result.error.message
                    }
                    if (result.error.apiCode?.startsWith("EVENT_") == true) {
                        claimKeys.remove(eventId)
                        loadEvents()
                    }
                    _state.update { it.copy(claimingEventId = null, message = contractMessage) }
                }
            }
        }
    }

    fun showMessage(message: String) {
        _state.update { it.copy(message = message, section = CreditsSection.BUY) }
    }

    fun clearMessage() {
        _state.update { it.copy(message = null, errorMessage = null) }
    }

    private suspend fun reloadCreditData() {
        loadBalance()
        loadTransactions()
    }

    private suspend fun loadBalance() {
        when (val result = repository.getBalance()) {
            is AppResult.Success -> _state.update { it.copy(balance = result.data) }
            is AppResult.Failure -> recordError(result.error)
        }
    }

    private suspend fun loadTransactions() {
        when (val result = repository.getTransactions()) {
            is AppResult.Success -> _state.update {
                it.copy(
                    transactions = result.data.items,
                    transactionsNextCursor = result.data.nextCursor,
                )
            }
            is AppResult.Failure -> recordError(result.error)
        }
    }

    private suspend fun loadPackages() {
        when (val result = repository.getPackages()) {
            is AppResult.Success -> _state.update { it.copy(packages = result.data) }
            is AppResult.Failure -> recordError(result.error)
        }
    }

    private suspend fun loadEvents() {
        when (val result = repository.getEvents()) {
            is AppResult.Success -> _state.update { it.copy(events = result.data.items) }
            is AppResult.Failure -> recordError(result.error)
        }
    }

    private fun recordError(error: AppError) {
        _state.update { if (it.errorMessage == null) it.copy(errorMessage = error.message) else it }
    }

    private val AppError.apiCode: String?
        get() = (this as? AppError.Server)?.apiCode
}
