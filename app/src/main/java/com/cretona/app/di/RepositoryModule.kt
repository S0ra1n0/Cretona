package com.cretona.app.di

import com.cretona.app.data.AuthRepositoryImpl
import com.cretona.app.data.CretonaRepositoryImpl
import com.cretona.app.data.FakeCreditsRepository
import com.cretona.app.domain.repository.AuthRepository
import com.cretona.app.domain.repository.CreditsRepository
import com.cretona.app.domain.repository.CretonaRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    @Singleton
    abstract fun bindCretonaRepository(implementation: CretonaRepositoryImpl): CretonaRepository

    @Binds
    @Singleton
    abstract fun bindAuthRepository(implementation: AuthRepositoryImpl): AuthRepository

    /**
     * B-02: the credits feature runs on an in-memory fake until the endpoints
     * land (S-07, S-11). Screens are built against [CreditsRepository], so
     * switching this line to the real implementation is the whole migration.
     *
     * TODO(S-07/S-11): bind CreditsRepositoryImpl once the endpoints exist.
     */
    @Binds
    @Singleton
    abstract fun bindCreditsRepository(
        implementation: FakeCreditsRepository,
    ): CreditsRepository
}
