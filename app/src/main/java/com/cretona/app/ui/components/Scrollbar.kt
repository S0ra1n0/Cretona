package com.cretona.app.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Draws a scroll position indicator down the right edge of a LazyColumn.
 *
 * Compose has no built-in scrollbar for lazy lists, and the Home form is long
 * enough that without one there is no cue for how much is left below the fold.
 *
 * The thumb size and offset are estimated from the average size of the
 * currently visible items rather than measured exactly -- a lazy list does not
 * know the size of items it has never composed. For uniform-ish content this
 * tracks closely; with wildly varying item heights it drifts, which is the
 * accepted trade for not having to measure everything up front.
 *
 * It fades in while scrolling and back out when idle, so it never competes with
 * the content it sits beside.
 */
@Composable
fun Modifier.verticalScrollbar(
    state: LazyListState,
    width: Dp = 4.dp,
    minimumThumbHeight: Dp = 24.dp,
    color: Color,
): Modifier {
    val targetAlpha = if (state.isScrollInProgress) 0.6f else 0f
    val alpha by animateFloatAsState(
        targetValue = targetAlpha,
        // Appears immediately on touch, lingers briefly so a short flick does
        // not flash it in and out.
        animationSpec = tween(durationMillis = if (state.isScrollInProgress) 120 else 500),
        label = "scrollbarAlpha",
    )

    return this.drawWithContent {
        drawContent()

        val info = state.layoutInfo
        val visibleItems = info.visibleItemsInfo
        if (alpha <= 0f || visibleItems.isEmpty()) return@drawWithContent

        val viewportHeight = (info.viewportEndOffset - info.viewportStartOffset).toFloat()
        val averageItemSize = visibleItems.sumOf { it.size }.toFloat() / visibleItems.size
        val estimatedContentHeight = averageItemSize * info.totalItemsCount
        // Nothing to indicate when everything already fits on screen.
        if (estimatedContentHeight <= viewportHeight || viewportHeight <= 0f) return@drawWithContent

        val firstVisible = visibleItems.first()
        val scrolledPast = firstVisible.index * averageItemSize - firstVisible.offset
        val scrollableDistance = estimatedContentHeight - viewportHeight
        val progress = (scrolledPast / scrollableDistance).coerceIn(0f, 1f)

        val thumbHeight = (viewportHeight * (viewportHeight / estimatedContentHeight))
            .coerceAtLeast(minimumThumbHeight.toPx())
            .coerceAtMost(viewportHeight)
        val thumbTop = (viewportHeight - thumbHeight) * progress

        val thumbWidth = width.toPx()
        drawRoundRect(
            color = color,
            topLeft = Offset(x = size.width - thumbWidth, y = thumbTop),
            size = Size(thumbWidth, thumbHeight),
            cornerRadius = CornerRadius(thumbWidth / 2f),
            alpha = alpha,
        )
    }
}
