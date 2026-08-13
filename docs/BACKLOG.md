# Cretona — post-parity backlog

Status: written 2026-08-12, after FastAPI reached behavioural parity with the
Express reference. Last updated 2026-08-13 after B-3.

## Progress

| | Item | State |
|---|---|---|
| B-1 | Per-attempt `started_at` | **Done** — `1f1b39c`, verified 239 passed |
| B-2 | Poller lease fencing | **Done** — `32b6b0d`, verified 245 passed |
| B-3 | Shared-store rate limiting | **Done** — Postgres sliding window with atomic advisory-lock transactions, bounded cleanup, hashed caller keys, and SQLite in-memory fallback; 241 passed / 20 Postgres-only skipped; live migration remains unapplied |
| B-4 | `generation_logs` retention | **Done** — 180-day, oldest-first bounded cleanup with metadata-only aggregation; verified 239 passed / 19 Postgres-only skipped; live migration remains unapplied |
| B-8 | Android consumes `/me` | **Done** — quota/identity loading, retry, exhausted-state prevention, post-submit refresh, and AVD evidence; 12 Android tests plus clean lint/assembly |
| B-9 | Android shows thumbnails | **Done** — Coil history preview with loading/error fallback, project aspect ratio, and AVD evidence; 12 Android tests plus clean lint/assembly |

**Four migrations are prepared and unapplied**, all additive and re-runnable.
Apply them in numeric order:

- `supabase/004_add_started_at.sql` (B-1)
- `supabase/005_add_poll_lease.sql` (B-2)
- `supabase/006_add_generation_log_retention_index.sql` (B-4)
- `supabase/007_add_shared_rate_limits.sql` (B-3)

Until 004, 005, and 007 are applied, `CRETONA_DATABASE_BACKEND=postgres` against
Supabase refuses to start and names the files to run. That is the intended
behaviour, not a fault. Missing 006 does not change correctness, but leaves the
retention sweep without its table-wide cutoff index. Local Postgres already
models all four changes via `tests/postgres_schema.sql`; the Postgres suite was
not run on 2026-08-13 because no disposable database or Docker daemon was
available.

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

**Live Supabase verification.** Nothing has ever run against the real project.
Every green test is local Postgres, a local file mount, and locally minted
tokens. This can invalidate work already committed, so it outranks everything
below. Blocked on `backend-fastapi/.env` and permission to write to a live
project.

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
Migration 007 and its live verification remain deployment hold points.

## Tier 2 — Operability

The system works but is hard to run and hard to diagnose.

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| ~~B-4~~ | ~~`generation_logs` retention~~ | **Done.** Raw rows expire after 180 days; cleanup is atomic and batch-bounded, while only non-sensitive aggregate counts leave the table | S | D |
| B-5 | Admin read endpoint for logs | Diagnosing a failed generation currently needs direct database access | M | P |
| B-6 | Queryable admin audit | Admin actions are logged to stdout only, so "who disabled this account" is not answerable after log rotation | M | D |
| B-7 | Log shipping and sampling | Every request logs a line, with no sampling and nowhere to ship it | M | D |

## Tier 3 — Product surface

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| ~~B-8~~ | ~~Android consumes `/me`~~ | **Done.** Home shows remaining quota before Generate, explains loading/exhaustion, retries read failures, and refreshes after submit | M | P |
| ~~B-9~~ | ~~Android shows thumbnails~~ | **Done.** Completed history cards load `thumbnailUrl`, preserve project ratio, and retain usable metadata when the preview is absent or fails | S | P |
| B-10 | Android admin screens | `/admin/*` exists with no client | L | P |
| B-11 | Provider webhook receiver | P3-7, deferred by ADR-003. `verify_webhook` is on the interface and unimplemented | M | R |
| B-12 | Bucket-backed thumbnails | `SupabaseStorage.local_video_path` returns None, so bucket deployments get no thumbnails at all | M | D |
| B-13 | Thumbnail backfill | Projects completed before thumbnails existed have none | S | D |
| B-14 | Quota cost weighting | Every generation counts as 1 regardless of duration or provider price. Needs a product decision on weights before it is codeable | M | D |

B-8 through B-10 are the only items here a user would notice. The backend is
currently ahead of the client.

## Tier 4 — Structural decisions

These need a human decision, not just implementation time.

| ID | Item | Why | Effort | Mark |
|---|---|---|---|---|
| B-15 | ADR-008 folder rename | Its "Revisit when" triggers once FastAPI has parity and Android E2E is recorded. Android evidence exists; parity is behavioural but **unverified against live Supabase**, so the trigger is arguably not yet met. Renaming `backend-fastapi/` to `backend/` and archiving Express is a large, reviewable commit | L | R |
| B-16 | Second provider | P3-10, to prove the abstraction. Blocked behind a first real provider | L | R |

---

## Suggested order

1. ~~**B-1, B-2**~~ — done.
2. ~~**B-4**~~ — done.
3. ~~**B-8, B-9**~~ — done.
4. ~~**B-3**~~ — done; migration 007 must precede a multi-instance deploy.
5. Everything else, as the situation demands.

Do not start B-15 until live Supabase verification has happened. Renaming the
active backend on the strength of unverified parity would make the first real
integration failure much harder to attribute.

## What this list deliberately omits

- Anything requiring credentials I do not have
- Anything gated behind EXP-005
- Anything requiring a hardware or spend decision
- Test coverage as its own item; each entry above carries its own tests
