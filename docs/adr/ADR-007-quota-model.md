# ADR-007: Per-user rolling daily generation quota, enforced server-side

**Status:** Accepted · **Date:** 2026-08-06 · **Amended:** 2026-09-03 · **Roadmap:** P0-6

## Context

Without a cap, one user in a retry loop — or one script with a stolen token —
can exhaust a limited shared resource in minutes. Rate limiting alone does not
solve this: 5 requests per minute is still thousands of generations per day.

## Amendment, 2026-09-03: both premises changed, the decision did not

This ADR was written on 2026-08-06 and its Context said two things that are no
longer true. Both are corrected here rather than quietly left standing, because
a control defended by an obsolete reason invites the question of whether anyone
still knows why it exists.

**"Every generation costs real money at the provider."** It no longer does.
The accepted path is Wan2.1 on free Kaggle compute, at zero additional spend
(`DEC-013`). What a generation costs now is roughly 20 minutes of a **shared
free-tier GPU allowance** — about 30 hours a week for the whole team. Ten jobs
a day is around 3.3 hours of that. The resource being protected changed from
money to GPU time; the need for a cap did not.

**"There is no payment system in the MVP."** There is one now. S-05 added
credits, purchasable packages and event grants. That makes the relationship
between the two limits worth stating explicitly, because they are easy to
mistake for duplicates:

| | Credits | Quota |
|---|---|---|
| Kind of rule | Product | Safety rail |
| Required by | The course brief, §2.1 | This ADR |
| Runs out | Buy more, or claim an event | **Wait for the window to slide** |
| Can be bought past | Yes | **No** |

That last row is the whole point. Quota is the control that a compromised
token cannot purchase its way around. Credits measure entitlement; quota bounds
blast radius. Removing quota because credits exist would delete the only limit
that holds when an attacker has a funded account.

At current settings — `generation_cost_credits = 1`, a 5-credit signup bonus,
quota 10 per 24 hours — **credits bind first for a new account**. Quota only
becomes the binding constraint once a user holds more than ten credits, which
is exactly the case it was written for.

## Decision

A **rolling-window per-user quota**, counted in the database and checked before any provider call.

- Config: `GENERATION_QUOTA_LIMIT` (default **10**) over `GENERATION_QUOTA_WINDOW` (default **P1D**).
- Counted by `COUNT(*) FROM video_projects WHERE user_id = ? AND created_at > now() - window`, excluding projects that failed with `provider_error` or `timeout`.
- Enforced in the service layer *before* submission; exceeded returns `429 QUOTA_EXCEEDED`.
- Retry (FR-2.11) consumes quota, since it is a real provider call.
- Remaining quota is returned by `GET /me` so the app can show it before the user writes a prompt (FR-5.2).
- Admins are subject to the same quota. Bypassing it is not needed and would make the limit untested in practice.

Rate limiting stays as a separate, independent control ([API_CONTRACT.md §5](../API_CONTRACT.md)) — it protects against bursts, quota bounds sustained consumption.

## Rationale

- A rolling window avoids the midnight stampede a fixed calendar reset creates, and cannot be gamed by submitting on both sides of a boundary.
- Counting rows rather than maintaining a counter column means there is no counter to drift out of sync, and no reconciliation job. At MVP volume the query is trivially indexed by `(user_id, created_at DESC)`.
- Not charging for our own infrastructure failures matters: if a provider 500s, the user did not receive a video and should not lose an allowance. Charging for `content_policy` rejections is deliberate, though — the provider call was made and the work was done.
- Checking before submission is the only placement that actually prevents consumption. Checking after is accounting, not control.

## Consequences

- The limit of 10/day is now anchored to the free Kaggle GPU allowance rather than to a provider price. It is config, not code, so changing it is a restart at most.
- **A weighted provider costs two quota but still one credit.** `WEIGHTED_PROVIDERS` in `project_service.py` charges 2 for `real`, `cloud`, `local` and `wan21`, while `generation_cost_credits` stays at 1. That is deliberate — the heavier tiers consume more of the resource quota exists to protect — but it was undocumented until this amendment, and the asymmetry surprises anyone reading either mechanism alone.
- `GET /me` returns a `quota` object; the app surfaces `remaining` and disables submit at zero, with the server as the real gate.
- Excluding infrastructure failures means the count query has a condition on `status` and `error_message`, so the failure taxonomy in [AI_PROVIDER_SPEC.md](../AI_PROVIDER_SPEC.md) is load-bearing — it must be recorded per project, not just logged.
- `Idempotency-Key` on submit prevents a network retry from consuming two allowances.
- Provider-side spend caps remain configured as an independent backstop. Two layers, because this one lives in our code and our code can have bugs.
- When paid tiers arrive, `limit` moves from global config to a per-user column. The check site does not change.
