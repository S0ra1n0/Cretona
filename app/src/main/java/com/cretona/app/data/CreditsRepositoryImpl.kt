package com.cretona.app.data

import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.CretonaApi
import com.cretona.app.data.remote.PaymentCreateRequest
import com.cretona.app.data.remote.toDomain
import com.cretona.app.domain.model.CreditBalance
import com.cretona.app.domain.model.CreditPackage
import com.cretona.app.domain.model.CreditTransaction
import com.cretona.app.domain.model.EventClaimResult
import com.cretona.app.domain.model.Page
import com.cretona.app.domain.model.PaymentReceipt
import com.cretona.app.domain.model.PromoEvent
import com.cretona.app.domain.repository.CreditsRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CreditsRepositoryImpl @Inject constructor(
    private val api: CretonaApi,
) : CreditsRepository {
    override suspend fun getBalance(): AppResult<CreditBalance> = apiCall {
        api.getCreditBalance().toDomain()
    }

    override suspend fun getTransactions(
        limit: Int,
        cursor: String?,
    ): AppResult<Page<CreditTransaction>> = apiCall {
        api.getCreditTransactions(limit, cursor).toDomain()
    }

    override suspend fun getPackages(): AppResult<List<CreditPackage>> = apiCall {
        api.getCreditPackages().items.map { it.toDomain() }
    }

    override suspend fun purchase(
        packageId: String,
        idempotencyKey: String,
    ): AppResult<PaymentReceipt> = apiCall {
        api.createPayment(idempotencyKey, PaymentCreateRequest(packageId)).toDomain()
    }

    override suspend fun getEvents(cursor: String?): AppResult<Page<PromoEvent>> = apiCall {
        api.getEvents(cursor).toDomain()
    }

    override suspend fun claimEvent(
        eventId: String,
        idempotencyKey: String,
    ): AppResult<EventClaimResult> = apiCall {
        api.claimEvent(eventId, idempotencyKey).toDomain()
    }
}
