# Cretona

Cretona is a Mobile 1 project by Bruce and S0ra1n0 for creating short AI
videos from text and, after the text path is proven, an optional reference
image.

The current technical baseline is `b4bf348`. GitHub Actions
[run 33598905267](https://github.com/S0ra1n0/Cretona/actions/runs/33598905267)
builds and tests Android, exercises FastAPI against SQLite and PostgreSQL 17,
replays the complete Supabase bootstrap plus migrations 002–015 from empty,
audits Python dependencies, and scans the release APK for server-only
credential markers. Live Supabase migration 015 and the matching private
Kaggle worker bundle have also passed their guarded verification and
empty-queue smoke.

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
is pinned Wan2.1 T2V 1.3B on free Kaggle compute. Four experiment clips were
generated and reviewed as demo-adequate, with direction and camera-motion
limitations recorded. A real Android-submitted job completed through the live
worker, reached private Storage, and played in Android on 2026-09-01.

Migration 015 requires every worker completion to upload both `video.mp4` and
`thumbnail.jpg`. A post-migration job completed on 2026-09-02 with both
objects in private Storage, so the thumbnail path is proven end to end. Every
engineering item is closed; what remains is the live demonstrations and the
human deliverables — the demo recording (B-17) and report/submission package
(B-18).

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
- Use [docs/KAGGLE_WORKER_RUNBOOK.md](docs/KAGGLE_WORKER_RUNBOOK.md) for a
  post-MIG-015 worker-to-Android acceptance run.
- See [docs/DECISIONS.md](docs/DECISIONS.md) for reconciled team decisions.
- See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for credential boundaries.
- See [docs/evidence/ANDROID_FASTAPI_E2E.md](docs/evidence/ANDROID_FASTAPI_E2E.md)
  for the verified emulator-to-video vertical slice and its evidence limits.
- See [docs/evidence/NON_DEVICE_PREFLIGHT_2026-08-31.md](docs/evidence/NON_DEVICE_PREFLIGHT_2026-08-31.md)
  for the earlier non-device release gate.
- See [docs/evidence/MIG015_FIRST_THUMBNAIL_JOB_2026-09-02.md](docs/evidence/MIG015_FIRST_THUMBNAIL_JOB_2026-09-02.md)
  for the accepted post-MIG-015 job, thumbnail included.
- See [docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md) for the live-run
  checklist used at the 09-03 and 09-05 sessions.
- See [docs/evidence/LIVE_SUPABASE_MIGRATION_015_2026-09-02.md](docs/evidence/LIVE_SUPABASE_MIGRATION_015_2026-09-02.md)
  for the current live migration and worker-bundle smoke boundary.
- See [docs/discovery/FREE-LOCAL-BEST-OUTPUT.md](docs/discovery/FREE-LOCAL-BEST-OUTPUT.md)
  for the evidence-gated local model strategy.

The Android client may know only the stable Cretona API. Provider credentials,
raw provider payloads, and billable retry decisions remain server-side.
