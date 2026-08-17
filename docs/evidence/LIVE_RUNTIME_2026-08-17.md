# Live FastAPI-to-Supabase runtime, 2026-08-17

Read-only. No `INSERT`, `UPDATE` or `DELETE` was issued by this exercise; the
poller, the retention sweeper and the rate limiter were disabled so that nothing
in the startup path could write either.

This closes the first of the two items `BACKLOG.md` calls "the two things that
matter most" — *"no FastAPI revision has been started or smoke-tested against
live Auth/Postgres/Storage"*.

## What ran

The app was constructed through `create_app(Settings())` with `backend/.env`
unmodified, so the profile is the real one:

```
db=postgres  storage=supabase  auth=supabase  env=production
poller=False retention=False ratelimit=False   (overridden for this run only)
```

## Result

| Check | Result |
|---|---|
| `PostgresDatabase.initialize()` schema gate | **passed** against live |
| App startup (`lifespan` complete) | **OK** |
| `GET /healthz` | 200 `{"status":"ok","version":"0.1.0"}` |
| `GET /api/v1/health` | 200 — note this endpoint does **not** touch the database |
| `GET /api/v1/me` with no token | 401 `UNAUTHENTICATED` |
| `list_projects` (full `SELECTED_COLUMNS`) | executed against live, returned cleanly |
| `admin_stats` | executed against live |

## Live data observed

```
users: 2   activeUsers: 2   projects: 7

byStatus:    completed 6, failed 1, pending 0, generating 0
byProvider:  cloud 6, fake 1

completed  n=6  first 2026-08-16 07:00:50Z  last 2026-08-17 04:17:07Z
failed     n=1       2026-08-16 06:56:34Z
```

Newest row, read through the exact column list the adapter selects:

```
id                0e7ab3f4-5477-4a60-b19d-10f067d3d366
status            completed
provider          fake
progress_percent  100
step_message      'Mock video rendering complete'
error_code        None
created_at        2026-08-17T04:17:07.810779Z
```

## What this settles

**T1-2 is done.** Seven projects exist on live, written between 2026-08-16 and
2026-08-17, and they carry populated `progress_percent` and `step_message`
values. The write path — create, poll, complete — has demonstrably run against
live Postgres. It was recorded as "no write has ever gone to live Postgres";
that is no longer true, and the rows are the evidence.

**The 009 columns were always readable.** `SELECTED_COLUMNS` names
`progress_percent` and `step_message`, and the query runs against live without
error. An earlier claim in `ROADMAP-NEXT.md` that this query would fail at
startup was wrong; see T1-3 for how the gate's type-exact check produced it.

## Authenticated live run — later the same day

Signed in as `admin@cretona.test` via `scripts/get-live-token.ps1`, then ran
`scripts/verify-live-runtime.py`. **The first authenticated request this
project has ever made against live.**

```
6 passed, 0 failed, 1 skipped

PASS  GET /me -- ES256 verified against a live token
PASS  quota read -- limit=10 remaining=9
PASS  GET /projects -- media gallery -- 1 item(s)
PASS  GET /projects/{id} -- progress fields present -- status=completed progress=100
PASS  videoUrl signed from live storage -- True
PASS  GET /events -- SSE -- text/event-stream; first line: event: project_update
SKIP  write cycle -- re-run with --generate
```

That settles the second half of the auth story: ES256-via-JWKS had been proven
against a token in isolation, but never through the running app against the
live project. It is proven now. `videoUrl` signing means the Supabase Storage
read path also ran for real, not against a mock transport.

`GET /projects` returning 1 item for an account on a project holding 7 is
correct — projects are owner-scoped, and the other 6 belong to the other user.

## Finding: the Postgres rate limiter costs ~1.4s per request

Measured, because every request in the run above took 2.6–3.4 s.

The database is not nearby:

```
pooler host      : aws-0-ap-south-1.pooler.supabase.com   (Mumbai)
connect          : 1519 ms
SELECT 1         :  191 ms min, 231 ms avg
count projects   :  192 ms min, 195 ms avg
```

