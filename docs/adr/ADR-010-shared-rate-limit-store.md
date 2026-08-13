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
