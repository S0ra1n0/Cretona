# ADR-004: Launch AI video provider

**Status:** Accepted (verification checklist outstanding) · **Date:** 2026-08-06 · **Roadmap:** P0-2

## Context

The plan lists Runway, Kling, Pika, Luma, and Google Veo as pluggable providers. Building all of them at once would spread effort across five sets of quirks before a single end-to-end path works, so exactly one ships first and the rest arrive behind the interface in [AI_PROVIDER_SPEC.md](../AI_PROVIDER_SPEC.md).

The choice is constrained by things this document cannot verify — current pricing, regional availability, and whether an account can be created without a waitlist or enterprise agreement. Those must be checked at signup time, not assumed here.

Selection criteria, in priority order:

1. **Obtainable** — self-serve API access, no waitlist, available from the developer's region.
2. **Supports all three input modes** — text, image, and text+image. A provider missing image-to-video cannot satisfy FR-2.2/FR-2.3, which would force a second provider into the MVP.
3. **Asynchronous job API** — submit returns a job id, with a status endpoint. Matches ADR-003 directly.
4. **Predictable per-generation cost** with a spend cap in the dashboard.
5. **Documented, stable REST API** — the adapter is a day of work, not a reverse-engineering project.

## Decision

**Runway is the launch provider. Kling is the second (P3-10).**

Runway was chosen because it is the option most likely to satisfy criteria 1–3 together: self-serve API access, all three input modes, and a conventional submit/poll job model. Kling is the second implementation specifically because it is architecturally similar enough to be quick, yet different enough in its request shape and status vocabulary to prove the abstraction actually abstracts.

**The choice is agreed; the facts behind it are not yet verified.** Before writing the adapter (P3-3), confirm against live provider documentation:

- [ ] Self-serve API access without a waitlist, from this region
- [ ] Text-to-video, image-to-video, and text+image all available on the API tier
- [ ] Async submit → job id → status endpoint (not a blocking call)
- [ ] Per-generation price and whether a hard spend cap can be set
- [ ] Result URL expiry (drives the re-hosting deadline in P3-8)
- [ ] Rate limits, to size the poller
- [ ] Content-moderation behaviour and the error shape it returns, for the `content_policy` mapping

If any of the first three fails, switch to the next candidate and update this ADR rather than working around it in the adapter.

## Consequences

- P3-3 implements one adapter; `DEFAULT_AI_PROVIDER` names it in backend config.
- MVP does not expose a provider picker in the app (FR-2.12 is post-MVP). The API already accepts an optional `provider` field so the app needs no change when it arrives.
- `capabilities` values must be filled in from real documentation, since they drive request validation and error messages — a wrong `maxPromptLength` produces a confusing rejection.
- Being wrong here is cheap by construction: a different launch provider is one file plus a config change, which is the entire point of the provider interface.

## Revisit when

The verification checklist fails, pricing changes materially, or a provider offers meaningfully better quality or latency for the same money.
