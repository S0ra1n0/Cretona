package com.cretona.app.core.result

/**
 * Result type used across repositories so ViewModels never see raw exceptions.
 */
sealed interface AppResult<out T> {
    data class Success<T>(val data: T) : AppResult<T>
    data class Failure(val error: AppError) : AppResult<Nothing>
}

sealed interface AppError {
    val message: String

    data class Network(override val message: String = "No connection") : AppError
    data class Unauthorized(override val message: String = "Session expired") : AppError
    data class Forbidden(override val message: String = "Not allowed") : AppError
    data class NotFound(override val message: String = "Not found") : AppError
    data class Server(
        val code: Int,
        override val message: String,
        val apiCode: String? = null,
    ) : AppError
    data class Unknown(override val message: String = "Something went wrong") : AppError
}

inline fun <T, R> AppResult<T>.map(transform: (T) -> R): AppResult<R> = when (this) {
    is AppResult.Success -> AppResult.Success(transform(data))
    is AppResult.Failure -> this
}
