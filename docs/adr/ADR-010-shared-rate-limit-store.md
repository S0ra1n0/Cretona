# ADR-010: Use Postgres for shared rate-limit windows

**Status:** Accepted · **Date:** 2026-08-13 · **Backlog:** B-3

## Context

The FastAPI limiter currently holds a sliding window in each process. That is
correct for the credential-free SQLite demo, but not for deployment: two API
instances each grant a complete allowance, and a restart erases active hits.
The database-backed generation quota still protects spend, but it does not
replace burst control.

The two viable shared stores were Redis and the existing Supabase/Postgres
database. Redis has purpose-built expiry and atomic-counter primitives, but it
would add another service, connection secret, local dependency, monitoring
surface, and failure mode for a two-developer course project. Postgres is
already required for the deployed profile and the expected request volume is
small.

## Decision

Postgres deployments store one row per allowed hit in
`public.rate_limit_hits`. A transaction-level advisory lock scoped to the
hashed caller and bucket serializes the prune/count/insert operation across API
instances. Postgres `clock_timestamp()` is the sole clock. Every request also
removes at most 1,000 expired rows with `FOR UPDATE SKIP LOCKED`.

SQLite continues to use the in-memory implementation. It is the deliberate
credential-free, single-process profile and must not require Supabase merely to
run locally.

The existing HTTP contract remains unchanged: health bypasses the limiter;
accepted and rejected requests carry `X-RateLimit-*`; rejection remains
`429 RATE_LIMITED` with `Retry-After`. Caller sources are hashed before storage,
so bearer tokens, debug user ids, and IP addresses are never persisted in
plaintext.

## Consequences

- Multiple FastAPI instances share one atomic sliding window after migration
  007 is applied.
- Postgres receives one small transaction per limited request; this is an
  accepted trade at MVP scale and should be measured before high traffic.
- Advisory-lock hash collisions can serialize unrelated callers, but cannot
  grant excess requests or merge their rows.
- The new app fails at startup with a named migration when the table is absent,
  preventing a silent return to process-local enforcement in deployment.
- The table is internal and ephemeral. RLS is enabled without client policies,
  and `anon`, `authenticated`, and `service_role` receive no Data API grants.
- Redis becomes worth reconsidering only if rate-limit transactions become a
  measurable database bottleneck or deployment no longer includes Postgres.

## Rollout and rollback

Apply migration 007 before deploying the B-3 backend. Older backends ignore
the additive table, so mixed-version rollout is compatible. Rollback the app
first; the unused table may remain safely and can be dropped in a later,
explicit migration because it contains no business records.

---

## Addendum, 2026-08-17: the measurement this ADR asked for

Appended rather than edited, per this repo's ADR convention — the decision
below is unchanged and reaffirmed, not reversed. If it had been reversed this
would be a new ADR instead.

The Consequences section above flagged "one small transaction per limited
request... should be measured before high traffic," and named the exit
condition: "Redis becomes worth reconsidering only if rate-limit transactions
become a measurable database bottleneck." Both have now been checked against
the live project (T3-3, `docs/ROADMAP-NEXT.md`), with a real deployment
context that wasn't available in 2026-08-13: `DEC-006` places the actual
target as a team laptop over ordinary internet, not a server co-located with
Supabase, so the ~190ms/round-trip pooler latency measured from a dev machine
is a reasonable proxy for the real deployment, not an artifact of testing from
far away.

**What was measured, and what it means:**

- The original `consume_rate_limit` issued 5-6 sequential round trips per
  call. Disabling the limiter for an A/B against live cut `GET /projects`
  from 2979ms to 1468ms — roughly 1.5s attributable to rate limiting alone.
- The bottleneck was round-trip count, not Postgres throughput or the store
  choice — Redis would pay the same per-trip tax for the same access pattern.
  So the fix was to reduce trips, not to replace the store: `consume_rate_limit`
  was rewritten to 2 round trips (a lock, then one statement combining the
  clock read, this caller's prune, the count, and a conditional insert via
  CTEs), with the unconditional global cleanup sweep now sampled
  (`RATE_LIMIT_SWEEP_SAMPLE_RATE = 0.02`) instead of run on every call, since
  it has no per-request correctness role.
- Measured directly against live afterward: **~750-800ms average per call**,
  down from an estimated ~1.4-1.5s — real, but a smaller win than the naive
  "6 trips to 2 trips should mean ~3x faster" arithmetic predicted.
- Splitting the two round trips apart to see why surfaced something separate
  and unexplained: back-to-back statements on the same connection showed an
  alternating ~180ms / ~360ms pattern rather than two uniform ~190ms trips —
  consistent with a Nagle's-algorithm/delayed-ACK interaction somewhere on the
  path to the transaction pooler, though this was not confirmed. This is not
  specific to rate limiting; it plausibly also explains an earlier, separately
  logged finding of ~1.4s for a single-row project fetch (~7 round trips'
  worth of latency for work that should need one or two). Left as an open
  question rather than chased further here — out of scope for what this
  addendum measures, and worth its own investigation if it matters later.

**The decision stands.** Postgres remains the shared rate-limit store; no new
service was added. `test_rate_limit_is_atomic_across_postgres_instances` (the
load-bearing correctness test — 20 concurrent requests across 2 store
instances, limit 5, asserting exactly 5 succeed) passed against the rewrite,
run 8 times back-to-back with no flakiness, plus new tests pinning the sliding
window's exact boundary behaviour, expiry, the sweep's sampling in both
directions, and the round-trip count itself (`backend/tests/test_postgres_parity.py`).
