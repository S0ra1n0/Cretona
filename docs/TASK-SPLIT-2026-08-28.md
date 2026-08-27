# Cretona — task split to 2026-09-05

- **Document ID:** `CRETONA-TASKS-005`
- **Written:** 2026-08-28 · **Submit:** 2026-09-05 (8 working days)
- **Contract:** `API_CONTRACT.md` Part II — **agreed, do not renegotiate
  informally.** A change gets told to the other person the same day.
- **Decisions:** `PLAN-TO-2026-09-05.md` §2 (D1–D4, all resolved)
- **S0ra1n0** — backend, database, Kaggle worker · **Bruce** — Android, admin UI

Ticket ids are stable. Use them in commit messages: `feat(credits): S-03 …`.

---

## 0. How the two lanes stay parallel

Bruce is **not** blocked on S0ra1n0. Every screen is built against
`API_CONTRACT.md` Part II with a fake implementation behind the existing
`CretonaRepository` interface. `CretonaRepositoryImpl` swaps in when the real
endpoint lands, and the screen does not change.

Three integration points, and only three:

| When | What | Who checks |
|---|---|---|
| End of 08-30 | Credits + events endpoints live; Bruce switches off fakes | Both, 30 min |
| End of 09-02 | Worker produces a real clip; Bruce plays it in the app | Both, 30 min |
| 09-03 18:00 | Feature freeze. Everything after is integration and docs | Both |

---

## 1. S0ra1n0 — backend

### Day 1 · Fri 08-28

**S-01 · Migration `013_add_credits_and_events.sql`** — ✅ **DONE 08-28**
: Seven schema objects: `users.credit_balance`, `credit_transactions`,
  `credit_packages`, `payments`, `events`, `event_claims`, `settings`.
: Landed in **four** places: `supabase/013_add_credits_and_events.sql`,
  `supabase/bootstrap.sql` (§9, folded in verbatim), `database.py` → `SCHEMA`
  **and** `ADDED_COLUMNS["users"]`, `tests/postgres_schema.sql` (plus explicit
  drops — `drop table users cascade` does not reach `events` or
  `credit_packages`, which have no FK to users).
: `live-supabase-migration-gate.py` needs no change: it validates index health
  generically rather than against a table list. Confirmed by running
  `test_migration_gate.py`.
: **Verified:** 373 passed / 31 skipped, ruff clean. Constraint smoke tests
  pass on a real SQLite database — `delta <> 0`, reason whitelist, grant
  requires `bonus_credits`, discount excludes it, double-claim in the same
  period blocked, next period allowed, replayed idempotency key blocked.
: **Remaining:** apply the migration to live Supabase Postgres (needs the
  dashboard).

**S-02 · Seed data** — ✅ **DONE 08-28**
: `supabase/seed_credits_and_events.sql`. Cost = 1 credit, three packages
  (Starter/Creator/Studio), and all five events: `SIGNUP_BONUS` (+5, auto),
  `HOT_HOURS` (daily −50%, 1200–1320), `WEEKEND_GIFT` (+10 weekly, sat/sun,
  cap 500), `NATIONAL_DAY` (+20, 09-02, cap 1000), `WELCOME_BACK` (+15, cap 100).
: Every insert is guarded, so re-running is safe.

**S-03 · `ADR-010` — simulated payments** — ✅ **DONE 08-28**
: `docs/adr/ADR-010-simulated-payments.md`. Adds one implementation
  constraint worth knowing before S-07: `payments.method` stores
  `'simulated'` on every row, so the database itself discloses the stub rather
  than relying on the report to do it.

### Day 2 · Sat 08-29

**S-04 · `CreditService`** — ✅ **DONE 08-28**
: `app/credit_service.py` plus repository methods on **both** adapters:
  `apply_credit_delta`, `list_credit_transactions`, `credit_totals`,
  `get_setting`/`set_setting`, `get_credit_balance`, `ledger_drift`.
: The invariants live in the database, not the service. Non-negative balance is
  the `WHERE credit_balance + ? >= 0` clause on the UPDATE; single-charge is the
  unique partial index; atomicity is one transaction. SQLite opens it with
  `BEGIN IMMEDIATE` so two concurrent charges cannot both read the old balance.
: **36 tests in `tests/test_credits.py`**, including ten threads racing a
  balance that covers three — exactly three win, and the ledger still explains
  the balance afterwards. `ledger_drift()` is tested both ways: clean after a
  grant/charge/refund cycle, and detecting a balance written behind the
  service's back.
: **Note for S-05:** `refund_for()` reads the amount back from the original
  charge rather than recomputing it, so a discount ending mid-job cannot change
  what comes back (contract §10.4).

**S-05 · Wire charging into `project_service`** — ✅ **DONE 08-28**
: Reserve at submit, refund on `failed` and `cancelled`. `402
  INSUFFICIENT_CREDITS` before any provider call or row insert. Retry charges
  again, keyed per attempt. `QuotaService` untouched — now defence in depth.
