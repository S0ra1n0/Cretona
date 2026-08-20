package com.cretona.app.ui.setup

import com.cretona.app.core.result.AppError
import com.cretona.app.core.result.AppResult
import com.cretona.app.data.remote.HealthResponse
import com.cretona.app.domain.model.AdminAuditLog
import com.cretona.app.domain.model.AdminMetrics
import com.cretona.app.domain.model.AdminStats
import com.cretona.app.domain.model.AdminUser
import com.cretona.app.domain.model.BackfillResult
import com.cretona.app.domain.model.CursorPage
import com.cretona.app.domain.model.EnhancedPrompt
import com.cretona.app.domain.model.GenerationQuota
import com.cretona.app.domain.model.UserProfile
import com.cretona.app.domain.model.VideoProject
import com.cretona.app.domain.repository.CretonaRepository
import com.cretona.app.ui.home.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ProfileSetupViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    // --- optional details start unanswered -----------------------------------

    @Test
    fun `a fresh form has no gender or birthday chosen`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        val state = viewModel.state.value
        assertEquals("", state.gender)
        assertEquals("", state.birthday)
        assertNull(state.selectedGender)
    }

    @Test
    fun `only the username gates submission`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onUsernameChanged("valid_name")

        // Neither detail has been answered, and the form is still saveable.
        assertTrue(viewModel.state.value.canSubmit)
    }

    @Test
    fun `a malformed birthday blocks submission`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onUsernameChanged("valid_name")
        viewModel.onBirthdayChanged("17-04-1998")

        assertFalse(viewModel.state.value.canSubmit)
        assertEquals("Use the date picker, or type YYYY-MM-DD.", viewModel.state.value.birthdayError)
    }

    @Test
    fun `an empty birthday is not an error`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onUsernameChanged("valid_name")
        viewModel.onBirthdayChanged("")

        assertNull(viewModel.state.value.birthdayError)
        assertTrue(viewModel.state.value.canSubmit)
    }

    @Test
    fun `avatar picker failure is visible to the user`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onAvatarSelectionFailed("The selected image could not be read.")

        assertEquals("The selected image could not be read.", viewModel.state.value.errorMessage)
    }

    // --- gender selection ----------------------------------------------------

    @Test
    fun `selecting a gender stores its lowercase wire value`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onGenderSelected(GenderOption.FEMALE)

        assertEquals("female", viewModel.state.value.gender)
        assertEquals(GenderOption.FEMALE, viewModel.state.value.selectedGender)
    }

    @Test
    fun `re-selecting the same gender clears it`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onGenderSelected(GenderOption.MALE)
        viewModel.onGenderSelected(GenderOption.MALE)

        // The only route back to "prefer not to say" once an answer is given.
        assertEquals("", viewModel.state.value.gender)
        assertNull(viewModel.state.value.selectedGender)
    }

    @Test
    fun `selecting a different gender replaces rather than clears`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onGenderSelected(GenderOption.MALE)
        viewModel.onGenderSelected(GenderOption.OTHER)

        assertEquals("other", viewModel.state.value.gender)
    }

    // --- prefill -------------------------------------------------------------

    @Test
    fun `editing prefills the stored details`() = runTest {
        val repository = FakeRepository(
            profile = profile(username = "someone", gender = "male", birthday = "1998-04-17"),
        )
        val viewModel = ProfileSetupViewModel(repository)

        viewModel.startEdit()
        advanceUntilIdle()

        val state = viewModel.state.value
        assertEquals("someone", state.username)
        assertEquals("male", state.gender)
        assertEquals("1998-04-17", state.birthday)
        assertEquals(GenderOption.MALE, state.selectedGender)
    }

    @Test
    fun `editing an account that answered neither leaves both empty`() = runTest {
        val repository = FakeRepository(profile = profile(username = "someone"))
        val viewModel = ProfileSetupViewModel(repository)

        viewModel.startEdit()
        advanceUntilIdle()

        assertEquals("", viewModel.state.value.gender)
        assertEquals("", viewModel.state.value.birthday)
    }

    // --- saving --------------------------------------------------------------

    @Test
    fun `saving sends both details`() = runTest {
        val repository = FakeRepository()
        val viewModel = ProfileSetupViewModel(repository)

        viewModel.onUsernameChanged("valid_name")
        viewModel.onGenderSelected(GenderOption.OTHER)
        viewModel.onBirthdayChanged("2000-12-31")
        viewModel.submit()
        advanceUntilIdle()

        assertEquals("other", repository.lastGender)
        assertEquals("2000-12-31", repository.lastBirthday)
    }

    @Test
    fun `clearing a detail sends empty rather than omitting it`() = runTest {
        val repository = FakeRepository(
            profile = profile(username = "someone", gender = "male", birthday = "1998-04-17"),
        )
        val viewModel = ProfileSetupViewModel(repository)

        viewModel.startEdit()
        advanceUntilIdle()
        viewModel.onGenderSelected(GenderOption.MALE) // Re-tap clears it.
        viewModel.onBirthdayCleared()
        viewModel.submit()
        advanceUntilIdle()

        // Empty is what tells the backend to clear. Omitting would mean
        // "leave as is", and the value could never be taken back.
        assertEquals("", repository.lastGender)
        assertEquals("", repository.lastBirthday)
    }

    // --- date picker ---------------------------------------------------------

    @Test
    fun `picking a date fills the field and closes the picker`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onDatePickerRequested()
        assertTrue(viewModel.state.value.showDatePicker)

        viewModel.onBirthdayPicked("1990-06-01")

        assertEquals("1990-06-01", viewModel.state.value.birthday)
        assertFalse(viewModel.state.value.showDatePicker)
    }

    @Test
    fun `dismissing the picker leaves the field alone`() {
        val viewModel = ProfileSetupViewModel(FakeRepository())

        viewModel.onBirthdayChanged("1990-06-01")
        viewModel.onDatePickerRequested()
        viewModel.onDatePickerDismissed()

        assertEquals("1990-06-01", viewModel.state.value.birthday)
        assertFalse(viewModel.state.value.showDatePicker)
    }
}

