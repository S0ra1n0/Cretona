# Cretona — task split to 2026-09-05

- **Document ID:** `CRETONA-TASKS-005`
- **Written:** 2026-08-28 · **Submit:** 2026-09-05 (8 working days)
- **Contract:** `API_CONTRACT.md` Part II — **agreed, do not renegotiate
  informally.** A change gets told to the other person the same day.
- **Decisions:** `PLAN-TO-2026-09-05.md` §2 (D1–D4, all resolved)
- **S0ra1n0** — backend, database, Kaggle worker · **Bruce** — Android, admin UI

Ticket ids are stable. Use them in commit messages: `feat(credits): S-03 …`.

> **Audit update 2026-08-29.** Bruce's B-03 through B-13 implementations are
> present on `main`, compile against the real repositories, and passed the
> relevant automated gates. They are **source-complete**, not yet device-
> accepted: B-14 and B-16 still own the final emulator journeys, screenshots
> and live integration proof. S-12 is stretch scope because the lecturer gave
> no model or image-conditioning mandate; S-13/S-14 are the release-critical
> worker and real-video path. See `ROADMAP.md` for the concise current state.

---

## 0. How the two lanes stay parallel

> **Updated 2026-08-28.** The fake repository was insurance against Bruce
> waiting on endpoints. He is not waiting: every endpoint his screens need
> exists and is tested. The first integration point below was scheduled for
> 08-30 and happened on 08-28.

Bruce built B-02's `FakeCreditsRepository` so screens were buildable on day 1.
That seam worked. `CreditsRepositoryImpl` is now bound to the real FastAPI
endpoints; the fake is no longer the application binding.

| When | What | Status |
|---|---|---|
| ~~End of 08-30~~ | Credits + events endpoints live; Bruce switches off fakes | ✅ endpoints landed 08-28; real binding and screens audited 08-29 |
| End of 09-02 | Worker produces a real clip; Bruce plays it in the app | ⏸ blocked on a Kaggle session |
| 09-03 18:00 | Feature freeze. Everything after is integration and docs | pending |

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
: Suite stood at **492 passed, 0 skipped** when this ticket closed; see §6 for
  the current total.

**S-08 · Generation modes** — ✅ **DONE 08-28**
: `prompt` was already nullable with an "at least one input" validator from the
  W4 work. What was missing: `mode` on the response, and routing.
: `mode` is **derived and recomputed**, never stored and never sent by the
  client — there is no column to drift and no way for client and server to
  disagree about what was asked for.
: Providers now declare `supports_image`. `fake` is False (returns a bundled
  clip), `real` and `local` are True (they pan across the account's own upload,
  W4), `kaggle` is False (Wan2.1 T2V reads the prompt and nothing else).
: **A provider that cannot use an image refuses the request** with
  `PROVIDER_ERROR`, before the charge and before the row. This changed an
  existing expectation: `test_create_project_with_image_path` sent an image to
  `fake` and expected 201. The mock's own comment already said accepting an
  image and returning an unrelated clip "would not be" honest — it just did it
  silently. That test now uses `local` and asserts `mode == "text_image"`.
: Ownership is still checked **before** capability, so the status code cannot
  be used to probe whether someone else's storage path exists.
: **19 tests in `test_generation_modes.py`**, including one that follows the
  error message's own advice — remove the image, and the same prompt succeeds.
: **D1 does not block this.** The lecturer imposed no model requirement;
  `supports_image` remains the honest capability gate if the team later adds
  an image-conditioned model.

**S-09 · W2 — external provider mode** — ✅ **DONE 08-28**
: `ExternalVideoProvider` in `providers.py`, registered as `kaggle`.
  `submit()` records only — no network, no model. `poll()` returns `running`
  so the row keeps whatever the worker last wrote; reporting anything else
  would overwrite real progress with a guess from a process that cannot see
  the GPU.
: `verify_webhook()` **refuses outright**. The worker writes results directly,
  so a webhook would be a second, unauthenticated way to mark work finished.
: `external = True` pairs with S-06: `in_process_names()` now returns
  `('fake', 'local', 'real')` and the poller leaves `kaggle` rows alone.
  W1 + W2 together are what make the worker safe to add.

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

### Day 5 · Tue 09-01

**S-12 · Optional image-to-video spike** — **STRETCH, after S-14; hard stop 3h**
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

