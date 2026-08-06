# ADR-002: The app authenticates directly with Supabase Auth; the backend verifies the JWT

**Status:** Accepted · **Date:** 2026-08-06 · **Roadmap:** P0 (open question raised during roadmap review)

## Context

The plan specifies Supabase Auth and an Express backend without saying which one the app talks to for sign-in. Two coherent designs exist:

1. **Proxy** — the app posts credentials to Express, which calls Supabase and returns tokens. Express owns the whole session lifecycle.
2. **Direct** — the app uses the Supabase SDK for sign-up, sign-in, and refresh. Express only verifies the resulting JWT on each request.

## Decision

Direct. The Android app uses the Supabase Kotlin SDK for all authentication. The backend verifies the JWT's signature and expiry, resolves the `users` row from the `sub` claim, and never handles a password.

## Rationale

- Proxying means writing password handling, refresh-token rotation, and secure session persistence ourselves — the highest-risk code in the system, reimplemented for no gain. Direct authentication deletes that surface entirely.
- Token refresh is the part that is easy to get subtly wrong (races, expiry skew, retry storms). The SDK already solves it and stores tokens in encrypted storage.
- Password reset, email confirmation, and future OAuth providers come from Supabase without backend work.
- Verification on the server is a small, well-understood piece of middleware.

The cost is that the app now depends on two hosts instead of one, and the anon key ships in the APK. The anon key is designed to be public and carries no authority beyond what RLS permits — which is why [DATA_MODEL.md §4](../DATA_MODEL.md) makes RLS mandatory rather than optional.

## Consequences

- `SUPABASE_URL` and `SUPABASE_ANON_KEY` are build config in the app; `service_role` never is ([SECURITY.md](../SECURITY.md)).
- Every backend request carries `Authorization: Bearer <supabase JWT>` ([API_CONTRACT.md §1.2](../API_CONTRACT.md)).
- **Roles are read from the database on each request, never from a JWT claim.** A client-influenced claim is not an authorization source.
- Account state that Supabase does not know about — `is_disabled` — is enforced by our middleware, so a valid token alone is not sufficient to be served.
- Image upload can go straight from the app to Storage via a signed URL, so image bytes never pass through Express.
- If we ever need auth Supabase can't express, the proxy design is still reachable; the app's repository interface would change but nothing above it.
