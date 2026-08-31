# Non-device release preflight — 2026-08-31

## Scope and evidence cutoff

This record covers the checks that can be completed without an Android emulator
or a live Kaggle worker session. The checked-out and live remote revision was
`ed4c1723a4335ca2c55d34aec174da39da8b26b3`; local `main`, `origin/main` and
`git ls-remote origin refs/heads/main` matched before the run.

It does not contain credential values, user data, prompts or private media.

## Executed gates

### FastAPI

Run from `backend/` with the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

Observed result:

- dependency consistency: no broken requirements;
- Ruff check: passed;
- Ruff format: 72 files already formatted;
- tests: **546 passed, 55 skipped** in 61.18 seconds. The skips are the
  repository's Postgres-only profile, not hidden failures.

### Android source/build gate

Run from the repository root with Android Studio's JDK 17:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug `
  :app:assembleRelease :app:compileDebugAndroidTestKotlin --no-daemon
```

Observed result:

- Gradle: **BUILD SUCCESSFUL**;
- JVM tests: **123 tests, 0 failures, 0 errors, 0 skipped** across 20 reports;
- Android lint: **0 errors, 5 warnings**;
- debug APK and unsigned release APK assembled;
- debug Android-test Kotlin compiled. Instrumented tests were not executed
  because this preflight deliberately excluded the emulator.

Artifact inventory:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `app/build/outputs/apk/debug/app-debug.apk` | 27,636,325 | `497D1072742EA248D829ECC170A2ECF15531DAD7340BE868B72C12E9603FAA0A` |
| `app/build/outputs/apk/release/app-release-unsigned.apk` | 2,993,267 | `EED69FB72D85598FB1DB0D0CF3E63E12E61DC9147818109BC81A4B5250D0E698` |

The release artifact is unsigned and is not a store-ready release. The debug
APK is the current installable classroom/demo artifact.

### Hosted CI

GitHub Actions run
[`33366381890`](https://github.com/S0ra1n0/Cretona/actions/runs/33366381890)
completed successfully for the exact `ed4c172` revision. Its Android/JVM 17,
FastAPI/Python 3.12 and FastAPI/PostgreSQL 17 parity jobs all passed.

## Live integration readiness

- The existing read-only Supabase record still proves migration 014 and its
  least-privilege worker contracts at the 2026-08-31 evidence cutoff. It was
  not reapplied during this preflight.
- The private Kaggle notebook
  `bruce335/cretona-wan2-1` opened successfully in the authenticated browser,
  but **Add-ons → Secrets showed “No secrets added”**. No secret name or value
  was created, read or transmitted by this audit.
- The local Docker engine was unavailable and no local `psql` client was
  installed, so the current `bootstrap.sql` plus seed was not re-executed from
  an empty database. Historical bootstrap evidence and the current hosted
  Postgres parity suite remain separate evidence; S-18's fresh-install rerun is
  still open.

## Open acceptance gates

1. Add and enable the five named Kaggle Secrets without exposing their values.
2. Run one text-only, 4-second Wan2.1 job through the worker and record its
   project ID, timestamps, progress, Storage object and MP4 metadata.
3. On an emulator/device, verify the queued/generating/completed journey and
   signed-video playback, then run the screenshot pass.
4. Bruce and S0ra1n0 score the four blind EXP-005 clips independently and lock
   the result.
5. Record the one-take demo and assemble the report/submission package only
   after the live evidence above exists.

Until those gates pass, the accurate release statement is **source/build/CI
green; live Kaggle-to-Android acceptance and human deliverables pending**.
