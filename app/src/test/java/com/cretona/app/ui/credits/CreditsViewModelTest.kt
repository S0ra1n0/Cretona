package com.cretona.app.ui.credits

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.Page
import com.cretona.app.domain.model.PaymentReceipt
import com.cretona.app.domain.repository.CreditsRepository
import com.cretona.app.ui.home.MainDispatcherRule
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class CreditsViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `purchase retry reuses the original idempotency key`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = mockk<CreditsRepository>()
            val packageItem = CreditPackage("pkg-1", "Starter", 10, 20_000, 1)
            coEvery { repository.getBalance() } returns AppResult.Success(
                CreditBalance(5, 2, 2, null, 5, 0),
            )
            coEvery { repository.getTransactions(any(), any()) } returns AppResult.Success(Page(emptyList(), null))
            coEvery { repository.getPackages() } returns AppResult.Success(listOf(packageItem))
            coEvery { repository.getEvents(any()) } returns AppResult.Success(Page(emptyList(), null))

            val observedKeys = mutableListOf<String>()
            var attempt = 0
            coEvery { repository.purchase("pkg-1", any()) } answers {
                observedKeys += arg<String>(1)
                if (attempt++ == 0) {
                    AppResult.Failure(AppError.Network("Connection lost"))
                } else {
                    AppResult.Success(
                        PaymentReceipt(
                            id = "pay-1",
                            status = "completed",
                            packageId = "pkg-1",
                            amountVnd = 20_000,
                            creditsGranted = 10,
                            balance = 15,
                            method = "simulated",
                            createdAt = "2026-08-28T00:00:00Z",
                            completedAt = "2026-08-28T00:00:00Z",
                        ),
                    )
                }
            }

            val viewModel = CreditsViewModel(repository)
            advanceUntilIdle()
            viewModel.selectPackage(packageItem)
            viewModel.confirmPurchase()
            advanceUntilIdle()
            viewModel.confirmPurchase()
            advanceUntilIdle()

            assertEquals(2, observedKeys.size)
            assertEquals(observedKeys[0], observedKeys[1])
            assertNull(viewModel.state.value.selectedPackage)
        }
}
