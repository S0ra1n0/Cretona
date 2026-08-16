# Cretona

Cretona is a Mobile 1 project by Bruce and S0ra1n0 for creating short AI
videos from text and, after the text path is proven, an optional reference
image.

## Current integration status

S0ra1n0's remote implementation establishes a root Android project using
Kotlin, Jetpack Compose, MVVM, Retrofit, and a provider-neutral project/job
contract. It also contains an Express/Prisma/Supabase backend implementation
with authentication, quota, storage, a fake provider, and a tested polling job
runner.

The instructor requirement recorded by Bruce is that model calls go through
FastAPI. Therefore the Express backend is valuable migration evidence and its
behavior/tests must be preserved, but Express is not the final active backend
technology. The migration must retain the provider-neutral contract, security
rules, state transitions, idempotency, and deterministic fake provider before
any local video model is integrated.

No paid provider call is enabled by the accepted zero-additional-spend path.
Local Qwen3-4B has passed a real FastAPI call. No real video model is selected:
LTX-Video 2B was rejected by the pinned host-envelope pre-screen, and the
installed FramePack F1 runtime is blocked before inference by resource and
weight-license gates in `EXP-005`.

## Repository layout

```text
Cretona/             open this folder in Android Studio
├── app/             Android application (Kotlin + Jetpack Compose)
├── backend/         Production FastAPI backend (port 8000, Supabase Postgres & Auth)
├── docs/            Requirements, contracts, decisions, ADRs, and evidence
├── scripts/         Repeatable toolchain and local-runtime entry points
├── supabase/        Database migrations and bootstrap artifacts
└── gradle/          Android version catalog and wrapper
```

## Documentation

- Start with [docs/README.md](docs/README.md) for the teammate implementation.
- See [docs/DECISIONS.md](docs/DECISIONS.md) for reconciled team decisions.
- See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for credential boundaries.
- See [docs/evidence/ANDROID_FASTAPI_E2E.md](docs/evidence/ANDROID_FASTAPI_E2E.md)
  for the verified emulator-to-video vertical slice and its evidence limits.
- See [docs/discovery/FREE-LOCAL-BEST-OUTPUT.md](docs/discovery/FREE-LOCAL-BEST-OUTPUT.md)
  for the evidence-gated local model strategy.

The Android client may know only the stable Cretona API. Provider credentials,
raw provider payloads, and billable retry decisions remain server-side.
