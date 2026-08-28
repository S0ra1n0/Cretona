package com.cretona.app.data

import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.CretonaApi
import com.cretona.app.data.remote.PaymentCreateRequest
import com.cretona.app.data.remote.PaymentDto
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

class CreditsRepositoryImplTest {
    private val api = mockk<CretonaApi>()
    private val repository = CreditsRepositoryImpl(api)

    @Test
    fun `purchase forwards the same idempotency key and package`() = runTest {
        coEvery { api.createPayment("intent-1", PaymentCreateRequest("pkg-1")) } returns PaymentDto(
            id = "pay-1",
            status = "completed",
            packageId = "pkg-1",
            amountVnd = 20_000,
            creditsGranted = 10,
            balance = 15,
            createdAt = "2026-08-28T00:00:00Z",
        )

        val result = repository.purchase("pkg-1", "intent-1")

        assertEquals(15, (result as AppResult.Success).data.balance)
        coVerify(exactly = 1) { api.createPayment("intent-1", PaymentCreateRequest("pkg-1")) }
    }
}
