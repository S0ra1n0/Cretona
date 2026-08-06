package com.cretona.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.cretona.app.ui.home.HomeScreen

@Composable
fun CretonaNavHost(
    navController: NavHostController,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = CretonaRoute.Home,
        modifier = modifier,
    ) {
        composable<CretonaRoute.Home> {
            HomeScreen()
        }
    }
}
