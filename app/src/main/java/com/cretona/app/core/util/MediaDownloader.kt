package com.cretona.app.core.util

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream

/**
 * Utility for real Android devices:
 *  1. Saves generated videos directly into MediaStore (Gallery / Photos) so they appear instantly.
 *  2. Shares videos securely via Android Share Sheet using FileProvider content:// URIs (preventing FileUriExposedException).
 */
object MediaDownloader {

    private val httpClient = OkHttpClient()

    /**
     * Downloads video bytes and inserts into Android's public MediaStore (Movies/Cretona).
     * Works across Android 10 (API 29) to Android 15 without requiring legacy WRITE_EXTERNAL_STORAGE.
     */
    suspend fun saveVideoToGallery(
        context: Context,
        videoUrl: String,
        title: String,
    ): Result<Uri> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder().url(videoUrl).build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("Failed to download video: HTTP ${response.code}"))
            }

            val sanitizedTitle = title.replace(Regex("[^a-zA-Z0-9_-]"), "_").take(40)
            val fileName = "Cretona_${sanitizedTitle}_${System.currentTimeMillis()}.mp4"

            val contentValues = ContentValues().apply {
                put(MediaStore.Video.Media.DISPLAY_NAME, fileName)
                put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    put(MediaStore.Video.Media.RELATIVE_PATH, "${Environment.DIRECTORY_MOVIES}/Cretona")
                    put(MediaStore.Video.Media.IS_PENDING, 1)
                }
            }

            val resolver = context.contentResolver
            val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            } else {
                MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            }

            val itemUri = resolver.insert(collection, contentValues)
                ?: return@withContext Result.failure(Exception("Could not create MediaStore entry."))

            resolver.openOutputStream(itemUri)?.use { outputStream ->
                response.body.byteStream().copyTo(outputStream)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                contentValues.clear()
                contentValues.put(MediaStore.Video.Media.IS_PENDING, 0)
                resolver.update(itemUri, contentValues, null, null)
            }

            Result.success(itemUri)
        } catch (e: Exception) {
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
    ) = withContext(Dispatchers.IO) {
        try {
            val cacheDir = File(context.cacheDir, "videos").apply { mkdirs() }
            val cacheFile = File(cacheDir, "share_${System.currentTimeMillis()}.mp4")

            val request = Request.Builder().url(videoUrl).build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) return@withContext

            response.body.byteStream().use { input ->
                FileOutputStream(cacheFile).use { output ->
                    input.copyTo(output)
                }
            }

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
        } catch (_: Exception) {}
    }
}
