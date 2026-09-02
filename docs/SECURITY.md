# Security Notes — Cretona

**Version:** 0.2 · **Status:** Implemented controls with open release checks

Implements the NFR-2.x requirements in [SRS.md](SRS.md). This is a working document for the team, not a compliance artifact.

---

## 1. Secret Classification

| Secret | Lives in | May reach the device? |
|---|---|---|
| Supabase project URL | `local.properties` → `BuildConfig` | yes |
| Supabase **anon** key | `local.properties` → `BuildConfig` | yes — it is designed to be public |
| Supabase **service_role** key | backend env only | **never** |
| Supabase JWT secret | backend env only | **never** |
| AI provider API keys | backend env only | **never** |
| Database connection strings | backend env only | **never** |
| Release signing keystore | out of the repo, secret store | n/a |

The anon key being shippable rests entirely on RLS being correct. It is not a credential — it identifies the project and carries no authority beyond what policies permit. That is why [DATA_MODEL.md §4](DATA_MODEL.md) treats RLS as mandatory rather than optional hardening.

**Anything in `BuildConfig` is readable by anyone who unzips the APK.** Treat it as public.

---

## 2. Authentication

- The app authenticates with Supabase Auth; the backend never sees a password.
- The backend verifies the JWT signature and expiry on every non-public request, then resolves the `users` row from the `sub` claim.
- Roles come from the database, **never** from a client-supplied header or a JWT claim the client could influence.
- The SDK owns session state and rotation. The full session is persisted only as
  an AES-GCM blob whose non-exportable key lives in Android Keystore; tokens are
  not copied into DataStore, logs, backups, or crash reports.
- The SDK proactively refreshes the session. The current backend client does not
  perform a second, hand-written refresh/retry path after a `401`; a rejected
  token is surfaced to the UI and the user can sign in again.
- `X-Debug-User-Id` is emitted only by an unconfigured debug build. It is never
  a fallback for a configured signed-out build or any release build.

---

## 3. Authorization

Two independent layers, both required:

1. **Service layer** — every read and write filters by `user_id = <caller>` or requires role `admin`. This is the primary control.
2. **RLS** — the same rule expressed in the database, defending against a compromised anon key or a query that forgets its filter.

Hiding a button is not authorization. Admin endpoints are verified server-side (FR-4.5); the app hiding admin screens is a UX nicety.

**IDOR:** `GET /projects/:id` for someone else's project returns `404`, not `403` — existence is not disclosed. This must be covered by a test, not just a code review.

---

## 4. Storage

- Both buckets are private. Nothing is served from a public URL.
- Reads use signed URLs with ~1 h expiry, minted per response.
- Uploads use a signed upload URL scoped to a single object key.
- The object key embeds the owner: `uploads/{user_id}/…`, `videos/{user_id}/{project_id}/…`, so Storage policies authorize on the path prefix.
- `POST /projects` rejects an `imagePath` whose `{user_id}` segment is not the caller's — otherwise a user could attach someone else's uploaded image to their own project.
- Signed URLs are never persisted in the database or on the device.

---

## 5. Input Handling

| Input | Validation |
|---|---|
| `prompt` | length 1–1000; stored as-is, never interpolated into SQL or shell |
| `imagePath` | must match the expected key pattern and the caller's user id |
| Uploaded image | content type allow-list, ≤ 10 MB, size enforced when signing **and** verified after upload |
| `username` | 3–30 chars, `[a-zA-Z0-9_]`, unique |
| Pagination `limit` | integer 1–50 — an unbounded limit is a denial-of-service vector |
| Provider name | must exist in the registry; never used to build a URL or path |

Application database access uses SQLite or psycopg with bound parameters. The
few dynamic SQL fragments are assembled only from server-owned allow-lists;
untrusted values are never concatenated into SQL.

---

## 6. Logging

Redaction happens where the data is produced, not at the logger, so no code path can bypass it:

- `Authorization` headers redacted at the OkHttp interceptor (app) and the HTTP logger (backend).
- Provider keys stripped in the adapter before a `generation_logs` row is built ([AI_PROVIDER_SPEC.md §5](AI_PROVIDER_SPEC.md)).
- Signed URLs logged as their object path only.
- No prompt content in error-reporting payloads — prompts are user content and may be sensitive.
- `requestId` correlates app reports with server logs without carrying user data.

---

## 7. Transport

- HTTPS/TLS 1.2+ in staging and production.
- Cleartext permitted only for `10.0.2.2` in debug builds, via a debug-only network security config — never `usesCleartextTraffic="true"` app-wide.
- Certificate pinning is not planned for MVP; it complicates certificate rotation and the threat it addresses is not our main risk.

---

## 8. Abuse and Cost

Generation costs real money per call, which makes abuse a financial problem, not just a load problem:

- Per-user quota enforced server-side before any provider call (FR-5.1).
- Rate limits per user and per IP, independent of quota (API_CONTRACT §5).
- `Idempotency-Key` on submit so a retried request cannot double-charge.
- Provider spend caps configured in the provider dashboard as a backstop.
- Admins can disable an abusive account immediately (FR-4.2), and the check runs before authorization so a disabled admin is stopped too.

---

## 9. Third-Party Data Flow

Prompts and uploaded images leave our infrastructure and are processed by the AI provider under their terms. This must be:

- stated in the privacy policy,
- declared in the Play Store data-safety form (NFR-6.2),
- surfaced in the app before a user's first generation.

---

## 10. Pre-Release Checklist

The repository CI uses read-only token permissions. Third-party workflow
actions are pinned to commit SHAs, the Gradle wrapper JAR is verified against
Gradle's published checksum, and the wrapper distribution ZIP has its own
`distributionSha256Sum`. Dependency updates arrive as reviewable grouped PRs.

- [ ] RLS enabled and policies verified live on `users`, `video_projects`, and
      `generation_logs`; migrations and disposable-Postgres tests are green,
      but this exact live probe is still separate.
- [ ] Cross-user access attempted with a real second account and blocked at the
      API, not just the UI; SQLite and PostgreSQL tests already cover the rule.
- [x] `/admin/*` rejected for a non-admin token by automated tests.
- [x] Release APK is decompressed and scanned in CI for server-only credential
      markers; the build fails on a match.
- [x] Disabled account is refused on its next request by SQLite and PostgreSQL
      tests.
- [x] Quota exhaustion returns `429` and blocks the provider call in automated
      tests.
- [ ] Live logs inspected for tokens, keys, and signed URLs; redaction behavior
      is covered by automated tests.
- [ ] Email confirmation re-enabled in Supabase Auth
- [ ] Release build signed with a keystore that is not in the repo
- [ ] Privacy policy published and linked from the store listing
