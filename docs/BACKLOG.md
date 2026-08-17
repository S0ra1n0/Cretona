# Cretona — post-parity backlog

Status: written 2026-08-12, after FastAPI reached behavioural parity with the
Express reference. Last updated 2026-08-14 after live Supabase migrations 006
and 007 were applied and verified.

## Progress

| | Item | State |
|---|---|---|
| B-1 | Per-attempt `started_at` | **Done** — `1f1b39c`, verified 239 passed |
| B-2 | Poller lease fencing | **Done** — `32b6b0d`, verified 245 passed |
| B-3 | Shared-store rate limiting | **Done** — Postgres sliding window with atomic advisory-lock transactions, bounded cleanup, hashed caller keys, and SQLite in-memory fallback; verified 261 passed / 0 skipped on disposable PostgreSQL 16.14; migration 007 rehearsed twice and applied/verified on live Supabase; live FastAPI deployment remains separate |
| B-4 | `generation_logs` retention | **Done** — 180-day, oldest-first bounded cleanup with metadata-only aggregation; verified 239 passed / 19 Postgres-only skipped; migration 006 retention index applied/verified on live Supabase |
| B-5 | Admin read endpoint for logs | **Done** — `GET /admin/projects/{id}/logs` exposes generation log trail to admins; 244 tests passed |
| B-6 | Queryable admin audit | **Code done, not deployable until migration 008 is applied.** Confirmed unapplied on the live project 2026-08-15. The Postgres path had no test at all, and the original migration disagreed with the calling code on `target_id`, `details`, and their types; corrected before first application. Startup now refuses to boot without the table |
| B-7 | Log shipping and sampling | **Done** — `request_log_sample_rate` configuration and middleware sampling for 2xx while preserving >=400 errors |
| B-8 | Android consumes `/me` | **Done** — quota/identity loading, retry, exhausted-state prevention, post-submit refresh, and AVD evidence; 12 Android tests plus clean lint/assembly |
| B-9 | Android shows thumbnails | **Done** — Coil history preview with loading/error fallback, project aspect ratio, and AVD evidence; 12 Android tests plus clean lint/assembly |
| B-10 | Android admin screens | **Done** — `AdminScreen.kt`, `AdminViewModel.kt`, `AdminUiState.kt` with Overview, Users, Audit Logs, Diagnostics tabs, navigation, and unit tests passing |
| B-11 | Provider webhook receiver | **Done** — `verify_webhook` in `VideoProvider` adapters, `POST /api/v1/webhooks/{provider}` route, automated lifecycle tests |
| B-12 | Bucket-backed thumbnails | **Done** — `SupabaseStorage` resolves video frame extraction and uploads frame stills to Supabase Storage bucket; 244 tests passed |
| B-13 | Thumbnail backfill | **Done** — `POST /admin/thumbnails/backfill` scans completed projects with missing thumbnails and extracts/uploads frame stills |
| B-14 | Quota cost weighting | **Done** — duration and provider cost weighting (standard 1 unit, Real AI / Wan2.1 / >5s 2 units) with SQL weighted sum and balance assertions |
| B-16 | Second provider adapter | **Done, corrected 2026-08-17 (T0-2)** — `LocalModelVideoProvider` (alias `wan21`) registered as a third tier; multi-provider selector chips in Android UI. It is a placeholder, not a Wan 2.1 integration: no local model runs, and its output is identical to the cloud tier's hosted-still-plus-pan |

The numbered migration sequence is now observed applied on live Supabase:

- `supabase/004_add_started_at.sql` (B-1) — present before the 2026-08-14 live preflight
- `supabase/005_add_poll_lease.sql` (B-2) — present before the 2026-08-14 live preflight
- `supabase/006_add_generation_log_retention_index.sql` (B-4) — applied and verified 2026-08-14
- `supabase/007_add_shared_rate_limits.sql` (B-3) — applied and verified 2026-08-14
- `supabase/008_add_admin_audit_logs.sql` (B-6) — **prepared, not applied.** Apply
  before deploying the audit feature; the backend refuses to start without it

The live schema gate required by `CRETONA_DATABASE_BACKEND=postgres` now passes
at the database layer. This does not prove that a live FastAPI revision is
deployed or configured against the project. Local Postgres models all four
changes via `tests/postgres_schema.sql`; the disposable run passed all 261 tests
and applied migration 007 twice. See `docs/evidence/B3_POSTGRES_VERIFICATION.md`
and `docs/evidence/LIVE_SUPABASE_MIGRATIONS_006_007_2026-08-14.md`.

## How to read this

**Most of this list is a proposal, not an assignment.** The original handoff
assigned three tasks (Supabase JWT, Postgres, Storage); all three are done. The
provenance column says where each item actually comes from, so nobody treats a
suggestion as a commitment:

| Mark | Meaning |
|---|---|
| **R** | Comes from the repo — an ADR, a roadmap task ID, or a documented spec |
| **D** | Debt created by the parity work, named in the commit that created it |
| **P** | My proposal. Legitimate to drop |

Effort is rough: **S** ≈ under an hour, **M** ≈ a few hours, **L** ≈ a day or more.

---

## Not on this list: the two things that matter most

Neither is doable right now, and neither should be forgotten because of that.

