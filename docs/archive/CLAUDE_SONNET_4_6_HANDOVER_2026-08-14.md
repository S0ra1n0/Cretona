# Cretona handover to Claude Sonnet 4.6

> Start here before changing code, configuration, Supabase, local AI runtimes,
> or Git history. This is a durable receiver brief, not proof that the receiver
> has verified or accepted the system.

## 1. Transfer contract

| Field | Value |
|---|---|
| Project | Cretona — Mobile 1 course project for Plus26 |
| Repository | `https://github.com/S0ra1n0/Cretona` |
| Canonical local root | `D:\1. UMT\3.5. PLUS26\Cretona` |
| Operational code/data baseline | `9ff8ff967203707f6c6cfbdfed814766247f1803` on `main` |
| Baseline remote proof | local `HEAD`, `origin/main`, and live `refs/heads/main` matched the hash above on 2026-08-14 |
| Sender/integrator | Codex working for Bruce |
| Receiving agent | Claude Sonnet 4.6 |
| Product/acceptance authority | Bruce |
| Other developer/reviewer | S0ra1n0 (review must not be claimed without evidence) |
| Transfer date | 2026-08-14, Asia/Saigon |
| Transfer state | `delivered`; not yet `receiver-verified` or `accepted` |
| Handover artifact revision | Resolve with `git log -1 --format=%H -- docs/CLAUDE_SONNET_4_6_HANDOVER_2026-08-14.md`; a commit cannot embed its own final hash |
| Refresh trigger | Any new commit, live environment change, provider/model decision, credential rotation, or course rubric/deadline update |

Bruce and S0ra1n0 are a two-developer team. This file transfers durable working
context to another coding agent; it does **not** transfer external account
access, approve live writes, accept deliverables on Bruce's behalf, or authorize
paid model calls.

## 2. First instructions for Claude

1. Read this file completely.
2. From the repository root, run read-only orientation commands first:

   ```powershell
   rtk git status --short --branch
   rtk git pull --rebase origin main
   rtk git log -8 --oneline
   ```

3. Confirm the handover file's commit is on `origin/main` and that the worktree
   is clean. Preserve any unexpected local changes as user-owned work.
4. Do **not** reapply Supabase migrations 006 or 007. They are already live and
   independently verified.
5. Do **not** print, paste, summarize, or commit values from `env`,
   `local.properties`, any `.env`, a database URL, JWT secret, service-role key,
   browser session, or backup dump.
6. Before the next implementation, give Bruce a bounded task proposal with:
   objective, source requirement/backlog ID, files, live effects, verification,
   rollback/cleanup, and the exact authority needed.
7. Safe read-only inspection and local tests may proceed. Any live data write,
   account/object creation, deployment, paid API call, model-weight download,
   pagefile/system change, or access transfer needs explicit Bruce approval.

If your observed state conflicts with this file, stop and report the exact
source, revision, and mismatch. Current repository/live evidence outranks this
derived handover view.

## 3. Product DNA and authoritative truth

Cretona is an Android app that creates a short video from text and, only after
the text path is proven, an optional reference image. The instructor's only
known technical requirement is that model calls pass through **FastAPI**. The
instructor mentioned familiar LLM products such as ChatGPT and Gemini, but did
not require a specific provider, paid product, or model.

The accepted product boundary is:

- Android knows only the stable Cretona REST contract;
- FastAPI owns prompt/model orchestration, provider secrets, quotas, rate
  limits, normalized job state, and safe error mapping;
- Supabase is the intended Auth/Postgres/Storage platform behind FastAPI;
- the deterministic fake provider proves orchestration and UI, not AI quality;
- Qwen3-4B through Ollama is a proven prompt LLM, not a video generator;
- no real video model/provider is accepted yet.

When sources disagree, use this priority from [`docs/README.md`](README.md):

1. [`API_CONTRACT.md`](API_CONTRACT.md) for wire format;
2. [`DATA_MODEL.md`](DATA_MODEL.md) for schema/RLS/storage data contracts;
3. [`SRS.md`](SRS.md) for required behavior;
4. [`docs/adr/`](adr/README.md) for rationale and accepted trade-offs;
5. implemented code plus executed evidence for observed reality.

Keep desired, designed, implemented, and observed truth separate. A green local
test is not live runtime proof, and live schema proof is not FastAPI deployment
proof.

## 4. Current architecture

### Demonstrated local profile

```text
Android (Kotlin/Compose/MVVM)
  -> FastAPI on host port 8000
     -> SQLite
     -> deterministic prompt enhancer or local Ollama/Qwen3-4B
     -> fake video provider returning bundled H.264/AAC MP4
```

