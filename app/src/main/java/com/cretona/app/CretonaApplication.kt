package com.cretona.app

import android.app.Application
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.disk.DiskCache
import coil3.memory.MemoryCache
import coil3.request.crossfade
import dagger.hilt.android.HiltAndroidApp
import okio.Path.Companion.toOkioPath

/**
 * Application entry point.
 *
 * Configures the Coil singleton [ImageLoader] with explicit disk and memory
 * caches so that history scrolling at 60 fps does not re-decode thumbnails
 * on every frame and generated videos are not re-downloaded on each visit.
 *
 * Cache budgets:
 *  - Disk  : 100 MB  (thumbnails + poster frames, survives process death)
 *  - Memory: 25% of available heap (decoded bitmaps, instant re-render)
 */
@HiltAndroidApp
class CretonaApplication : Application(), SingletonImageLoader.Factory {

    override fun newImageLoader(context: PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            .diskCache {
                DiskCache.Builder()
                    .directory(cacheDir.resolve("coil_image_cache").toOkioPath())
                    .maxSizeBytes(100L * 1024 * 1024)   // 100 MB
                    .build()
            }
            .memoryCache {
                MemoryCache.Builder()
                    .maxSizePercent(context, 0.25)       // 25% of available heap
                    .build()
            }
            .crossfade(true)
            .build()
}
