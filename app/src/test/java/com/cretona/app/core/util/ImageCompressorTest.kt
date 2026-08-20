package com.cretona.app.core.util

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.ByteArrayInputStream

class ImageCompressorTest {

    @Test
    fun `bounded reader accepts exactly the configured limit`() {
        val source = ByteArray(16) { it.toByte() }

        val result = ImageCompressor.readBounded(ByteArrayInputStream(source), maxBytes = 16)

        assertArrayEquals(source, result)
    }

    @Test
    fun `bounded reader rejects the first byte over the limit`() {
        val source = ByteArray(17)

        assertThrows(ImageCompressor.ImageTooLargeException::class.java) {
            ImageCompressor.readBounded(ByteArrayInputStream(source), maxBytes = 16)
        }
    }

    @Test
    fun `sample size bounds large photos and extreme panoramas`() {
        assertEquals(8, ImageCompressor.calculateInSampleSize(12_000, 9_000))
        assertEquals(4, ImageCompressor.calculateInSampleSize(8_000, 500))
        assertEquals(1, ImageCompressor.calculateInSampleSize(1_920, 1_080))
    }

    @Test
    fun `target dimensions preserve aspect ratio inside model bounds`() {
        assertEquals(1_440 to 1_080, ImageCompressor.targetDimensions(4_000, 3_000))
        assertEquals(1_920 to 120, ImageCompressor.targetDimensions(8_000, 500))
        assertEquals(640 to 480, ImageCompressor.targetDimensions(640, 480))
    }
}