This profile is credential-free, repeatable, and already demonstrated on an
Android emulator. It uses development identity injection and must never be
presented as a production auth profile.

### Target/live-integration profile

```text
Android -> Supabase Auth -> JWT -> FastAPI
FastAPI -> live Supabase PostgreSQL
FastAPI -> private Supabase Storage buckets
FastAPI -> provider-neutral prompt/video adapters
```

The live database schema is ready through migration 007. The FastAPI process
has **not** been started or smoke-tested against live Supabase Auth/Postgres/
Storage. That is the most important remaining integration boundary.

`backend-fastapi/` is active. `backend/` is the tested Express/Prisma reference
and behavioral oracle. Do not rename/delete/archive either folder until live
FastAPI runtime parity passes and both developers approve ADR-008's revisit.

## 5. Delivered and demonstrated state

| Area | State | Evidence / qualification |
|---|---|---|
| Android text generation journey | `demonstrated` | prompt → create → poll → playback → history recorded in [`ANDROID_FASTAPI_E2E.md`](evidence/ANDROID_FASTAPI_E2E.md) |
| Android quota surface B-8 | `demonstrated` | consumes `/me`, prevents exhausted submit, refreshes after create; 12 Android tests plus lint/assembly and AVD image |
| Android thumbnails B-9 | `demonstrated` | Coil loads `thumbnailUrl`, preserves API `aspectRatio`, and falls back safely; AVD evidence |
| FastAPI local profile | `demonstrated` | current standard run: `241 passed, 20 skipped`; canonical Ruff invocation passed |
| FastAPI Postgres parity | `demonstrated` on disposable DB | PostgreSQL 16.14 run: `261 passed, 0 skipped`; migration 007 applied twice; see [`B3_POSTGRES_VERIFICATION.md`](evidence/B3_POSTGRES_VERIFICATION.md) |
| Express reference | `delivered` | historical 77 tests, typecheck, and build; migration oracle only |
| Prompt LLM | `demonstrated` | local Ollama/Qwen3-4B returned `usedFallback=false` through FastAPI |
| Real video generation | `blocked/unselected` | fake MP4 only; no real video output may be claimed |
| Live Supabase schema | `demonstrated` | PostgreSQL 17.6; migrations 004–007 present; 006/007 applied at baseline commit; see live migration evidence |
| Live FastAPI + Supabase runtime | `not demonstrated` | no configured `backend-fastapi/.env`, startup, real JWT journey, Storage write, or application smoke evidence |
| Public backend deployment | `not delivered` | no hosting/CD environment is established |
| CI/CD | `not delivered` | no repository workflow files were observed |
| Course acceptance | `not accepted` | deadline, submission artifacts, presentation date, and exact rubric remain unknown |

## 6. Live Supabase state — do not redo it

The authoritative report is
[`LIVE_SUPABASE_MIGRATIONS_006_007_2026-08-14.md`](evidence/LIVE_SUPABASE_MIGRATIONS_006_007_2026-08-14.md).

Observed final state:

- project is a Free-plan production Supabase project;
- Bruce is an Administrator;
- PostgreSQL is `17.6`;
- migrations 004 and 005 were already present at preflight;
- MIG-006 created `idx_logs_retention` on `(created_at, id)`;
- MIG-007 created backend-only `public.rate_limit_hits` with two secondary
  indexes, constraints, and RLS;
- all relevant indexes were `valid`, `ready`, and `live`;
- `rate_limit_hits` intentionally has zero client policies;
- effective table/sequence privileges for `anon`, `authenticated`, and
  `service_role` all verified false (30 checks);
- `supabase_migrations.schema_migrations` is absent, so earlier migration
  provenance is incomplete;
- the SQL files retain historical `PREPARED, NOT APPLIED` headers to preserve
  their exact execution hashes. Current live status is in README/evidence, not
  those immutable comments.

MIG-006 and MIG-007 were executed only after a protected logical export. The
backup lives outside Git in a sibling `Cretona-backups` directory. It contains
roles/schema/data and Storage metadata, but **not Storage object bytes**. Its
hashes are in the evidence report. No restore drill has been performed. Treat
the dump as sensitive operational data and never open/copy it into chat or Git.

Supabase Advisors after DDL returned 19 findings: zero `ERROR`, seven `WARN`,
and twelve `INFO`.

- six performance warnings: pre-existing RLS policies re-evaluate auth helpers;
- one security warning: pre-existing mutable search path on `set_updated_at`;
- info: one unindexed foreign key, unused indexes, and two RLS/no-policy tables;
- the `rate_limit_hits` RLS/no-policy info is intentional because the table is
  direct-Postgres-only and effective Data API privileges are false;
