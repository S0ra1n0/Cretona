# ADR-006: Two deployed environments, three app build configurations

**Status:** Accepted · **Date:** 2026-08-06 · **Roadmap:** P0-4

## Context

Generations cost money, so testing against production data and a production provider account is not acceptable. But a solo/small team maintaining three full stacks is overhead that buys little. The Android side also needs to point at different backends without editing source.

## Decision

**Two deployed environments:**

| | Supabase project | Backend | Provider account |
|---|---|---|---|
| **staging** | separate project | staging deployment | separate key, low spend cap |
| **production** | separate project | production deployment | production key, spend cap |

Local development runs the backend on `localhost:3000` against the **staging** Supabase project. There is no third Supabase project for local work.

**Three Android configurations**, from build type plus `local.properties`:

| Points at | Build | `cretona.api.baseUrl.*` |
|---|---|---|
| Local backend | debug | `http://10.0.2.2:3000/api/v1/` |
| Staging | debug | `https://staging-api.cretona.app/api/v1/` |
| Production | release | `https://api.cretona.app/api/v1/` |

Debug builds carry `applicationIdSuffix = ".debug"` so they install alongside a release build.

## Rationale

- Separate Supabase projects are the only clean boundary. Sharing one project across environments means one bad migration or one careless delete touches real user data.
- Local development sharing staging's database avoids a third project to migrate and seed on every schema change. The risk is bounded because staging holds no real user data by definition.
- Switching environments through `local.properties` rather than product flavors keeps the Gradle build simple — flavors multiply every variant and task, and the only thing that actually differs here is a URL.
- Separate provider keys per environment mean staging spend is visible separately and a runaway test loop can't exhaust the production budget.

## Consequences

- Migrations run against staging first, always. Production migrations happen only after staging is verified.
- Staging data is disposable and may be wiped; nothing may depend on it persisting.
- Because local and staging share a database, a developer running a destructive script affects the shared staging environment. Acceptable at this team size; the mitigation is that staging is disposable.
- Switching an app build between local and staging is a `local.properties` edit plus a Gradle sync, not a rebuild of a different variant.
- A third "local" Supabase project remains an option if the shared-staging friction becomes real. Adding one later costs a migration run, nothing more.
