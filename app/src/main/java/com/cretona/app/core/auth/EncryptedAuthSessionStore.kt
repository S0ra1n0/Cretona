package com.cretona.app.core.auth

import android.annotation.SuppressLint
import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import dagger.hilt.android.qualifiers.ApplicationContext
import io.github.jan.supabase.auth.SessionManager as SupabaseSdkSessionManager
import io.github.jan.supabase.auth.exception.NoSessionFoundException
import io.github.jan.supabase.auth.user.UserSession
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Persists the rotating Supabase session as one AES-GCM authenticated blob.
 * The AES key is non-exportable and remains in Android Keystore; neither token
 * is ever written to disk or logs in plaintext.
 *
 * The store intentionally uses synchronous SharedPreferences commits. The SDK
 * treats a completed save/delete call as durable, so returning before the disk
 * write has finished would make process death race session rotation or sign-out.
 */
@SuppressLint("ApplySharedPref", "UseKtx")
@Singleton
class EncryptedAuthSessionStore @Inject constructor(
    @ApplicationContext context: Context,
    private val json: Json,
) : SupabaseSdkSessionManager {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val mutex = Mutex()

    override suspend fun saveSession(session: UserSession) = withContext(Dispatchers.IO) {
        mutex.withLock {
            val plaintext = json.encodeToString(UserSession.serializer(), session).encodeToByteArray()
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(Cipher.ENCRYPT_MODE, loadOrCreateKey())
                updateAAD(AAD)
            }
            val encrypted = cipher.doFinal(plaintext)
            val payload = listOf(
                FORMAT_VERSION,
                Base64.encodeToString(cipher.iv, Base64.NO_WRAP),
                Base64.encodeToString(encrypted, Base64.NO_WRAP),
            ).joinToString(SEPARATOR)
            check(preferences.edit().putString(SESSION_KEY, payload).commit()) {
                "Could not persist the authenticated session."
            }
        }
    }

    override suspend fun loadSession(): UserSession = withContext(Dispatchers.IO) {
        mutex.withLock {
            val payload = preferences.getString(SESSION_KEY, null) ?: throw NoSessionFoundException()
            try {
                val parts = payload.split(SEPARATOR)
                require(parts.size == 3 && parts[0] == FORMAT_VERSION)
                val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                    init(
                        Cipher.DECRYPT_MODE,
                        loadOrCreateKey(),
                        GCMParameterSpec(GCM_TAG_BITS, Base64.decode(parts[1], Base64.NO_WRAP)),
                    )
                    updateAAD(AAD)
                }
                val plaintext = cipher.doFinal(Base64.decode(parts[2], Base64.NO_WRAP))
                json.decodeFromString(UserSession.serializer(), plaintext.decodeToString())
            } catch (_: Exception) {
                // A restored backup cannot use a device-bound Keystore key;
                // corrupt or obsolete data must fail closed as signed out.
                preferences.edit().remove(SESSION_KEY).commit()
                throw NoSessionFoundException()
            }
        }
    }

    override suspend fun deleteSession() = withContext(Dispatchers.IO) {
        mutex.withLock {
            check(preferences.edit().remove(SESSION_KEY).commit()) {
                "Could not clear the authenticated session."
            }
        }
    }

    private fun loadOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            generateKey()
        }
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "cretona_supabase_session_aes_v1"
        const val PREFERENCES_NAME = "cretona_secure_auth"
        const val SESSION_KEY = "session_v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val FORMAT_VERSION = "v1"
        const val SEPARATOR = ":"
        const val GCM_TAG_BITS = 128
        val AAD = "com.cretona.app:session_v1".encodeToByteArray()
    }
}