- new unused indexes are expected before the corresponding live worker runs;
  an advisor finding is not authorization to drop them.

Do not silently fix these findings during another task. Triage each in a
separate reviewed change with query-plan/security evidence.

## 7. Credential and access inventory

Only metadata belongs in this handover. Secret values are deliberately absent.

| System/artifact | Owner/role | Local state | Transfer status |
|---|---|---|---|
| GitHub repository | S0ra1n0 remote; Bruce can push through current Git credential flow | `origin/main` synchronized at baseline | Existing machine access only; no credential transferred here |
| Supabase project | Bruce observed as Administrator | root ignored `env` contains live project/database material | Access exists for Bruce; receiver must not reveal or redistribute it |
| Android config | teammate-provided root `local.properties` | present and ignored | machine-local; may contain another developer's SDK path/public anon config |
| Active FastAPI config | `backend-fastapi/.env` | **absent** at transfer time | must be created from `.env.example` only with Bruce's explicit live-smoke authorization |
| Express config | `backend/.env` | absent | reference backend does not need live access for this handover |
| Logical DB backup | Bruce/operator | protected sibling directory outside Git | sensitive; available for recovery planning, not receiver-verified restore |
| Ollama/Qwen runtime | Bruce's laptop | local runtime/model previously proven | optional prompt path; check presence before assuming it is running |
| FramePack runtime/weights | Bruce's laptop | pinned machine-local runtime and snapshots | inference remains blocked by resource/license gates |
| Paid provider accounts | none authorized for this baseline | no active adapter/key should be assumed | paid activation requires a new budget/provider decision |

Never enable `CRETONA_TEST_DATABASE_ALLOW_REMOTE=1` against the live database.
The Postgres test fixture drops/recreates tables and is only for a disposable
local database.

## 8. Recommended next task

### Objective

Prove the pinned FastAPI revision against live Supabase Auth/Postgres/Storage
without changing the mobile contract or enabling a real/paid video provider.
This is MIG-007 operation OP-03 followed by a bounded observation window, not a
new schema migration.

### Before any live write

Claude should first produce a short execution contract for Bruce covering:

- exact commit and environment profile;
- presence-only credential checks and mapping from the ignored root `env` to an
  ignored `backend-fastapi/.env` (never print values);
- QA identities/objects to create and how they will be recognized;
- endpoints and expected status/error contracts;
- cleanup for QA database rows and Storage objects;
- log/redaction checks;
- stop/rollback thresholds;
- whether the test uses existing accounts or creates disposable QA accounts;
- explicit Bruce authorization for the proposed Auth/data/Storage effects.

Do not copy the whole root `env` mechanically. The active FastAPI loader accepts
only the documented `CRETONA_*` keys in `backend-fastapi/.env.example`.

### Minimum smoke ladder after authorization

1. Pin `HEAD`; run local Ruff/Pytest and the read-only `verify-007` gate.
2. Create the ignored `backend-fastapi/.env` with:
   `AUTH_MODE=supabase`, `DATABASE_BACKEND=postgres`,
   `STORAGE_BACKEND=supabase`, and `DEFAULT_VIDEO_PROVIDER=fake`; supply only
   the required secret values through the ignored file.
3. Start FastAPI locally and confirm startup schema checks and `GET /health`.
4. Use a real Supabase JWT for a dedicated QA user; verify `GET /me`.
5. Execute one bounded fake-provider text project: create → poll → completed →
   list/detail, preserving quota/idempotency/error contracts.
6. Verify signed/private Storage behavior using only dedicated QA objects.
7. With a second QA identity, prove cross-user project access returns the
   contract result and does not leak existence.
8. If an admin QA identity is explicitly authorized, verify the minimum admin
   read/authorization boundary without modifying a real user.
9. Inspect redacted logs for tokens, keys, signed URLs, and prompt leakage.
10. Delete every QA row/object created by the smoke exercise and verify cleanup.
11. Record non-secret evidence, update OP-03/OP-04 status, commit, pull/rebase,
    push, and verify the live remote hash.

Stop immediately on project-identity mismatch, startup schema drift, unexpected
existing data, privilege exposure, unredacted secret material, an inability to
identify/clean QA artifacts, elevated 5xx, incorrect quota/rate behavior, or
missing Bruce authorization.

### After the live runtime gate

- Only then reconsider B-15 (rename/archive the two backend folders).
- B-12 bucket-backed thumbnails is a concrete user-visible follow-up.
- Admin UI B-10, observability B-5/B-6/B-7, image input, and release work remain
  separate tasks.
