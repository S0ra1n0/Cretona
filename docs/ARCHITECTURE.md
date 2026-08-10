# Architecture — Cretona

**Version:** 0.2 · **Status:** Implemented local vertical slice; production profile remains draft

---

## 1. Current local system

```mermaid
flowchart LR
    subgraph Device
        A[Android app<br/>Kotlin · Compose · MVVM]
    end
    subgraph Host
        B[FastAPI<br/>Python · port 8000]
        C[(SQLite)]
        D[Deterministic prompt fallback<br/>or optional Ollama]
        E[Fake video provider<br/>synthetic MP4]
    end

    A -- "REST · X-Debug-User-Id" --> B
    B -- "persist jobs" --> C
    B -- "enhance prompt" --> D
    B -- "submit · poll" --> E
    E -- "H.264/AAC URL" --> A
```

This is the executable, zero-spend integration profile. It proves the stable
job contract, persistence, ownership, polling, history, and Android playback.
It does **not** prove a real video model or deployed authentication. The tested
Express/Prisma/Supabase service in `backend/` is migration reference evidence;
the desired deployment profile is still Supabase Auth/Postgres/Storage behind
FastAPI. See [ADR-008](adr/ADR-008-fastapi-migration.md) and
[ADR-009](adr/ADR-009-zero-spend-provider-gate.md).

### Why the app will use Supabase Auth directly in the target profile

Auth is the one place where reimplementing the flow in the backend buys nothing: the Supabase SDK already handles sign-up, sign-in, token refresh, and secure session persistence. The backend only needs to *verify* the resulting JWT. This removes a whole class of credential-handling code from our own server. See [ADR-002](adr/ADR-002-auth-strategy.md).

### Why generation goes through the backend
The opposite reasoning applies to provider calls. Provider keys must never reach the device (NFR-2.5), quota and cost control must be server-enforced (FR-5.1), and results need re-hosting because provider URLs expire (C-3). All of that requires a trusted server between the app and the provider.

---

## 2. Repository Layout

The repo is a monorepo whose **root is the Android Gradle project**, so `Cretona/` opens directly in Android Studio and syncs without extra configuration ([ADR-001](adr/ADR-001-repo-layout.md)).

```text
Cretona/
├── app/                        Android application module
│   └── src/main/java/com/cretona/app/
│       ├── core/               cross-cutting (result types, network plumbing)
│       ├── data/               DTOs, Retrofit services, repository implementations
│       ├── domain/             models and use cases, no Android imports
│       ├── di/                 Hilt modules
│       └── ui/                 Compose screens, ViewModels, theme, navigation
├── backend-fastapi/            active FastAPI + SQLite local slice
├── backend/                    Express + Prisma migration reference
├── scripts/                    repeatable setup/runtime helpers
├── docs/                       this documentation set
├── gradle/                     version catalog + wrapper
├── build.gradle.kts            root Gradle build
└── settings.gradle.kts
```

Android Studio indexes `backend/` as plain files and ignores it during Gradle sync.

---

## 3. Android Architecture

### 3.1 Layers

```mermaid
flowchart TD
    UI["ui/ — Compose screens"] --> VM["ui/ — ViewModels"]
    VM --> UC["domain/ — use cases"]
    UC --> R["domain/ — repository interfaces"]
    R -.implemented by.-> RI["data/ — repository impls"]
    RI --> RS["data/remote — Retrofit"]
    RI --> LS["data/local — DataStore"]
```

**Dependency rule:** `ui → domain ← data`. `domain` imports nothing from Android or from `data`. Repository *interfaces* live in `domain`; their implementations live in `data` and are bound with Hilt. This is what makes ViewModels unit-testable without Robolectric.

### 3.2 State and events

Each screen has one immutable UI state exposed as `StateFlow<XxxUiState>`, collected with `collectAsStateWithLifecycle()`. Loading, empty, error, and content are states of that object — not scattered booleans (NFR-4.1).

```kotlin
data class HistoryUiState(
    val items: List<ProjectSummary> = emptyList(),
    val isLoading: Boolean = false,
    val error: UiText? = null,
    val filter: ProjectStatus? = null,
)
```

One-shot effects (navigation, snackbars) go through a separate `Channel`/`SharedFlow` so they are not replayed on configuration change.

### 3.3 Error handling

Nothing above `data` sees an exception. Repositories return `AppResult<T>`
(`core/result/AppResult.kt`). The current slice maps HTTP status classes to
`AppError`; parsing the backend's stable `error.code` field is still required
before richer error-specific UX. ViewModels turn `AppError` into user-facing
text (NFR-4.2).

### 3.4 Generation status

The Android side treats generation as a long-running background fact, not a screen-scoped operation:

