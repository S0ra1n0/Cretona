package com.cretona.app.ui.setup

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.compose.AsyncImage
import com.cretona.app.core.util.ImageCompressor
import com.cretona.app.ui.theme.GalaxyBrightAccent
import com.cretona.app.ui.theme.GalaxyDeepBlue
import com.cretona.app.ui.theme.GalaxyIndigo
import com.cretona.app.ui.theme.GalaxyViolet
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * First-run profile setup, and the same form reused for editing later.
 *
 * One composable rather than two so the username rules, the upload-then-save
 * ordering, and the avatar handling cannot drift apart between the two places
 * a profile can be written.
 */
@Composable
fun ProfileSetupScreen(
    onSetupComplete: () -> Unit,
    modifier: Modifier = Modifier,
    isEdit: Boolean = false,
    onCancel: (() -> Unit)? = null,
    viewModel: ProfileSetupViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val imagePickerScope = rememberCoroutineScope()

    LaunchedEffect(isEdit) {
        if (isEdit) viewModel.startEdit()
    }

    LaunchedEffect(state.isComplete) {
        if (state.isComplete) {
            viewModel.consumeCompletion()
            onSetupComplete()
        }
    }

    // PickVisualMedia is the modern picker: it needs no storage permission and
    // covers gallery, Photos, and the documents providers behind one sheet.
    val photoPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
        onResult = { uri ->
            if (uri != null) {
                imagePickerScope.launch {
                    try {
                        val selection = withContext(Dispatchers.IO) {
                            val rawBytes = context.contentResolver.openInputStream(uri)?.use {
                                ImageCompressor.readBounded(it)
                            } ?: throw IllegalStateException("The selected image could not be opened.")
                            val originalMime = context.contentResolver.getType(uri) ?: "image/jpeg"
                            val (bytes, mime) = ImageCompressor.compress(rawBytes, originalMime)
                            val name = uri.lastPathSegment ?: "avatar.jpg"
                            Triple(bytes, mime, name)
                        }
                        viewModel.onAvatarSelected(
                            uri,
                            selection.first,
                            selection.second,
                            selection.third,
                        )
                    } catch (error: CancellationException) {
                        throw error
                    } catch (error: Exception) {
                        viewModel.onAvatarSelectionFailed(
                            error.message ?: "The selected image could not be read.",
                        )
                    }
                }
            }
        },
    )

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(GalaxyDeepBlue, GalaxyIndigo, GalaxyViolet)),
            )
            .systemBarsPadding()
            .imePadding(),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 480.dp)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(modifier = Modifier.height(48.dp))

            Text(
                text = if (isEdit) "Edit your profile" else "Set up your profile",
                color = Color.White,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = if (isEdit) {
                    "Change your picture, username or details."
                } else {
                    "Choose a username. The rest is optional."
                },
                color = Color.White.copy(alpha = 0.75f),
                style = MaterialTheme.typography.bodyMedium,
            )

            Spacer(modifier = Modifier.height(32.dp))

            Box(
                modifier = Modifier
                    .size(120.dp)
                    .clip(CircleShape)
                    .background(Color.White.copy(alpha = 0.12f))
                    .clickable {
                        photoPicker.launch(
                            PickVisualMediaRequest(
                                ActivityResultContracts.PickVisualMedia.ImageOnly,
                            ),
                        )
                    },
                contentAlignment = Alignment.Center,
            ) {
                // A freshly picked image wins over the stored one, so the
                // preview always shows what Confirm would actually save.
                val preview = state.avatarUri ?: state.existingAvatarUrl
                if (preview != null) {
                    AsyncImage(
                        model = preview,
                        contentDescription = "Selected profile picture",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize(),
                    )
                } else {
                    Icon(
                        imageVector = Icons.Default.Person,
                        contentDescription = "Choose a profile picture",
                        modifier = Modifier.size(56.dp),
                        tint = Color.White.copy(alpha = 0.75f),
                    )
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(
                    onClick = {
                        photoPicker.launch(
                            PickVisualMediaRequest(
                                ActivityResultContracts.PickVisualMedia.ImageOnly,
                            ),
                        )
                    },
                ) {
                    val hasPicture = state.avatarUri != null || state.existingAvatarUrl != null
                    Text(
                        if (hasPicture) "Change" else "Choose picture",
                        color = GalaxyBrightAccent,
                    )
                }
                if (state.avatarUri != null || state.existingAvatarUrl != null) {
                    TextButton(onClick = viewModel::onAvatarCleared) {
                        Text("Remove", color = Color.White.copy(alpha = 0.7f))
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            OutlinedTextField(
                value = state.username,
                onValueChange = viewModel::onUsernameChanged,
                label = { Text("Username") },
                singleLine = true,
                isError = state.usernameError != null,
                supportingText = {
                    Text(
                        text = state.usernameError
                            ?: "${state.username.length}/${UsernameRules.MAX_LENGTH}",
                        color = if (state.usernameError != null) {
                            Color(0xFFFF8E8E)
                        } else {
                            Color.White.copy(alpha = 0.7f)
                        },
                    )
                },
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.None,
                    imeAction = ImeAction.Done,
                ),
                modifier = Modifier.fillMaxWidth(),
                colors = galaxySetupFieldColors(),
            )

            Spacer(modifier = Modifier.height(18.dp))

            // Gender and birthday are optional, and the form says so rather
            // than leaving an empty field looking unfinished.
            Text(
                text = "Gender (optional)",
                color = Color.White.copy(alpha = 0.85f),
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                GenderOption.entries.forEach { option ->
                    val selected = state.selectedGender == option
                    FilterChip(
                        selected = selected,
                        onClick = { viewModel.onGenderSelected(option) },
                        label = { Text(option.label) },
                        modifier = Modifier.weight(1f),
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = Color.White.copy(alpha = 0.10f),
                            labelColor = Color.White.copy(alpha = 0.85f),
                            selectedContainerColor = GalaxyBrightAccent,
                            selectedLabelColor = Color.White,
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = selected,
                            borderColor = Color.White.copy(alpha = 0.4f),
                            selectedBorderColor = Color.Transparent,
                        ),
                    )
                }
            }
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = if (state.selectedGender == null) {
                    "Not answered. You can choose later."
                } else {
                    "Tap the selected option again to clear it."
                },
                color = Color.White.copy(alpha = 0.6f),
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(modifier = Modifier.height(16.dp))

            OutlinedTextField(
                value = state.birthday,
                onValueChange = viewModel::onBirthdayChanged,
                label = { Text("Birthday (optional)") },
                placeholder = { Text("YYYY-MM-DD", color = Color.White.copy(alpha = 0.4f)) },
                singleLine = true,
                isError = state.birthdayError != null,
                supportingText = {
                    Text(
                        text = state.birthdayError ?: "Not answered. You can choose later.",
                        color = if (state.birthdayError != null) {
                            Color(0xFFFF8E8E)
                        } else {
                            Color.White.copy(alpha = 0.7f)
                        },
                    )
                },
                trailingIcon = {
                    Row {
                        if (state.birthday.isNotEmpty()) {
                            IconButton(onClick = viewModel::onBirthdayCleared) {
                                Icon(
                                    imageVector = Icons.Default.Clear,
                                    contentDescription = "Clear birthday",
                                    tint = Color.White.copy(alpha = 0.7f),
                                )
                            }
                        }
                        IconButton(onClick = viewModel::onDatePickerRequested) {
                            Icon(
                                imageVector = Icons.Default.DateRange,
                                contentDescription = "Pick a birthday",
                                tint = GalaxyBrightAccent,
                            )
                        }
                    }
                },
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Number,
                    imeAction = ImeAction.Done,
                ),
                modifier = Modifier.fillMaxWidth(),
                colors = galaxySetupFieldColors(),
            )

            if (state.showDatePicker) {
                BirthdayPickerDialog(
                    initialIsoDate = state.birthday,
                    onDismiss = viewModel::onDatePickerDismissed,
                    onPicked = viewModel::onBirthdayPicked,
                )
            }

            if (state.errorMessage != null) {
                Spacer(modifier = Modifier.height(10.dp))
                Text(
                    text = state.errorMessage.orEmpty(),
                    color = Color(0xFFFF8E8E),
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = viewModel::submit,
                enabled = state.canSubmit,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = GalaxyBrightAccent,
                    contentColor = Color.White,
                    disabledContainerColor = Color.White.copy(alpha = 0.12f),
                    disabledContentColor = Color.White.copy(alpha = 0.45f),
                ),
            ) {
                if (state.isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(
                        text = if (isEdit) "Save changes" else "Confirm",
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            if (isEdit && onCancel != null) {
                Spacer(modifier = Modifier.height(4.dp))
                TextButton(
                    onClick = onCancel,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !state.isSubmitting,
                ) {
                    Text("Cancel", color = Color.White.copy(alpha = 0.8f))
                }
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

/**
 * Calendar picker for the birthday, writing back the same ISO string the
 * field accepts by hand.
 *
 * The picker works in UTC millis, so the conversion is pinned to UTC at both
 * ends. Reading the selection back in the device's zone would shift the date
 * by one for anyone west of Greenwich, which is how a birthday silently
 * becomes the day before.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BirthdayPickerDialog(
    initialIsoDate: String,
    onDismiss: () -> Unit,
    onPicked: (String) -> Unit,
) {
    val today = remember { LocalDate.now(ZoneOffset.UTC) }
    val initialMillis = remember(initialIsoDate) {
        runCatching { LocalDate.parse(initialIsoDate) }
            .getOrNull()
            ?.atStartOfDay(ZoneOffset.UTC)
            ?.toInstant()
            ?.toEpochMilli()
    }

    val state = rememberDatePickerState(
        initialSelectedDateMillis = initialMillis,
        selectableDates = object : SelectableDates {
            // A birthday in the future is a typo, and the backend rejects it.
            // Refusing it in the calendar is friendlier than a save that fails.
            override fun isSelectableDate(utcTimeMillis: Long): Boolean =
                utcTimeMillis <= today.plusDays(1).atStartOfDay(ZoneOffset.UTC)
                    .toInstant().toEpochMilli()

            override fun isSelectableYear(year: Int): Boolean = year <= today.year
        },
    )

    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                onClick = {
                    val millis = state.selectedDateMillis
                    if (millis != null) {
                        onPicked(
                            Instant.ofEpochMilli(millis)
                                .atZone(ZoneOffset.UTC)
                                .toLocalDate()
                                .toString(),
                        )
                    } else {
                        onDismiss()
                    }
                },
                enabled = state.selectedDateMillis != null,
            ) {
                Text("Select")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    ) {
        DatePicker(state = state, title = null)
    }
}

@Composable
private fun galaxySetupFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = Color.White,
    unfocusedTextColor = Color.White,
    errorTextColor = Color.White, // Always crisp white text when typing!
    focusedLabelColor = Color.White,
    unfocusedLabelColor = Color.White.copy(alpha = 0.7f),
    errorLabelColor = Color(0xFFFF8E8E),
    focusedBorderColor = GalaxyBrightAccent,
    unfocusedBorderColor = Color.White.copy(alpha = 0.5f),
    errorBorderColor = Color(0xFFFF6B6B),
    cursorColor = GalaxyBrightAccent,
    errorCursorColor = Color(0xFFFF8E8E),
    errorLeadingIconColor = Color.White.copy(alpha = 0.8f),
    errorTrailingIconColor = Color.White.copy(alpha = 0.8f),
)
