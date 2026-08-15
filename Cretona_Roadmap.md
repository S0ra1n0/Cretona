# Cretona — Implementation Roadmap

Derived from [Cretona_Development_Plan_Kotlin.md](Cretona_Development_Plan_Kotlin.md).
Task IDs are stable — use them to pick what to implement next (e.g. "do P1-3 and P1-4").

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` skipped/deferred

**Current state (2026-08-12):** FastAPI has reached behavioural parity with the
Express/Prisma/Supabase reference. Its credential-free suite has **239 passing
tests, 19 Postgres-only skips, and clean Ruff**. The expanded 258-test run is
pending because local Docker/Postgres was unavailable for B-4 verification;
the Express reference still has its 77 tests and clean typecheck/build, and
remains migration evidence rather than a runtime. The Android app has 12
passing tests, clean lint/assembly, and recorded
emulator evidence for prompt → create → poll → playback → history. FastAPI has
also called pinned local Qwen3-4B with `usedFallback=false`.
Android now also consumes `/me` and shows the rolling quota before submission;
the rendered AVD result is recorded in
[the E2E evidence](docs/evidence/ANDROID_FASTAPI_E2E.md#b-8-quota-surface--2026-08-12).
Completed history cards now consume `thumbnailUrl` through Coil, preserve the
project's `16:9`, `9:16`, or `1:1` ratio, and degrade to a labelled fallback;
[B-9 AVD evidence](docs/evidence/ANDROID_FASTAPI_E2E.md#b-9-history-thumbnails--2026-08-12)
records the rendered result.

Ported since the migration slice: Supabase JWT identity, Postgres persistence,
Supabase Storage, role authorization and the admin surface, `/me`, the spend
quota, `generation_logs`, rate limiting, a background poller, structured
logging with central redaction, and thumbnails.
The raw provider audit now also has bounded 180-day retention; its Postgres
cutoff index is prepared in migration 006 but remains unapplied to Supabase.

**Two things are still unproven, and they are the important ones.** No code
has ever run against live Supabase — every green test is local Postgres, a
local file mount, and locally minted tokens. And video is still the
deterministic fake: LTX 2B was rejected by pre-screen, FramePack is installed
but blocked before inference by resource and licence gates, and no real video
provider is selected. See
[executed evidence](docs/evidence/ANDROID_FASTAPI_E2E.md).

Post-parity work is tracked separately in [docs/BACKLOG.md](docs/BACKLOG.md),
which marks each item by provenance so a proposal is not mistaken for an
assignment.

**Corrected 2026-08-15:** the project signs user tokens with **ES256**, not the
legacy HS256 shared secret. An earlier note here claimed the opposite and was
wrong; the HS256-only verifier could never have authenticated a real user, and
only running the service against live Supabase exposed it. Both schemes are now
supported, chosen by `CRETONA_SUPABASE_JWT_ALGORITHM` rather than inferred from
the token, with the public keys fetched from the project's JWKS endpoint.

**Live verification 2026-08-15:** a real Supabase-issued token authenticated
end to end against live Postgres — signature verified from JWKS, `sub` resolved
to a `public.users` row, role read from the database, quota computed from
`video_projects`. That closes the gap open since TASK A.

Runway is not a pending task — ADR-009 superseded it, `RUNWAY_API_KEY`
is deliberately empty, and the FastAPI provider registry does not accept it.

---

## Phase 0 — Foundations & Decisions ✅

| ID | Task | Outcome |
|----|------|---------|
| P0-1 | `[x]` Repo layout decision | Monorepo, Android at repo root — [ADR-001](docs/adr/ADR-001-repo-layout.md) |
| P0-2 | `[~]` Pick the launch AI provider | Paid Runway assumption superseded by [ADR-009](docs/adr/ADR-009-zero-spend-provider-gate.md). Qwen prompt LLM is proven; LTX is rejected; FramePack I2V is installed but blocked; real video remains unselected |
| P0-3 | `[x]` Secrets strategy | Nothing sensitive on device; `local.properties` for per-machine config — [ADR-005](docs/adr/ADR-005-secrets-management.md) |
| P0-4 | `[x]` Environments + config matrix | Two deployed envs, three app configurations — [ADR-006](docs/adr/ADR-006-environments.md) |
| P0-5 | `[x]` Async completion strategy | Server-side polling; webhooks designed for but deferred — [ADR-003](docs/adr/ADR-003-async-strategy.md) |
| P0-6 | `[x]` Cost/quota model | Rolling daily per-user quota, default 10/day — [ADR-007](docs/adr/ADR-007-quota-model.md). Limit is provisional until P0-2 gives real pricing |
| P0-7 | `[x]` Auth topology (open question from the first review) | App → Supabase Auth directly; backend verifies the JWT — [ADR-002](docs/adr/ADR-002-auth-strategy.md) |

---

## Phase D — Documentation (living) ✅

| ID | Task |
|----|------|
| D-1 | `[x]` [SRS](docs/SRS.md) — actors, FR/NFR with ids, MVP acceptance criteria |
| D-2 | `[x]` [API contract](docs/API_CONTRACT.md) — endpoints, error envelope, pagination, idempotency, rate limits |
| D-3 | `[x]` [Data model](docs/DATA_MODEL.md) — ERD, columns, constraints, indexes, RLS, storage layout, retention |
| D-4 | `[x]` [Architecture](docs/ARCHITECTURE.md) — system diagram, Android layering, backend pipeline, trade-offs |
| D-5 | `[x]` [AI provider spec](docs/AI_PROVIDER_SPEC.md) — interface, normalization, failure taxonomy, add-a-provider checklist |
| D-6 | `[x]` [Setup guide](docs/SETUP.md) — prerequisites, `local.properties` keys, build commands, troubleshooting |
| D-7 | `[x]` [Security notes](docs/SECURITY.md) — secret classification, authz layers, redaction, pre-release checklist |
| D-8 | `[x]` [ADR set](docs/adr/README.md) — ADR-001 … ADR-009 |
| D-9 | `[ ]` Keep the contract and data model in sync with code as each phase lands |

---

## Phase 1 — Supabase & Data Layer

All SQL lives in [`supabase/bootstrap.sql`](supabase/bootstrap.sql). **Executed and behaviour-tested** against Postgres 16 in Docker with `auth`/`storage` stubbed to Supabase's shape — clean apply, idempotent re-run, and 11 behavioural checks passing (RLS isolation, privilege escalation blocked, constraints, storage prefix scoping). Evidence table in [supabase/README.md](supabase/README.md). Not yet applied to a real Supabase project — that's P1-1.

| ID | Task |
|----|------|
| P1-1 | `[ ]` **Yours** — create the Supabase project, apply `bootstrap.sql`, run the verification queries, copy keys into `local.properties` / `backend/.env`. Steps in [supabase/README.md](supabase/README.md) |
| P1-2 | `[x]` Schema: `project_status` enum, four tables, CHECK constraints. Plus [`prisma/schema.prisma`](backend/prisma/schema.prisma) as the client model |
| P1-3 | `[x]` `roles` seeded with `user` (1) and `admin` (2) |
| P1-4 | `[x]` `auth.users` → `public.users` signup trigger, email-change sync, `updated_at` triggers |
| P1-5 | `[x]` RLS on all three tables + `is_admin()` + 6 policies, **plus column-level grants** — the grant is what stops a client promoting itself to admin |
| P1-6 | `[x]` Private `uploads` and `videos` buckets, 4 owner-scoped object policies |
| P1-7 | `[x]` 6 indexes, 3 of them partial (poller scan, history list, idempotency) |
| P1-8 | `[x]` `is_disabled` added to `users` |

**Schema gaps found in the plan** — all closed in the authored schema:
- ~~No way to disable a user~~ → `users.is_disabled`.
- ~~No `provider` / `provider_job_id` on `video_projects`~~ → both added; the poller needs them without joining logs.
- ~~No `error_message` for the `failed` status~~ → added, and a CHECK enforces that `failed` rows have one.
- ~~Consider `deleted_at`~~ → added, with the history index partial on it.
- Also added: `idempotency_key` (safe submit retries), `attempt_count` (retry accounting), `thumbnail_path`.

---

## Phase 2 — Reference backend (Node.js + Express + Prisma)

This implementation is preserved as a behavioral migration oracle: typecheck
and production build pass, and **77 tests pass**. FastAPI is the active course
runtime under ADR-008; the status table below describes the reference stack and
must not be read as the active framework plan.

| ID | Task |
|----|------|
| P2-1 | `[x]` Express 5 + TypeScript (ESM) scaffold, layout per plan |
| P2-2 | `[x]` Prisma 7 client over the `pg` driver adapter; `prisma.config.ts` for CLI URLs; `prisma generate` verified |
| P2-3 | `[x]` Config loader with zod validation — **verified**: missing keys exit 1 and name every one |
| P2-4 | `[x]` Auth chain: verify Supabase JWT (HS256) → load user → reject if disabled |
| P2-5 | `[x]` RBAC: `requireRole()` / `requireAdmin` |
| P2-6 | `[x]` `AppError` + error-code table + the single error-envelope handler |
| P2-7 | `[x]` pino structured logging with central redaction; `X-Request-Id` assigned and echoed |
| P2-8 | `[x]` `GET /health` (liveness) and `GET /health/ready` (503 when the DB is down) |
| P2-18 | `[x]` Rate limiting emits `X-RateLimit-*`; the database-backed per-user quota is the actual spend control, and Android now displays it before submission |
| P2-19 | `[~]` `validate()` middleware built; per-route schemas arrive with each endpoint |

### API surface

| ID | Task |
|----|------|
| P2-9  | `[x]` `GET /me`, `PATCH /me` — profile read/update, with quota; unique-username violation mapped to 409 |
| P2-10 | `[ ]` `POST /projects` — create generation job (text / image / text+image) |
| P2-11 | `[ ]` `GET /projects` — paginated history for current user, filter by status |
| P2-12 | `[ ]` `GET /projects/:id` — detail incl. current status |
| P2-13 | `[ ]` `DELETE /projects/:id` — delete project + its stored media |
| P2-14 | `[ ]` `POST /uploads/sign` — signed upload URL for source images (app uploads direct to Storage) |
| P2-15 | `[x]` `GET /admin/users` — cursor pagination, search, role and disabled filters |
| P2-16 | `[x]` `PATCH /admin/users/:id` — role change and enable/disable, self-modification blocked (FR-4.6) |
| P2-17 | `[x]` `GET /admin/stats` — totals, per-status, per-provider, failure rate, daily series |
| P2-18 | `[x]` Rate limiting **and** the per-user rolling quota service (ADR-007), which required a new `error_code` column — [migration 002](supabase/002_add_error_code.sql) |
| P2-19 | `[x]` zod validation wired on every route defined so far; new routes add their schema in `src/schemas/` |

---

## Phase 3 — AI provider integration

| ID | Task |
|----|------|
| P3-1 | `[x]` Define a provider-neutral interface and canonical states; implemented in both the Express reference and FastAPI local slice |
| P3-2 | `[x]` Select provider by backend configuration; FastAPI currently permits only the deterministic fake |
| P3-3 | `[ ]` Implement the launch provider chosen in P0-2 |
| P3-4 | `[~]` Text mode is normalized and validated in FastAPI; image/text+image await the next slice |
| P3-5 | `[ ]` Write every request/response to `generation_logs` (redact keys) |
| P3-6 | `[x]` Deterministic local state progression is implemented and proven through Android polling; production worker parity remains open |
| P3-7 | `[ ]` OR webhook receiver + signature verification (if P0-5 chose webhooks) |
| P3-8 | `[ ]` On completion: download result, re-upload to Supabase Storage, persist permanent `video_url` (provider URLs expire) |
| P3-9 | `[ ]` Failure handling: retries with backoff, timeout → `failed` + error message |
| P3-10 | `[ ]` Second provider implementation to prove the abstraction |

---

## Phase 4 — Android App (Kotlin + Compose)

### Setup
| ID | Task |
|----|------|
| P4-1 | `[x]` Android project at repo root — AGP 9.2.1, Kotlin 2.3.20, compileSdk 37, minSdk 26, Compose + Material 3 |
| P4-2 | `[x]` Version catalog wired: Compose BOM, Navigation, Hilt+KSP, Retrofit 3/OkHttp 5, kotlinx-serialization, Coil 3, Media3, DataStore, Paging |
| P4-3 | `[x]` Package structure for MVVM + Repository (`core/`, `data/`, `domain/`, `di/`, `ui/`) |
| P4-4 | `[~]` Retrofit + OkHttp + `Json` provided via Hilt; `AppResult`/`AppError` defined. **Still to do:** auth interceptor injecting the JWT, and the HTTP→`AppError` mapper |
| P4-5 | `[x]` Nav graph (type-safe routes) + Material 3 theme, light/dark |
| P4-18 | `[ ]` Add Supabase Kotlin SDK and the session store (deferred until the Supabase project exists — P1-1) |

### Features
| ID | Task |
|----|------|
| P4-6  | `[ ]` Auth: register, login, logout, session persistence, token refresh |
| P4-7  | `[ ]` Profile screen: view/edit |
| P4-8  | `[~]` Generate screen — text prompt mode works against FastAPI fake; real-model validation remains |
| P4-9  | `[ ]` Generate screen — image picker + upload to Storage |
| P4-10 | `[ ]` Generate screen — combined text+image mode + provider/params selector |
| P4-11 | `[x]` Generation progress UI: pending/generating/completed states and polling proven on emulator |
| P4-12 | `[~]` History list: local history renders; pagination, filters, thumbnails, and pull-to-refresh remain |
| P4-13 | `[~]` Completed result plays through Media3; dedicated detail/delete UX remains |
| P4-14 | `[ ]` Download video to device storage + share intent |
| P4-15 | `[ ]` Admin screens: user list, disable/enable, role change, stats dashboard (gated by role) |
| P4-16 | `[ ]` Global states: loading, empty, error, offline; retry affordances |
| P4-17 | `[ ]` Optional: push/local notification when a generation finishes |

---

## Phase 5 — Quality & Testing

| ID | Task |
|----|------|
| P5-1 | `[~]` FastAPI service/provider tests pass for the local fake profile; real adapter tests remain |
| P5-2 | `[~]` FastAPI project lifecycle, ownership, idempotency, and persistence tests pass with dev auth/SQLite; deployed auth/database remain |
| P5-3 | `[~]` Seven Android unit tests pass across existing scaffold, mapping, repository, and ViewModel behavior; expand edge cases with new features |
| P5-4 | `[ ]` Compose UI tests for the critical paths (login, generate, history) |
| P5-5 | `[~]` Emulator generate → poll → playback → history passes with fake/dev profile; signup and real generation remain |
| P5-6 | `[ ]` Security review: RLS actually enforced, no keys in the APK, signed URLs scoped, IDOR checks on `/projects/:id` |
| P5-7 | `[ ]` Lint/format/static analysis: ESLint+Prettier, ktlint/detekt |

---

## Phase 6 — Deployment & Ops

| ID | Task |
|----|------|
| P6-1 | `[ ]` Backend hosting (Railway/Render/Fly) + env vars + managed migrations |
| P6-2 | `[ ]` CI: build + test on push; CD to staging |
| P6-3 | `[ ]` Android release build: signing config, ProGuard/R8 rules, build flavors per environment |
| P6-4 | `[ ]` Crash/error reporting (Sentry or Crashlytics) both sides |
| P6-5 | `[ ]` Structured logging + basic metrics/alerts on failed generations |
| P6-6 | `[ ]` Play Store listing, privacy policy, data-safety form (AI content + user uploads) |
| P6-7 | `[ ]` Backups/retention policy for Storage and DB |

---

## Suggested order from the verified vertical slice

1. Resolve FramePack's host resource/pagefile and downloaded-weight license
   gates, then run it twice or reject it; do not wire Android to model-specific
   fields.
2. Select and gate a replacement text-to-video candidate. LTX 2B must remain
   rejected unless new pinned Ampere evidence changes its host envelope.
3. Implement a real FastAPI video adapter only for a candidate that passes;
   keep the raw model ID server-side.
4. Port Supabase JWT verification, Postgres persistence, and permanent media
   storage into FastAPI while retaining the current API tests.
5. Add reference-image input only after the text path remains green.
6. Add quota/admin/release evidence, then execute the SRS acceptance suite.

The dependency spine is now: **verified fake vertical slice + real Qwen prompt
proof → EXP-005 video decision → real provider adapter → Supabase parity/auth
→ image mode → acceptance/security/release evidence**.

---

## Deliberately Out of Scope for MVP
Payments/subscriptions · social features/sharing feed · in-app video editing · multi-language · web client · offline generation queue.
