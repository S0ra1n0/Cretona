package com.cretona.app.ui.main

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cretona.app.ui.history.HistoryScreen
import com.cretona.app.ui.home.HomeScreen
import com.cretona.app.ui.home.HomeViewModel
import com.cretona.app.ui.profile.ProfileScreen
import com.cretona.app.ui.theme.GalaxyIndigo
import com.cretona.app.ui.theme.GalaxyViolet

enum class MainTab(val label: String, val icon: ImageVector) {
    HOME("Home", Icons.Default.Home),
    HISTORY("History", Icons.Default.List),
    PROFILE("Profile", Icons.Default.Person),
}

/**
 * The signed-in shell: one app bar and one bottom navigation bar shared by the
 * three tabs.
 *
 * The tabs are switched here rather than through a nested NavHost because they
 * all read the same account and project list. Hilt scopes the ViewModel to this
 * destination's back stack entry, so the instance obtained here is the same one
 * HomeScreen resolves internally -- switching tabs does not refetch, and a
 * generation started on Home is already present when History opens.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    onNavigateToAdmin: () -> Unit,
    onSignedOut: () -> Unit,
    onEditProfile: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var selectedTab by rememberSaveable { mutableStateOf(MainTab.HOME) }

    // Returning from profile editing (or the admin screen) must not leave a
    // stale username, avatar or quota on screen. The first resume is skipped
    // because the ViewModel already loads on construction.
    var isFirstResume by rememberSaveable { mutableStateOf(true) }
    LifecycleResumeEffect(Unit) {
        if (isFirstResume) {
            isFirstResume = false
        } else {
            viewModel.refreshAccount()
        }
        onPauseOrDispose { }
    }

    val headerGradient = remember {
        Brush.horizontalGradient(colors = listOf(GalaxyIndigo, GalaxyViolet))
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = {
            // The gradient is painted by this Box rather than by the app bar so
            // it also covers the status bar area behind it; the app bar itself
            // stays transparent and keeps its own inset handling.
            Box(modifier = Modifier.fillMaxWidth().background(headerGradient)) {
                CenterAlignedTopAppBar(
                    title = {
                        Text(
                            text = "Cretona",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                        )
                    },
                    colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                        containerColor = Color.Transparent,
                        titleContentColor = Color.White,
                    ),
                    actions = {
                        if (state.account?.role == "admin") {
                            TextButton(onClick = onNavigateToAdmin) {
                                Text("Admin", color = Color.White)
                            }
                        }
                    },
                )
            }
        },
        bottomBar = {
            NavigationBar {
                MainTab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = selectedTab == tab,
                        onClick = { selectedTab = tab },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.primary,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                        ),
                    )
                }
            }
        },
    ) { innerPadding ->
        // Passed as contentPadding rather than applied as a modifier so each
        // tab's list scrolls *under* the bars instead of being clipped by them.
        when (selectedTab) {
            MainTab.HOME -> HomeScreen(
                contentPadding = innerPadding,
                viewModel = viewModel,
            )

            MainTab.HISTORY -> HistoryScreen(
                projects = state.projects,
                onRemixProject = { project ->
                    viewModel.remixProject(project)
                    // Remix populates the create form, which lives on Home.
                    selectedTab = MainTab.HOME
                },
                onDeleteProject = viewModel::deleteProject,
                onRefresh = viewModel::refreshHistory,
                contentPadding = innerPadding,
            )

            MainTab.PROFILE -> ProfileScreen(
                account = state.account,
                onSignedOut = onSignedOut,
                onEditProfile = onEditProfile,
                isLoading = state.isAccountLoading,
                errorMessage = state.accountErrorMessage,
                onRetry = viewModel::refreshAccount,
                contentPadding = innerPadding,
            )
        }
    }
}