: `_mark_failed` is the single choke point every terminal failure passes
  through, so the refund lives there once rather than at each call site.
  `_refund_generation` swallows its own errors on purpose: a refund that raised
  would turn a failed generation into a 500 and strand the project in flight.
: **15 tests in `tests/test_credit_charging.py`.** Suite is 424 passed, ruff
  clean.

**S-05a · Signup bonus** — ✅ **DONE 08-28** *(pulled forward from S-11)*
: **This was blocking everything.** A new account starts at 0 credits and
  nothing else granted a first one, so a real user could complete their profile
  and then never generate anything. The end-to-end test caught it.
: `CreditService.ensure_signup_bonus()` applies the active `auto_grant` event,
  idempotent on `signup:{user_id}`. Called from `GET /me` rather than at
  signup: the row is created three different ways depending on profile (the
  Supabase trigger, the sqlite provisioner, a seed script) and only two run
  Python we control. Reading the profile is the one thing every client does
  after signing in.
: `Database.initialize()` now seeds the cost setting and the signup-bonus event
  into sqlite, mirroring the Supabase seed. Local and test databases had the
  tables but no rows, so local dev behaved differently from production.
: **Left for S-11:** `GET /events`, claiming, and the discount applied at
  charge time. `ProjectService._active_discount_percent()` is stubbed to return
  None and is the only line S-11 has to change.

**S-06 · W1 — provider-scoped claiming** — ✅ **DONE 08-28**
: `claim_in_flight_projects` takes `providers: Sequence[str] | None` on both
  adapters and in the `ProjectRepository` protocol. `ProviderRegistry.
  in_process_names()` reports what this process can actually run, and
  `JobPoller` claims only those.
: `None` means "any" (admin backfill, tests). An **empty** sequence returns
  early rather than falling through to no filter — a claimant that can run
  nothing must claim nothing, not everything.
: **Ready for W2:** a provider marked `external = True` is excluded
  automatically, so registering the Kaggle provider is the only step left.

### Day 3 · Sun 08-30

**S-07 · User credit + package + payment endpoints** — ✅ **DONE 08-28**
: `GET /me/credits`, `GET /me/credits/transactions`, `GET /credit-packages`,
  `POST /payments`, plus `GET /admin/credits/drift`. `PaymentService` in
  `app/payment_service.py`; `record_payment` on both adapters writes the
  payment row, the ledger row and the balance in **one** transaction.
: `Idempotency-Key` is **required** on `POST /payments`, not optional as it is
  on project creation: a replayed generation wastes a slot, a replayed purchase
  grants credits twice.
: `GET /admin/credits/drift` closes the gap where a silently-swallowed refund
  failure was invisible. Tested both ways — healthy after a full cycle, and
  detecting a balance written behind `CreditService`.
: **20 endpoint tests + 4 Postgres payment parity tests.** One of them,
  `test_sqlite_defaults_match_the_seed`, parses the Supabase seed file and fails
  if the sqlite package prices drift from it — the duplication is deliberate so
  a local demo has something to buy, and that test is what keeps it honest.
: **492 passed, 0 skipped** with a disposable Postgres running.

**S-08 · Generation modes** — 2h
: `prompt` nullable; at least one of `prompt`/`imagePath` required; server
  derives `mode` and returns it. Provider routing by mode. `image` and
  `text_image` return `PROVIDER_ERROR` until a model exists — **never** a silent
  fall back to text. Contract §5.

**S-09 · W2 — external provider mode** — 1h
: `submit()` records only; `poll()` reads the row. Registered as `kaggle`.

> **Integration point, end of day:** tell Bruce the endpoints are live.

### Day 4 · Mon 08-31

**S-10 · `EventService`** — ✅ **DONE 08-28**
: `app/event_service.py`. Windows for `once` / `daily` / `weekly` in **local
  Vietnam time (UTC+7)**; `period_key` is `''`, the local date, or the ISO week,
  which is what makes "once per weekend" mean a weekend.
: A minute window that **wraps midnight** (22:00–02:00) is two ranges, not one.
  Treated as one it would never open at all.
: **Cap and per-period uniqueness enforced in SQL** — the cap is a `WHERE` on
  the INSERT, the period rule is the unique index. A test races 8 threads at a
  3-slot event; exactly 3 win.

**S-11 · Event endpoints + discount at charge time** — ✅ **DONE 08-28**
: `GET /events`, `POST /events/{id}/claim`. `_active_discount_percent()` is no
  longer a stub, so **Hot Hours now actually lowers the price**, resolved at
  charge time rather than read from the request. `GET /me/credits` reports the
  live discount so the Create screen can quote the real number.
