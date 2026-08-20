package com.cretona.app.core.util

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.core.graphics.scale
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream

/**
 * Compresses a reference image before upload.
 *
 * Camera photos can easily exceed 5–10 MB. This utility downscales the image
 * to at most 1920×1080 and re-encodes it as 85%-quality JPEG when the raw
 * bytes exceed [THRESHOLD_BYTES] or their pixel dimensions exceed the model
 * input budget. Small, already-bounded assets remain unchanged.
 *
 * Must be called from a background thread (IO dispatcher) — BitmapFactory
 * and JPEG encoding are CPU-intensive.
 */
object ImageCompressor {

    /** Below this size only already-bounded images are returned untouched. */
    private const val THRESHOLD_BYTES = 1_500_000L // 1.5 MB

    private const val MAX_WIDTH = 1920
    private const val MAX_HEIGHT = 1080
    private const val JPEG_QUALITY = 85

    /** Matches the FastAPI upload contract. The extra byte is never retained. */
    internal const val MAX_INPUT_BYTES = 10 * 1024 * 1024

    class ImageTooLargeException : IOException("Images must be 10 MB or smaller.")

    /** Reads a picker stream without allowing an unbounded ByteArray allocation. */
    fun readBounded(input: InputStream, maxBytes: Int = MAX_INPUT_BYTES): ByteArray {
        require(maxBytes > 0)
        val output = ByteArrayOutputStream(minOf(maxBytes, DEFAULT_BUFFER_SIZE))
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var total = 0
        while (true) {
            val count = input.read(buffer)
            if (count == -1) break
            total += count
            if (total > maxBytes) throw ImageTooLargeException()
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    /**
     * @param bytes   Raw file bytes from [ContentResolver].
     * @param mimeType Original MIME type (used to decide if re-encoding is worthwhile).
     * @return Compressed bytes (always JPEG when compression occurs) or [bytes] unchanged.
     */
    fun compress(bytes: ByteArray, mimeType: String = "image/jpeg"): Pair<ByteArray, String> {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return bytes to mimeType

        val exceedsDimensions = bounds.outWidth > MAX_WIDTH || bounds.outHeight > MAX_HEIGHT
        if (bytes.size < THRESHOLD_BYTES && !exceedsDimensions) return bytes to mimeType

        val options = BitmapFactory.Options().apply {
            inSampleSize = calculateInSampleSize(bounds.outWidth, bounds.outHeight)
        }
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
            ?: return bytes to mimeType // Decode failed — return original

        return try {
            val (targetW, targetH) = targetDimensions(bitmap.width, bitmap.height)
            val scaled = if (targetW < bitmap.width || targetH < bitmap.height) {
                bitmap.scale(targetW, targetH, /* filter = */ true)
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

    /** Bounds decode memory before the exact resize, including extreme panoramas. */
    internal fun calculateInSampleSize(width: Int, height: Int): Int {
        var sample = 1
        while (width / sample > MAX_WIDTH * 2 || height / sample > MAX_HEIGHT * 2) {
            sample *= 2
        }
        return sample
    }

    /** Returns dimensions scaled so neither side exceeds [MAX_WIDTH] × [MAX_HEIGHT]. */
    internal fun targetDimensions(w: Int, h: Int): Pair<Int, Int> {
        if (w <= MAX_WIDTH && h <= MAX_HEIGHT) return w to h
        val scale = minOf(MAX_WIDTH.toFloat() / w, MAX_HEIGHT.toFloat() / h)
        return (w * scale).toInt().coerceAtLeast(1) to (h * scale).toInt().coerceAtLeast(1)
    }
}
