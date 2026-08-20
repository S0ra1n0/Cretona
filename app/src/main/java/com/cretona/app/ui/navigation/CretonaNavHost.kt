package com.cretona.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cretona.app.ui.admin.AdminScreen
import com.cretona.app.ui.auth.AuthScreen
import com.cretona.app.ui.auth.RestoredDestination
import com.cretona.app.ui.auth.SessionRestoreScreen
import com.cretona.app.ui.auth.SessionRestoreViewModel
import com.cretona.app.ui.main.MainScreen
import com.cretona.app.ui.setup.ProfileSetupScreen

@Composable
fun CretonaNavHost(
    navController: NavHostController,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = CretonaRoute.SessionRestore,
        modifier = modifier,
    ) {
        composable<CretonaRoute.SessionRestore> {
            val viewModel = hiltViewModel<SessionRestoreViewModel>()
            val state by viewModel.state.collectAsStateWithLifecycle()

            LaunchedEffect(state.destination) {
                val destination = when (state.destination) {
                    RestoredDestination.AUTH -> CretonaRoute.Auth
                    RestoredDestination.PROFILE_SETUP -> CretonaRoute.ProfileSetup(isEdit = false)
                    RestoredDestination.MAIN -> CretonaRoute.Main
                    null -> return@LaunchedEffect
                }
                navController.navigate(destination) {
                    popUpTo(CretonaRoute.SessionRestore) { inclusive = true }
                }
            }

            SessionRestoreScreen(
                state = state,
                onRetry = viewModel::restore,
            )
        }

        composable<CretonaRoute.Auth> {
            AuthScreen(
                onLoginSuccess = { needsProfileSetup ->
                    // An account with no username has never completed setup,
                    // which is the state a freshly created one is in.
                    val destination = if (needsProfileSetup) {
                        CretonaRoute.ProfileSetup(isEdit = false)
                    } else {
                        CretonaRoute.Main
                    }
                    navController.navigate(destination) {
                        // Successful login must not leave the login screen on
                        // the back stack -- pressing back from Home would
                        // otherwise return to a stale, already-submitted form.
                        popUpTo(CretonaRoute.Auth) { inclusive = true }
                    }
                },
            )
        }
        composable<CretonaRoute.ProfileSetup> { entry ->
            val route = entry.toRoute<CretonaRoute.ProfileSetup>()
            if (route.isEdit) {
                // Editing returns to where it was opened from, so Main keeps
                // its state and simply refreshes the account it already holds.
                ProfileSetupScreen(
                    isEdit = true,
                    onSetupComplete = { navController.popBackStack() },
                    onCancel = { navController.popBackStack() },
                )
            } else {
                ProfileSetupScreen(
                    onSetupComplete = {
                        navController.navigate(CretonaRoute.Main) {
                            // Setup is finished and persisted; going back into
                            // it would offer to redo a completed step.
                            popUpTo(route) { inclusive = true }
                        }
                    },
                )
            }
        }
        composable<CretonaRoute.Main> {
            MainScreen(
                onNavigateToAdmin = {
                    navController.navigate(CretonaRoute.Admin)
                },
                onSignedOut = {
                    navController.navigate(CretonaRoute.Auth) {
                        // Clear the whole signed-in graph, so back cannot
                        // re-enter a session that was just ended.
                        popUpTo(CretonaRoute.Main) { inclusive = true }
                    }
                },
                onEditProfile = {
                    navController.navigate(CretonaRoute.ProfileSetup(isEdit = true))
                },
            )
        }
        composable<CretonaRoute.Admin> {
            AdminScreen(
                onNavigateBack = {
                    navController.popBackStack()
                },
            )
        }
    }
}