: The charge note records the discount, because the ledger has to explain why
  today's row is 1 when yesterday's was 2. A refund still returns what was
  taken, not what it would cost now — tested by ending the campaign mid-job.
: A failure resolving the discount is swallowed: a broken campaign should cost
  full price, not the ability to generate at all.
: **32 tests in `test_events.py` + 5 Postgres parity tests.** Every window case
  is pinned to a fixed instant, so none of them pass or fail depending on when
  the suite runs.

**Final state: 529 passed, 0 skipped** with a disposable Postgres running.

### Day 5 · Tue 09-01

**S-12 · D1 spike — image-to-video** — **hard stop 3h**
: One Kaggle session. LTX-Video 2B first (T2V + I2V, distilled — may also help
  D2), then Stable Video Diffusion. **Stop at 3 hours regardless of progress**
  and record the result either way.
: **Done when:** either an image-conditioned clip exists, or a disconfirming
  evidence-ledger entry does.

**S-13 · W3 — the Kaggle worker** — the rest of the day
: Claim → `generating` → generate → upload → `completed`, honouring
  `transitions.py`.
: Three things it must get right: **renew the lease on a timer**
  (`poll_lease_seconds` is 120 by default, ceiling 3600 — a 15-minute job at the
  default is re-claimed seven times); **keep the encoder resident between jobs**
  (phase 1 is ~5 min); **report progress per denoising step**.
: Credentials: a dedicated Postgres role with `SELECT`/`UPDATE` on
  `video_projects` only, and a storage credential scoped to the `videos` bucket,
  both in Kaggle Secrets. **Never the `service_role` key.**

### Day 6 · Wed 09-02

**S-14 · W3 finish + first real clip** — all day
: Settings: 65 frames, 30 steps. **Measure the first clip** — 65 frames is
  interpolated, not measured (D2). If it exceeds ~20 min, drop to 49 frames.
: **Done when:** a video generated on Kaggle plays in the Android app. Tell
  Bruce the moment it works — the demo recording starts immediately.

### Day 7 · Thu 09-03

**S-15 · `/admin/stats` extension** — 2h
: `newUsers` (signups, not projects), `creditsGranted`, `creditsUsed`,
  `revenueVnd`, per-event `claims`. Contract §9.1.

**S-16 · Remaining admin endpoints** — 3h
: `POST /admin/users/{id}/credits`, `GET /admin/credit-transactions`,
  `GET/PATCH /admin/settings`, `GET /admin/projects`, `CRUD /admin/events`,
  `CRUD /admin/credit-packages`, `GET /admin/payments`,
  `GET /admin/events/{id}/claims`. All audit-logged in the same transaction.

> **Feature freeze 18:00.** Nothing new after this, in either lane.

### Days 8–9 · Fri 09-04, Sat 09-05

**S-17 · Evidence and docs** — update `DATA_MODEL.md`, `API_CONTRACT.md` §2.x,
`ARCHITECTURE.md`; evidence-ledger entries for the worker and the first real
generation.
**S-18 · Submission package** — `bootstrap.sql` + seed verified from empty;
sample accounts; final suite run.

---

## 2. Bruce — Android

### Day 1 · Fri 08-28

**B-01 · Camera capture** — ✅ **DONE 08-28**
: `CAMERA` permission plus `<uses-feature required="false">` so the app still
  installs on a device without one. `TakePicture` writes into a FileProvider
  `cache-path` (`captures/`) — a `file://` URI throws `FileUriExposedException`.
: The "Attach Reference Image" button is now **Choose** and **Take photo** side
  by side. Permission is checked before asking, so the system dialog appears
  once rather than on every tap, and a denial explains that the gallery still
  works instead of failing silently.
: Both sources share one `readImage` path, so a fix to compression or MIME
  detection cannot apply to one and miss the other. Backing out of the camera
  reports nothing — that is a cancellation, not an error.

**B-02 · Contract models + fake repository** — ✅ **DONE 08-28**
: `domain/model/Credits.kt` (domain types), `data/remote/CreditsDto.kt` (wire
  types + mappers), six endpoints added to `CretonaApi`,
  `domain/repository/CreditsRepository.kt`, and `data/FakeCreditsRepository.kt`
  bound in `RepositoryModule` with a `TODO(S-07/S-11)` marking the swap.
: The fake reproduces the **refusals**, not just the happy path: a replayed
  idempotency key returns the original result, claiming a `discount` event is
  refused, an already-claimed event is refused, and a 350 ms delay keeps
  loading states honest. All four seeded events match the SQL seed.
: `reason` stays a `String`, not an enum — the server may add one before the
  app ships again, and an unknown value must render rather than crash.
: **8 tests in `CreditsSerializationTest`**, including a descriptor-level guard
  that fails if anyone gives a request field a default value, which is what
  `encodeDefaults = false` silently drops.

