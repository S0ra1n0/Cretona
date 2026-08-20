package com.cretona.app.domain.model

/**
 * A cursor-addressed slice returned by the backend.
 *
 * Keeping the continuation metadata in the domain contract prevents callers
 * from silently truncating server collections to their first page.
 */
data class CursorPage<T>(
    val items: List<T>,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
) {
    init {
        require(!hasMore || !nextCursor.isNullOrBlank()) {
            "A page marked hasMore must include a continuation cursor."
        }
    }
}
