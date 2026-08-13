# Architecture Decision Records

Each ADR captures one decision, why it was made, and what it costs us. They are immutable once accepted — a decision that changes gets a new ADR that supersedes the old one, rather than an edit that erases the reasoning.

| ADR | Decision | Status | Roadmap |
|---|---|---|---|
| [001](ADR-001-repo-layout.md) | Monorepo with the Android project at the repository root | Accepted | P0-1 |
| [002](ADR-002-auth-strategy.md) | App authenticates directly with Supabase Auth; backend verifies the JWT | Accepted | — |
| [003](ADR-003-async-strategy.md) | Server-side polling for completion; webhooks deferred | Accepted | P0-5 |
| [004](ADR-004-launch-provider.md) | Runway as launch provider, Kling second | Superseded by ADR-009 | P0-2 |
| [005](ADR-005-secrets-management.md) | Secrets never reach the device; `local.properties` for per-machine config | Accepted | P0-3 |
| [006](ADR-006-environments.md) | Two deployed environments, three app configurations | Accepted; local backend/port superseded by ADR-008 | P0-4 |
| [007](ADR-007-quota-model.md) | Per-user rolling daily generation quota | Accepted (limit provisional) | P0-6 |
| [008](ADR-008-fastapi-migration.md) | FastAPI is the active backend; Express remains a tested migration reference until parity | Accepted | P0-7 |
| [009](ADR-009-zero-spend-provider-gate.md) | Keep fake integration evidence and select a real local video model only through EXP-005 | Accepted | P0-2 |
| [010](ADR-010-shared-rate-limit-store.md) | Postgres-backed shared rate-limit windows; in-memory fallback for SQLite | Accepted | B-3 |

## Status values

- **Proposed** — written down, not yet agreed. Do not build on it.
- **Accepted** — in force. Code should match it; if it doesn't, one of the two is wrong.
- **Superseded by ADR-NNN** — kept for the reasoning, no longer in force.

## Writing a new one

Copy the shape of an existing record: context (the forces, and the options actually considered), decision (one sentence, unambiguous), rationale (why this one won), consequences (including what it costs — an ADR with no downsides listed is an advert, not a decision record).