**B-03 · Credits screen** — 2h · *depends: B-02*
: Balance, `effectiveCost`, the `activeDiscount` banner when non-null, and the
  paged transaction list. Each `reason` maps to a label and icon; an unknown
  value renders as the raw string rather than crashing.

### Day 2 · Sat 08-29

**B-04 · Buy credits flow** — 3h
: Package list → confirm → `POST /payments` with an `Idempotency-Key` → balance
  updates. Handle `PACKAGE_INACTIVE` by refreshing.

**B-05 · Home: replace the quota chip** — 2h
: The chip currently reads `"⚡ ${quota.remaining} of ${quota.limit} credits
  remaining"` — that is the rate limit, not a balance. Replace with the real
  balance and the effective cost of one generation.

**B-06 · `402` handling** — 1h
: `INSUFFICIENT_CREDITS` routes to the Credits screen with an actionable
  message. Never a raw error. Keep `QUOTA_EXCEEDED` (429) distinct — different
  message, different action.

### Day 3 · Sun 08-30

**B-07 · Three generation modes** — 3h
: Prompt optional; image optional; submit enabled when either is present. Show
  the derived `mode` back from the server. Handle `PROVIDER_ERROR` on image
  modes with an honest message — the feature is not available yet, not "try
  again".

**B-08 · Admin: Manage list replaces the tab row** — 2h
: Four tabs will not become ten on a phone. Stats stays the landing dashboard;
  everything else becomes a row that navigates to its own screen.

**B-09 · Admin: Videos screen** — 2h
: List with status and owner filters, from `GET /admin/projects`.

> **Integration point:** switch `CretonaRepositoryImpl` off the fakes.

### Day 4 · Mon 08-31

**B-10 · Events screen** — 3h
: Cards for grants and discounts. **Bind the button to `claimable` only** — do
  not re-derive it from windows and counts; the server owns that rule.
  Discounts render as information, never as a button. Show `nextActiveAt` when
  not active.
: Handle `EVENT_NOT_ACTIVE`, `EVENT_ALREADY_CLAIMED`, `EVENT_FULL` distinctly.

**B-11 · Admin: Credits and Transactions screens** — 3h
: Per-user credit adjustment with a note; the global transaction list with
  filters.

### Day 5 · Tue 09-01

**B-12 · Admin: Events, Packages, Settings screens** — 5h
: Event create and edit covering every field in contract §7 — kind, recurrence,
  window, minutes, days, cap. Package CRUD. Generation cost in Settings.

### Day 6 · Wed 09-02

**B-13 · Admin dashboard tiles** — 3h · *depends: S-15*
: New users, credits granted, credits used, revenue, per-event take-up. Build
  against the contract shape; wire to the live endpoint on 09-03.

**B-14 · Screenshot pass** — 2h
: Every screen, user and admin, light and dark. These go in the report.

> **The moment S0ra1n0 says a real clip exists: play it in the app and start
> recording the demo.** Do not leave the recording to 09-04.

### Day 7 · Thu 09-03

**B-15 · Wire the dashboard to live stats** — 1h
**B-16 · Integration defects** — the rest of the day.

> **Feature freeze 18:00.**

### Days 8–9 · Fri 09-04, Sat 09-05

**B-17 · Demo video** — the full flow in one take: register → signup bonus →
claim a weekend gift → buy a package → generate with an image → watch the
charge in the ledger → play, download, share → admin locks a user, adjusts
credits, creates an event, reads the dashboard.
**B-18 · Report and screenshots.**

---

## 3. Shared, and unassigned on purpose

| Item | Who | When |
|---|---|---|
| Ask the lecturer the D1 question | S0ra1n0 | **today** |
| Decide the FramePack/LTX fallback if the answer is "image must drive it" | Both | before the reply arrives |
| Resolve `durationSeconds` 2–10 vs a fixed 4.06 s clip | Both | with the contract, day 1 |
| Report writing | Both | 09-04 |

---

## 4. Cut order, if behind

Decided now so it is not decided at 2am on the 4th.

1. Per-event take-up reporting (one of six §3 metrics)
2. Admin video moderation beyond a read-only list
3. Admin `Packages` screen — seed three and manage them in SQL
4. `weekly` recurrence — ship `once` and `daily` only, seed the weekend gift as
   a series of `once` events
5. Admin tablet and desktop layouts

**Never cut:** the eight tables · real video generation · the admin screens ·
the report and demo video.

---

## 5. Gates

- **End of 08-29** — if credits do not charge and refund, drop events to a
  read-only list with manual admin grants and keep the tables.
- **End of 09-01** — if W3 is not claiming rows, spend 09-02 getting one clip
  through the notebook with a manual upload so §6 has a demo video, then resume.
- **09-01, 3 hours in** — the D1 spike stops whether or not it has worked.
- **09-03 18:00** — feature freeze regardless of state.
