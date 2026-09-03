package com.cretona.app.ui.admin

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.OffsetDateTime
import java.time.temporal.ChronoUnit
import com.cretona.app.domain.model.AdminEvent
import com.cretona.app.domain.model.AdminEventDraft
import com.cretona.app.domain.model.AdminPackage
import com.cretona.app.domain.model.AdminPackageDraft
import com.cretona.app.domain.model.CreditReason

@Composable
internal fun VideosManagementContent(
    state: AdminUiState,
    onStatusFilter: (String?) -> Unit,
    onOwnerChanged: (String) -> Unit,
    onSearch: () -> Unit,
    onLoadMore: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("All user videos", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        }
        item {
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                listOf(null, "pending", "generating", "completed", "failed", "cancelled").forEach { status ->
                    FilterChip(
                        selected = state.projectStatusFilter == status,
                        onClick = { onStatusFilter(status) },
                        label = { Text(status ?: "All") },
                    )
                }
            }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = state.projectOwnerFilter,
                    onValueChange = onOwnerChanged,
                    label = { Text("Owner user ID") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Button(onClick = onSearch, modifier = Modifier.padding(start = 8.dp)) { Text("Apply") }
            }
        }
        managementStatus(state)
        items(state.adminProjects, key = { it.id }) { project ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(project.title, fontWeight = FontWeight.Bold)
                    Text("${project.status.name.lowercase()} · ${project.provider} · ${project.mode}")
                    Text("Project: ${project.id}", style = MaterialTheme.typography.labelSmall)
                    Text("Created: ${project.createdAt.take(16).replace('T', ' ')}")
                }
            }
        }
        if (state.projectsNextCursor != null) {
            item {
                OutlinedButton(onClick = onLoadMore, modifier = Modifier.fillMaxWidth()) {
                    Text(if (state.isLoadingMoreManagement) "Loading…" else "Load more")
                }
            }
        }
    }
}

@Composable
internal fun CreditsManagementContent(
    state: AdminUiState,
    onFiltersChanged: (String, String?) -> Unit,
    onSearch: () -> Unit,
    onLoadMore: () -> Unit,
    onAdjust: (String, Int?, String) -> Unit,
) {
    var adjustmentUser by remember { mutableStateOf("") }
    var adjustmentDelta by remember { mutableStateOf("") }
    var adjustmentNote by remember { mutableStateOf("") }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Text("Adjust a balance", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold) }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(adjustmentUser, { adjustmentUser = it }, label = { Text("User ID") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(adjustmentDelta, { adjustmentDelta = it }, label = { Text("Delta, e.g. 25 or -5") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(adjustmentNote, { adjustmentNote = it }, label = { Text("Required audit note") }, modifier = Modifier.fillMaxWidth())
                Button(
                    onClick = { onAdjust(adjustmentUser, adjustmentDelta.toIntOrNull(), adjustmentNote) },
                    enabled = !state.isSavingManagement,
                ) { Text("Apply adjustment") }
            }
        }
        item { Text("Global transactions", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold) }
        item {
            OutlinedTextField(
                value = state.creditUserFilter,
                onValueChange = { onFiltersChanged(it, state.creditReasonFilter) },
                label = { Text("Filter by user ID") },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                listOf(null, CreditReason.PURCHASE, CreditReason.GENERATION, CreditReason.REFUND, CreditReason.ADMIN_ADJUSTMENT).forEach { reason ->
                    FilterChip(
                        selected = state.creditReasonFilter == reason,
                        onClick = { onFiltersChanged(state.creditUserFilter, reason) },
                        label = { Text(reason ?: "All") },
                    )
                }
            }
        }
        item { Button(onClick = onSearch) { Text("Apply filters") } }
        managementStatus(state)
        items(state.creditTransactions, key = { it.id }) { tx ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("${CreditReason.label(tx.reason)} · ${if (tx.delta > 0) "+" else ""}${tx.delta}", fontWeight = FontWeight.Bold)
                    Text("User: ${tx.userId}")
                    Text("Balance after: ${tx.balanceAfter}")
                    tx.note?.let { Text("Note: $it") }
                }
            }
        }
        if (state.creditTransactionsNextCursor != null) {
            item { OutlinedButton(onClick = onLoadMore, modifier = Modifier.fillMaxWidth()) { Text("Load more") } }
        }
    }
}

