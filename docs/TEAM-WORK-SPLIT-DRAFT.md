# Cretona — Two-developer work split (Draft)

- **Team:** Bruce + S0ra1n0 (two developers total)
- **Status:** Initial ownership accepted on 2026-08-10; later swaps require a
  recorded team decision
- **MVP recommendation:** `CAND-002` final scope; `CAND-001` is the mandatory
first vertical slice and image input starts only after it passes end to end.

## 1. Ownership proposal

| Area | Primary owner | Reviewer | Owned paths after scaffold |
|---|---|---|---|
| Android application | Bruce | S0ra1n0 | `app/` |
| FastAPI, database, auth, provider adapter | S0ra1n0 | Bruce | `backend-fastapi/` |
| API behavior and OpenAPI review | S0ra1n0 | Bruce | generated OpenAPI + `docs/API_CONTRACT.md` |
| Product scope and acceptance | Bruce | S0ra1n0 | `docs/` |
| End-to-end integration and demo | Both | Both | cross-system evidence |

This is a recommendation, not an assumption about existing skill. Swapping the
two primary owners changes names, not the task boundaries.

## 2. Shared invariants

Both developers protect these rules:

1. Android calls only Cretona FastAPI; provider secrets remain server-side.
2. FastAPI is the authority for identity, role, job ownership, job state, and
   provider/model capability.
3. Android uses stable API error codes and canonical job states; it does not
   parse provider payloads.
4. One video-router contract owns model endpoints; Android sees only stable
   `Standard` and `Premium` profiles.
5. No automatic operation may create an untracked second paid generation.
6. Every task is complete only with executed evidence, not source code alone.

## 3. Delivery waves and task contracts

### Verified implementation checkpoint — 2026-08-10

`TASK-A01`, `TASK-B01`, `TASK-I01`, and the fake-provider portions of
`TASK-B04`, `TASK-B05`, `TASK-A03`, and `TASK-A04` have executable evidence.
This is a local development slice, not completion of authentication, Supabase
parity, real model integration, reference-image input, admin, or release scope.
See `docs/evidence/ANDROID_FASTAPI_E2E.md` before assigning the next tasks.

### Wave 0 — Decide and contract (both; serialize)

| Task | Owner | Deliverable | Exit evidence | Depends on |
|---|---|---|---|---|
| `TASK-001` Collect exact rubric/deadline | Bruce | Source copy or instructor clarification | Decisions `DEC-001`–`DEC-006` updated | None |
| `TASK-002` Approve MVP, router strategy, benchmark, and budget buckets | Both | Written decision record | Account/region/cost check, no secret committed, paid activation owner named | `TASK-001` |
| `TASK-003` Freeze API v1 contract | S0ra1n0 | Request/response schemas and errors | Bruce can map every Android screen to the contract | `TASK-002` |
| `TASK-004` Define demo acceptance | Bruce | Final scenario checklist | Both developers agree pass/fail criteria | `TASK-001` |

Do not parallelize feature code before `TASK-003`; otherwise Android and FastAPI
will invent incompatible payloads.

### Wave 1 — Walking skeleton (parallel after API draft)

| Task | Owner | Deliverable | Exit evidence |
|---|---|---|---|
| `TASK-A01` Scaffold Android module | Bruce | App navigation, environment base URL, network client, placeholder screens | APK builds; `/health` response rendered |
| `TASK-B01` Scaffold FastAPI module | S0ra1n0 | App factory, settings, `/health`, test setup, example env | Backend starts; health test passes; no secret in Git |
| `TASK-I01` Integrate walking skeleton | Both | Android → FastAPI health path | Recorded emulator/device request and correlated server log |

### Wave 2 — Authentication and ownership (parallel by path)

| Task | Owner | Deliverable | Exit evidence |
|---|---|---|---|
| `TASK-B02` Implement user/auth persistence | S0ra1n0 | Register/login/me, password hashing, token/session validation | Backend success/failure tests pass |
| `TASK-B03` Implement authorization boundaries | S0ra1n0 | User/admin dependencies and ownership policy | User cannot access admin or another user's object |
| `TASK-A02` Build auth screens/session handling | Bruce | Register, login, logout, protected navigation | UI tests/manual evidence for valid, invalid, expired session |
| `TASK-I02` Verify auth end to end | Both | Android auth against FastAPI | `AC-003` and admin rejection evidence |

### Wave 3 — Core generation vertical slice