At ~190 ms per round trip, per-request cost is set by how many round trips a
request makes. `consume_rate_limit` takes an advisory lock, runs a bounded
cleanup delete, inserts, and counts — several round trips, in its own
connection, on every request. Re-running the identical checks with
`CRETONA_RATE_LIMIT_ENABLED=false`:

| Endpoint | Rate limiting on | Off |
|---|---|---|
| `GET /me` | 3378 ms | 2637 ms |
| `GET /projects` | 2979 ms | 1468 ms |
| `GET /projects/{id}` | 2684 ms | 1437 ms |
| `GET /projects/{id}/events` | 3064 ms | 1575 ms |

Roughly **half the latency of every authenticated request** is the shared
rate-limit store. ADR-010 chose Postgres for this because it "adds no new
service at this scale" — a sound call when the database is a millisecond away,
and a different one at 190 ms. Worth revisiting in ADR-010 rather than treated
as a defect: the mechanism is correct, its siting is what costs.

The remaining ~1.4 s is still high for a single-row fetch — around seven round
trips — and has not been attributed. Not investigated here.

## What this does NOT establish

- **No write path was exercised.** The `--generate` cycle — create, progress,
  cancel, refund — was skipped. The rows above are evidence of writes that
  happened earlier, not of writes made by these runs. Cancellation in
  particular has still never completed end to end against live through the API,
  though its SQL is now proven against the live constraints (see below).
- **`GET /api/v1/health` proves nothing about the database** — it returns a
  version string and no more. The live proof is the startup gate and the
  adapter reads, not the health endpoint. The Android admin panel's "Ping
  Server Health" button implies otherwise.
- **Latency was measured on one machine, on one network.** It says nothing
  about what a deployed backend sitting next to the database would do.

## Rolled-back write probes

Separately, every T3-2 write was executed against live inside a transaction
ending in `ROLLBACK`, to test the real constraints without leaving a row:

```
PASS  error_code='cancelled' accepted by chk_error_code
PASS  status='cancelled' accepted by the project_status enum
PASS  progress_percent=42 + step_message write
PASS  progress_percent=100 boundary
PASS  all seven error codes: content_policy, invalid_input, quota, timeout,
      provider_error, cancelled, unknown

11 passed, 0 failed     row unchanged: True
```

Before migration 009 was applied this morning, the first of these would have
failed against live.

## Write cycle — create, cancel, refund, all through the API against live

`verify-live-runtime.py --generate --slow`, authenticated as
`admin@cretona.test`. `--slow` forces the mock provider to take three polls
instead of one, so the cancel lands while the job is still `generating` rather
than racing a job that finishes first.

```
10 passed, 0 failed, 1 skipped

PASS  POST /projects -- live create -- id=74aae55b-3fdf-4e9b-99fb-36868afbd6bd
PASS  progress tracking observed -- ('generating', 15)
PASS  POST /cancel -- first live cancellation -- cancelled=True refunded=True
PASS  cancellation persisted to live -- status=failed
      errorMessage='Generation was cancelled by the user.'
PASS  quota accounting -- remaining 9 -> 9
```

Quota unchanged (9 -> 9) is correct: the create charged one unit, the cancel
refunded it, and the API was not asked for the balance in between.

**This is the first cancellation this project has ever completed end to end
against live** — create through the API, poll through the API, cancel through
the API, and the persisted row confirmed by a fourth read. It could not have
worked before migration 009 was applied this morning: the constraint
`ProjectService.cancel` writes through (`error_code='cancelled'`) was rejected
by live until then.

Two rows now exist on live as a result, both `status=failed`, titled
`live-verification-<hex>`:

- `903bebc5-2d77-4b98-a023-6879cd94b721` (first attempt — see below)
- `74aae55b-3fdf-4e9b-99fb-36868afbd6bd`

They soft-delete; harmless to leave, or `DELETE /api/v1/projects/{id}` removes
each cleanly.

