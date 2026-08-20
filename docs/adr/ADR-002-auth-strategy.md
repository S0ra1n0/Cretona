# ADR-002: Android authenticates directly with Supabase Auth

**Status:** Accepted and implemented · **Date:** 2026-08-06 · **Updated:** 2026-08-20

## Context

The client can either proxy email/password through FastAPI or authenticate
directly with Supabase. Proxying would make Cretona responsible for password
handling, refresh-token rotation, and an additional session protocol.

The application also needs to survive process death without storing access or
refresh tokens as plaintext, and FastAPI must remain the only model/provider
orchestration boundary required by the instructor.

## Decision

The Android app uses `supabase-kt` Auth for sign-up, sign-in, sign-out, session
loading, and refresh-token rotation. FastAPI never receives a password. It
verifies the Supabase JWT on each protected request and resolves role/account
state from PostgreSQL rather than trusting a client-controlled claim.

The complete rotating `UserSession` is serialized into one AES-GCM
authenticated blob. Its non-exportable key lives in Android Keystore and the
ciphertext lives in private SharedPreferences. Cloud backup and device transfer
are disabled because ciphertext restored to a different device cannot be
decrypted with that device's Keystore. Corrupt or undecryptable data fails
closed to a signed-out state.

On process start, a dedicated restore destination waits for SDK initialization
before choosing Auth, Profile Setup, or Main. The SDK owns proactive refresh;
Cretona does not copy tokens into DataStore or implement its own rotation
algorithm.

Credential-free debug builds remain usable against local FastAPI development
auth. They send the fixed `X-Debug-User-Id` only when Supabase is completely
unconfigured. A Supabase-configured but signed-out build—and every signed-out
release build—sends no debug identity.

## Consequences

- `SUPABASE_URL` and the public anon/publishable key are Android build config;
  `service_role`, database credentials, and provider keys never reach the APK.
- Authenticated FastAPI calls carry only `Authorization: Bearer <access-token>`.
- The custom encrypted store has an Android Keystore instrumented test. It can
  compile on the host but requires an emulator/device to execute.
- The app depends on both Supabase Auth and FastAPI availability for a full
  authenticated journey.
- Email-confirmation-required sign-up does not call FastAPI until a real session
  exists, preventing the local debug identity from being mistaken for the new
  account.
- The anon/publishable key is intentionally distributable; RLS and FastAPI
  authorization remain mandatory because the key is not an authorization
  boundary.

## Rejected alternative

Proxying credentials through FastAPI was rejected because it adds password and
session-lifecycle code without improving the provider boundary. If a future
identity requirement cannot be expressed by Supabase Auth, the app-owned
`AuthRepository` and `SessionManager` interfaces preserve a bounded migration
seam.
