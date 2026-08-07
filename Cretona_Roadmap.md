# Cretona — Implementation Roadmap

Derived from [Cretona_Development_Plan_Kotlin.md](Cretona_Development_Plan_Kotlin.md).
Task IDs are stable — use them to pick what to implement next (e.g. "do P1-3 and P1-4").

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` skipped/deferred

**Current state (2026-08-06):** Phase 0 decisions all recorded as ADRs. Documentation set written. Android scaffold builds and tests clean. Phase 1 schema verified against a real Postgres. Phase 2 core scaffold built and running — typecheck clean, 16 tests passing, server serves `/health`. Next: the P2 route handlers.

---

## Phase 0 — Foundations & Decisions ✅

| ID | Task | Outcome |
|----|------|---------|
| P0-1 | `[x]` Repo layout decision | Monorepo, Android at repo root — [ADR-001](docs/adr/ADR-001-repo-layout.md) |
| P0-2 | `[x]` Pick the launch AI provider | **Runway** confirmed, Kling second — [ADR-004](docs/adr/ADR-004-launch-provider.md). The 7-point verification checklist in that ADR still runs before P3-3 |
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
| D-8 | `[x]` [ADR set](docs/adr/README.md) — ADR-001 … ADR-007 |
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

## Phase 2 — Backend (Node.js + Express + Prisma)

Core scaffold is built and verified: typecheck clean, 16 tests passing, production build runs, server boots and serves traffic.

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
| P2-18 | `[~]` Rate limiting middleware built and emitting `X-RateLimit-*`. Per-user **quota** (the actual spend control) still to do |
| P2-19 | `[~]` `validate()` middleware built; per-route schemas arrive with each endpoint |

### API surface

| ID | Task |
|----|------|
| P2-9  | `[ ]` `GET /me`, `PATCH /me` — profile read/update |
| P2-10 | `[ ]` `POST /projects` — create generation job (text / image / text+image) |
| P2-11 | `[ ]` `GET /projects` — paginated history for current user, filter by status |
| P2-12 | `[ ]` `GET /projects/:id` — detail incl. current status |
| P2-13 | `[ ]` `DELETE /projects/:id` — delete project + its stored media |
| P2-14 | `[ ]` `POST /uploads/sign` — signed upload URL for source images (app uploads direct to Storage) |
| P2-15 | `[ ]` `GET /admin/users` — list/search/paginate |
| P2-16 | `[ ]` `PATCH /admin/users/:id` — change role, enable/disable |
| P2-17 | `[ ]` `GET /admin/stats` — totals, per-status counts, per-provider counts, recent activity |
| P2-18 | `[ ]` Rate limiting on generation endpoints + per-user quota enforcement (from P0-6) |
| P2-19 | `[ ]` Input validation (zod/joi) on every route |

---

## Phase 3 — AI Provider Integration

| ID | Task |
|----|------|
| P3-1 | `[ ]` Define `VideoProvider` interface: `submit(input) -> jobId`, `getStatus(jobId) -> {status, videoUrl, error}` |
| P3-2 | `[ ]` Provider registry/factory keyed by name; config-driven default |
| P3-3 | `[ ]` Implement the launch provider chosen in P0-2 |
| P3-4 | `[ ]` Normalize inputs across modes (text-only, image-only, text+image) and validate per-provider capability |
| P3-5 | `[ ]` Write every request/response to `generation_logs` (redact keys) |
| P3-6 | `[ ]` Job runner: poll pending jobs on an interval, update `video_projects.status` |
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
| P4-8  | `[ ]` Generate screen — text prompt mode |
| P4-9  | `[ ]` Generate screen — image picker + upload to Storage |
| P4-10 | `[ ]` Generate screen — combined text+image mode + provider/params selector |
| P4-11 | `[ ]` Generation progress UI: pending/generating states, poll or refresh for result |
| P4-12 | `[ ]` History list: paginated, status badges, thumbnails, pull-to-refresh |
| P4-13 | `[ ]` Project detail: video playback (Media3), prompt shown, delete action |
| P4-14 | `[ ]` Download video to device storage + share intent |
| P4-15 | `[ ]` Admin screens: user list, disable/enable, role change, stats dashboard (gated by role) |
| P4-16 | `[ ]` Global states: loading, empty, error, offline; retry affordances |
| P4-17 | `[ ]` Optional: push/local notification when a generation finishes |

---

## Phase 5 — Quality & Testing

| ID | Task |
|----|------|
| P5-1 | `[ ]` Backend unit tests: services, provider adapters (mocked HTTP) |
| P5-2 | `[ ]` Backend integration tests: auth + RBAC + project lifecycle against a test DB |
| P5-3 | `[ ]` Android unit tests: ViewModels, repositories |
| P5-4 | `[ ]` Compose UI tests for the critical paths (login, generate, history) |
| P5-5 | `[ ]` Manual end-to-end pass: signup → generate → poll → download |
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

## Suggested Order

**Next up:** P1-1 is yours — create the Supabase project and apply the SQL. Once its verification queries pass, P2 (backend scaffold) is unblocked and is the natural next build. P2-1 … P2-8 can actually be written before then, since they don't need a live database until they run.

The dependency spine is: **P0 ✅ → P1 → P2 core (P2-1..P2-8) → P3-1..P3-6 → P4-6 → rest of P4 → P5 → P6.**

A good first slice ("vertical MVP" — proves the whole pipeline end to end):
`P0-1, P0-2, P0-5` → `P1-1..P1-4, P1-6` → `P2-1..P2-4, P2-8, P2-10, P2-12` → `P3-1, P3-3, P3-6, P3-8` → `P4-1..P4-6, P4-8, P4-11`.

Everything after that (admin, image modes, history polish, quotas, second provider) is additive.

---

## Deliberately Out of Scope for MVP
Payments/subscriptions · social features/sharing feed · in-app video editing · multi-language · web client · offline generation queue.
