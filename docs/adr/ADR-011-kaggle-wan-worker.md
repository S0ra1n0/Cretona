# ADR-011: Use Kaggle as the external Wan2.1 worker

**Status:** Accepted · **Date:** 2026-08-30 · **Supersedes:** ADR-009 for the
selected real text-to-video path

## Context

Cretona needs real AI video without additional cash spend, while the Android
client must call the stable FastAPI contract rather than a model directly. The
laptop does not have the memory envelope for the selected temporal model. The
committed EXP-005 run proved that pinned Wan2.1 T2V 1.3B can generate four
distinct MP4 clips on free Kaggle 2×T4 compute with a two-phase prompt-encoding
and generation profile. Kaggle notebooks cannot accept inbound application
traffic and are not always-on services.

## Decision

The `kaggle` provider is an external, text-only provider for 2–5 second videos.
FastAPI validates and queues the project in Supabase Postgres. A private Kaggle
notebook runs `backend/kaggle_worker.py`, claims work through four
`SECURITY DEFINER` functions using a dedicated no-inherit login role, renews a
lease during generation, uploads the canonical MP4 through a separate Supabase
Auth worker, and atomically completes or fails/refunds the project. Neither
credential is a Supabase `service_role` key. Android sees only the stable
Cretona API and provider alias.

`fake` remains the credential-free integration/default demo provider. Wan2.1
does not accept a reference image; the API must refuse image-conditioned
requests instead of silently ignoring the image. Paid providers remain opt-in
and require a separate budget decision.

## Consequences

- The real-video path preserves the selected zero-additional-spend baseline and
  the lecturer's FastAPI boundary.
- A Kaggle session and remaining weekly GPU quota are operational prerequisites;
  the path is not an always-on production service.
- The proven full profile takes about 49 minutes per five-second clip, so the
  in-process FastAPI timeout must never own Kaggle job state.
- Migration 014, two worker identities and Kaggle Secrets add setup work, but
  keep table access and media writes least-privileged.
- Source and disposable-Postgres tests prove contracts, not live Supabase
  application, Kaggle execution, Android playback or output quality. Those
  remain explicit release-acceptance gates.
- A future local or image-conditioned provider still requires its own measured
  EXP-005 evidence; this ADR does not claim either capability.
