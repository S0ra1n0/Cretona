# Cretona — next roadmap

Written 2026-08-15 after reviewing the 23 commits that landed on `main`, and
verifying the branch directly rather than trusting its documentation. Updated
2026-08-17 after Tier 2, migration 009, and full live verification including an
authenticated write cycle.

## Verified state

Measured, not claimed. Re-measured 2026-08-17:

| | |
|---|---|
| Backend suite | **324 passed, 28 skipped**, Ruff check and format clean; +5 Postgres-parity rate-limit tests, 28/28 against a disposable Postgres 17 |
| Auth | ES256 via JWKS, proven against a real Supabase token |
| Persistence | Postgres proven live for reads and writes; migrations 006–009 applied and verified live |
| Rate limiting | `consume_rate_limit` cut from 5-6 round trips to 2; ~750-800ms measured live, down from ~1.4-1.5s (T3-3, ADR-010 addendum) |
| Android | compiles; **29 unit tests**, 0 failures |
| Dependencies | lock matches `pyproject.toml`; no drift |
| Toolchain | `backend/.venv` is the pinned environment; `backend-fastapi/` is deleted |

**Migrations 006–009 are all applied and verified on live** as of 2026-08-17.
See T1-3 for what 009 needed and for the gate bug found in the process.

**The app runs against live end to end**, authenticated, including a write: the
first live cancellation completed through the full API path — create, poll,
cancel, refund, re-fetch — on the real profile (`postgres` + `supabase` storage
+ `supabase` auth). See T1-2, T3-2, and
`docs/evidence/LIVE_RUNTIME_2026-08-17.md`.

**Supabase Storage is verified** (T1-1): both buckets present, service-role key
has access, and the round trip — upload, sign, fetch, delete — was run and
confirmed by hand.

Nothing in this project remains unverified against live at the level this file
tracks. `backend-fastapi/` is deleted (T2-3). The rate limiter's round-trip
cost is fixed and verified live (T3-3). What's left is one product-wording
decision (T0-2), one open latency question worth a look but not urgent (T3-5),
and the real video provider (T3-1).

---

## Tier 0 — Integrity

The gap between what the code does and what it says it does. Partly fixed
already; the rest is unresolved.

### T0-1 — Video generation is a still image with a camera move ✅ done

`_render_kenburns_from_ai_still` fetches one frame from a hosted text-to-image
endpoint and applies ffmpeg `zoompan`. There is no temporal model. All three
provider tiers call it, so Mock, Cloud AI and Local produce identical output
and differ only in wording and timing.

Renamed and re-documented on 2026-08-15, and the fabricated progress messages
("Local diffusion denoising latents (steps 1-10/20)") now describe the real
work. The product question — differentiate the three tiers, or collapse them —
is resolved under T0-2: keep three tiers as-is. The chip labels and
descriptions were already accurate as of 2026-08-16 (`"AI image + motion"`,
`"Placeholder — no local model runs yet"`); no UI change was needed.

### T0-2 — Decide what the demo claims ✅ done 2026-08-17

EXP-005 and ADR-009 gate a real video provider, and neither has passed. The
current output is a defensible zero-spend placeholder; describing it as AI
video generation is not. Agreed with the user:

**Tiers stay as three, un-collapsed.** The provider-adapter pattern itself —
three registered tiers, one clean interface, `ALIASES` resolving old and new
names to the same canonical adapter — has demo value independent of whether a
real video model exists yet. Collapsing to one tier would have hidden that.

**Report/demo wording, agreed:**

> Cretona's Cloud and Local tiers use a real hosted text-to-image diffusion
> model to generate a still frame from the prompt, then apply a five-second Ken
> Burns pan/zoom via ffmpeg. This produces a short video artifact but does not
> run a temporal video-generation model — no frame-to-frame motion is
> synthesized. The Mock tier is a zero-spend bundled placeholder for testing. A
> real video model remains gated behind EXP-005: LTX-Video was rejected at
> pre-screen, FramePack is blocked by a hardware resource gate, and a paid
> hosted API would break the project's zero-spend baseline (ADR-009).

