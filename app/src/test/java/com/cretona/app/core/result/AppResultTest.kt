package com.cretona.app.core.result

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AppResultTest {

    @Test
    fun `map transforms success payload`() {
        val result: AppResult<Int> = AppResult.Success(2)

        val mapped = result.map { it * 3 }

        assertEquals(AppResult.Success(6), mapped)
    }

    @Test
    fun `map leaves failure untouched`() {
        val failure = AppResult.Failure(AppError.Unauthorized())

        val mapped = failure.map { "unreachable" }

        assertTrue(mapped is AppResult.Failure)
        assertEquals(failure, mapped)
    }
}
