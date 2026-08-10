# Cretona — Software Requirements Specification (Draft)

- **Document ID:** `CRETONA-SRS-001`
- **Status:** Baseline accepted for scaffold on 2026-08-10
- **Version:** `0.3`
- **Original date:** 2026-08-06
- **Decision authority:** Bruce and S0ra1n0, subject to instructor requirements

## 1. Purpose and evidence boundary

Cretona is a Mobile 1 Android project that demonstrates a complete mobile-to-AI
workflow. A user authenticates, submits a text prompt and optionally a reference
image, tracks an asynchronous generation job, and views the resulting short
video. A FastAPI backend is the mandatory integration boundary: it validates
requests, protects provider credentials, calls the selected model service, and
maps provider-specific responses into a stable Cretona job model.

This SRS is derived from the repository README, the instructor constraint
reported by Bruce, and current provider documentation recorded in
`docs/discovery/SOFTWARE_OPPORTUNITY_BRIEF.yaml`. It is not evidence of market
demand and does not select an AI provider.

## 2. Proposed MVP decision

The recommended final MVP is `CAND-002`: text and one optional reference image
to short video through one configured video-router contract. It shall be built
in two gates. Gate 1 is
the acceptance-critical `CAND-001` text-only vertical slice:

1. Register/login as a user.
2. Submit a text prompt from Android.
3. FastAPI starts one canonical generation job through the configured video
   router without exposing any API key or raw model ID.
4. Android displays `queued`, `processing`, `succeeded`, or `failed`.
5. A successful result can be played and accessed again from history.
6. An administrator can view users/jobs and disable inappropriate access.

Gate 2 adds one reference image through the same provider adapter and canonical
job model. Gate 2 may begin only after Gate 1 passes end to end. Multi-provider
support remains outside the MVP.

## 3. Actors and permissions

| Actor | Allowed behavior | Explicitly disallowed |
|---|---|---|
| Guest | Register, log in, view public app information | Generate videos or view histories |
| User | Manage own session, submit generation, view own jobs/results | View another user's jobs or admin data |
| Admin | Perform user actions; view users and all job metadata; enable/disable users | Read plaintext passwords or provider secrets |
| Video router/underlying model | Accept server-side generation requests and return job/result state | Receive the user's Cretona password or authorization token |

The MVP has only `user` and `admin` authenticated roles. Additional roles and a
custom permission editor are out of scope.

## 4. Functional requirements

### 4.1 Authentication and authorization

- `FR-AUTH-001` — A guest shall be able to register with a unique email and a
  password meeting the server's validation rules.
- `FR-AUTH-002` — A registered, enabled account shall be able to log in and
  receive an authenticated session/token accepted by FastAPI.
- `FR-AUTH-003` — The Android app shall support logout and clear locally stored
  session credentials.
- `FR-AUTH-004` — FastAPI shall reject missing, invalid, or expired credentials
  with a stable `401` error contract.
- `FR-RBAC-001` — FastAPI, not the Android UI, shall enforce user/admin access.
- `FR-RBAC-002` — A disabled user shall be denied new authenticated actions.

### 4.2 Video generation

- `FR-GEN-001` — An authenticated, enabled user shall be able to submit a
  non-empty text prompt within a server-configured length limit.
- `FR-GEN-002` — The request may include approved generation options such as
  duration and aspect ratio; allowed values shall come from server capability,
  not be assumed by the Android client.
- `FR-GEN-003` — The user shall be able to attach zero or one supported reference
  image. FastAPI shall validate type and size before contacting the provider.
- `FR-GEN-004` — FastAPI shall create one Cretona job and respond without
  blocking until video completion. The create response shall contain the
  Cretona job ID and current state.
- `FR-GEN-005` — FastAPI shall store the external provider job ID only on the
  server and map provider states to the Cretona states in section 5.
- `FR-GEN-006` — The same job shall not silently create a second billable
  provider request. Any retry that can create a new charge requires an explicit
  server rule and a new auditable attempt.
- `FR-GEN-007` — A rejected, moderated, rate-limited, timed-out, or provider-
  failed request shall end in a visible failure state with a safe user message.
- `FR-GEN-008` — FastAPI shall expose stable `Standard` and `Premium` quality
  profiles with current duration, resolution, audio, and maximum cost estimate.
  Android shall not receive or submit raw provider endpoint IDs.
- `FR-GEN-009` — The user shall explicitly confirm the current server estimate
  before a `Premium` job. FastAPI shall reject a stale estimate/version rather
  than submit a potentially more expensive request.

### 4.3 Job history and result access

- `FR-HIST-001` — A user shall be able to list only their own generation jobs,
  newest first.
- `FR-HIST-002` — A job detail shall show prompt summary, creation time, current
  state, quality profile, chosen options, estimated/actual cost metadata when
  available, and safe failure information when applicable.