- Submitting returns immediately with a `pending` project.
- The current `HomeViewModel` drives `GET /projects/:id` on a bounded schedule
  and exposes updates through its screen `StateFlow`.
- Moving polling into a repository/work manager and resuming it across process
  or lifecycle changes is still a production-profile task. The server remains
  the job-state authority either way.

### 3.5 Media

- **Images:** Coil 3 with the shared OkHttp client, so signed-URL requests reuse the same connection pool and interceptors.
- **Video:** Media3/ExoPlayer, with the current player remembered by the video
  composable and released by `DisposableEffect` when that UI leaves composition.
- **Signed URLs:** always fetched fresh before playback or download (API_CONTRACT §3.1) and never persisted to DataStore.

### 3.6 Dependency injection

Hilt with KSP. `SingletonComponent` provides `Json`, `OkHttpClient`, `Retrofit`, API services, and repositories. `ViewModelComponent` provides use cases. `@HiltViewModel` + `hiltViewModel()` in Compose.

---

## 4. Backend architecture

The active FastAPI slice separates HTTP routes, settings/auth dependencies,
project services, persistence, and provider adapters under
`backend-fastapi/app/`. Only the project service owns legal state changes.
The structure below describes the richer Express reference and the target
Supabase parity profile; it is not a claim that every component is already
ported to FastAPI.

```text
backend/src/
├── routes/          HTTP routing only — no logic
├── controllers/     parse request → call service → shape response
├── middleware/      auth, rbac, rate limit, validation, error handler, request id
├── services/
│   ├── projects/    project lifecycle and state transitions
│   ├── quota/       quota accounting
│   ├── storage/     signed URLs, re-hosting, deletion
│   └── ai/          provider interface, registry, implementations
├── jobs/            poller / worker loop
├── prisma/          schema + migrations
└── utils/           logging, errors, redaction
```

**Rules that keep this maintainable (NFR-5.3):**
- Controllers contain no business logic and no Prisma calls.
- Only `services/projects` may write `video_projects.status`; the legal-transition check lives in one function.
- Only `services/ai` knows a provider exists. Everything above it deals in the normalized interface.

### 4.1 Request pipeline

```
requestId → logger → rateLimit → authenticate(JWT) → loadUser → rejectIfDisabled
  → authorize(role) → validate(schema) → controller → service → errorHandler
```

`rejectIfDisabled` sits deliberately before authorization so a disabled admin is stopped too (FR-1.8).

### 4.2 The job runner

A single interval worker claims due jobs with `SELECT … FOR UPDATE SKIP LOCKED`, so running more than one backend instance does not double-poll a job. For each claimed project it asks the provider for status and then:

| Provider says | Action |
|---|---|
| still running | update `updated_at`, leave `generating` |
| succeeded | download result → upload to `videos` bucket → `completed` |
| failed | map to a user-readable message → `failed` |
| unreachable / 5xx | retry with backoff up to 3 attempts (NFR-3.2) |
| past timeout | `failed` with a timeout message (NFR-3.3) |

Because state lives entirely in Postgres, a backend restart resumes cleanly (NFR-3.1). Webhooks can later replace the polling trigger without changing any of the transition logic.

---

## 5. Cross-Cutting Concerns

| Concern | Approach |
|---|---|
| **Config** | FastAPI uses environment-backed settings with credential-free local defaults; deployment profiles must fail closed on missing auth/provider secrets. Android reads per-machine values from `local.properties` into `BuildConfig`. |
| **Secrets** | Provider keys and `service_role` exist only in backend env. The app holds only the Supabase URL and anon key. See [SECURITY.md](SECURITY.md). |
| **Logging** | Structured JSON with `requestId`, `userId`, `projectId`. Authorization headers and API keys redacted at the logger, not at call sites. |
| **Idempotency** | `Idempotency-Key` on submit, backed by a partial unique index (DATA_MODEL §2.3). |
| **Time** | UTC everywhere; formatting for display happens in the UI layer only. |

---

## 6. Known Trade-offs

| Decision | Cost we accept | Why |
|---|---|---|
| Polling instead of webhooks for MVP | Extra provider API calls; up to one poll-interval of latency | No public URL or signature handling needed to get the pipeline working end to end. Revisit at scale ([ADR-003](adr/ADR-003-async-strategy.md)) |
| Interval worker in the API process | Won't scale past a few hundred concurrent jobs | A queue (BullMQ/Redis) is a drop-in later; the claim query is already concurrency-safe |
| Single Android module | Slower incremental builds as the app grows | Module splitting is a mechanical refactor once the package boundaries above are respected |
| Denormalized `email` on `users` | Must stay in sync with `auth.users` | Admin search would otherwise need a cross-schema join on every keystroke |