**S-15 · `/admin/stats` extension** — ✅ **DONE 08-28**
: `creditsGranted`, `creditsUsed`, `revenueVnd` on totals; `newUsers` plus all
  three on the daily series; a per-campaign `events` block with claims, credits
  granted and slots remaining.
: **Four separate queries merged by date**, not one joined query. A join drops
  any day on which credits moved but no project was created, and a revenue
  chart with holes looks like data rather than a bug.
: A refund is a positive delta, so it counts in `creditsGranted` rather than
  netting off `creditsUsed` — otherwise "credits used" would mean something no
  single query produces and the two halves would stop summing to the balance.
: `remainingSlots` is `null` for an uncapped event, never `0` — "unlimited" and
  "none left" must not render the same.
: Empty systems report **zeroes, not nulls**: a dashboard tile bound to null
  renders blank, which reads as broken.
: **14 tests in `test_admin_stats.py`.**

**S-16 · Remaining admin endpoints** — ✅ **DONE 08-28**
: All twelve: credit adjustment, credit-transaction listing, settings get and
  patch, package list/create/patch, event list/create/patch, event claims,
  payments, and cross-user project listing. `AdminCreditService` in
  `app/admin_credit_service.py`.
: **The credit adjustment writes its audit row inside the same transaction as
  the money** — `apply_credit_delta` now takes an optional `AuditEntry` on both
  adapters. An admin changing a balance with no record of it was the one gap
  left in the T2-5 rule.
: Packages are never deleted, only deactivated: `payments` reference them, and
  a purchase history that loses what was purchased is not a history.
: Event validation repeats the CHECK constraints on purpose — the database
  would refuse a grant with no credits anyway, but an admin filling in a form
  deserves to be told *which field*, not a constraint violation.
: `GET /admin/projects` is a separate repository method from `list_projects`,
  so the user-facing path never grows a flag whose only job is skipping the
  ownership check.
: **28 tests**, including one that walks every new endpoint and asserts a
  normal user gets 403 — one place to notice if a route is ever added without
  a role gate.

Suite stood at **590 passed, 0 skipped** when this ticket closed; see §6 for
the current total.

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

**B-03 · Credits screen** — ✅ **SOURCE COMPLETE 08-29**
: Balance, `effectiveCost`, the `activeDiscount` banner when non-null, and the
  paged transaction list. Each `reason` maps to a label and icon; an unknown
  value renders as the raw string rather than crashing.

### Day 2 · Sat 08-29

**B-04 · Buy credits flow** — ✅ **SOURCE COMPLETE 08-29**
: Package list → confirm → `POST /payments` with an `Idempotency-Key` → balance
  updates. Handle `PACKAGE_INACTIVE` by refreshing.

**B-05 · Home: replace the quota chip** — ✅ **SOURCE COMPLETE 08-29**
: The chip currently reads `"⚡ ${quota.remaining} of ${quota.limit} credits
  remaining"` — that is the rate limit, not a balance. Replace with the real
  balance and the effective cost of one generation.

**B-06 · `402` handling** — ✅ **SOURCE COMPLETE 08-29**
: `INSUFFICIENT_CREDITS` routes to the Credits screen with an actionable
  message. Never a raw error. Keep `QUOTA_EXCEEDED` (429) distinct — different
  message, different action.

### Day 3 · Sun 08-30

**B-07 · Three generation modes** — ✅ **SOURCE COMPLETE 08-29**
: Prompt optional; image optional; submit enabled when either is present. Show
  the derived `mode` back from the server. Handle `PROVIDER_ERROR` on image
  modes with an honest message — the feature is not available yet, not "try
  again".

**B-08 · Admin: Manage list replaces the tab row** — ✅ **SOURCE COMPLETE 08-29**
: Four tabs will not become ten on a phone. Stats stays the landing dashboard;
  everything else becomes a row that navigates to its own screen.

**B-09 · Admin: Videos screen** — ✅ **SOURCE COMPLETE 08-29**
: List with status and owner filters, from `GET /admin/projects`.

> **Integration point:** completed 08-29; real repositories are bound.

### Day 4 · Mon 08-31

**B-10 · Events screen** — ✅ **SOURCE COMPLETE 08-29**
: Cards for grants and discounts. **Bind the button to `claimable` only** — do
  not re-derive it from windows and counts; the server owns that rule.
  Discounts render as information, never as a button. Show `nextActiveAt` when
  not active.