- `FR-HIST-003` — A succeeded job shall expose a playable result through a
  backend-controlled URL or content endpoint.
- `FR-HIST-004` — The app shall handle an expired provider asset without
  presenting the job as currently playable.
- `FR-HIST-005` — Result download/sharing is `SHOULD`, not an acceptance blocker,
  until Android storage and provider terms are confirmed.

### 4.4 Administration

- `FR-ADM-001` — An admin shall be able to list accounts with role and enabled
  status.
- `FR-ADM-002` — An admin shall be able to enable or disable a non-admin user.
- `FR-ADM-003` — An admin shall be able to list generation job metadata across
  users for demonstration and support.
- `FR-ADM-004` — Role promotion, billing dashboards, complex analytics, and
  destructive bulk deletion are outside the initial MVP.

### 4.5 Model/LLM requirement

- `FR-AI-001` — All external model calls shall originate from FastAPI.
- `FR-AI-002` — Provider names, model IDs, limits, and credentials shall be
  server configuration and shall not be hard-coded into Android screens.
- `FR-AI-003` — FastAPI shall use a text LLM for a bounded, visible prompt-
  enhancement step. The original prompt must remain available, and the user
  must approve the enhanced prompt before starting a paid video job.
- `FR-AI-004` — Failure of prompt enhancement shall not create a video charge.
  The user may keep the original prompt and continue or cancel.

## 5. Generation state model

```text
submitted -> queued -> processing -> succeeded
                 \          \------> failed
                  \----------------> failed
```

Canonical states:

- `submitted`: accepted by Cretona but not yet confirmed by the provider.
- `queued`: provider accepted the job or it is waiting for capacity.
- `processing`: provider reports active generation.
- `succeeded`: result metadata is available.
- `failed`: terminal failure with a stable Cretona error code.

The MVP shall not use UI-only state as the source of truth. Reloading a detail
screen must retrieve the persisted server state.

## 6. Draft external API contract

The exact request/response schema will be versioned before implementation.

| Method and path | Actor | Purpose | Success |
|---|---|---|---|
| `POST /api/v1/auth/register` | Guest | Create user account | `201` |
| `POST /api/v1/auth/login` | Guest | Create authenticated session/token | `200` |
| `GET /api/v1/users/me` | User/Admin | Get current profile and role | `200` |
| `POST /api/v1/generations` | User/Admin | Start a text or approved image-guided job | `202` |
| `GET /api/v1/generations` | User/Admin | List caller's jobs | `200` |
| `GET /api/v1/generations/{job_id}` | Owner/Admin | Read canonical job state | `200` |
| `GET /api/v1/generations/{job_id}/content` | Owner/Admin | Access playable result when available | `200`/redirect |
| `GET /api/v1/admin/users` | Admin | List accounts | `200` |
| `PATCH /api/v1/admin/users/{user_id}/status` | Admin | Enable/disable account | `200` |
| `GET /api/v1/admin/generations` | Admin | List all job metadata | `200` |
| `GET /health` | Public or restricted by deployment | Demo health check without secrets | `200` |

Every error response shall contain at least:

```json
{
  "error": {
    "code": "GENERATION_RATE_LIMITED",
    "message": "Generation is temporarily unavailable.",
    "request_id": "..."
  }
}
```

Android logic shall branch on `code`, not parse human-readable `message`.

## 7. Data requirements

Minimum entities:

- `User`: ID, email, password hash, role, enabled status, timestamps.
- `GenerationJob`: ID, owner ID, prompt, optional input-image metadata,
  quality profile, requested options, router/provider/model identifier, pricing
  snapshot/version, estimated/actual cost metadata, canonical state, external
  job ID, safe error code/message, output metadata, timestamps.
- `GenerationAttempt`: optional for the first implementation, but required if a
  retry can create another provider charge.

Passwords, raw tokens, and provider keys shall never be stored in
`GenerationJob`. The team must decide retention for uploaded images, generated
video copies, and provider URLs before enabling image input.

## 8. Non-functional requirements

- `NFR-SEC-001` — No provider secret, signing secret, or real password shall be
  committed to Git, packaged in the APK, logged, or returned by the API.
- `NFR-SEC-002` — Passwords shall be stored only as an accepted password hash;
  authorization checks shall cover object ownership as well as role.
- `NFR-SEC-003` — Upload validation shall use allowlisted media types and a
  server-side size limit. Filenames shall not determine trust.
- `NFR-COST-001` — The backend shall define a maximum clip duration, allowed
  model, per-user/demo quota, and no automatic billable retry.
- `NFR-COST-002` — Paid use shall stop at the active budget bucket: USD 15 for
  blind benchmarking, USD 5 for integration verification, and USD 5 for the
  final demo. `Premium` shall not exceed USD 2.50 per configured clip.
