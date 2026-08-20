package com.cretona.app.core.util

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.job
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.OutputStream

/**
 * Utility for real Android devices:
 *  1. Saves generated videos directly into MediaStore (Gallery / Photos) so they appear instantly.
 *  2. Shares videos securely via Android Share Sheet using FileProvider content:// URIs (preventing FileUriExposedException).
 */
object MediaDownloader {

    private val httpClient = OkHttpClient()

    /**
     * Downloads video bytes and inserts into Android's public MediaStore (Movies/Cretona).
     * Android 10+ needs no storage permission. Android 8/9 callers must obtain
     * WRITE_EXTERNAL_STORAGE before invoking this method.
     */
    @Suppress("DEPRECATION")
    suspend fun saveVideoToGallery(
        context: Context,
        videoUrl: String,
        title: String,
    ): Result<Uri> = withContext(Dispatchers.IO) {
        var itemUri: Uri? = null
        try {
            val sanitizedTitle = safeTitle(title)
            val fileName = "Cretona_${sanitizedTitle}_${System.currentTimeMillis()}.mp4"

            val contentValues = ContentValues().apply {
                put(MediaStore.Video.Media.DISPLAY_NAME, fileName)
                put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    put(MediaStore.Video.Media.RELATIVE_PATH, "${Environment.DIRECTORY_MOVIES}/Cretona")
                    put(MediaStore.Video.Media.IS_PENDING, 1)
                } else {
                    val legacyDirectory = File(
                        Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES),
                        "Cretona",
                    )
                    if (!legacyDirectory.exists() && !legacyDirectory.mkdirs()) {
                        throw IOException("Could not create Movies/Cretona.")
                    }
                    put(MediaStore.Video.Media.DATA, File(legacyDirectory, fileName).absolutePath)
                }
            }

            val resolver = context.contentResolver
            val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            } else {
                MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            }

            val createdUri = resolver.insert(collection, contentValues)
                ?: throw IOException("Could not create MediaStore entry.")
            itemUri = createdUri

            val bytesWritten = resolver.openOutputStream(createdUri)?.use { outputStream ->
                downloadInto(videoUrl, outputStream)
            } ?: throw IOException("Could not open the MediaStore destination.")
            if (bytesWritten == 0L) throw IOException("The downloaded video was empty.")

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                contentValues.clear()
                contentValues.put(MediaStore.Video.Media.IS_PENDING, 0)
                if (resolver.update(createdUri, contentValues, null, null) != 1) {
                    throw IOException("Could not publish the downloaded video.")
                }
            }

            Result.success(createdUri)
        } catch (error: CancellationException) {
            itemUri?.let { runCatching { context.contentResolver.delete(it, null, null) } }
            throw error
        } catch (e: Exception) {
            itemUri?.let { runCatching { context.contentResolver.delete(it, null, null) } }
            Result.failure(e)
        }
    }

    /**
     * Caches the video locally and launches the system Share Sheet.
     */
    suspend fun shareVideo(
        context: Context,
        videoUrl: String,
        title: String,
    ): Result<Unit> = withContext(Dispatchers.IO) {
        var cacheFile: File? = null
        try {
            val cacheDir = File(context.cacheDir, "videos")
            if (!cacheDir.exists() && !cacheDir.mkdirs()) {
                throw IOException("Could not create the video share cache.")
            }
            pruneExpiredShares(cacheDir)
            cacheFile = File(cacheDir, "share_${System.currentTimeMillis()}.mp4")

            val bytesWritten = FileOutputStream(cacheFile).use { output ->
                downloadInto(videoUrl, output)
            }
            if (bytesWritten == 0L) throw IOException("The downloaded video was empty.")

            val contentUri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                cacheFile,
            )

            withContext(Dispatchers.Main) {
                val shareIntent = Intent(Intent.ACTION_SEND).apply {
                    type = "video/mp4"
                    putExtra(Intent.EXTRA_STREAM, contentUri)
                    putExtra(Intent.EXTRA_SUBJECT, title)
                    putExtra(Intent.EXTRA_TEXT, "Created with Cretona AI Video: \"$title\"")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                val chooser = Intent.createChooser(shareIntent, "Share video via")
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(chooser)
            }
            Result.success(Unit)
        } catch (error: CancellationException) {
            cacheFile?.delete()
            throw error
        } catch (error: Exception) {
            cacheFile?.delete()
            Result.failure(error)
        }
    }

    internal fun safeTitle(title: String): String =
        title.replace(Regex("[^a-zA-Z0-9_-]"), "_")
            .trim('_')
            .take(40)
            .ifBlank { "video" }

    internal fun copyResponseTo(
        response: Response,
        output: OutputStream,
        maxBytes: Long = MAX_VIDEO_BYTES,
    ): Long = response.use {
        if (!it.isSuccessful) {
            throw IOException("Failed to download video: HTTP ${it.code}")
        }
        val declaredLength = it.body.contentLength()
        if (declaredLength > maxBytes) {
            throw IOException("The video exceeds the download size limit.")
        }
        it.body.byteStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            var total = 0L
            while (true) {
                val count = input.read(buffer)
                if (count == -1) break
                total += count
                if (total > maxBytes) {
                    throw IOException("The video exceeds the download size limit.")
                }
                output.write(buffer, 0, count)
            }
            total
        }
    }

    private suspend fun downloadInto(videoUrl: String, output: OutputStream): Long {
        val request = Request.Builder().url(videoUrl).build()
        val call = httpClient.newCall(request)
        val cancellationHandle = currentCoroutineContext().job.invokeOnCompletion { cause ->
            if (cause is CancellationException) call.cancel()
        }
        return try {
            copyResponseTo(call.execute(), output)
        } finally {
            cancellationHandle.dispose()
            currentCoroutineContext().ensureActive()
        }
    }

    private fun pruneExpiredShares(cacheDir: File, nowMillis: Long = System.currentTimeMillis()) {
        val oldestAllowed = nowMillis - SHARE_CACHE_MAX_AGE_MILLIS
        cacheDir.listFiles()
            ?.filter { it.isFile && it.name.startsWith("share_") && it.lastModified() < oldestAllowed }
            ?.forEach { it.delete() }
    }

    private const val SHARE_CACHE_MAX_AGE_MILLIS = 24L * 60L * 60L * 1000L
    internal const val MAX_VIDEO_BYTES = 500L * 1024L * 1024L
}
