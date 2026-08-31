# Cretona

Cretona is a Mobile 1 project by Bruce and S0ra1n0 for creating short AI
videos from text and, after the text path is proven, an optional reference
image.

Product source through revision `a7b6251` is on local and live `main`. GitHub
Actions [run 33356499355](https://github.com/S0ra1n0/Cretona/actions/runs/33356499355)
passed the Android/JVM 17, FastAPI/Python 3.12 and FastAPI/PostgreSQL 17 jobs.
Live Supabase migration 014 was separately verified read-only on 2026-08-31.
Neither result proves Kaggle worker execution or Android device acceptance.

## Current integration status

The active implementation is an Android app (Kotlin, Jetpack Compose, MVVM,
Hilt, Retrofit/OkHttp and Supabase Auth) calling a FastAPI backend. FastAPI owns
the stable project/job contract, authorization, quota, persistence, storage,
polling, prompt enhancement, and all media/provider orchestration. The Android
client never receives provider credentials or raw model identifiers.

Android authentication uses the Supabase Kotlin SDK with SDK-owned token
rotation and an AES-GCM Android Keystore session store. Startup restores a
valid session before routing; signed-out release builds fail closed instead of
falling back to a development identity.

No paid provider call is enabled by the accepted zero-additional-spend path.
Local Qwen3-4B has passed a real FastAPI call. The selected temporal-video path
is pinned Wan2.1 T2V 1.3B on free Kaggle compute: the experiment generated four
real clips, and the `kaggle` provider, worker and migration are complete in
source. Migration 014 is live and passes its security gate; the database role
has a password and exactly one Auth user is marked as the worker. Configuring
and validating the five Kaggle Secrets, running the worker, playing its result
in Android and scoring output quality are still acceptance steps;
source tests are not evidence that those live steps happened.

## Repository layout

```text
Cretona/             open this folder in Android Studio
|-- app/             Android application (Kotlin + Jetpack Compose)
|-- backend/         Production FastAPI backend (port 8000, Supabase Postgres & Auth)
|-- docs/            Requirements, contracts, decisions, ADRs, and evidence
|-- scripts/         Repeatable toolchain and local-runtime entry points
|-- supabase/        Database migrations and bootstrap artifacts
`-- gradle/          Android version catalog and wrapper
```

## Documentation

- Start with [docs/README.md](docs/README.md) for the teammate implementation.
- Use [docs/ROADMAP.md](docs/ROADMAP.md) as the current handover/status source.
- Use [docs/KAGGLE_WORKER_RUNBOOK.md](docs/KAGGLE_WORKER_RUNBOOK.md) for the
  first live worker-to-Android acceptance run.
- See [docs/DECISIONS.md](docs/DECISIONS.md) for reconciled team decisions.
- See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for credential boundaries.
- See [docs/evidence/ANDROID_FASTAPI_E2E.md](docs/evidence/ANDROID_FASTAPI_E2E.md)
  for the verified emulator-to-video vertical slice and its evidence limits.
- See [docs/discovery/FREE-LOCAL-BEST-OUTPUT.md](docs/discovery/FREE-LOCAL-BEST-OUTPUT.md)
  for the evidence-gated local model strategy.

The Android client may know only the stable Cretona API. Provider credentials,
raw provider payloads, and billable retry decisions remain server-side.