- `NFR-PERF-001` — Excluding provider generation time, authenticated list/detail
  requests should complete within two seconds on the demo environment under
  single-team-demo load.
- `NFR-ASYNC-001` — Starting a generation shall return a job within five seconds
  or a visible error; the mobile request shall not remain open for the full
  video-generation duration.
- `NFR-REL-001` — A FastAPI restart shall not convert persisted terminal jobs
  back to an in-progress state.
- `NFR-REL-002` — After a FastAPI restart, a non-terminal job shall either be
  safely reconciled using an existing provider job ID or become
  `failed/BACKEND_RESTARTED`; it shall never be automatically resubmitted.
- `NFR-UX-001` — Android shall show loading, empty, success, and recoverable
  error states for every network-backed screen.
- `NFR-UX-002` — Core actions shall have readable labels, adequate touch targets,
  and must not communicate state by color alone.
- `NFR-TEST-001` — The provider adapter shall support a deterministic fake so
  auth, job lifecycle, UI, and demo fallback can be tested without paid calls.
- `NFR-OBS-001` — Logs shall include a request/job correlation ID and stable
  error code but exclude credentials and uploaded media content.

## 9. Acceptance scenarios

### `AC-001` Successful text generation

Given an enabled user is logged in and under quota, when they submit a valid
prompt, then Android receives a job ID, displays non-terminal progress, and can
later play the succeeded result associated with that same job.

### `AC-002` Provider failure

Given a valid request and a provider failure, when the job reaches a terminal
state, then Android displays a safe failure message, history remains accessible,
and the backend does not silently start another billable request.

### `AC-003` Ownership isolation

Given two users have separate jobs, when one requests the other user's job ID,
then FastAPI returns `403` or `404` according to the approved security policy
and exposes no job metadata.

### `AC-004` Admin boundary

Given a normal user calls an admin endpoint, then FastAPI rejects the request.
Given an admin disables a normal user, that user can no longer start a job.

### `AC-005` Secret boundary

Given the APK, repository, API responses, and demo logs are inspected, then no
real provider API key or signing secret is present.

### `AC-006` Image-guided generation

Given a user uploads a supported synthetic image,
when generation succeeds, then the job retains only approved metadata and the
result is accessible through the same state model as text-only generation.

## 10. Out of scope for the first graded MVP

- Arbitrary provider/model selection, direct integrations with multiple
  provider-specific contracts, or exposing raw endpoint IDs to Android.
- Training/fine-tuning a video foundation model.
- Full timeline editing, filters, voice dubbing, or multi-scene composition.
- Payments, subscriptions, public social feeds, comments, or follower systems.
- Push notifications unless the rubric requires them.
- Complex RBAC, organization tenancy, or production-scale job queues.
- Unbounded retries, batch generation, or high concurrency.

## 11. Proposed technical baseline

The detailed rationale and delivery plan are in `docs/PROJECT-PROPOSAL.md`.

- Android: Kotlin, XML Views, Material Components, MVVM, ViewModel + StateFlow,
  Retrofit/OkHttp, Coroutines, DataStore, Coil, and Media3 ExoPlayer.
- Backend: Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy 2, SQLite, JWT,
  password hashing, Google GenAI SDK, and pytest.
- AI: Gemini 2.5 Flash for prompt enhancement; one fal video-router adapter with
  benchmark-selected `Standard` and `Premium` endpoint mappings.
- Runtime: local-network FastAPI for development and final demo. Public hosting
  is stretch scope.
- Cost: development uses a deterministic fake provider. Live generation is
  opt-in, has no automatic retry, and is bounded by a USD 25 envelope divided
  into benchmark, integration, and final-demo buckets.

## 12. Decisions proposed for team approval

| ID | Decision | Why it matters |
|---|---|---|
| `DEC-001` | `CAND-002` final MVP; `CAND-001` is Gate 1 | Controls image path and cut order |
| `DEC-002` | Five relative delivery waves until a course deadline exists | Controls planning cadence |
| `DEC-003` | Kotlin + XML Views + MVVM | Controls Android conventions |
| `DEC-004` | Required text-LLM prompt enhancement before optional paid generation | Makes the LLM call visible and testable |
| `DEC-005` | Gemini text API + fal video router, one account owner per service, USD 25 bucketed cap | Controls adapters, model benchmark, and live demo |
| `DEC-006` | Local-network FastAPI; public deployment is stretch | Controls operations and secret handling |
| `DEC-007` | Bruce owns Android; S0ra1n0 owns backend | Controls file ownership and review path |

`docs/DECISIONS.md` contains the complete rationale. The accepted decisions are
an approved build contract for the initial fake-provider scaffold. No paid API
usage is authorized until `DEC-005` is accepted separately.
