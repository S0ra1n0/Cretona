# Cretona Backend

Not implemented yet — this is **Phase 2** of [the roadmap](../Cretona_Roadmap.md).

The design is already settled, so start from the documents rather than from scratch:

| | |
|---|---|
| Endpoints, error envelope, pagination | [docs/API_CONTRACT.md](../docs/API_CONTRACT.md) |
| Schema, constraints, RLS, storage buckets | [docs/DATA_MODEL.md](../docs/DATA_MODEL.md) |
| Folder layout, request pipeline, job runner | [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §4 |
| Provider interface and failure taxonomy | [docs/AI_PROVIDER_SPEC.md](../docs/AI_PROVIDER_SPEC.md) |
| Environment variables | [docs/SETUP.md](../docs/SETUP.md) §4 |

Stack: Node.js 20 · Express · TypeScript · Prisma · Supabase Postgres.

This folder is invisible to Gradle — `settings.gradle.kts` does not include it — so it has no effect on Android Studio sync.
