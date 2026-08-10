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
            status = "completed",
            provider = "fake",
            durationSeconds = 5,
            createdAt = "2026-08-10T00:00:00Z",
            updatedAt = "2026-08-10T00:00:01Z",
            completedAt = "2026-08-10T00:00:01Z",
        ).toDomain()

        assertEquals(ProjectStatus.COMPLETED, project.status)
        assertEquals("http://example.test/media/demo.mp4", project.videoUrl)
        assertEquals(5, project.durationSeconds)
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
    }
}