**Found while settling this, and fixed unconditionally** (not the judgment
call — this part was just wrong): `docs/AI_PROVIDER_SPEC.md` described the
`cloud` tier as a "Real Cloud AI video generation router (Wan 2.1 / LTX-Video /
Pollinations / Fal.ai)" and `local` as having "memory preflight verification" —
neither is true; only Pollinations (a still-image endpoint) is called, and
`LocalModelVideoProvider`'s own docstring says outright "no GPU or memory
preflight is performed, and no local weights are loaded." The spec's own §7
detail table already stated this honestly; only the summary at the top
disagreed with it. `docs/ARCHITECTURE.md` had the same problem plus stale
class names (`FakeVideoProvider`/`RealAiVideoProvider`/`Wan21VideoProvider`
instead of the real `MockVideoProvider`/`CloudAiVideoProvider`/
`LocalModelVideoProvider`), and `docs/BACKLOG.md`'s B-16 entries claimed a
"`Wan21VideoProvider` adapter" was implemented when it's a placeholder with no
Wan 2.1 integration. All three corrected, grounded in the code's own
docstrings and comments rather than rewritten from assumption.

---

## Tier 1 — Unverified against reality

Ordered by how much they can still invalidate finished work.

### T1-1 — Supabase Storage

The last adapter that has never met a real bucket. Confirm `uploads` and
`videos` exist, set `CRETONA_STORAGE_BACKEND=supabase`, then sign an upload,
PUT an object, read it through a signed URL, delete it. Expect trouble around
bucket existence, service-role permissions, and the signed-URL response shape.

### T1-2 — First live project create ✅ already done, confirmed 2026-08-17

Not a pending task — it had already happened, and nothing in this file had
looked. Live holds **7 projects**, written 2026-08-16 to 2026-08-17:

```
users 2   projects 7
byStatus    completed 6, failed 1
byProvider  cloud 6, fake 1
newest      2026-08-17T04:17:07Z, completed, progress_percent 100,
            step_message 'Mock video rendering complete'
```

So the create → poll → complete path has run end to end against live Postgres,
and the rows carry populated 009 columns. "No write has ever gone to live
Postgres" was simply out of date.

Read-only evidence, with the poller, retention sweeper and rate limiter
disabled so the check itself could not write:
`docs/evidence/LIVE_RUNTIME_2026-08-17.md`. That run also boots the app on the
real profile (`postgres` + `supabase` storage + `supabase` auth) and passes the
startup schema gate, which closes the **live FastAPI runtime proof** that
`BACKLOG.md` calls one of "the two things that matter most".

Still open around it: no *authenticated* live request has been made. That needs
a real Supabase access token, which is the one thing blocking the rest of T3-2.

### T1-3 — Migration 009 ✅ applied and verified on live 2026-08-17

`verify-009` passes against the live project. 006, 007, 008 and 009 are all
applied.

**What was actually missing was one half of it.** 009 changes two things, and
only the constraint half was outstanding: `chk_error_code` listed the six
pre-009 codes and rejected the `cancelled` code that `ProjectService.cancel`
writes. `apply-009` fixed that; the constraint now carries `cancelled`.

The columns half was already in place before today — and the first run of this
gate reported it as absent, wrongly. `state_009` asserted `progress_percent`
was `smallint`, the type the migration declares. Live has it as `integer`: the
column pre-dated 009 there, so `add column if not exists` left the existing
width alone. A type-exact check turned "wider than declared" into "missing".

Two conclusions drawn from that false negative are withdrawn:

- **The backend could always boot against live.** `SELECTED_COLUMNS` selects
  these columns by name, not by type, so the startup check was never going to
  fail on an int4 `progress_percent`.
- **T1-2 does not need re-checking on this account.** The reason given for
  doubting it — that a live create was impossible — was not true.

The check now accepts any integer width for `progress_percent` and reports the
observed type alongside `progress_percent_matches_migration`, so the remaining
drift stays visible instead of being either fatal or invisible:

| | `progress_percent` |
|---|---|
| `supabase/009_add_progress_tracking.sql` | `smallint` |
| `backend/tests/postgres_schema.sql` | `smallint` |
| **live** | **`integer`** |