@Composable
internal fun PackagesManagementContent(
    state: AdminUiState,
    onSave: (String?, AdminPackageDraft) -> Unit,
) {
    var editing by remember { mutableStateOf<AdminPackage?>(null) }
    var creating by remember { mutableStateOf(false) }
    LaunchedEffect(state.managementMessage) {
        if (state.managementMessage == "Package saved.") {
            creating = false
            editing = null
        }
    }
    if (creating || editing != null) {
        PackageEditorDialog(
            existing = editing,
            saving = state.isSavingManagement,
            error = state.managementError,
            onDismiss = { creating = false; editing = null },
            onSave = { draft ->
                onSave(editing?.id, draft)
            },
        )
    }

    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Credit packages", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Button(onClick = { creating = true }) { Text("New package") }
            }
        }
        managementStatus(state)
        items(state.packages, key = { it.id }) { packageItem ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(packageItem.name, fontWeight = FontWeight.Bold)
                    Text("${packageItem.credits} credits · ${packageItem.priceVnd} VND · order ${packageItem.sortOrder}")
                    Text(if (packageItem.isActive) "Active" else "Inactive")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { editing = packageItem }) { Text("Edit") }
                        OutlinedButton(
                            onClick = {
                                onSave(
                                    packageItem.id,
                                    AdminPackageDraft(
                                        packageItem.name,
                                        packageItem.credits,
                                        packageItem.priceVnd,
                                        packageItem.sortOrder,
                                        !packageItem.isActive,
                                    ),
                                )
                            },
                        ) { Text(if (packageItem.isActive) "Disable" else "Enable") }
                    }
                }
            }
        }
    }
}

@Composable
internal fun EventsManagementContent(
    state: AdminUiState,
    onSave: (String?, AdminEventDraft) -> Unit,
) {
    var editing by remember { mutableStateOf<AdminEvent?>(null) }
    var creating by remember { mutableStateOf(false) }
    LaunchedEffect(state.managementMessage) {
        if (state.managementMessage == "Event saved.") {
            creating = false
            editing = null
        }
    }
    if (creating || editing != null) {
        EventEditorDialog(
            existing = editing,
            saving = state.isSavingManagement,
            error = state.managementError,
            onDismiss = { creating = false; editing = null },
            onSave = { draft ->
                onSave(editing?.id, draft)
            },
        )
    }

    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Promotion events", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Button(onClick = { creating = true }) { Text("New event") }
            }
        }
        managementStatus(state)
        items(state.events, key = { it.id }) { event ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("${event.name} (${event.code})", fontWeight = FontWeight.Bold)
                    Text("${event.kind} · ${event.recurrence} · ${if (event.isActive) "active" else "inactive"}")
                    Text("Value: ${event.bonusCredits ?: event.discountPercent ?: 0}${if (event.kind == "discount") "%" else " credits"}")
                    Text("Days/time: ${event.activeDays ?: "any"} · ${event.activeFromMinute ?: "any"}-${event.activeToMinute ?: "any"}")
                    Text("Window: ${event.startsAt} → ${event.endsAt}")
                    Text("Cap: ${event.maxClaims?.toString() ?: "unlimited"} · auto grant: ${event.autoGrant}")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { editing = event }) { Text("Edit") }
                        OutlinedButton(onClick = { onSave(event.id, event.toDraft().copy(isActive = !event.isActive)) }) {
                            Text(if (event.isActive) "Disable" else "Enable")
                        }
                    }
                }
            }
        }
    }
}

@Composable
internal fun SettingsManagementContent(
    state: AdminUiState,
    onSave: (Int?) -> Unit,
) {
    var cost by remember(state.settings) {
        mutableStateOf(state.settings?.generationCostCredits?.toString().orEmpty())
    }
    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Generation cost", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text("This value is read again by the server when it charges a generation.")
        OutlinedTextField(
            value = cost,
            onValueChange = { cost = it },
            label = { Text("Credits per generation (1–1000)") },
            singleLine = true,
        )
        Button(onClick = { onSave(cost.toIntOrNull()) }, enabled = !state.isSavingManagement) {
            Text("Save setting")
        }
        state.managementError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.managementMessage?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
    }
}

