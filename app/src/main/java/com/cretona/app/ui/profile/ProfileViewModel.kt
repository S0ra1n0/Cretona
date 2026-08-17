package com.cretona.app.ui.profile

import androidx.lifecycle.ViewModel
import com.cretona.app.core.auth.SessionManager
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val session: SessionManager,
) : ViewModel() {
    /**
     * Drops the access token so subsequent requests are no longer made as this
     * user. The caller navigates back to the auth screen; clearing here rather
     * than in the composable keeps the token's lifetime owned by one place.
     */
    fun signOut() {
        session.clear()
    }
}