private fun profile(
    username: String? = null,
    gender: String? = null,
    birthday: String? = null,
) = UserProfile(
    id = "user-1",
    email = "someone@example.com",
    username = username,
    avatarUrl = null,
    gender = gender,
    birthday = birthday,
    role = "user",
    isDisabled = false,
    createdAt = "2026-01-01T00:00:00Z",
    quota = GenerationQuota(limit = 10, used = 0, remaining = 10, resetsAt = null),
)

private class FakeRepository(
    private val profile: UserProfile = profile(),
) : CretonaRepository {
    var lastGender: String? = null
    var lastBirthday: String? = null

    override suspend fun getCurrentUser(): AppResult<UserProfile> = AppResult.Success(profile)

    override suspend fun updateProfile(
        username: String,
        avatarPath: String?,
        gender: String,
        birthday: String,
    ): AppResult<UserProfile> {
        lastGender = gender
        lastBirthday = birthday
        return AppResult.Success(
            profile.copy(
                username = username,
                gender = gender.ifEmpty { null },
                birthday = birthday.ifEmpty { null },
            ),
        )
    }

    override suspend fun enhancePrompt(prompt: String): AppResult<EnhancedPrompt> =
        AppResult.Failure(AppError.Unknown("not used in this test"))

    override suspend fun uploadImage(
        bytes: ByteArray,
        mimeType: String,
        fileName: String,
    ): AppResult<String> = AppResult.Failure(AppError.Unknown("not used in this test"))

    override suspend fun createProject(
        prompt: String?,
        imagePath: String?,
        idempotencyKey: String,
        provider: String,
        aspectRatio: String,
        stylePreset: String?,
        cameraMotion: String?,
    ): AppResult<VideoProject> = throw NotImplementedError()

    override suspend fun getProject(id: String): AppResult<VideoProject> = throw NotImplementedError()
    override suspend fun cancelProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun deleteProject(id: String): AppResult<Unit> = throw NotImplementedError()
    override suspend fun listProjects(limit: Int, cursor: String?): AppResult<CursorPage<VideoProject>> = throw NotImplementedError()
    override suspend fun getAdminStats(days: Int): AppResult<AdminStats> = throw NotImplementedError()

    override suspend fun getAdminUsers(
        limit: Int,
        cursor: String?,
        query: String?,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<CursorPage<AdminUser>> = throw NotImplementedError()

    override suspend fun updateAdminUser(
        id: String,
        role: String?,
        isDisabled: Boolean?,
    ): AppResult<AdminUser> = throw NotImplementedError()

    override suspend fun getAdminAuditLogs(
        limit: Int,
        cursor: String?,
        action: String?,
        actorId: String?,
    ): AppResult<CursorPage<AdminAuditLog>> = throw NotImplementedError()

    override suspend fun backfillThumbnails(): AppResult<BackfillResult> = throw NotImplementedError()
    override suspend fun checkHealth(): AppResult<HealthResponse> = throw NotImplementedError()
    override suspend fun getAdminMetrics(): AppResult<AdminMetrics> = throw NotImplementedError()
}
