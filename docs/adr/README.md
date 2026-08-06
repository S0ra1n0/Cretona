# Architecture Decision Records

Each ADR captures one decision, why it was made, and what it costs us. They are immutable once accepted — a decision that changes gets a new ADR that supersedes the old one, rather than an edit that erases the reasoning.

| ADR | Decision | Status | Roadmap |
|---|---|---|---|
| [001](ADR-001-repo-layout.md) | Monorepo with the Android project at the repository root | Accepted | P0-1 |
| [002](ADR-002-auth-strategy.md) | App authenticates directly with Supabase Auth; backend verifies the JWT | Accepted | — |
| [003](ADR-003-async-strategy.md) | Server-side polling for completion; webhooks deferred | Accepted | P0-5 |
| [004](ADR-004-launch-provider.md) | Runway as launch provider, Kling second | Accepted (checklist outstanding) | P0-2 |
| [005](ADR-005-secrets-management.md) | Secrets never reach the device; `local.properties` for per-machine config | Accepted | P0-3 |
| [006](ADR-006-environments.md) | Two deployed environments, three app configurations | Accepted | P0-4 |
| [007](ADR-007-quota-model.md) | Per-user rolling daily generation quota | Accepted (limit provisional) | P0-6 |

## Status values

- **Proposed** — written down, not yet agreed. Do not build on it.
- **Accepted** — in force. Code should match it; if it doesn't, one of the two is wrong.
- **Superseded by ADR-NNN** — kept for the reasoning, no longer in force.

## Writing a new one

Copy the shape of an existing record: context (the forces, and the options actually considered), decision (one sentence, unambiguous), rationale (why this one won), consequences (including what it costs — an ADR with no downsides listed is an advert, not a decision record).
