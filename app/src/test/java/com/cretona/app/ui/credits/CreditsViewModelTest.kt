package com.cretona.app.ui.credits

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.EventClaimResult
import com.cretona.app.domain.model.Page
import com.cretona.app.domain.model.PaymentReceipt
import com.cretona.app.domain.model.PromoEvent
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

    @Test
    fun `a claim survives a refetch that never arrives`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = mockk<CreditsRepository>()
            val event = grantEvent(claimable = true, claimedThisPeriod = false, remainingSlots = 3)

            var balanceFetches = 0
            coEvery { repository.getBalance() } answers {
                if (balanceFetches++ == 0) {
                    AppResult.Success(CreditBalance(5, 1, 1, null, 5, 0))
                } else {
                    AppResult.Failure(AppError.Network("Connection lost"))
                }
            }
            coEvery { repository.getTransactions(any(), any()) } returns
                AppResult.Success(Page(emptyList(), null))
            coEvery { repository.getPackages() } returns AppResult.Success(emptyList())

            // The list loads once, then the network drops. Everything the card
            // shows after the claim therefore came from the local edit, which is
            // exactly what makes the button flip without waiting for a round trip.
            var eventFetches = 0
            coEvery { repository.getEvents(any()) } answers {
                if (eventFetches++ == 0) {
                    AppResult.Success(Page(listOf(event), null))
                } else {
                    AppResult.Failure(AppError.Network("Connection lost"))
                }
            }
            coEvery { repository.claimEvent("evt-1", any()) } returns AppResult.Success(
                EventClaimResult(creditsGranted = 20, balance = 25, transactionId = "txn-1"),
            )

            val viewModel = CreditsViewModel(repository)
            advanceUntilIdle()
            viewModel.claimEvent("evt-1")
            advanceUntilIdle()

            val claimed = viewModel.state.value.events.first { it.id == "evt-1" }
            assertEquals(true, claimed.claimedThisPeriod)
            assertEquals(false, claimed.claimable)
            assertEquals(2, claimed.remainingSlots)
            assertEquals(25, viewModel.state.value.balance?.balance)
            assertEquals("Claimed 20 credits.", viewModel.state.value.message)
        }

    @Test
    fun `a refused claim leaves the card alone`() =
        runTest(mainDispatcherRule.dispatcher) {
            val repository = mockk<CreditsRepository>()
            val event = grantEvent(claimable = true, claimedThisPeriod = false, remainingSlots = 3)

            coEvery { repository.getBalance() } returns AppResult.Success(
                CreditBalance(5, 1, 1, null, 5, 0),
            )
            coEvery { repository.getTransactions(any(), any()) } returns
                AppResult.Success(Page(emptyList(), null))
            coEvery { repository.getPackages() } returns AppResult.Success(emptyList())
            coEvery { repository.getEvents(any()) } returns AppResult.Success(Page(listOf(event), null))
            coEvery { repository.claimEvent("evt-1", any()) } returns AppResult.Failure(
                AppError.Network("Connection lost"),
            )

            val viewModel = CreditsViewModel(repository)
            advanceUntilIdle()
            viewModel.claimEvent("evt-1")
            advanceUntilIdle()

            // A failed claim granted nothing, so the button must stay usable.
            val untouched = viewModel.state.value.events.first { it.id == "evt-1" }
            assertEquals(false, untouched.claimedThisPeriod)
            assertEquals(true, untouched.claimable)
            assertEquals(5, viewModel.state.value.balance?.balance)
        }

    private fun grantEvent(
        claimable: Boolean,
        claimedThisPeriod: Boolean,
        remainingSlots: Int?,
    ) = PromoEvent(
        id = "evt-1",
        code = "WEEKEND_GIFT",
        name = "Weekend gift",
        description = null,
        kind = "grant",
        bonusCredits = 20,
        discountPercent = null,
        recurrence = "weekly",
        isActiveNow = true,
        activeUntil = null,
        nextActiveAt = null,
        claimable = claimable,
        claimedThisPeriod = claimedThisPeriod,
        remainingSlots = remainingSlots,
    )
}
