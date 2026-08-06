package com.cretona.app.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.cretona.app.BuildConfig
import com.cretona.app.ui.theme.CretonaTheme

/**
 * Placeholder start destination. It exists so the scaffold is runnable and so
 * the build-time configuration is visible on device while the real screens
 * (P4-6 onwards) are being built.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(modifier: Modifier = Modifier) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = { TopAppBar(title = { Text("Cretona") }) },
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "AI video generation",
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = "Project scaffold is up. Screens land per the roadmap.",
                style = MaterialTheme.typography.bodyMedium,
            )

            ConfigCard(
                label = "API base URL",
                value = BuildConfig.API_BASE_URL,
            )
            ConfigCard(
                label = "Supabase URL",
                value = BuildConfig.SUPABASE_URL.ifBlank { "not configured (see docs/SETUP.md)" },
            )
            ConfigCard(
                label = "Build",
                value = "${BuildConfig.BUILD_TYPE} · v${BuildConfig.VERSION_NAME}",
            )
        }
    }
}

@Composable
private fun ConfigCard(label: String, value: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(text = label, style = MaterialTheme.typography.titleMedium)
            Text(text = value, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun HomeScreenPreview() {
    CretonaTheme { HomeScreen() }
}
