# ADR-003: Server-side polling for generation completion, webhooks deferred

**Status:** Accepted · **Date:** 2026-08-06 · **Roadmap:** P0-5

## Context

AI video generation takes roughly 30 seconds to several minutes. The backend must learn when a provider job finishes so it can re-host the result and move the project to `completed`.

Options:

1. **Server-side polling** — a worker asks the provider for status on an interval.
2. **Provider webhooks** — the provider calls us when the job finishes.
3. **Client polling only** — the app asks the provider directly. Rejected immediately: it would put provider keys on the device.

## Decision

Server-side polling for MVP. A worker claims due jobs with `SELECT … FOR UPDATE SKIP LOCKED` and polls the provider. Webhook support is designed for but not built (`verifyWebhook` is an optional method on the provider interface, and `POST /webhooks/providers/:provider` is specified in the API contract).

The app separately polls `GET /projects/:id` for UI updates. That is a different concern and stays regardless of which mechanism the backend uses upstream.

## Rationale

- Webhooks require a publicly reachable HTTPS endpoint. During development that means a tunnel, which is one more moving part between "I wrote code" and "I saw a video".
- Each provider signs webhooks differently, so webhook support is per-provider work, whereas `getStatus` is needed anyway — every adapter must implement it for reconciliation after a missed delivery.
- Webhooks are not a reliability win on their own. Deliveries get lost, so a poller is required as a backstop even in a webhook design. Building the poller first means building the part that can't be skipped.
- At MVP volume the extra provider calls are negligible.

## Consequences

- Completion is detected up to one poll interval late. Acceptable against a multi-minute generation.
- Polling frequency backs off: every 10 s for the first two minutes, then every 30 s, until the provider's `timeoutSeconds`.
- Every poll writes a `generation_logs` row, so cost is reconcilable and the retry path is auditable.
- Job state lives entirely in Postgres, so a backend restart resumes cleanly (NFR-3.1) and horizontal scaling is safe via `SKIP LOCKED`.
- A job with no terminal state by its timeout is marked `failed` rather than polled forever (NFR-3.3).
- Adding webhooks later changes only what *triggers* a status check. The transition logic, re-hosting, and failure mapping are shared, so this is additive, not a rewrite.

## Revisit when

Provider polling cost becomes material, generation volume exceeds a few hundred concurrent jobs, or a provider's rate limits make polling impractical. At that point the interval worker also wants replacing with a real queue.
