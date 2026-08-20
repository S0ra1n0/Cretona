package com.cretona.app.data

import com.cretona.app.data.remote.ProjectDto
import com.cretona.app.domain.model.ProjectStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProjectDtoMappingTest {
    @Test
    fun `completed DTO maps all playback fields`() {
        val project = ProjectDto(
            id = "project-1",
            title = "Lantern city",
            prompt = "A paper dragon",
            videoUrl = "http://example.test/media/demo.mp4",
            thumbnailUrl = "http://example.test/media/demo-thumbnail.jpg",
            status = "completed",
            provider = "fake",
            durationSeconds = 5,
            aspectRatio = "9:16",
            createdAt = "2026-08-10T00:00:00Z",
            updatedAt = "2026-08-10T00:00:01Z",
            completedAt = "2026-08-10T00:00:01Z",
        ).toDomain()

        assertEquals(ProjectStatus.COMPLETED, project.status)
        assertEquals("http://example.test/media/demo.mp4", project.videoUrl)
        assertEquals("http://example.test/media/demo-thumbnail.jpg", project.thumbnailUrl)
        assertEquals(5, project.durationSeconds)
        assertEquals("9:16", project.aspectRatio)
        assertEquals(9f / 16f, project.thumbnailAspectRatio)
        assertNull(project.errorMessage)
    }

    @Test
    fun `unknown status fails closed`() {
        val project = ProjectDto(
            id = "project-2",
            title = "Unknown",
            status = "provider_added_new_state",
            provider = "fake",
            createdAt = "2026-08-10T00:00:00Z",
            updatedAt = "2026-08-10T00:00:00Z",
        ).toDomain()

        assertEquals(ProjectStatus.FAILED, project.status)
        assertEquals("Unknown job status.", project.errorMessage)
        assertNull(project.thumbnailUrl)
    }

    @Test
    fun `cancelled status remains a non-error terminal state`() {
        val project = ProjectDto(
            id = "project-cancelled",
            title = "Cancelled project",
            status = "cancelled",
            provider = "fake",
            createdAt = "2026-08-10T00:00:00Z",
            updatedAt = "2026-08-10T00:00:01Z",
        ).toDomain()

        assertEquals(ProjectStatus.CANCELLED, project.status)
        assertEquals(true, project.isTerminal)
        assertNull(project.errorMessage)
    }
}
