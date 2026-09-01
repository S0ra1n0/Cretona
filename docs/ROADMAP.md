# Cretona — current delivery roadmap

- **Last reconciled:** 2026-09-02
- **Deadline:** 2026-09-05 (2026-09-06 is buffer only)
- **Team:** Bruce — Android/admin UI · S0ra1n0 — FastAPI/database/Kaggle worker
- **Detailed tickets:** [TASK-SPLIT-2026-08-28.md](TASK-SPLIT-2026-08-28.md)
- **Evidence baseline:** `ed4c1723a4335ca2c55d34aec174da39da8b26b3`
- **S-13 worker revision:** `73666f023d2e618b02401f62c6afe4df13513595`
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
  migration 014 is live and security-verified, and the private Kaggle worker
  has passed Auth plus an empty-queue PostgreSQL claim smoke. A generated
  Android-to-playback run remains unproven.

## 2. Audited status

| Area | Implemented | Observed evidence | Remaining boundary |
|---|---|---|---|
| FastAPI API, auth, ownership, quotas, admin | Complete in source | Fresh 2026-08-31 gate: 546 passed / 55 Postgres-only skipped on SQLite, Ruff and `pip check` clean; 601 passed / 0 skipped on disposable PostgreSQL 17 in hosted CI | Live deployment and real-client acceptance remain separate |
| Credits, payments, events and refund ledger | Complete in SQLite/Postgres adapters; migration `013` and seed exist | Current 601-test PostgreSQL run covers charge, per-attempt refund and worker failure parity; migration 013 has historical live probes | Live state is not re-verified by the disposable database |
| Android user journeys | B-01 through B-07 source-complete; real repositories are bound | Final full gate: 123 unit tests, lint, debug/release APK and instrumentation-test compile passed | Record emulator journeys and screenshots |
| Android admin console | B-08 through B-13 source-complete against real endpoints | Included in the final compile/test/lint gate | Emulator acceptance, light/dark screenshots and live-endpoint walkthrough |
| Prompt LLM | Qwen/Ollama adapter plus explicit fallback implemented | Historical live FastAPI evidence selected Qwen; not re-run in this audit | Re-run with `usedFallback=false` before the demo if Ollama is part of the demo |
| Free generative video | Wan2.1 T2V 1.3B two-phase Kaggle notebook proven to generate | 4/4 distinct 832×480, 81-frame clips; mean 48.6 min/clip on 2×T4 | Blind quality scorecard is empty; no quality pass may be claimed |
| Real video in the app | External `kaggle` provider, least-privilege worker, lease heartbeat, Storage upload and atomic completion/refund exist in source | **S-14 generation accepted 2026-09-01:** an Android-submitted job completed through the worker; the MP4 is in Storage and parses as avc1 832x480, 65 frames, 4.06 s. See [S14_FIRST_LIVE_CLIP_2026-09-01.md](evidence/S14_FIRST_LIVE_CLIP_2026-09-01.md) | **Playback accepted 2026-09-01.** Remaining: the worker writes no thumbnail, so the gallery card reads "Preview unavailable" |

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
| B-14 screenshot pass | Two real defects fixed: `2>&1` made adb's stderr fatal on PowerShell 5.1 even at exit 0, and a fixed 2 s wait captured the previous screen. Both user and admin sets now capture. **Open:** the `-IncludeAdmin` step still fails its own guard — the node it finds has the same bounds a manual tap succeeds at, so the cause is inside the script's navigation, not the coordinates. The admin console shot is captured by hand until that is found |
| B-16 integration defects | Source audit complete; fixed per-attempt refunds, Kaggle read/state ownership, provider duration limits and retry validation. Device/live defects remain evidence-driven |
| B-17 demo video | Unblocked — the S-14 clip exists. Record after B-14 reshoots the app in its completed state |
| B-18 report/screenshots | Pending B-14/B-17 |

“Source complete” does not mean device-accepted. B-14 and B-16 own that last
proof so the same UI work is not reimplemented under a new ticket.

## 4. S0ra1n0 lane

The API/database work through S-16 is present. The remaining critical path is:

1. **S-13:** complete. Five Kaggle Secrets are enabled; the revision-bound
   worker passed Supabase Auth and the empty PostgreSQL claim path live.
