package com.cretona.app.ui.home

import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Test

class HomeScreenFormattingTest {
    @Test
    fun `quota reset time uses the requested local timezone`() {
        assertEquals(
            "13 Aug 2026, 19:00",
            formatQuotaResetTime("2026-08-13T12:00:00Z", ZoneId.of("Asia/Ho_Chi_Minh")),
        )
    }

    @Test
    fun `invalid quota reset time stays readable`() {
        assertEquals("not-a-date", formatQuotaResetTime("not-a-date"))
    }
}
