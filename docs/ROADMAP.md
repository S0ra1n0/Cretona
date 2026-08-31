# Cretona — current delivery roadmap

- **Last reconciled:** 2026-08-31
- **Deadline:** 2026-09-05 (2026-09-06 is buffer only)
- **Team:** Bruce — Android/admin UI · S0ra1n0 — FastAPI/database/Kaggle worker
- **Detailed tickets:** [TASK-SPLIT-2026-08-28.md](TASK-SPLIT-2026-08-28.md)
- **Evidence baseline:** `ed4c1723a4335ca2c55d34aec174da39da8b26b3`
- **Hosted CI:** [run 33366381890](https://github.com/S0ra1n0/Cretona/actions/runs/33366381890)
  passed Android/JVM 17, FastAPI/Python 3.12 and FastAPI/PostgreSQL 17 parity
- **Fresh local gate:** [non-device preflight](evidence/NON_DEVICE_PREFLIGHT_2026-08-31.md)

This is the progress source of truth. Requirements remain in `SRS.md`, wire
formats in `API_CONTRACT.md`, and schema rules in `DATA_MODEL.md`.

## 1. Product and architecture

Cretona is a native Kotlin/Jetpack Compose Android app backed by FastAPI.
Supabase supplies Auth, Postgres and Storage in the deployment profile; SQLite,
development identity and the fake provider support credential-free local tests.

The AI responsibilities are deliberately separate:

- prompt enhancement uses a text LLM through FastAPI; the configured local
  model is `qwen3:4b-instruct-2507-q4_K_M`, with a labelled deterministic
  fallback when Ollama is unavailable;
- video generation is provider-neutral in Android and FastAPI;
- `fake` is deterministic test/demo output;
- `real` and `local` are image-plus-motion placeholders, not evidence of a
  generative video model;
- `kaggle` is an external-provider queue with a source-complete Wan2.1 worker;
  migration 014 is live and security-verified, while worker authentication and
  the first live Android-to-playback run remain unproven.

## 2. Audited status

| Area | Implemented | Observed evidence | Remaining boundary |
|---|---|---|---|
| FastAPI API, auth, ownership, quotas, admin | Complete in source | Fresh 2026-08-31 gate: 546 passed / 55 Postgres-only skipped on SQLite, Ruff and `pip check` clean; 601 passed / 0 skipped on disposable PostgreSQL 17 in hosted CI | Live deployment and real-client acceptance remain separate |
| Credits, payments, events and refund ledger | Complete in SQLite/Postgres adapters; migration `013` and seed exist | Current 601-test PostgreSQL run covers charge, per-attempt refund and worker failure parity; migration 013 has historical live probes | Live state is not re-verified by the disposable database |
| Android user journeys | B-01 through B-07 source-complete; real repositories are bound | Final full gate: 123 unit tests, lint, debug/release APK and instrumentation-test compile passed | Record emulator journeys and screenshots |
| Android admin console | B-08 through B-13 source-complete against real endpoints | Included in the final compile/test/lint gate | Emulator acceptance, light/dark screenshots and live-endpoint walkthrough |
| Prompt LLM | Qwen/Ollama adapter plus explicit fallback implemented | Historical live FastAPI evidence selected Qwen; not re-run in this audit | Re-run with `usedFallback=false` before the demo if Ollama is part of the demo |
| Free generative video | Wan2.1 T2V 1.3B two-phase Kaggle notebook proven to generate | 4/4 distinct 832×480, 81-frame clips; mean 48.6 min/clip on 2×T4 | Blind quality scorecard is empty; no quality pass may be claimed |
| Real video in the app | External `kaggle` provider, least-privilege worker, lease heartbeat, Storage upload and atomic completion/refund exist in source | Worker tests, disposable-Postgres parity, live migration 014, a password-set database role and exactly one marked Auth worker | Configure/validate the five Kaggle Secrets, then complete S-14 real result and Android playback |

## 3. Bruce lane

| Ticket | Current source status |
|---|---|
| B-01 camera capture | Source complete |
| B-02 credit contracts and repository seam | Source complete; real repository now bound |
| B-03 Credits screen | Source complete |
| B-04 simulated purchase flow | Source complete; retry key is stable |
| B-05 real credit balance/cost on Home | Source complete |
| B-06 402 routing | Source complete; remains distinct from 429 quota |
| B-07 text, image and text+image contract modes | Source complete; unsupported image providers fail honestly |
| B-08 Manage navigation | Source complete; dashboard list replaces a wide tab row |
| B-09 admin videos | Source complete |
| B-10 user events | Source complete |
| B-11 admin credits/transactions | Source complete |
| B-12 admin events/packages/settings | Source complete |
| B-13 dashboard credit/revenue/event tiles | Source complete |
| B-14 screenshot pass | Fail-fast portable script complete; current emulator screenshots still pending |
| B-16 integration defects | Source audit complete; fixed per-attempt refunds, Kaggle read/state ownership, provider duration limits and retry validation. Device/live defects remain evidence-driven |
| B-17 demo video | Blocked on S-14 real clip |
| B-18 report/screenshots | Pending B-14/B-17 |

“Source complete” does not mean device-accepted. B-14 and B-16 own that last
proof so the same UI work is not reimplemented under a new ticket.

## 4. S0ra1n0 lane

The API/database work through S-16 is present. The remaining critical path is:

1. **S-13:** worker source, live migration 014 and both identity records are
   present. Configure/validate their five Kaggle Secrets, and start the worker.
2. **S-14:** submit one text job from Android, let the worker complete it, and
   play the returned real MP4 in Android. Capture IDs, timestamps and media
   metadata as evidence.
3. **S-17:** the non-device evidence and canonical docs are reconciled. Append
   the live worker result and locked blind score when those runs exist.
4. **S-18:** verify the current bootstrap plus seed from an empty disposable
   Supabase-compatible database, then assemble the secret-free report and
   submission package after B-14/B-17.

S-12 image-conditioned model research is now **stretch scope**, not a release
gate. The lecturer gave no model or image-conditioning mandate. The app/API may
keep all three input modes, but a provider that cannot honor an image must keep
returning `PROVIDER_ERROR`; it must never silently ignore the image.

## 5. Wan2.1 decision boundary

The committed Kaggle experiment proves feasibility, not selection quality:

- model: `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` at the pinned revision in the
  experiment manifest;
- host: free Kaggle, 2× NVIDIA T4, about 31.3 GiB RAM;
- working method: encode prompts on CPU, free the text encoder, then load the
  transformer/VAE on GPU using cached prompt embeddings;
- full result: 4 distinct 5.06-second clips at 832×480 and 16 fps;
- cost: about 48.6 minutes per full clip, with about 12.45 GiB peak VRAM and
  29.13 GiB peak RAM;
- received: all four blind MP4s were copied into the ignored run directory and
  receiver-verified by SHA-256 plus H.264 metadata on 2026-08-31;
- unresolved: Bruce and S0ra1n0 must score the blind clips independently in
  `experiments/EXP-005/QUALITY_SCORECARD.md` before calling output quality
  acceptable.

For the first end-to-end demo, text-to-video is the shortest valid path. Do not
spend the delivery window adding a second video model unless the worker path is
already proven and the scorecard shows Wan2.1 is unacceptable.

## 6. Current verification and blockers

Verified through 2026-08-31:

- backend SQLite profile: 546 passed and 55 intentionally skipped;
- backend disposable-Postgres profile: all 601 passed; the only first-run
  failure was a missing `USAGE` grant in the local Storage test stub, fixed in
  the owning fixture before the clean full rerun;
- backend Ruff check/format and `pip check` are clean; PowerShell screenshot
  script syntax is valid;
- Android final gate was rerun on 2026-08-31: 123 tests, 0
  failures/errors/skips; lint 0 errors and 5 dependency/target warnings;
  debug/release assembly and debug-android-test compilation passed;
- dependency workflow uses least privilege, immutable action SHAs and verified
  Gradle wrapper/distribution checksums;
- hosted CI run 33366381890 passed all Android, SQLite-backend and
  PostgreSQL-parity jobs for evidence baseline `ed4c172`;
- the live Supabase gate ran with `transaction_read_only=on` against PostgreSQL
  17.6: migrations 006-014 are present, the worker role has no superuser,
  database, role, bypass-RLS, replication, membership or direct table power,
  and all worker functions and lease-scoped Storage policies passed;
- live `video_projects.progress_percent` is `int4`, not migration 009's
  `smallint`; its constraint remains present and application values are bounded,
  so this is recorded drift rather than a blocker;
- the four received EXP-005 clips match the ledger digests and each parses as
  H.264 832x480, 81 frames, 5.06 seconds at 16 fps;
- tracked secret-pattern scan found only the deliberate service-role placeholder
  in `backend/.env.example`, not a plaintext credential.

Not run or not accepted in this audit:

- the database role has a password and exactly one Auth user has protected
  `cretona_worker=true` metadata, but the authenticated notebook showed **No
  secrets added** on 2026-08-31; its five Kaggle Secrets and actual
  authentication therefore remain open;
- the current bootstrap plus seed was not re-executed from an empty database in
  this gate because Docker/Postgres was unavailable locally; historical
  bootstrap evidence and hosted adapter parity do not close that S-18 rerun;
- the Kaggle worker was not run with live credentials, so no app-submitted job
  has completed through the new worker path;
- emulator and live Supabase acceptance still require a current run.

## 7. Definition of done

- [x] Eight required business tables exist in migration/bootstrap source.
- [x] User credits, events, purchase, charge and refund paths are implemented.
- [x] Admin user, project, credits, events, packages, settings and dashboard
      paths are implemented.
- [x] Final backend SQLite gate is green at the evidence baseline.
- [x] Final Postgres gate is green at the evidence baseline.
- [x] Final Android source/build gate is green at the evidence baseline.
- [x] Hosted CI is green at the evidence baseline.
- [x] Live Supabase migration 014 passes its read-only security verification.
- [ ] Required emulator journeys are green at the delivered revision.
- [ ] A Wan2.1 Kaggle job submitted through FastAPI completes and its real video
      plays in Android.
- [ ] Blind quality scorecard has both reviewers' entries and a recorded decision.
- [ ] Current screenshots, demo video, report, sample accounts and submission
      package are complete and secret-free.
