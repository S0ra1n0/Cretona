package com.cretona.app.core.media

import android.content.Context
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.database.StandaloneDatabaseProvider
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.datasource.cache.CacheDataSource
import androidx.media3.datasource.cache.LeastRecentlyUsedCacheEvictor
import androidx.media3.datasource.cache.SimpleCache
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import java.io.File

/**
 * Manages local disk caching for video playback using Media3 ExoPlayer SimpleCache.
 *
 * When a video is streamed, chunks are automatically saved to local storage
 * (up to 250 MB LRU cache limit). Subsequent playbacks read directly from disk cache,
 * ensuring instant replay with zero network overhead and full offline replay support.
 */
@OptIn(UnstableApi::class)
object VideoCacheManager {
    private const val MAX_CACHE_SIZE_BYTES = 250L * 1024L * 1024L // 250 MB
    private const val CACHE_DIR_NAME = "cretona_video_cache"

    @Volatile
    private var simpleCache: SimpleCache? = null

    @Synchronized
    fun getCache(context: Context): SimpleCache {
        return simpleCache ?: synchronized(this) {
            simpleCache ?: run {
                val cacheDir = File(context.cacheDir, CACHE_DIR_NAME)
                if (!cacheDir.exists()) {
                    cacheDir.mkdirs()
                }
                val evictor = LeastRecentlyUsedCacheEvictor(MAX_CACHE_SIZE_BYTES)
                val databaseProvider = StandaloneDatabaseProvider(context)
                SimpleCache(cacheDir, evictor, databaseProvider).also {
                    simpleCache = it
                }
            }
        }
    }

    /**
     * Creates a CacheDataSource.Factory that transparently reads from local disk cache
     * if the video has been downloaded before, or streams from the network and saves
     * chunks to local cache simultaneously.
     */
    fun createCacheDataSourceFactory(context: Context): DataSource.Factory {
        val cache = getCache(context.applicationContext)
        val httpDataSourceFactory = DefaultHttpDataSource.Factory()
            .setAllowCrossProtocolRedirects(true)
            .setConnectTimeoutMs(15_000)
            .setReadTimeoutMs(30_000)

        val upstreamFactory = DefaultDataSource.Factory(context.applicationContext, httpDataSourceFactory)

        return CacheDataSource.Factory()
            .setCache(cache)
            .setUpstreamDataSourceFactory(upstreamFactory)
            .setFlags(CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)
    }

    /**
     * Creates a DefaultMediaSourceFactory pre-configured with local video caching.
     */
    fun createMediaSourceFactory(context: Context): DefaultMediaSourceFactory {
        val cacheDataSourceFactory = createCacheDataSourceFactory(context)
        return DefaultMediaSourceFactory(context.applicationContext)
            .setDataSourceFactory(cacheDataSourceFactory)
    }

    /**
     * Releases cache resources when the application terminates.
     */
    @Synchronized
    fun release() {
        try {
            simpleCache?.release()
            simpleCache = null
        } catch (_: Exception) {}
    }
}