2. **S-14:** generation is **accepted**. Job `4ad038f6…` was submitted from
   Android on 2026-09-01, completed by the worker at 14:11 UTC, and its MP4 is
   in Storage — IDs, timestamps and media metadata are captured in
   [S14_FIRST_LIVE_CLIP_2026-09-01.md](evidence/S14_FIRST_LIVE_CLIP_2026-09-01.md).
   What remains is opening that project in Android and watching the signed URL
   play through Media3; nothing else in the chain is unproven.
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
- **reviewed 2026-09-02, abbreviated:** subject and setting adhere to both
  prompts and the two seeds per prompt differ, but **direction and camera motion
  are ignored in all four clips** — the dragon flies right-to-left when the
  prompt says left-to-right (both seeds), the forward dolly and the rightward
  orbit never happen, and B1/B2 travel in opposite directions. Judged adequate
  for the demo on that basis, with one constraint: **demo prompts must not
  depend on a direction or a camera move.** No numeric score was taken, so the
  honest status is demo-adequate, quality unverified.

For the first end-to-end demo, text-to-video is the shortest valid path. Do not
spend the delivery window adding a second video model unless the worker path is
already proven and the scorecard shows Wan2.1 is unacceptable.

## 6. Current verification and blockers

Verified through 2026-09-01:

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
- the private Kaggle notebook has exactly five enabled worker secrets; the
  revision-bound worker obtained a Supabase Auth session, reached the live
  PostgreSQL claim function with an empty queue and exited 0 without loading a
  model. See `evidence/KAGGLE_WORKER_S13_2026-09-01.md`;
- tracked secret-pattern scan found only the deliberate service-role placeholder
  in `backend/.env.example`, not a plaintext credential.

Not run or not accepted in this audit:

- the current bootstrap plus seed was not re-executed from an empty database in
  this gate because Docker/Postgres was unavailable locally; historical
  bootstrap evidence and hosted adapter parity do not close that S-18 rerun;
- the 2026-09-01 connectivity smoke had an empty queue and loaded no model, but
  a **later** run on the same day completed a real app-submitted job:
  `4ad038f6-081d-4e81-894a-01301391ed36`, `completed` at 14:11 UTC, MP4 in the
  private `videos` bucket at the canonical path, charged once with no refund and
  no ledger drift. The `_test/screenshots/cretona-s14-*.png` pair was captured at
  13:38 while it was still `pending`, so those images predate the result rather
  than contradict it. Detail:
  [S14_FIRST_LIVE_CLIP_2026-09-01.md](evidence/S14_FIRST_LIVE_CLIP_2026-09-01.md);
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
- [x] Five Kaggle Secrets and the live Auth/empty-queue claim smoke pass.
- [~] Emulator journeys: the four signed-in user screens (Home, History,
      Credits, Profile) were captured live on the `Pixel_10_Pro` emulator
      against the Supabase profile on 2026-09-02 —
      `_test/screenshots/journeys/`. Credits shows real ledger data
      (`Welcome bonus +5`, `Video generated -1`). The admin set is in
      `_test/screenshots/journeys-admin/`, captured as `admin@cretona.test`
      and including the console (`Overview`: 6 users, 10 projects, 30% failure
      rate, providers FAKE 3 / CLOUD 6 / KAGGLE 1).
      **`live_screen_05_admin.png` was captured by hand**, not by the script —
      see the B-14 row.
- [x] A Wan2.1 Kaggle job submitted through FastAPI completes and its real video
      reaches Storage (`4ad038f6…`, 2026-09-01, verified by container parse).
- [x] That completed project is opened in Android and the signed MP4 plays.
      Observed on the Pixel_10_Pro emulator, 2026-09-01 11:36: the clip plays at
      0:01 of 0:04 and its content matches the prompt.
      `_test/screenshots/s14-playback.png`.
- [x] Output quality has a **recorded decision**. The two-reviewer blind
      protocol was deliberately descoped on 2026-09-02 — the brief sets no
      quality threshold — and replaced by a single-reviewer non-blind review
      in `experiments/EXP-005/QUALITY_SCORECARD.md`. Outcome:
      **demo-adequate, quality unverified.**
- [ ] Current screenshots, demo video, report, sample accounts and submission
      package are complete and secret-free.