Harmless — the column holds 0–100 and int4 stores that exactly — but it means
the local Postgres test schema does not model live precisely. Worth reconciling
if `supabase/drift_check.sql` is ever pointed at this table.

Both gates now cover 009:

- `backend/app/postgres.py` checks the columns and the constraint separately, so
  a half-applied 009 names itself instead of surfacing as the old, misleading
  "apply 002–005" message. This is the check that would have caught the real
  problem: a database that takes the columns but keeps the old constraint
  accepts every progress update and rejects every cancellation.
- `scripts/live-supabase-migration-gate.py` gained `apply-009` / `verify-009`,
  plus a `status` action that reports what is applied without asserting.

**The lesson is the one this file already states, aimed at itself.** A gate is
also code, and its expectations can be wrong in the same way the code's can.
This one failed closed, which is the right direction to fail — but it still
produced a confident, specific, wrong answer, and the correction came from
querying the live schema directly rather than from trusting the tool.

---

## Tier 2 — Debt from this review

Done 2026-08-17 unless marked otherwise. 324 backend tests pass, Ruff check and
format clean, Android compiles and its unit tests pass.

### T2-1 — Orphaned media on delete ✅
`discard_provider_scratch` in `storage.py` deletes the provider's per-job output
once its bytes are re-hosted, in both the local and Supabase backends. It only
touches files sitting directly in the media root, so the owner-scoped copy it
just wrote can never be the thing removed, and the bundled demo clip is passed
in as a reserved name because every mock generation points at that one file
rather than producing it. Discard happens after the store succeeds — a failed
upload keeps the scratch file, which is its own test.

### T2-2 — Third-party prompt egress ✅
Now `CRETONA_IMAGE_ENDPOINT`, a real setting wired through `main.py` rather than
a constructor default the app never passed. Empty disables the egress and falls
the tiers back to the bundled clip. The call moved from `urllib` to httpx, the
spoofed `Mozilla/5.0` User-Agent is gone, and the response is refused unless it
is a JPEG, PNG, or WebP under 16 MB — it gets written into `MEDIA_DIR` and
served as user media, so an HTML error page must not land there. An ffmpeg
timeout no longer leaves the still behind either.

While documenting it, two adjacent claims in `CONFIGURATION.md` turned out to be
false and were corrected: `DEFAULT_VIDEO_PROVIDER` defaults to `mock`, not
`fake`, and accepts six values rather than "`fake` is the only accepted value".

### T2-3 — Recreate the venv ✅ done
`backend/.venv` exists, built from `constraints-windows-py312.lock`; tests and
Ruff both run in it and `pip freeze` no longer errors. `backend-fastapi/` —
duplicate credentials, dead editable install, orphaned bytecode — is deleted.
324 tests still pass afterward: nothing referenced it.

### T2-4 — Webhook replay ✅
The signature now covers `<timestamp>.<raw body>`, sent as `X-Cretona-Timestamp`
in unix seconds, and a delivery outside `CRETONA_WEBHOOK_TOLERANCE_SECONDS`
(default 300, either direction) is refused. Because the timestamp is inside the
MAC, a captured delivery cannot be re-dated without the secret.

This narrows the window rather than closing it: a replay *within* the tolerance
is still accepted. Closing that needs a stored nonce, which needs a table, and
that is deliberately not built until a provider exists to send one. The old
bare-body signing scheme is no longer accepted at all.

### T2-5 — Audit writes are not transactional ✅
`update_user_flags` now takes an `AuditEntry` and writes the row inside the same
transaction as the mutation, on both adapters. If the audit row cannot be
written, the privilege change does not happen — proven by a test that makes the
insert fail and asserts the role is unchanged.

The thumbnail backfill deliberately still uses the old best-effort `_audit`: it
commits one project at a time, so there is no single transaction its summary row
could join. That is now stated in the docstring rather than left as a
repository-wide excuse.

### T2-6 — `AdminScreen.kt` reviewed ✅ findings below
Fixed: a hardcoded `Color.Gray` role label and two hardcoded `Color.White`
spinners, all three of which ignored the theme; and an unused destructured
`label`. Compiles clean, unit tests pass.