: Handle `EVENT_NOT_ACTIVE`, `EVENT_ALREADY_CLAIMED`, `EVENT_FULL` distinctly.

**B-11 · Admin: Credits and Transactions screens** — ✅ **SOURCE COMPLETE 08-29**
: Per-user credit adjustment with a note; the global transaction list with
  filters.

### Day 5 · Tue 09-01

**B-12 · Admin: Events, Packages, Settings screens** — ✅ **SOURCE COMPLETE 08-29**
: Event create and edit covering every field in contract §7 — kind, recurrence,
  window, minutes, days, cap. Package CRUD. Generation cost in Settings.

### Day 6 · Wed 09-02

**B-13 · Admin dashboard tiles** — ✅ **SOURCE COMPLETE 08-29**
: New users, credits granted, credits used, revenue, per-event take-up.
: `GET /admin/stats` already returns all of it (S-15, done 08-28), so build
  straight against the live endpoint — there is no contract-shape phase and
  **B-15 no longer exists**.
: Two shapes worth handling deliberately: `remainingSlots` is `null` for an
  uncapped event (render "unlimited", not "0"), and an empty system returns
  zeroes rather than nulls, so a tile never renders blank.

**B-14 · Screenshot pass** — 2h
: Every screen, user and admin, light and dark. These go in the report.

> **The moment S0ra1n0 says a real clip exists: play it in the app and start
> recording the demo.** Do not leave the recording to 09-04.

### Day 7 · Thu 09-03

~~**B-15 · Wire the dashboard to live stats**~~ — **dropped.** It existed
because `/admin/stats` was not expected until 09-03. It landed on 08-28, so
B-13 wires to the real endpoint directly.

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
| D1 lecturer question | — | Resolved: no model or image-conditioning mandate; S-12 is stretch scope |
| Decide whether an image model is worth the quota | Both | after S-14 and blind Wan2.1 scoring |
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
- **09-01, 3 hours in** — any optional image-model spike stops whether or not it has worked.
- **09-03 18:00** — feature freeze regardless of state.

---

## 6. Progress — reconciled 2026-08-30

**Backend API/database and Kaggle worker source are done.** S-12 is an optional
image-model spike; applying migration 014, the S-13 live worker run and S-14
first real-video playback remain the critical path.

| Ticket | | Ticket | |
|---|---|---|---|
| S-01 migration | ✅ | S-10 `EventService` | ✅ |
| S-02 seed | ✅ | S-11 event endpoints + discount | ✅ |
| S-03 `ADR-010` | ✅ | S-12 image-to-video spike | stretch, timeboxed |
| S-04 `CreditService` | ✅ | S-13 Kaggle worker | ✅ source/local parity; live run pending |
| S-05 charge and refund | ✅ | S-14 first real clip | ⏸ needs Kaggle |
| S-05a signup bonus | ✅ | S-15 `/admin/stats` | ✅ |
| S-06 W1 scoped claiming | ✅ | S-16 admin endpoints | ✅ |
| S-07 credit endpoints | ✅ | S-17 evidence and docs | in progress |
| S-08 generation modes | ✅ | S-18 submission package | pending |
| S-09 W2 external provider | ✅ | | |

### Verification

Migration `013` and its seed were historically applied and constraint-probed on
live Supabase. The current 2026-08-30 audit records **546 passed / 55
Postgres-only skipped** on SQLite and **601 passed / 0 skipped** on disposable
PostgreSQL 17, with Ruff and `pip check` clean. This local run does not prove
that migration 014 is present on live Supabase.

Running the Postgres half is documented in `backend/README.md`. Plain `pytest`
skips 31–66 tests, and production runs Postgres — so a green plain run is not a
green run.

### Three things worth carrying forward

1. **A gap the tests found, not the plan.** A new account starts at 0 credits
   and nothing granted a first one, so a real user could finish their profile
   and then never generate anything. The end-to-end test caught it. The signup
   bonus (S-05a) was pulled forward from S-11 to close it.
2. **Every adapter method exists twice.** Three times running, code written for
   Postgres had never executed while the SQLite suite passed — production runs
   Postgres. The parity suite now covers credits, payments and events, and
   `backend/README.md` says why a plain `pytest` run is not enough.
3. **The money invariants live in the database.** Non-negative balances,
   single-charge, single-claim and campaign caps are CHECKs, unique indexes and
   `WHERE` clauses inside the write — never a read-then-write in Python, which
   loses to a second tap. Concurrency tests on both backends prove each one.

