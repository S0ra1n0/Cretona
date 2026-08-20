package com.cretona.app.ui.profile

import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import coil3.compose.AsyncImage
import com.cretona.app.domain.model.UserProfile

@Composable
fun ProfileScreen(
    account: UserProfile?,
    onSignedOut: () -> Unit,
    modifier: Modifier = Modifier,
    onEditProfile: () -> Unit = {},
    isLoading: Boolean = false,
    errorMessage: String? = null,
    onRetry: () -> Unit = {},
    contentPadding: PaddingValues = PaddingValues(0.dp),
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    var showSignOutDialog by remember { mutableStateOf(false) }

    if (showSignOutDialog) {
        AlertDialog(
            onDismissRequest = { showSignOutDialog = false },
            title = { Text("Sign out?") },
            text = { Text("You will need to sign in again to keep generating videos.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showSignOutDialog = false
                        viewModel.signOut()
                        onSignedOut()
                    },
                ) {
                    Text("Sign out", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showSignOutDialog = false }) { Text("Cancel") }
            },
        )
    }

    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 560.dp)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(contentPadding)
                .padding(horizontal = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(modifier = Modifier.height(32.dp))

        Box(
            modifier = Modifier
                .size(104.dp)
                .background(
                    brush = com.cretona.app.ui.theme.PrimaryGradient,
                    shape = CircleShape,
                )
                .padding(3.dp),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center,
            ) {
                val avatarUrl = account?.avatarUrl
                if (avatarUrl != null) {
                    AsyncImage(
                        model = avatarUrl,
                        contentDescription = "Profile picture",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize(),
                    )
                } else {
                    // The neutral placeholder, for accounts that skipped or have
                    // not reached profile setup.
                    Icon(
                        imageVector = Icons.Default.Person,
                        contentDescription = "Profile picture",
                        modifier = Modifier.size(56.dp),
                        tint = Color.Gray,
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Three distinct states. Collapsing them into one "Not signed in" label
        // was actively misleading: a failed /me call looked identical to having
        // no session at all, so a transient network error read as a logout.
        when {
            account != null -> {
                // The username is the name the account chose for itself, so
                // it leads here; the email is an identifier and belongs with
                // the other details below.
                Text(
                    text = account.username ?: account.email ?: account.id,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                if (account.role == "admin") {
                    Text(
                        text = "Administrator",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }

            isLoading -> {
                CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                Spacer(modifier = Modifier.height(8.dp))
                Text("Loading your profile...", style = MaterialTheme.typography.bodyMedium)
            }

            else -> {
                Text(
                    text = "Could not load your profile",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = errorMessage ?: "You may still be signed in. Try again.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
                Spacer(modifier = Modifier.height(12.dp))
                Button(onClick = onRetry) { Text("Retry") }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        if (account != null) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.85f),
                ),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    ProfileRow("Email", account.email ?: NOT_SET)
                    ProfileRow("Role", account.role)
                    // Optional, so an account that skipped profile setup shows
                    // the placeholder rather than an empty-looking row.
                    ProfileRow("Gender", account.gender?.let(::genderLabel) ?: NOT_SET)
                    ProfileRow("Birthday", account.birthday ?: NOT_SET)
                    ProfileRow(
                        "Quota",
                        "${account.quota.remaining} of ${account.quota.limit} remaining",
                    )
                }
            }
        }

        if (account != null) {
            Spacer(modifier = Modifier.height(16.dp))
            OutlinedButton(
                onClick = onEditProfile,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Edit profile")
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        Button(
            onClick = { showSignOutDialog = true },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.error,
            ),
        ) {
            Text("Sign out")
        }

        Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

/**
 * Shown for a detail the account has not chosen yet. The same marker the
 * username row has always used, so an unanswered field reads as unanswered
 * rather than as a blank the screen failed to load.
 */
private const val NOT_SET = "--"

/** Stored lowercase; shown the way a person would write it. */
internal fun genderLabel(stored: String): String = when (stored.lowercase()) {
    "male" -> "Male"
    "female" -> "Female"
    "other" -> "Other"
    // A value this build does not know about is still the account's own
    // answer, so it is shown rather than hidden behind the placeholder.
    else -> stored.replaceFirstChar { it.uppercase() }
}

@Composable
private fun ProfileRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(text = value, style = MaterialTheme.typography.bodyMedium)
    }
}