Three findings left as decisions, because they are product calls rather than
defects:

1. **Destructive admin actions have no confirmation.** "Demote to User" and
   "Disable" fire on a single tap, with no dialog. The backend refuses
   self-modification, but nothing stops a mis-tap on someone else's row.
2. **Pagination is ignored.** The API returns `nextCursor`/`hasMore`; neither
   `AdminUiState` nor `AdminViewModel` carries a cursor, so the users and audit
   lists silently show only the first page with no way to reach the rest.
3. **The stats chart's labels do not line up with its bars.** Bars are drawn at
   fixed 24px offsets from the left; the legend below uses `SpaceAround`, so the
   two disagree at any width.

Search is debounced in the ViewModel, so that earlier suspicion was unfounded.

---

## Tier 3 — Product

### T3-1 — A real video provider
The actual remaining feature. EXP-005 gates it: LTX-Video was rejected at
pre-screen, FramePack is blocked by the resource gate. Options are a paid
hosted video API (breaks the zero-spend baseline, needs a decision) or clearing
the hardware gate. **L**

### T3-2 — Verify the new features end to end ✅ done 2026-08-17

Two harnesses now exist: `scripts/get-live-token.ps1` signs in and writes a
token to the git-ignored `backend/.token`, and `scripts/verify-live-runtime.py`
drives `create_app` against live with it.

Verified 2026-08-17, authenticated as `admin@cretona.test` — the first
authenticated live request this project has ever made:

| | |
|---|---|
| `GET /me` | ES256 verified against a live token |
| quota | limit=10, remaining=9 |
| media gallery | `GET /projects` returns owner-scoped items |
| progress fields | `status=completed progress=100` |
| `videoUrl` | signed from live Supabase Storage |
| SSE | `text/event-stream`, first line `event: project_update` |

Every T3-2 write was also proven against the live constraints inside
rolled-back transactions — all seven error codes, both 009 columns, and
`error_code='cancelled'`, which live rejected until 009 was applied this
morning. 11 passed, row unchanged.

**Done.** `verify-live-runtime.py --generate --slow` ran the full write cycle
against live: create → progress (`generating`, 15%) → cancel → refund →
re-fetch. 10 passed, 0 failed. Cancellation now works end to end through the
API against live — the DB write, the HTTP response, and the persisted row all
agree.

The first attempt caught a bug in the *check*, not the app: it asserted an
`errorCode` field on the response that `ProjectResponse` has never had. Fixing
the assertion to check `errorMessage` (the field that actually exists) surfaced
the real gap it was reaching for — see T3-4.

Two verification rows now exist on live, both titled `live-verification-<hex>`,
status `failed`: `903bebc5-2d77-4b98-a023-6879cd94b721` and
`74aae55b-3fdf-4e9b-99fb-36868afbd6bd`. They soft-delete; harmless to leave, or
`DELETE /api/v1/projects/{id}` removes each cleanly.

### T3-4 — `docs/API_CONTRACT.md` documented fields the API never returns 🆕✅ corrected
Found while fixing the T3-2 harness. `ProjectResponse` (`schemas.py`) has no
`errorCode` field, and `to_response()` never sets one — but the doc's example
payload showed it, plus a nested `options` object with `stylePreset` and
`cameraMotion` that the response also never returns (they're accepted at
creation and folded into the stored prompt via directive text, not echoed
back). The doc also described `POST /cancel` as returning a full Project Object
with `status: "cancelled"`; the real response is the distinct
`{cancelled, projectId, quotaRefunded}` shape, and `status` can never actually
be `"cancelled"` — `ProjectStatus` only has pending/generating/completed/failed.
SSE events keyed the id as `projectId`; the code sends `id`.

All four corrected in `API_CONTRACT.md`, verified against `schemas.py`,
`project_service.py`, `routes.py`, and a live response. One real product gap
surfaced in the process and left as a note rather than fixed: **the API has no
way to tell a client why a project failed** — `errorMessage` is the only signal
and it doesn't vary meaningfully by cause beyond the fixed strings in
`FAILURE_MESSAGES`. Neither the Android client nor any other endpoint reads
`error_code` anywhere. Worth a decision: expose it, or accept that "failed" is
all a user ever sees.

