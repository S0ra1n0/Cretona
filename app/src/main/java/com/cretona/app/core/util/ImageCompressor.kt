package com.cretona.app.core.util

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.ByteArrayOutputStream

/**
 * Compresses a reference image before upload.
 *
 * Camera photos can easily exceed 5–10 MB. This utility downscales the image
 * to at most 1920×1080 and re-encodes it as 85%-quality JPEG when the raw
 * bytes exceed [THRESHOLD_BYTES]. Files already below the threshold are
 * returned unchanged so that small assets do not lose quality unnecessarily.
 *
 * Must be called from a background thread (IO dispatcher) — BitmapFactory
 * and JPEG encoding are CPU-intensive.
 */
object ImageCompressor {

    /** Below this size the image is returned untouched. */
    private const val THRESHOLD_BYTES = 1_500_000L // 1.5 MB

    private const val MAX_WIDTH = 1920
    private const val MAX_HEIGHT = 1080
    private const val JPEG_QUALITY = 85

    /**
     * @param bytes   Raw file bytes from [ContentResolver].
     * @param mimeType Original MIME type (used to decide if re-encoding is worthwhile).
     * @return Compressed bytes (always JPEG when compression occurs) or [bytes] unchanged.
     */
    fun compress(bytes: ByteArray, mimeType: String = "image/jpeg"): Pair<ByteArray, String> {
        if (bytes.size < THRESHOLD_BYTES) return bytes to mimeType

        val options = BitmapFactory.Options().apply { inJustDecodeBounds = false }
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
            ?: return bytes to mimeType  // Decode failed — return original

        return try {
            val (targetW, targetH) = targetDimensions(bitmap.width, bitmap.height)
            val scaled = if (targetW < bitmap.width || targetH < bitmap.height) {
                Bitmap.createScaledBitmap(bitmap, targetW, targetH, /* filter = */ true)
            } else {
                bitmap
            }
            val out = ByteArrayOutputStream()
            scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
            if (scaled !== bitmap) scaled.recycle()
            out.toByteArray() to "image/jpeg"
        } finally {
            bitmap.recycle()
        }
    }

    /** Returns dimensions scaled so neither side exceeds [MAX_WIDTH] × [MAX_HEIGHT]. */
    private fun targetDimensions(w: Int, h: Int): Pair<Int, Int> {
        if (w <= MAX_WIDTH && h <= MAX_HEIGHT) return w to h
        val scale = minOf(MAX_WIDTH.toFloat() / w, MAX_HEIGHT.toFloat() / h)
        return (w * scale).toInt().coerceAtLeast(1) to (h * scale).toInt().coerceAtLeast(1)
    }
}
