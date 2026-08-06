# ADR-001: Monorepo with the Android project at the repository root

**Status:** Accepted · **Date:** 2026-08-06 · **Roadmap:** P0-1

## Context

Cretona has two deployable pieces — an Android app and an Express backend — plus a documentation set. They share one API contract and one data model, and during MVP they will change together on nearly every feature.

The developer works in Android Studio and expects to open the checkout and hit Run. Android Studio treats the folder it opens as the Gradle project root; if the Gradle build lives in a subfolder, opening the repository root gives a broken or non-Android project view.

Options considered:

1. **Two repositories** — `cretona-android`, `cretona-backend`.
2. **Monorepo, both nested** — `/android`, `/backend`; open `/android` in Studio.
3. **Monorepo, Android at root** — Gradle build at the top, `/backend` and `/docs` alongside.

## Decision

Option 3. The repository root is the Android Gradle project. The backend lives in `backend/`, documentation in `docs/`.

## Rationale

- A contract change touching the API, the backend, and the app lands as one commit and one review. With two repos the same change is two PRs that can merge out of order.
- Opening `Cretona/` in Android Studio just works — no "open the subfolder" step, which is the daily-friction cost of option 2 for the person actually building this.
- Gradle only sees what `settings.gradle.kts` includes, so `backend/` and `docs/` are inert during sync. Studio indexes them as plain files, which is convenient for editing docs in place.
- One issue tracker, one CI config, one version history for a system whose parts are meaningless apart.

## Consequences

- CI must filter by path so an Android-only change doesn't run backend tests and vice versa.
- `.gitignore` covers both ecosystems (`node_modules/`, `.gradle/`, `local.properties`, `.env`).
- Cloning pulls both stacks even if you only need one. Acceptable at this size.
- If the backend is ever extracted, `git filter-repo` on `backend/` preserves its history. Reversible.
- Adding Android modules later (`:core`, `:feature:*`) is unaffected — they are siblings of `app/`.
