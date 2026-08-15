# Cretona configuration and secret boundary

Status: accepted baseline on 2026-08-10; FastAPI variables added 2026-08-12.

## Authoritative configuration

- Android machine-local values belong in root `local.properties`, because the
  repository root is the Android Gradle project.
- Backend environment values belong in `backend-fastapi/.env` for the active
  service, and `backend/.env` for the Express reference. Each committed
  `.env.example` must mirror its config loader without containing a real value.
- Only `local.properties.example` and the two `.env.example` files are safe to
  commit.
- Android must never receive a provider service key, JWT signing secret, or
  database administrator credential.

## FastAPI variables

Every setting is prefixed `CRETONA_` and loaded by `backend-fastapi/app/config.py`.
Startup fails rather than degrading when a profile is selected without the
credentials it needs.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` refuses `AUTH_MODE=dev` |
| `LOG_LEVEL` | `info` | JSON logs; redaction is central, not per call site |
| `AUTH_MODE` | `dev` | `dev` injects an identity and honours `X-Debug-User-Id`; `supabase` verifies tokens and ignores that header entirely |
| `SUPABASE_JWT_ALGORITHM` | `HS256` | `ES256` is Supabase's current default and what this project uses; `HS256` is the legacy shared secret. Chosen here, never inferred from the token |
| `SUPABASE_JWKS_URL` | derived | ES256 only. Defaults to `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` |
| **`SUPABASE_JWT_SECRET`** | — | **Secret.** HS256 only. Not needed under ES256, where the backend holds no signing material at all |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | |
| `SUPABASE_JWT_ISSUER` | empty | Enforced only when set |
| `SUPABASE_JWT_LEEWAY_SECONDS` | `0` | Clock-skew tolerance |
| `DATABASE_BACKEND` | `sqlite` | `postgres` targets Supabase |
| `DATABASE_PATH` | `data/cretona.db` | SQLite only |
| **`DATABASE_URL`** | — | **Secret**, carries a password. Required when `DATABASE_BACKEND=postgres`. Prefer the direct connection: psycopg uses prepared statements, which Supabase's transaction pooler does not support |
| `STORAGE_BACKEND` | `local` | `supabase` uses buckets and signed URLs |
| `SUPABASE_URL` | — | Required when `STORAGE_BACKEND=supabase` |
| **`SUPABASE_SERVICE_ROLE_KEY`** | — | **Secret.** Bypasses RLS, so it is server-side only and never reaches the app |
| `SUPABASE_UPLOADS_BUCKET` / `SUPABASE_VIDEOS_BUCKET` | `uploads` / `videos` | |
| `SIGNED_URL_TTL_SECONDS` | `3600` | Bounded to 60…604800, so a signed URL cannot be minted permanent |
| `MEDIA_DIR` | `assets` | Local storage root |
| `DEFAULT_VIDEO_PROVIDER` | `fake` | `fake` is the only accepted value; see ADR-009 |
| `MAX_GENERATION_ATTEMPTS` | `3` | Submissions per project before a retry is refused |
| `GENERATION_QUOTA_LIMIT` | `10` | Per user per window. This is the spend control (ADR-007) |
| `GENERATION_QUOTA_WINDOW_HOURS` | `24` | |
| `RATE_LIMIT_ENABLED` | `true` | Burst protection only; Postgres shares one atomic window across API instances, while SQLite uses the credential-free in-memory fallback |
| `RATE_LIMIT_DEFAULT_PER_MIN` | `120` | |
| `RATE_LIMIT_GENERATION_PER_MIN` | `10` | Tighter bucket for writes that cost money |
| `POLLER_ENABLED` | `true` | Advances jobs without waiting for a client read |
| `POLL_INTERVAL_SECONDS` / `POLL_BATCH_SIZE` | `5` / `20` | |
| **`WEBHOOK_SECRET`** | — | **Secret.** HMAC-SHA256 over the raw webhook body. Empty rejects every webhook; the route is public, so this is its only gate |
| `POLL_LEASE_SECONDS` | `120` | Durable claim on a batch. Must exceed batch duration, or another instance re-claims rows still being worked |
| `GENERATION_LOG_RETENTION_ENABLED` | `true` | Runs one cleanup batch at startup and then on the configured interval |
| `GENERATION_LOG_RETENTION_DAYS` | `180` | Raw provider audit lifetime; rows exactly at the cutoff are retained |
| `GENERATION_LOG_RETENTION_INTERVAL_SECONDS` | `86400` | Cleanup cadence; bounded to 60...604800 seconds |
| `GENERATION_LOG_RETENTION_BATCH_SIZE` | `10000` | Oldest-first delete ceiling per pass; bounded to 1...100000 |
| `GENERATION_TIMEOUT_SECONDS` | `600` | Per attempt, measured from `started_at`; sweeps stuck jobs to `failed` |
| `THUMBNAILS_ENABLED` | `true` | Needs `ffmpeg` on PATH; absent means `thumbnailUrl` stays null |
| `FFMPEG_PATH` | `ffmpeg` | |
| `THUMBNAIL_SEEK_SECONDS` | `1.0` | |
| `PROMPT_LLM_PROVIDER` | `deterministic` | `ollama` uses the pinned local model |
| `OLLAMA_*` | see `.env.example` | Base URL, model, timeout, context, token budget, temperature |
| `FAKE_POLLS_BEFORE_COMPLETE` / `FAKE_VIDEO_FILENAME` | `1` / `demo-output.mp4` | Deterministic demo timing |

The four bolded variables are the only secrets. All are `SecretStr`, so they
are excluded from reprs and logs, and none appear in `.env.example` with a
value.

### Test-only

`CRETONA_TEST_DATABASE_URL` selects the Postgres parity suite. **It must point
at a disposable local database**: the fixture drops and recreates tables, so
aiming it at a real project would destroy data. `tests/db_safety.py` refuses
any non-local host unless `CRETONA_TEST_DATABASE_ALLOW_REMOTE=1` is set
explicitly.

## Teammate-provided local files

Bruce confirmed on 2026-08-10 that S0ra1n0 supplied the untracked root files
`env` and `local.properties`. Their keys indicate a Node/Supabase/Runway
direction, and the Android SDK path in the root `local.properties` belongs to
S0ra1n0's Windows profile rather than Bruce's machine. The live remote audit on
2026-08-10 found the matching Compose, Express, Prisma, and Supabase source plus
tests in commits `ac6804d` through `2cb3d91`.

These files are therefore classified as **teammate-provided, machine-local
configuration for the remote implementation**. They remain untouched so no
team data is lost, and `.gitignore` prevents them from being staged. Values
must be copied selectively into the canonical machine-local files; SDK paths
must never be copied between developers unchanged.

## Credential verification result

- Git history contains no occurrence of the three sensitive configuration key
  names detected in the local files.
- The local values were not printed, copied into documentation, or sent to a
  provider.
- Because validity and account ownership cannot be proved safely from this
  repository, they are treated as potentially real and owned by the teammate
  who supplied them until the team records otherwise.

Rotate a credential if it has ever been pasted into chat, shared through an
unsafe channel, committed in another repository, or exposed to someone who
should not retain access. Bruce should ask S0ra1n0 whether the service-role and
JWT values are live and whether their transfer channel was appropriate.
Rotation is an external account action and is not performed by this repository
setup.

## Accepted backend direction

FastAPI is the required final model-orchestration boundary. The teammate's
Express implementation is preserved as migration evidence because it already
defines tested auth, quota, project lifecycle, storage, provider, and job-runner
behavior. The migration replaces the web framework, not those invariants.

Supabase Auth/Postgres/Storage may remain behind FastAPI during the migration so
the team does not rewrite working identity, data, and storage boundaries at the
same time. Runway remains disabled; zero-cost local video providers may be
added only behind the provider interface after `EXP-005` passes.

As of 2026-08-12 that migration is behaviourally complete: identity,
persistence, storage, authorization, quota, logging, rate limiting, and the job
runner all exist in `backend-fastapi/`. None of it has run against live
Supabase, so the credentials above are configured but unexercised.