- Real video work returns to EXP-005/model selection only after respecting the
  resource/license gates below.

## 9. Real AI/video lane

Current provider truth:

| Component | Status | Rule |
|---|---|---|
| Qwen3-4B via Ollama | proven prompt enhancer | `usedFallback=false` proves the real text LLM answered; it does not create video |
| FakeVideoProvider | integrated | deterministic integration fixture only; label output synthetic |
| LTX-Video 2B Q8 | rejected on current host envelope | do not download/run unless new pinned Ampere evidence reverses the recorded gate |
| FramePack F1 | installed, inference blocked | resource preflight and downloaded-weight license review must pass first |
| Wan2.1 1.3B / CogVideoX 2B | research candidates only | neither is an accepted adapter |
| Runway/Kling/Veo/OpenAI video | not selected/paid | requires current pricing/region/API verification, budget approval, and a new ADR/decision |

Before any FramePack process, run both repository-owned checks:

```powershell
rtk powershell -ExecutionPolicy Bypass -File .\scripts\check-toolchain.ps1
rtk powershell -ExecutionPolicy Bypass -File .\scripts\check-exp005-preflight.ps1 -Profile framepack
```

The second check currently fails by design on the measured 16 GB RAM / RTX
3070 Ti Laptop 8 GB host. Do not run FramePack's bundled `update.bat`; its
failure path can execute `git reset --hard`. Do not change the Windows pagefile
or download more weights without explicit Bruce approval. Canonical sources:

- [`ADR-009`](adr/ADR-009-zero-spend-provider-gate.md)
- [`EXP-005 README`](experiments/EXP-005/README.md)
- [`MODEL_RUNTIME_MANIFEST.json`](experiments/EXP-005/MODEL_RUNTIME_MANIFEST.json)
- [`FREE-LOCAL-BEST-OUTPUT.md`](discovery/FREE-LOCAL-BEST-OUTPUT.md)

## 10. Repository map

| Path | Purpose / authority |
|---|---|
| `app/` | active Android Kotlin/Compose client |
| `backend-fastapi/` | active course backend and provider boundary |
| `backend/` | executable Express/Prisma migration oracle; preserve |
| `supabase/` | bootstrap and numbered live schema migrations |
| `scripts/` | repeatable toolchain, runtime, backup, advisor, and migration gates |
| `docs/API_CONTRACT.md` | canonical HTTP contract |
| `docs/DATA_MODEL.md` | canonical database/RLS/storage model |
| `docs/SRS.md` | canonical product behavior; some stack prose predates FastAPI ADR |
| `docs/DECISIONS.md`, `docs/adr/` | accepted decisions and rationale |
| `docs/BACKLOG.md` | newest post-parity implementation status and proposed follow-ups |
| `docs/evidence/` | executed evidence and its limitations |
| `docs/experiments/EXP-005/` | local video feasibility contract, manifest, and evidence |
| `Cretona_Roadmap.md` | stable historical task IDs, but its top status/Phase 1 claims are stale |

## 11. Canonical commands

Run from the repository root unless stated otherwise. Repository instructions
require the `rtk` prefix for shell commands.

### Toolchain

```powershell
rtk powershell -ExecutionPolicy Bypass -File .\scripts\check-toolchain.ps1
```

### FastAPI local verification

```powershell
Set-Location backend-fastapi
rtk .\.venv\Scripts\python.exe -m ruff check .
rtk .\.venv\Scripts\python.exe -m pytest
Set-Location ..
```

The ordinary credential-free run currently skips the 20 Postgres-gated tests.
Never point those tests at live Supabase.

### Android gates

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
rtk .\gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug --no-daemon
```

### Read-only live schema/security check

```powershell
rtk backend-fastapi/.venv/Scripts/python.exe scripts/live-supabase-migration-gate.py verify-007
```

This reads the ignored root `env`, validates project identity, opens a read-only
transaction, and emits metadata only. Do not use `apply-006` or `apply-007`.

### Supabase Advisors

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-live-supabase-advisors.ps1
```

