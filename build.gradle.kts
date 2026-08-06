// Top-level build file. Plugins are declared here without applying them so
// each module can opt in via `alias(libs.plugins.…)`.
plugins {
    // AGP 9 has built-in Kotlin support, so there is no kotlin-android plugin here.
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.hilt) apply false
}