**Live FastAPI-to-Supabase runtime proof.** The live database schema is now
verified through migration 007, but no FastAPI revision has been started or
smoke-tested against live Auth/Postgres/Storage. The ignored
`backend-fastapi/.env` is not configured on this machine, and any QA writes or
account/object creation require a separately authorized, cleanup-bounded smoke
task. Schema evidence must not be reported as application/runtime parity.

**A real video provider.** The fake proves the workflow and nothing about
video. LTX 2B was rejected at pre-screen; FramePack is installed but blocked
before inference by resource and licence gates. Blocked on EXP-005, and on a
hardware decision that is explicitly not mine to make.

---

## Tier 1 — Correctness and safety

Do these first. Each one is a case where the system is currently wrong rather
than merely incomplete.

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| ~~B-1~~ | ~~Per-attempt `started_at`~~ | **Done.** Timeout now measures per attempt; retry gets a fresh budget | M | D |
| ~~B-2~~ | ~~Lease fencing on poller claims~~ | **Done.** The claim is now data that survives the transaction, not a lock that evaporated before the work started | M | D |
| ~~B-3~~ | ~~Shared-store rate limiting~~ | **Done.** Postgres instances share an atomic sliding window; SQLite retains the explicit single-process fallback | M | D |

B-3 selected Postgres in ADR-010 because it adds no new service at this scale.
Migration 007 and its live verification are complete. Deploying and smoke
testing the pinned B-3 FastAPI revision remain separate hold points.

## Tier 2 — Operability

The system works but is hard to run and hard to diagnose.

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| ~~B-4~~ | ~~`generation_logs` retention~~ | **Done.** Raw rows expire after 180 days; cleanup is atomic and batch-bounded, while only non-sensitive aggregate counts leave the table | S | D |
| ~~B-5~~ | ~~Admin read endpoint for logs~~ | **Done.** `GET /admin/projects/{project_id}/logs` returns generation log history for diagnostic inspection | M | P |
| ~~B-6~~ | ~~Queryable admin audit~~ | **Done.** `admin_audit_logs` table, `insert_audit_log`/`list_audit_logs`, and `GET /admin/audit-logs` endpoint | M | D |
| ~~B-7~~ | ~~Log shipping and sampling~~ | **Done.** `request_log_sample_rate` middleware sampling for 2xx while preserving >=400 errors | M | D |

## Tier 3 — Product surface

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| ~~B-8~~ | ~~Android consumes `/me`~~ | **Done.** Home shows remaining quota before Generate, explains loading/exhaustion, retries read failures, and refreshes after submit | M | P |
| ~~B-9~~ | ~~Android shows thumbnails~~ | **Done.** Completed history cards load `thumbnailUrl`, preserve project ratio, and retain usable metadata when the preview is absent or fails | S | P |
| ~~B-10~~ | ~~Android admin screens~~ | **Done.** `AdminScreen.kt`, `AdminViewModel.kt`, `AdminUiState.kt` with Overview, Users, Audit Logs, Diagnostics tabs, navigation, and unit tests passing | L | P |
| ~~B-11~~ | ~~Provider webhook receiver~~ | **Done.** `verify_webhook` in `VideoProvider` adapters, `POST /api/v1/webhooks/{provider}` route, automated lifecycle tests | M | R |
| ~~B-12~~ | ~~Bucket-backed thumbnails~~ | **Done.** `SupabaseStorage` resolves video frame extraction and uploads generated thumbnail images to Supabase Storage bucket | M | D |
| ~~B-13~~ | ~~Thumbnail backfill~~ | **Done.** `POST /admin/thumbnails/backfill` scans completed projects with missing thumbnails and extracts/uploads frame stills | S | D |
| ~~B-14~~ | ~~Quota cost weighting~~ | **Done.** Duration and provider cost weighting (standard 1 unit, Real AI / Wan2.1 / >5s 2 units) with SQL weighted sum and balance assertions | M | D |
| ~~B-17~~ | ~~Image-to-Video~~ | **Done.** Direct multipart image upload, storage image persistence, signed upload URL support, Android image picker + preview card + Image-to-Video badge, project image condition reference mapping | L | R |


## Tier 4 — Structural decisions

These need a human decision, not just implementation time.

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| B-15 | ADR-008 folder rename | Its "Revisit when" triggers once FastAPI has parity and Android E2E is recorded. Android evidence and live schema evidence exist, but FastAPI runtime parity is still **unverified against live Supabase**. Renaming `backend-fastapi/` to `backend/` and archiving Express remains a large, reviewable commit | L | R |
| ~~B-16~~ | ~~Second provider~~ | **Done, corrected 2026-08-17.** `LocalModelVideoProvider` (alias `wan21`) registered as a third tier — a placeholder, not a Wan 2.1 integration; see the entry above | L | R |

---

## Suggested order

1. ~~**B-1, B-2**~~ — done.
2. ~~**B-4**~~ — done.
3. ~~**B-8, B-9**~~ — done.
4. ~~**B-3**~~ — done; migration 007 is live, while application deployment and smoke verification remain pending.
5. Everything else, as the situation demands.

Do not start B-15 until the FastAPI runtime has passed live Supabase smoke
verification. Schema verification alone does not prove application/runtime
parity, and renaming first would make the first real integration failure much
harder to attribute.

## What this list deliberately omits

- Anything requiring credentials I do not have
- Anything gated behind EXP-005
- Anything requiring a hardware or spend decision
- Test coverage as its own item; each entry above carries its own tests