@Composable
private fun PackageEditorDialog(
    existing: AdminPackage?,
    saving: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onSave: (AdminPackageDraft) -> Unit,
) {
    var name by remember(existing) { mutableStateOf(existing?.name.orEmpty()) }
    var credits by remember(existing) { mutableStateOf(existing?.credits?.toString().orEmpty()) }
    var price by remember(existing) { mutableStateOf(existing?.priceVnd?.toString().orEmpty()) }
    var order by remember(existing) { mutableStateOf(existing?.sortOrder?.toString() ?: "0") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (existing == null) "New package" else "Edit package") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    name,
                    { name = it },
                    label = { Text("Name") },
                    placeholder = { Text("Starter pack") },
                    supportingText = { Text("Shown on the Buy tab. 1-80 characters.") },
                    singleLine = true,
                )
                OutlinedTextField(
                    credits,
                    { credits = it },
                    label = { Text("Credits") },
                    placeholder = { Text("50") },
                    supportingText = { Text("Credits granted on purchase, 1-100000.") },
                    singleLine = true,
                )
                OutlinedTextField(
                    price,
                    { price = it },
                    label = { Text("Price VND") },
                    placeholder = { Text("49000") },
                    // Whole dong, no separators: the field parses with toIntOrNull
                    // and "49.000" would silently become an invalid -1.
                    supportingText = { Text("Whole dong, digits only. 0 makes it free.") },
                    singleLine = true,
                )
                OutlinedTextField(
                    order,
                    { order = it },
                    label = { Text("Sort order") },
                    placeholder = { Text("0") },
                    supportingText = { Text("Lower shows first.") },
                    singleLine = true,
                )
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSave(
                        AdminPackageDraft(
                            name,
                            credits.toIntOrNull() ?: 0,
                            price.toIntOrNull() ?: -1,
                            order.toIntOrNull() ?: 0,
                            existing?.isActive ?: true,
                        ),
                    )
                },
                enabled = !saving,
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** Now, or a day offset from it, as ISO-8601 with the device's UTC offset.
 *
 * Seconds are trimmed because the backend parses with `fromisoformat` and the
 * extra precision only makes the field harder to read and edit by hand.
 */
private fun isoNow(plusDays: Long = 0): String =
    OffsetDateTime.now().plusDays(plusDays).truncatedTo(ChronoUnit.MINUTES).toString()

