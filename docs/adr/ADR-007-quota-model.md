# ADR-007: Per-user rolling daily generation quota, enforced server-side

**Status:** Accepted (limit value provisional) · **Date:** 2026-08-06 · **Roadmap:** P0-6

## Context

Every generation costs real money at the provider. Without a cap, one user in a retry loop — or one script with a stolen token — can exhaust the project budget in minutes. Rate limiting alone does not solve this: 5 requests per minute is still thousands of paid generations per day.

There is no payment system in the MVP, so quota is purely a cost-control mechanism, not a product tier.

## Decision

A **rolling-window per-user quota**, counted in the database and checked before any provider call.

- Config: `GENERATION_QUOTA_LIMIT` (default **10**) over `GENERATION_QUOTA_WINDOW` (default **P1D**).
- Counted by `COUNT(*) FROM video_projects WHERE user_id = ? AND created_at > now() - window`, excluding projects that failed with `provider_error` or `timeout`.
- Enforced in the service layer *before* submission; exceeded returns `429 QUOTA_EXCEEDED`.
- Retry (FR-2.11) consumes quota, since it is a real provider call.
- Remaining quota is returned by `GET /me` so the app can show it before the user writes a prompt (FR-5.2).
- Admins are subject to the same quota. Bypassing it is not needed and would make the limit untested in practice.

Rate limiting stays as a separate, independent control ([API_CONTRACT.md §5](../API_CONTRACT.md)) — it protects against bursts, quota protects the budget.

## Rationale

- A rolling window avoids the midnight stampede a fixed calendar reset creates, and cannot be gamed by submitting on both sides of a boundary.
- Counting rows rather than maintaining a counter column means there is no counter to drift out of sync, and no reconciliation job. At MVP volume the query is trivially indexed by `(user_id, created_at DESC)`.
- Not charging for our own infrastructure failures matters: if a provider 500s, the user did not receive a video and should not lose an allowance. Charging for `content_policy` rejections is deliberate, though — the provider call was made and billed.
- Checking before submission is the only placement that actually prevents spend. Checking after is accounting, not control.

## Consequences

- The limit of 10/day is a **provisional number** and must be revised once real per-generation cost is known (blocked on [ADR-004](ADR-004-launch-provider.md)). It is config, not code, so changing it is a redeploy at most.
- `GET /me` returns a `quota` object; the app surfaces `remaining` and disables submit at zero, with the server as the real gate.
- Excluding infrastructure failures means the count query has a condition on `status` and `error_message`, so the failure taxonomy in [AI_PROVIDER_SPEC.md](../AI_PROVIDER_SPEC.md) is load-bearing — it must be recorded per project, not just logged.
- `Idempotency-Key` on submit prevents a network retry from consuming two allowances.
- Provider-side spend caps remain configured as an independent backstop. Two layers, because this one lives in our code and our code can have bugs.
- When paid tiers arrive, `limit` moves from global config to a per-user column. The check site does not change.
