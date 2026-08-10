# ADR-008: Migrate the active backend contract to FastAPI

**Status:** Accepted · **Date:** 2026-08-10 · **Roadmap:** P0-7

This ADR supersedes ADR-006 only for the local backend technology and port. Its
debug/release separation and deployed-environment principles remain in force.

## Context

The upstream repository contains a substantial Express, Prisma, and Supabase
backend with 77 passing tests. The instructor separately requires FastAPI to
make the application's model calls. Replacing the tested implementation in
place before the new runtime reaches parity would erase useful evidence and
make regressions hard to attribute.

The Android app already depends on the versioned HTTP contract rather than on
Express-specific types. That contract, the provider boundary, canonical job
states, idempotency behavior, ownership rule, and safe error envelope are the
assets to preserve. The web framework is replaceable.

## Decision

`backend-fastapi/` is the active migration target and listens on port 8000.
`backend/` remains an unchanged, tested Express reference until the FastAPI
vertical slice passes its own tests and an Android-to-video end-to-end check.

The first FastAPI profile is deliberately deterministic and zero-spend:

- SQLite persistence for a repeatable local demo;
- development identity injection only when `CRETONA_AUTH_MODE=dev`;
- a provider-neutral fake video adapter producing a bundled MP4;
- optional local prompt enhancement through Ollama, with a deterministic
  fallback when no local LLM is running.

This profile does not claim that a real video model has run. LTX-Video and
FramePack remain behind EXP-005. Supabase Auth, Postgres, and Storage remain the
target integration profile and are ported only after the local vertical slice
is stable.

## Invariants preserved during migration

- Android never receives a provider secret.
- Project ownership is checked server-side.
- Status is one of `pending`, `generating`, `completed`, or `failed`.
- Provider failures are mapped to safe user messages; raw payloads are not
  returned.
- `Idempotency-Key` prevents duplicate project creation.
- A provider implementation stays behind one normalized interface.
- Media is playable from a server URL; generated URLs are never treated as
  permanent provider URLs.

## Consequences

- Two backend folders exist temporarily, but their roles are explicit rather
  than competing: FastAPI is active, Express is reference evidence.
- The local demo does not require credentials, network access, or billable
  generation.
- The first persistence implementation is not yet production-concurrent like
  the Express/Postgres `SKIP LOCKED` worker. That behavior remains a parity gate
  before deployment.
- Moving the Express reference to `reference/` or removing it is a later,
  reviewable commit after Soraino confirms the migration.

## Revisit when

FastAPI has Supabase parity and the Android end-to-end flow is recorded. At
that point rename folders so the sole active service is simply `backend/` and
retain the Express commit through Git history or a tagged archive.
