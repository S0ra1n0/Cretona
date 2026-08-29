package com.cretona.app.ui.credits

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.TrendingFlat
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CardGiftcard
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.SmartDisplay
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.CreditReason
import com.cretona.app.domain.model.CreditTransaction
import com.cretona.app.domain.model.PromoEvent
import java.text.NumberFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

@Composable
fun CreditsScreen(
    state: CreditsUiState,
    onSectionSelected: (CreditsSection) -> Unit,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onSelectPackage: (CreditPackage) -> Unit,
    onConfirmPurchase: () -> Unit,
    onDismissPurchase: () -> Unit,
    onClaimEvent: (String) -> Unit,
    onClearMessage: () -> Unit,
    contentPadding: PaddingValues,
    modifier: Modifier = Modifier,
) {
    state.selectedPackage?.let { packageItem ->
        AlertDialog(
            onDismissRequest = onDismissPurchase,
            title = { Text("Confirm simulated purchase") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${packageItem.name}: ${packageItem.credits} credits for ${formatVnd(packageItem.priceVnd)}")
                    Text(
                        "No real money is charged in this coursework build.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    state.purchaseError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error)
                    }
                }
            },
            confirmButton = {
                Button(onClick = onConfirmPurchase, enabled = !state.isPurchasing) {
                    if (state.isPurchasing) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    } else {
                        Text(if (state.purchaseError == null) "Confirm" else "Retry")
                    }
                }
            },
            dismissButton = {
                TextButton(onClick = onDismissPurchase, enabled = !state.isPurchasing) {
                    Text("Cancel")
                }
            },
        )
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().padding(horizontal = 20.dp),
        contentPadding = PaddingValues(
            top = contentPadding.calculateTopPadding() + 20.dp,
            bottom = contentPadding.calculateBottomPadding() + 20.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("Credits", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                    Text("Balance, purchases and rewards", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = onRefresh) {
                    Icon(Icons.Default.Refresh, contentDescription = "Refresh credits")
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CreditsSection.entries.forEach { section ->
                    FilterChip(
                        selected = state.section == section,
                        onClick = { onSectionSelected(section) },
                        label = { Text(section.label) },
                    )
                }
            }
        }

        state.message?.let { message ->
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(message, modifier = Modifier.weight(1f))
                        TextButton(onClick = onClearMessage) { Text("Dismiss") }
                    }
                }
            }
        }

        state.errorMessage?.let { message ->
            item { Text(message, color = MaterialTheme.colorScheme.error) }
        }

        if (state.isLoading) {
            item {
                Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
        } else {
            when (state.section) {
                CreditsSection.BALANCE -> {
                    item {
                        Card(
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                        ) {
                            Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("Available", style = MaterialTheme.typography.labelLarge)
                                Text(
                                    "${state.balance?.balance ?: 0} credits",
                                    style = MaterialTheme.typography.headlineLarge,
                                    fontWeight = FontWeight.Bold,
                                )
                                Text("Next video: ${state.balance?.effectiveCost ?: 0} credits")
                                state.balance?.activeDiscount?.let {
                                    Text("${it.name}: ${it.discountPercent}% off until ${displayTime(it.endsAt)}")
                                }
                            }
                        }
                    }
                    item { Text("Transactions", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold) }
                    items(state.transactions, key = { it.id }) { transaction ->
                        TransactionCard(transaction)
                    }
                    if (state.transactionsNextCursor != null) {
                        item {
                            OutlinedButton(onClick = onLoadMore, enabled = !state.isLoadingMore, modifier = Modifier.fillMaxWidth()) {
                                Text(if (state.isLoadingMore) "Loading…" else "Load more")
                            }
                        }
                    }
                }

                CreditsSection.BUY -> {
                    item {
                        Text(
                            "Payments are simulated for the Mobile 1 demo; credit accounting and idempotency are real.",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                    items(state.packages, key = { it.id }) { packageItem ->
                        PackageCard(packageItem, onClick = { onSelectPackage(packageItem) })
                    }
                }

                CreditsSection.EVENTS -> {
                    items(state.events, key = { it.id }) { event ->
                        EventCard(
                            event = event,
                            isClaiming = state.claimingEventId == event.id,
                            onClaim = { onClaimEvent(event.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TransactionCard(transaction: CreditTransaction) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(reasonIcon(transaction.reason), contentDescription = null)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(CreditReason.label(transaction.reason), fontWeight = FontWeight.SemiBold)
                transaction.note?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                Text(displayTime(transaction.createdAt), style = MaterialTheme.typography.labelSmall)
            }
            Text(
                text = if (transaction.delta > 0) "+${transaction.delta}" else transaction.delta.toString(),
                color = if (transaction.delta > 0) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.error,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun PackageCard(packageItem: CreditPackage, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(packageItem.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("${packageItem.credits} credits · ${formatVnd(packageItem.priceVnd)}")
            }
            Button(onClick = onClick) {
                Icon(Icons.Default.ShoppingCart, contentDescription = null)
                Spacer(Modifier.width(6.dp))
                Text("Buy")
            }
        }
    }
}

@Composable
private fun EventCard(event: PromoEvent, isClaiming: Boolean, onClaim: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.CardGiftcard, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(event.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            event.description?.let { Text(it) }
            Text(
                if (event.isDiscount) {
                    "${event.discountPercent ?: 0}% generation discount · applies automatically"
                } else {
                    "+${event.bonusCredits ?: 0} credits"
                },
                color = MaterialTheme.colorScheme.primary,
            )
            when {
                event.nextActiveAt != null -> Text("Next active: ${displayTime(event.nextActiveAt)}")
                event.activeUntil != null -> Text("Ends: ${displayTime(event.activeUntil)}")
            }
            if (event.isGrant) {
                Text("Slots: ${event.remainingSlots?.toString() ?: "unlimited"}")
                Button(onClick = onClaim, enabled = event.claimable && !isClaiming) {
                    Text(
                        when {
                            isClaiming -> "Claiming…"
                            event.claimedThisPeriod -> "Claimed"
                            event.remainingSlots == 0 -> "Fully claimed"
                            event.claimable -> "Claim"
                            else -> "Not active"
                        },
                    )
                }
            }
        }
    }
}

private fun reasonIcon(reason: String): ImageVector = when (reason) {
    CreditReason.PURCHASE -> Icons.Default.ShoppingCart
    CreditReason.GENERATION -> Icons.Default.SmartDisplay
    CreditReason.EVENT_GRANT, CreditReason.SIGNUP_BONUS -> Icons.Default.CardGiftcard
    CreditReason.REFUND -> Icons.AutoMirrored.Filled.TrendingFlat
    CreditReason.ADMIN_ADJUSTMENT -> Icons.Default.Tune
    else -> Icons.Default.History
}

private fun formatVnd(amount: Int): String =
    "${NumberFormat.getIntegerInstance(Locale.forLanguageTag("vi-VN")).format(amount)} ₫"

private val creditsDateFormatter: DateTimeFormatter =
    DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)

/** Parses an ISO-8601 string and formats it in the device locale and timezone. Falls back to the raw value. */
private fun displayTime(value: String): String = runCatching {
    Instant.parse(value).atZone(ZoneId.systemDefault()).format(creditsDateFormatter)
}.getOrDefault(value.take(16).replace("T", " "))

