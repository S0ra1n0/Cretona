package com.cretona.app.ui.credits

import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.CreditTransaction
import com.cretona.app.domain.model.PromoEvent

enum class CreditsSection(val label: String) {
    BALANCE("Balance"),
    BUY("Buy"),
    EVENTS("Events"),
}

data class CreditsUiState(
    val section: CreditsSection = CreditsSection.BALANCE,
    val balance: CreditBalance? = null,
    val transactions: List<CreditTransaction> = emptyList(),
    val transactionsNextCursor: String? = null,
    val packages: List<CreditPackage> = emptyList(),
    val events: List<PromoEvent> = emptyList(),
    val isLoading: Boolean = true,
    val isLoadingMore: Boolean = false,
    val selectedPackage: CreditPackage? = null,
    val isPurchasing: Boolean = false,
    val purchaseError: String? = null,
    val claimingEventId: String? = null,
    val message: String? = null,
    val errorMessage: String? = null,
)