## A first attempt caught a bug in the check, not the app

The first run of this same command reported `10 passed, 1 failed`:

```
FAIL  cancellation persisted to live -- status=failed errorCode=None
```

The cancel itself had already succeeded (`cancelled=True refunded=True`) — the
failure was in a follow-up assertion that read `errorCode` off the response.
`ProjectResponse` (`schemas.py`) has no `errorCode` field; `to_response()`
(`project_service.py`) never sets one. The DB row genuinely has
`error_code='cancelled'` — proven separately in the rolled-back probe above —
but nothing serves it to a client. The check was asking the response for a
field it never had.

Fixing the assertion to read `errorMessage` (the field that actually exists)
turned this into a clean pass on the second run, and separately surfaced that
`docs/API_CONTRACT.md` documented `errorCode` as part of the response — see
`ROADMAP-NEXT.md` T3-4 for what else in that doc turned out to be aspirational
rather than descriptive, and the corrections made to it.

## T3-3: the rate limiter rewrite, measured live before and after

Documented in full as an addendum to `docs/adr/ADR-010-shared-rate-limit-store.md`;
this is the raw measurement behind it.

**Before** (this morning, T3-2 section above): disabling `CRETONA_RATE_LIMIT_ENABLED`
for an A/B against live cut `GET /projects` from 2979ms to 1468ms — ~1.5s
attributable to the limiter's 5-6 sequential round trips per request.

**After the rewrite** (2 round trips: lock, then one CTE-based statement),
measured by calling `PostgresDatabase.consume_rate_limit` directly against
live 8 times in a row, writes cleaned up after:

```
consume_rate_limit (2 round trips, live pooler):
  min=753ms  avg=804ms  max=1133ms
  individual: [761, 755, 770, 755, 1133, 754, 754, 753]
```

~750-800ms, down from ~1.4-1.5s — real, roughly 45-50% faster. Smaller than
the ~3x a naive "6 trips to 2 trips" prediction would suggest.

**Splitting the two round trips apart to see why**, timing the lock and the
combined statement separately over the same connection, 6 iterations:

```
lock-only:      [178, 357, 358, 357, 358, 617]  avg=371ms
combined stmt:  [420, 176, 177, 182, 179, 401]  avg=256ms
```

Notice the alternation: whichever statement runs second in a pair tends to be
fast (~180ms, matching the plain `SELECT 1` baseline from this morning),
whichever runs first tends to be slow (~360-420ms). That pattern — not two
uniform round trips, but one fast and one slow depending on position — is
consistent with a Nagle's-algorithm/delayed-ACK interaction on the path to the
pooler, though the actual socket options were not inspected and this is
unconfirmed. Logged as T3-5. It was not chased further: it's a different,
deeper question than what T3-3 set out to fix, and it plausibly explains this
morning's separately-logged "~1.4s for one project fetch, ~7 round trips"
finding as well — a project fetch and a rate-limit check share the same
connection-to-pooler path.

**What was proven, not just measured.** Correctness was checked against a
disposable local Postgres 17 container (`docker run postgres:17`), not
reasoned through: the full parity suite (28 tests, including 5 new ones
covering sliding-window boundaries, expiry, the sweep's sampling in both
directions, and the round-trip count itself via a counting wrapper on
`psycopg.Connection.execute`) passed clean, and the load-bearing concurrency
test — 20 concurrent requests across 2 store instances, limit 5, asserting
exactly 5 succeed with remaining counts `[0,1,2,3,4]` — was run 8 times back to
back with no flakiness before the rewrite was considered done.

## Reproducing

```
& "C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona\backend\.venv\Scripts\python.exe" `
  "C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona\scripts\live-supabase-migration-gate.py" `
  status --env-file "C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona\backend\.env"
```

confirms the schema half. The runtime half was a throwaway harness rather than a
committed script; if it is worth repeating, it belongs next to
`scripts/verify-live-storage.py` as a `--read-only` mode.