| Task | Owner | Deliverable | Exit evidence |
|---|---|---|---|
| `TASK-B04` Build internal provider interface, background worker, and fake | S0ra1n0 | Deterministic fake with queued/processing/succeeded/failed paths and restart behavior | Unit tests cover every canonical transition and no-auto-resubmit rule |
| `TASK-B05` Implement generation API and persistence | S0ra1n0 | Create/list/detail/content endpoints, quota and no-auto-retry rule | API tests cover `202`, validation, ownership, rate/provider failures |
| `TASK-A03` Build generation form | Bruce | Prompt/options validation and submit UI | Valid and invalid form evidence |
| `TASK-A04` Build job status/history/player | Bruce | Poll/refresh, terminal state handling, history, result playback | Fake-provider end-to-end UI evidence |
| `TASK-I03` Run blind model benchmark and integrate `Standard` | Both | Scored evidence plus FastAPI router adapter enabled by environment configuration | Benchmark stays within USD 15; selected `Standard` reaches a terminal state |

### Wave 4 — Admin and conditional image path

| Task | Owner | Deliverable | Exit evidence | Scope rule |
|---|---|---|---|---|
| `TASK-B06` Add minimal admin endpoints | S0ra1n0 | List users/jobs and enable/disable user | Role tests pass | Required if README role management stays in MVP |
| `TASK-A05` Add admin screens | Bruce | User/job lists and status action | Normal user cannot enter/use admin flow | Same as above |
| `TASK-B07` Add validated reference-image input | S0ra1n0 | Upload validation, deletion/retention rule, provider mapping | Synthetic image tests and cleanup evidence | Required after `TASK-I03` passes |
| `TASK-A06` Add image picker/preview | Bruce | Supported picker, validation feedback, multipart upload | Device/emulator evidence | Same gate as `TASK-B07` |
| `TASK-B08` Integrate `Premium` quality profile | S0ra1n0 | Server profile mapping, price snapshot/version, USD 2.50 guard | Stale estimate is rejected; one paid result stays within integration bucket | After benchmark and `TASK-I03` |
| `TASK-A07` Add quality/cost confirmation | Bruce | `Standard`/`Premium` cards, server estimate, explicit premium confirmation | Android never sends raw model ID; stale-price error is visible | Same gate as `TASK-B08` |

### Wave 5 — Release evidence (both; integrate serially)

| Task | Primary | Reviewer | Exit evidence |
|---|---|---|---|
| `TASK-Q01` Run backend test suite | S0ra1n0 | Bruce | Saved command and result |
| `TASK-Q02` Run Android unit/UI/build checks | Bruce | S0ra1n0 | Saved command and result |
| `TASK-Q03` Execute SRS acceptance scenarios | Both | Both | `AC-001`–`AC-005`, plus `AC-006` only if approved |
| `TASK-Q04` Secret and cost-safety review | S0ra1n0 | Bruce | No secrets in repo/APK/log; quota and retry behavior demonstrated |
| `TASK-Q05` Prepare final demo and fallback | Bruce | S0ra1n0 | Live provider path plus deterministic fake/provider recording fallback |

## 4. Pull-request and integration rules

- One primary writer per owned path. Cross-owner edits require a short handoff.
- Backend contract changes update OpenAPI first and require Android-owner review.
- Android must not work around a backend contract defect by parsing provider
  fields or duplicating business rules.
- Each pull request names affected requirement IDs and includes real command or
  runtime evidence.
- Keep paid-provider tests opt-in and excluded from ordinary automated tests.
- Never paste credentials into chat, issues, screenshots, commits, or demo logs.

## 5. Scope cut order if time is short

Cut in this order:

1. Any third quality profile or direct provider-specific integration beyond the
   single video-router contract.
2. Download/share polish.
3. Reference-image input, but only through an explicit scope-reduction decision
   if it threatens the complete text-to-video demo.
4. Admin job analytics beyond list and enable/disable.
5. Prompt enhancement by a separate LLM, unless explicitly mandatory.

Do not cut authentication, backend authorization, the FastAPI integration,
canonical job status, provider failure handling, secret protection, or the
end-to-end text generation demo.

## 6. Immediate next decision meeting

Bruce and S0ra1n0 should resolve the seven decisions in
`docs/SRS-DRAFT.md` section 11. The initial assignments are accepted; keep task
names unchanged so requirements, commits, tests, and demo evidence remain
traceable.