@Composable
private fun EventEditorDialog(
    existing: AdminEvent?,
    saving: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onSave: (AdminEventDraft) -> Unit,
) {
    var draft by remember(existing) {
        mutableStateOf(
            existing?.toDraft() ?: AdminEventDraft(
                code = "",
                name = "",
                description = null,
                kind = "grant",
                bonusCredits = 10,
                discountPercent = null,
                recurrence = "once",
                activeDays = null,
                activeFromMinute = null,
                activeToMinute = null,
                // Empty boxes made the admin guess a format. A real,
                // editable window is a better starting point than a hint.
                startsAt = isoNow(),
                endsAt = isoNow(plusDays = 7),
                maxClaims = null,
                autoGrant = false,
            ),
        )
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (existing == null) "New event" else "Edit event") },
        text = {
            LazyColumn(Modifier.heightIn(max = 520.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item {
                    OutlinedTextField(
                        draft.code,
                        { draft = draft.copy(code = it) },
                        label = { Text("Code") },
                        placeholder = { Text("WEEKEND_GIFT") },
                        supportingText = {
                            Text(
                                if (existing == null) {
                                    "Unique id, 1-40 characters. Cannot be changed later."
                                } else {
                                    "Fixed once the event exists."
                                },
                            )
                        },
                        singleLine = true,
                        enabled = existing == null,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.name,
                        { draft = draft.copy(name = it) },
                        label = { Text("Name") },
                        placeholder = { Text("Weekend gift") },
                        supportingText = { Text("Shown to users. 1-120 characters.") },
                        singleLine = true,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.description.orEmpty(),
                        { draft = draft.copy(description = it.ifBlank { null }) },
                        label = { Text("Description") },
                        placeholder = { Text("Claim 20 free credits every weekend") },
                        supportingText = { Text("Optional.") },
                    )
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf("grant", "discount").forEach { kind ->
                            FilterChip(
                                selected = draft.kind == kind,
                                onClick = {
                                    if (existing == null) {
                                        draft = draft.copy(
                                            kind = kind,
                                            bonusCredits = if (kind == "grant") 10 else null,
                                            discountPercent = if (kind == "discount") 10 else null,
                                        )
                                    }
                                },
                                label = { Text(kind) },
                                enabled = existing == null,
                            )
                        }
                    }
                }
                item {
                    val value = (draft.bonusCredits ?: draft.discountPercent)?.toString().orEmpty()
                    OutlinedTextField(
                        value,
                        {
                            val number = it.toIntOrNull()
                            draft = if (draft.kind == "grant") draft.copy(bonusCredits = number)
                            else draft.copy(discountPercent = number)
                        },
                        label = { Text(if (draft.kind == "grant") "Bonus credits" else "Discount percent") },
                        placeholder = { Text(if (draft.kind == "grant") "20" else "30") },
                        supportingText = {
                            Text(
                                if (draft.kind == "grant") {
                                    "Credits added on claim. Must be above 0."
                                } else {
                                    "Percent off the generation cost, 1-100."
                                },
                            )
                        },
                        singleLine = true,
                    )
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("once", "daily", "weekly").forEach { recurrence ->
                            FilterChip(
                                selected = draft.recurrence == recurrence,
                                onClick = { if (existing == null) draft = draft.copy(recurrence = recurrence) },
                                label = { Text(recurrence) },
                                enabled = existing == null,
                            )
                        }
                    }
                }
                item {
                    OutlinedTextField(
                        draft.activeDays.orEmpty(),
                        { draft = draft.copy(activeDays = it.ifBlank { null }) },
                        label = { Text("Active days") },
                        placeholder = { Text("sat,sun") },
                        supportingText = { Text("Lowercase, comma separated. Blank = every day.") },
                        singleLine = true,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.activeFromMinute?.toString().orEmpty(),
                        { draft = draft.copy(activeFromMinute = it.toIntOrNull()) },
                        label = { Text("From minute of day") },
                        placeholder = { Text("1200") },
                        // Minutes since midnight is not a guessable unit, so the
                        // hint carries the arithmetic rather than the range alone.
                        supportingText = { Text("0-1440. 20:00 is 1200. Blank = all day.") },
                        singleLine = true,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.activeToMinute?.toString().orEmpty(),
                        { draft = draft.copy(activeToMinute = it.toIntOrNull()) },
                        label = { Text("To minute of day") },
                        placeholder = { Text("1320") },
                        supportingText = { Text("0-1440. 22:00 is 1320. Blank = all day.") },
                        singleLine = true,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.startsAt,
                        { draft = draft.copy(startsAt = it) },
                        label = { Text("Starts at") },
                        placeholder = { Text(isoNow()) },
                        supportingText = { Text("ISO-8601 with offset, e.g. ${'$'}{isoNow()}") },
                        singleLine = true,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.endsAt,
                        { draft = draft.copy(endsAt = it) },
                        label = { Text("Ends at") },
                        placeholder = { Text(isoNow(plusDays = 7)) },
                        supportingText = { Text("Must be after the start. Users cannot claim past it.") },
                        singleLine = true,
                    )
                }
                item {
                    OutlinedTextField(
                        draft.maxClaims?.toString().orEmpty(),
                        { draft = draft.copy(maxClaims = it.toIntOrNull()) },
                        label = { Text("Max claims") },
                        placeholder = { Text("100") },
                        supportingText = { Text("Total claims across all users. Blank = unlimited.") },
                        singleLine = true,
                    )
                }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Auto grant", Modifier.weight(1f))
                        Switch(draft.autoGrant, { if (existing == null) draft = draft.copy(autoGrant = it) }, enabled = existing == null)
                    }
                }
                if (existing != null) {
                    item {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Active", Modifier.weight(1f))
                            Switch(draft.isActive, { draft = draft.copy(isActive = it) })
                        }
                    }
                }
                error?.let { message ->
                    item { Text(message, color = MaterialTheme.colorScheme.error) }
                }
            }
        },
        confirmButton = { Button(onClick = { onSave(draft) }, enabled = !saving) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

private fun AdminEvent.toDraft() = AdminEventDraft(
    code,
    name,
    description,
    kind,
    bonusCredits,
    discountPercent,
    recurrence,
    activeDays,
    activeFromMinute,
    activeToMinute,
    startsAt,
    endsAt,
    maxClaims,
    autoGrant,
    isActive,
)

private fun androidx.compose.foundation.lazy.LazyListScope.managementStatus(state: AdminUiState) {
    if (state.isLoadingManagement) {
        item {
            Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }
    }
    state.managementError?.let { message ->
        item { Text(message, color = MaterialTheme.colorScheme.error) }
    }
    state.managementMessage?.let { message ->
        item { Text(message, color = MaterialTheme.colorScheme.primary) }
    }
}