### Protected logical backup

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup-live-supabase.ps1
```

This needs Docker Desktop and writes outside Git. Do not create another backup
or open existing dumps merely for orientation; do so only as part of an
authorized recovery/migration task.

## 12. Git and collaboration contract

- Two developers share `main`; do not assume cached `origin/main` is live.
- Pull/rebase before work when safe and **again immediately before push**.
- Complete one bounded task per commit. Match history with a concise
  conventional subject plus a descriptive body and verification paragraph.
- Stage explicit paths; never sweep in `env`, `local.properties`, `.env`, model
  weights, generated media, backup files, caches, or unrelated user changes.
- Preserve teammate changes and executable reference implementations.
- After push, require all three hashes to match:

  ```powershell
  rtk git rev-parse HEAD
  rtk git rev-parse origin/main
  rtk git ls-remote origin refs/heads/main
  ```

- A Git credential/sandbox error is not remote verification.
- Clean temporary QA processes/containers/artifacts before declaring done.
- Do not use `git reset --hard`, destructive checkout, or broad recursive
  deletion unless Bruce explicitly requested the exact operation.

Recent baseline commits:

```text
9ff8ff9 ops(db): apply live migrations 006 and 007
1e4786e docs: record live Supabase preflight
4463cd5 docs: record B-3 Postgres verification
101e16d feat(api): share rate limits through Postgres (B-3)
a0efe34 feat(android): render history thumbnails (B-9)
76f8c9d feat(android): show generation quota from me (B-8)
1027871 feat(api): enforce generation log retention (B-4)
```

## 13. Known documentation drift

Do not erase old evidence; classify it by snapshot date. At transfer time:

- `docs/BACKLOG.md` is the newest post-parity view and was reconciled with the
  live migration evidence.
- `Cretona_Roadmap.md` still says nothing has run against live Supabase,
  migration 006 is unapplied, and P1-1 is not done. Those statements are stale
  after commit `9ff8ff9`; the roadmap still has useful stable task IDs.
- the last paragraph of `docs/CONFIGURATION.md` says Supabase credentials are
  unexercised. Live schema access has now been exercised, but the important
  application claim remains true: active FastAPI Auth/Postgres/Storage has not
  been smoke-tested live.
- `docs/SRS.md` contains early Node/Express stack language. ADR-008 and the
  instructor constraint make FastAPI the active backend; SRS requirement IDs
  remain behavior authority.
- `docs/SECURITY.md` remains a draft checklist. RLS/catalog metadata is proven,
  but real two-user JWT/IDOR/admin/APK/log checks are not complete; do not check
  them off based only on schema evidence.
- migrations 004–007 retain pre-execution header comments to preserve hashes;
  use the live evidence and Supabase README for current state.

Reconcile stale views in the same commit as the future change that makes their
current truth relevant. Do not rewrite historical evidence to look newer.

## 14. Risks, blockers, and non-goals

### Material residual risks

- no live FastAPI runtime parity evidence;
- no real video-generation model/output;
- no Supabase restore drill and no Storage object-byte backup;
- Free plan lacks platform project backups;
- missing Supabase CLI migration-history table;
- no source-backed evidence that S0ra1n0 reviewed MIG-007; Bruce explicitly
  accepted that residual risk for execution, but review is not claimed;
- Supabase Advisor warnings remain untriaged;
- no CI/CD, public backend deployment, production TLS endpoint, release signing
  evidence, crash reporting, or observability pipeline;
- course deadline/rubric/submission format remain unknown.

### MVP non-goals unless Bruce changes scope

Payments/subscriptions, social feed, in-app editing, multilingual UI, web
client, offline generation queue, Redis-scale rate limiting, and paid provider
activation.

## 15. Receiver verification and acceptance checklist

Claude may update this section in a later evidence commit, but must not mark
Bruce's acceptance or S0ra1n0's review on their behalf.

- [ ] Receiver confirmed handover commit on live `origin/main`.
- [ ] Receiver confirmed clean worktree and repository root.
- [ ] Receiver read API, data model, SRS, ADR-008, ADR-009, backlog, and both
      live Supabase evidence reports.
- [ ] Receiver ran toolchain preflight.
- [ ] Receiver ran canonical FastAPI Ruff/Pytest.
- [ ] Receiver ran Android tests/lint/assembly or recorded why unavailable.
- [ ] Receiver ran read-only `verify-007` without exposing credentials.
- [ ] Receiver summarized the next bounded task and authority envelope to
      Bruce before any live write.
- [ ] Access gaps, environment gaps, and contradictions were recorded without
      copying secrets.
- [ ] Bruce explicitly accepted the next task or requested changes.

## 16. What success looks like for the next receiver turn

The first Claude response should not say merely “I understand.” It should
report:

1. observed branch/HEAD/remote/worktree state;
2. which canonical sources were read;
3. a short four-layer truth summary: desired, designed, implemented, observed;
4. the exact next task it recommends (normally live FastAPI-to-Supabase smoke);
5. files/environments affected;
6. authority needed before live effects;
7. verification, cleanup, rollback, and stop conditions;
8. unresolved contradictions or questions for Bruce.

Until Claude executes the checklist, this handover is `delivered`, not
`receiver-verified`. Until Bruce accepts it, it is not `accepted`.