### What is left, and who it needs

| | Needs |
|---|---|
| **D1 — must the image drive the video?** | Resolved from lecturer scope: no specific model or image-conditioning requirement |
| Optional image-model fallback | Only after S-13/S-14 and only if the Wan2.1 blind score is unacceptable |
| S-13 / S-14 | Apply/verify migration 014, configure Kaggle Secrets, run one Kaggle session and play its result in Android |
| Bruce's lane | B-14 screenshots, B-16 device/integration acceptance, then B-17/B-18 |

---

## 7. Integration status — audited 2026-08-29

The earlier `khoa` integration instructions are superseded. Local `main`
contains patch-equivalent Khoa work plus the later Android/admin integration;
the remaining remote branch is cleanup state, not unmerged product work.

### Runtime state

- Migration `013` and its seed were applied and verified on 08-28; that is
  historical evidence, not a new live verification from this audit.
- **Local SQLite migrates itself** on first start. `ADDED_COLUMNS` widens an
  existing file and `_seed_defaults` inserts the generation cost, the signup
  bonus and the three credit packages — so a local demo has something to buy.
- **No new dependencies**, backend or Android. No `.env` change.

### Repository binding

`CreditsRepositoryImpl` already implements the FastAPI endpoints and is bound
in `RepositoryModule.kt`. Do not recreate or rebind the fake in production.

### What is live, and what it means for a screen

| Endpoint | The bit that affects your UI |
|---|---|
| `GET /me/credits` | Show **`effectiveCost`**, never `generationCost`. During Hot Hours they differ, and quoting the wrong one misleads |
| `GET /me/credits/transactions` | Cursor-paged. `reason` may be a value this app build has never seen — render the raw string rather than crashing |
| `GET /credit-packages` | Active only. `PACKAGE_INACTIVE` on purchase means refresh, not retry |
| `POST /payments` | **`Idempotency-Key` is required**, unlike on `/projects`. Generate it once per user intent and reuse it across retries — a fresh key on retry is the same as no key |
| `GET /events` | Bind the button to **`claimable` alone**. Do not re-derive it from the window, the cap and the claim history: the server owns that rule, and the copy that gives credits away would be yours |
| `POST /events/{id}/claim` | Three distinct 409s — `EVENT_NOT_ACTIVE`, `EVENT_ALREADY_CLAIMED`, `EVENT_FULL`. They need different messages |
| `GET /admin/stats` | Everything B-13 needs, including per-event take-up |
| 12 admin endpoints | Every screen in B-09 through B-12 |

### Three behaviours that changed under you

1. **A generation now costs credits.** `POST /projects` returns **402
   `INSUFFICIENT_CREDITS`** when the balance will not cover it. That is a
   different refusal from `429 QUOTA_EXCEEDED`, which still exists and still
   means the rolling rate limit — B-06 has to route them differently.
2. **An image sent to a provider that cannot use it is refused**, `502
   PROVIDER_ERROR`, rather than quietly ignored. `real` and `local` accept
   images; `fake` and `kaggle` do not. If your emulator default is `fake`, an
   image submission will fail until an image-capable model exists — that is
   deliberate (§5 of the contract), not a bug to work around.
3. **Every project response carries `mode`** — `text`, `image` or
   `text_image`, derived server-side. Do not send it.

### Where a new account gets its first credits

`GET /me` grants the signup bonus on the first read after sign-in, once, and is
a no-op afterwards. If a fresh test account has 0 credits and cannot generate,
call `/me` — that is the hook, not registration, because the `users` row is
created three different ways depending on profile and only two of them run
Python we control.

### Verifying the merge

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest        # expect 546 passed, 55 skipped
```

**The 53 skips are the Postgres suite, and production runs Postgres.** A green
plain run is not a green run. The full command is in `backend/README.md`;
with a disposable Postgres it is **601 passed, 0 skipped**.

### Two things still open for the team

Neither is Android work, but both affect what the demo can show, so they are
here where they will be read:

- **A Kaggle session** for S-13 and S-14. Wan2.1 generation is proven in the
  notebook, but the worker-to-FastAPI-to-Android path is not.
- **Blind scoring.** The four distinct Wan2.1 clips are scoreable, but the
  quality scorecard remains empty; feasibility must not be reported as quality.
