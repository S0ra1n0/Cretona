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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.compose.AsyncImage
import com.cretona.app.ui.theme.GalaxyBrightAccent
import com.cretona.app.ui.theme.GalaxyDeepBlue
import com.cretona.app.ui.theme.GalaxyIndigo
import com.cretona.app.ui.theme.GalaxyViolet

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
                try {
                    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
                    val name = uri.lastPathSegment ?: "avatar.jpg"
                    if (bytes != null) {
                        viewModel.onAvatarSelected(uri, bytes, mime, name)
                    }
                } catch (_: Exception) {
                    // A picked file we cannot read is not worth crashing over;
                    // the avatar is optional and the user can pick another.
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
                    "Change your picture or username."
                } else {
                    "Pick a picture and choose a username."
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
                            MaterialTheme.colorScheme.error
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
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White,
                    focusedLabelColor = Color.White,
                    unfocusedLabelColor = Color.White.copy(alpha = 0.7f),
                    focusedBorderColor = GalaxyBrightAccent,
                    unfocusedBorderColor = Color.White.copy(alpha = 0.5f),
                    cursorColor = GalaxyBrightAccent,
                ),
            )

            if (state.errorMessage != null) {
                Spacer(modifier = Modifier.height(10.dp))
                Text(
                    text = state.errorMessage.orEmpty(),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = viewModel::submit,
                enabled = state.canSubmit,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = GalaxyBrightAccent),
            ) {
                if (state.isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(if (isEdit) "Save changes" else "Confirm")
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
