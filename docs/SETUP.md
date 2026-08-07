# Development Setup

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Android Studio | Otter / 2025.2+ | Must support AGP 9.2 |
| JDK | 17+ | Android Studio's bundled JBR is used automatically |
| Android SDK Platform | **API 37** | Required by AndroidX 1.19 / lifecycle 2.11 |
| Node.js | 20 LTS | backend, Phase 2 |
| Supabase account | — | free tier is enough for development |

Verify the SDK platform is installed: **Settings → Languages & Frameworks → Android SDK → SDK Platforms → Android API 37**.

---

## 2. Android

### 2.1 Open the project
Open the repository root (`Cretona/`) in Android Studio — **not** the `app/` folder. The root is the Gradle project; `backend/` and `docs/` sit alongside it and are ignored by Gradle sync.

### 2.2 Configure `local.properties`
`local.properties` is per-machine and git-ignored. Android Studio creates it with `sdk.dir` on first sync; add the rest:

```properties
sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk

# Backend base URL. 10.0.2.2 is the host machine as seen from the emulator.
# Use your LAN IP instead when running on a physical device.
cretona.api.baseUrl.debug=http\://10.0.2.2\:3000/api/v1/
cretona.api.baseUrl.release=https\://api.cretona.app/api/v1/

# Supabase project settings → API
supabase.url=https\://<project-ref>.supabase.co
supabase.anonKey=<anon-public-key>
```

These are surfaced to Kotlin as `BuildConfig.API_BASE_URL`, `BuildConfig.SUPABASE_URL`, and `BuildConfig.SUPABASE_ANON_KEY`. Missing values fall back to empty strings, so the app builds before Supabase exists.

> **Only the anon key belongs here.** The `service_role` key and every AI provider key live in backend environment variables and must never appear in an Android build. See [SECURITY.md](SECURITY.md).

### 2.3 Build and run

Sync Gradle, then **Run ▶** with an emulator on API 26+.

From the command line:

```bash
./gradlew :app:assembleDebug
```

```bash
./gradlew :app:testDebugUnitTest
```

```bash
./gradlew :app:lintDebug
```

> On Windows the system `java` may be an old JRE. If a CLI build fails with a Java version error, point `JAVA_HOME` at Android Studio's bundled runtime — `C:\Program Files\Android\Android Studio\jbr` — for that shell. Android Studio itself always uses the correct one.

### 2.4 Build configuration

| | debug | release |
|---|---|---|
| Application id | `com.cretona.app.debug` | `com.cretona.app` |
| Minify / shrink | off | R8 on |
| HTTP logging | full bodies, `Authorization` redacted | off |

The debug suffix means debug and release builds install side by side.

---

## 3. Supabase

1. Create a project at [supabase.com](https://supabase.com); note the region.
2. **Settings → API**: copy the project URL and the `anon` key into `local.properties`; copy the `service_role` key into the backend `.env` **only**.
3. **Settings → Database**: copy the pooled connection string (`DATABASE_URL`) and the direct one (`DIRECT_URL`, used for migrations).
4. Apply the schema from [DATA_MODEL.md](DATA_MODEL.md) — tables, enum, trigger, indexes, RLS policies.
5. Create the private `uploads` and `videos` buckets (DATA_MODEL §5).
6. **Authentication → Providers**: enable Email. Disable email confirmation while developing so test accounts work immediately; re-enable before release.

---

## 4. Backend

*Not yet implemented — Phase 2 of the roadmap.* When it lands, `backend/.env` follows `backend/.env.example`:

```bash
NODE_ENV=development
PORT=3000

DATABASE_URL=postgresql://…       # pooled
DIRECT_URL=postgresql://…         # direct, migrations only

SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=…       # server only, never in the app
SUPABASE_JWT_SECRET=…

DEFAULT_AI_PROVIDER=runway
RUNWAY_API_KEY=…

GENERATION_QUOTA_LIMIT=10
GENERATION_QUOTA_WINDOW=P1D
```

`.env` is git-ignored; `.env.example` is committed and must list every key with a placeholder.

---

## 5. Emulator Networking

| Running on | `cretona.api.baseUrl.debug` |
|---|---|
| Emulator, backend on the same machine | `http://10.0.2.2:3000/api/v1/` |
| Physical device on the same Wi-Fi | `http://<your-LAN-ip>:3000/api/v1/` |
| Remote staging | `https://staging-api.cretona.app/api/v1/` |

Android blocks cleartext HTTP by default. If you switch the debug base URL to a LAN IP, add it to a debug-only network security config rather than enabling cleartext app-wide.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `P1001 Can't reach database server at aws-0-REGION.pooler…` | The placeholder in `.env.example` was copied literally. Get the real string from **Connect → ORMs → Prisma**; the hostname is not predictable |
| `P1001` with a real-looking hostname | Special character in the database password is not URL-encoded (`@` → `%40`). This fails identically to a network problem |
| `prisma migrate` hangs or errors on advisory locks | `DIRECT_URL` points at the transaction pooler (6543). It must be the session pooler (5432) |
| `P4002 Cross schema references are only allowed…` from `prisma db pull` | Expected — `users.id` references `auth.users`. Introspection is not used on this project; run `supabase/drift_check.sql` instead. `prisma generate` and runtime are unaffected |
| `requires ... compile against version 37 or later` | API 37 platform not installed — install it in SDK Manager |
| `The 'org.jetbrains.kotlin.android' plugin is no longer required` | AGP 9 has built-in Kotlin support; don't re-add the plugin |
| `SUPABASE_URL` empty on the Home screen | `local.properties` not filled in, or Gradle not re-synced after editing it |
| Hilt "cannot find symbol" after adding an `@Inject` | Run `./gradlew :app:kspDebugKotlin` or Build → Clean Project |
| Emulator can't reach the backend | Use `10.0.2.2`, not `localhost`; confirm the backend binds `0.0.0.0` |
