package com.cretona.app.ui.auth

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cretona.app.ui.theme.GalaxyBrightAccent
import com.cretona.app.ui.theme.GalaxyDeepBlue
import com.cretona.app.ui.theme.GalaxyIndigo
import com.cretona.app.ui.theme.GalaxyViolet

import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.widthIn

@Composable
fun AuthScreen(
    onLoginSuccess: (needsProfileSetup: Boolean) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(state.loginSucceeded) {
        if (state.loginSucceeded) {
            val needsSetup = state.needsProfileSetup
            viewModel.consumeLoginSucceeded()
            onLoginSuccess(needsSetup)
        }
    }

    val galaxyGradient = Brush.verticalGradient(
        colors = listOf(GalaxyDeepBlue, GalaxyIndigo, GalaxyViolet),
    )

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(galaxyGradient)
            .systemBarsPadding()
            .imePadding(),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 440.dp)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 28.dp, vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = if (state.isSignUpMode) "Create Account" else "Welcome to",
                color = Color.White,
                style = MaterialTheme.typography.headlineSmall,
            )
            Text(
                text = "Cretona",
                color = GalaxyBrightAccent,
                style = MaterialTheme.typography.displayMedium,
                fontWeight = FontWeight.Bold,
            )

            Spacer(modifier = Modifier.height(36.dp))

            OutlinedTextField(
                value = state.email,
                onValueChange = viewModel::onEmailChanged,
                label = { Text("Email") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Email,
                    imeAction = ImeAction.Next,
                ),
                modifier = Modifier.fillMaxWidth(),
                colors = authFieldColors(),
            )

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedTextField(
                value = state.password,
                onValueChange = viewModel::onPasswordChanged,
                label = { Text(if (state.isSignUpMode) "Password (min. 6 chars)" else "Password") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = if (state.isSignUpMode) ImeAction.Next else ImeAction.Done,
                ),
                keyboardActions = KeyboardActions(
                    onDone = {
                        if (!state.isSignUpMode) viewModel.submit()
                    },
                ),
                modifier = Modifier.fillMaxWidth(),
                colors = authFieldColors(),
            )

            AnimatedVisibility(
                visible = state.isSignUpMode,
                enter = fadeIn(),
                exit = fadeOut(),
            ) {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = state.confirmPassword,
                        onValueChange = viewModel::onConfirmPasswordChanged,
                        label = { Text("Confirm Password") },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Password,
                            imeAction = ImeAction.Done,
                        ),
                        keyboardActions = KeyboardActions(
                            onDone = { viewModel.submit() },
                        ),
                        modifier = Modifier.fillMaxWidth(),
                        colors = authFieldColors(),
                    )
                }
            }

            if (state.errorMessage != null) {
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = state.errorMessage.orEmpty(),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            if (state.successNotice != null) {
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = state.successNotice.orEmpty(),
                    color = GalaxyBrightAccent,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = viewModel::submit,
                enabled = state.canSubmit,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = GalaxyBrightAccent),
            ) {
                if (state.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(if (state.isSignUpMode) "Create Account" else "Login")
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedButton(
                onClick = viewModel::toggleMode,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
                border = BorderStroke(1.dp, Color.White.copy(alpha = 0.6f)),
            ) {
                Text(
                    if (state.isSignUpMode) {
                        "Already have an account? Sign In"
                    } else {
                        "Don't have an account? Create an account"
                    },
                )
            }
        }
    }
}

@Composable
private fun authFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = Color.White,
    unfocusedTextColor = Color.White,
    errorTextColor = Color.White,
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