### T3-3 — Rate limiting cost ~1.4s per request against a remote database ✅ fixed
Found while timing T3-2. The pooler is in `ap-south-1` at ~190ms per round
trip, and `consume_rate_limit` spent 5-6 of them — lock, clock, this caller's
prune, count, insert, then an *unconditional* global cleanup sweep — on every
single request.

Decided with the user: not a store-swap (ADR-010's Postgres-vs-Redis choice
stands — the round trips would cost the same against Redis), but a rewrite to
issue fewer of them. `consume_rate_limit` in `backend/app/postgres.py` now
does 2: the advisory lock, then one CTE-based statement combining the clock
read, prune, count, and conditional insert. The global sweep is sampled
(`RATE_LIMIT_SWEEP_SAMPLE_RATE = 0.02`) instead of running on every call,
matching the sampling pattern this codebase already uses elsewhere
(`request_log_sample_rate`).

Verified two ways before touching live: a disposable local Postgres 17
container ran the full parity suite plus five new tests (sliding-window
boundary, expiry, the sweep firing and not firing, and the round-trip count
itself, pinned via a counting wrapper) — 28/28 passed, and the load-bearing
concurrency test (20 concurrent requests, limit 5, exactly 5 succeed) was run
8 times back to back with no flakiness. Then measured directly against live:
**~750-800ms average**, down from an estimated ~1.4-1.5s — real, roughly
45-50% faster, smaller than the ~3x naive round-trip arithmetic predicted.

**Why smaller than predicted, and a new open question.** Splitting the two
round trips apart to see where the gap went showed an alternating ~180ms /
~360ms pattern on back-to-back statements over the same connection, not two
uniform ~190ms trips. Consistent with a Nagle's-algorithm/delayed-ACK
interaction somewhere on the path to the pooler, unconfirmed. This isn't
specific to rate limiting — it plausibly explains the *previously* unattributed
~1.4s / ~7-round-trip cost of a single project fetch, logged separately below.
Not chased further here; out of scope for this fix.

Full write-up as an addendum to `docs/adr/ADR-010-shared-rate-limit-store.md`
(appended, not edited — the original decision stands) and in
`docs/evidence/LIVE_RUNTIME_2026-08-17.md`. **M**

### T3-5 — Possible Nagle/delayed-ACK pattern on the Supabase connection 🆕
Surfaced while verifying T3-3's fix. Two back-to-back statements over the same
live connection showed alternating ~180ms / ~360ms timings rather than two
uniform round trips — the kind of pattern a Nagle's-algorithm/delayed-ACK
interaction produces, though this was not confirmed against the actual socket
options or the pooler's behavior. If real, it would compound with every
sequential-round-trip code path in the backend, not just rate limiting, and
would plausibly explain T3-2's separately-logged "~1.4s for one project fetch,
~7 round trips' worth" finding. Needs someone to actually check `TCP_NODELAY`
on the connection and compare direct-vs-pooled connection strings before it's
worth acting on. **S** to investigate, unknown to fix.

---

## Suggested order

Rewritten 2026-08-17, after T1-1, T1-2, T1-3, Tier 2, T2-3, T3-2, and T3-3 all
closed the same day.

1. **T0-2** — the wording. Costs nothing, and everything downstream inherits
   it.
2. **T3-5**, if it's ever worth an hour — check `TCP_NODELAY` and a
   direct-vs-pooled connection string before assuming it's real.
3. **T3-1** — the real feature, once the gates are settled.

~~Delete the `backend-fastapi/` leftover~~ — done. Nothing here is a
correctness blocker. What's left is a siting decision, one product-wording
decision, and the genuinely large item.

## The rule this project keeps relearning

A green suite means the code does what its author expected. It says nothing
about whether the expectation matched reality. Auth passed 24 tests for three
months while being unable to authenticate anyone; the audit migration passed
its tests against a schema that would never be deployed. Both were found by
running the real thing.

Where a doc and the code disagree, the code wins. Where the code and the live
system disagree, the live system wins.
