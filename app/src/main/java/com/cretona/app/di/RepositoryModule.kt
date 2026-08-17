package com.cretona.app.di

import com.cretona.app.data.AuthRepositoryImpl
import com.cretona.app.data.CretonaRepositoryImpl
import com.cretona.app.domain.repository.AuthRepository
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
}
