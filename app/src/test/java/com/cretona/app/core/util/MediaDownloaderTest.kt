package com.cretona.app.core.util

import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException

class MediaDownloaderTest {

    @Test
    fun `safe title is bounded and never empty`() {
        assertEquals("video", MediaDownloader.safeTitle("🌌"))
        assertEquals("My_video", MediaDownloader.safeTitle("__My video__"))
        assertEquals(40, MediaDownloader.safeTitle("a".repeat(80)).length)
    }

    @Test
    fun `successful response is copied completely`() {
        val expected = byteArrayOf(1, 2, 3, 4)
        val output = ByteArrayOutputStream()

        val count = MediaDownloader.copyResponseTo(response(200, expected), output)

        assertEquals(expected.size.toLong(), count)
        assertArrayEquals(expected, output.toByteArray())
    }

    @Test
    fun `unsuccessful response fails before writing a destination`() {
        val output = ByteArrayOutputStream()

        val error = assertThrows(IOException::class.java) {
            MediaDownloader.copyResponseTo(response(503, byteArrayOf(1, 2)), output)
        }

        assertEquals("Failed to download video: HTTP 503", error.message)
        assertEquals(0, output.size())
    }

    @Test
    fun `declared video larger than the cap fails before writing`() {
        val output = ByteArrayOutputStream()

        val error = assertThrows(IOException::class.java) {
            MediaDownloader.copyResponseTo(
                response(200, byteArrayOf(1, 2, 3, 4)),
                output,
                maxBytes = 3,
            )
        }

        assertEquals("The video exceeds the download size limit.", error.message)
        assertEquals(0, output.size())
    }

    private fun response(code: Int, body: ByteArray): Response = Response.Builder()
        .request(Request.Builder().url("https://example.invalid/video.mp4").build())
        .protocol(Protocol.HTTP_1_1)
        .code(code)
        .message("test")
        .body(body.toResponseBody())
        .build()
}
