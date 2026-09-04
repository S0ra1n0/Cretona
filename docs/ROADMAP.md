# Cretona — current delivery roadmap

- **Last reconciled:** 2026-09-04
- **Final demo session:** 2026-09-05 (Saturday) — live, in front of the
  reviewer, same as 2026-09-03.
- **Submission deadline:** 2026-09-09 — source code, report and demo video
  packaged and submitted. This is separate from the 09-05 session: the demo
  is a live checkpoint, not the moment the deliverables are due.
- **Team:** Bruce — Android/admin UI · S0ra1n0 — FastAPI/database/Kaggle worker
- **Detailed tickets:** [TASK-SPLIT-2026-08-28.md](TASK-SPLIT-2026-08-28.md)
- **Latest green technical baseline:** `f6e1657dc5c91f2278b4debdc19e9441b136f6b8`
- **Final-demo worker:** the proven `STEPS = 25` silent-video build, worker
  SHA-256 `decc5f5d…`; full hashes are in section 7. The committed notebook
  pins this artifact and keeps experimental audio disabled.
- **Hosted CI:** [run 33879468605](https://github.com/S0ra1n0/Cretona/actions/runs/33879468605)
  passed Android/JVM 17, FastAPI/Python 3.12 and FastAPI/PostgreSQL 17 parity at
  the hosted-CI baseline
- **Earlier non-device gate:** [preflight](evidence/NON_DEVICE_PREFLIGHT_2026-08-31.md)

This is the progress source of truth. Requirements remain in `SRS.md`, wire
formats in `API_CONTRACT.md`, and schema rules in `DATA_MODEL.md`.

> **Acceptance standard.** A feature counts as delivered when the running system
> does it live — backend up, real accounts, real Supabase, operated in front of
> the reviewer. A green test suite and a folder of screenshots answer "it ran
> once", not "it works if you open it now", and only the second one is the
> deliverable. Every `[x]` below that rests on source tests or captured images
> says so explicitly, and stays distinct from a live acceptance. Script:
> [LIVE_DEMO_RUNBOOK.md](LIVE_DEMO_RUNBOOK.md). Sessions: **2026-09-03**
> progress review, **2026-09-05** final demo. Source code, report and demo
> video are due **2026-09-09**, compiled after the 09-05 session rather than
> on the day of it.

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
- `kaggle` is an external-provider queue with a source-complete Wan2.1 worker.
  Migrations 014 and 015 are both live and security-verified. An
  Android-submitted job has generated a real clip that played in the app
  (S-14, 2026-09-01). Migration 015 then made completion fail closed on a
  missing thumbnail, and a **post-015 job completed with both objects on
  2026-09-02** — see the gallery-thumbnail row in section 2.

## 2. Audited status

| Area | Implemented | Observed evidence | Remaining boundary |
|---|---|---|---|
| FastAPI API, auth, ownership, quotas, admin | Complete in source | Hosted CI 2026-09-04: **626 passed / 0 skipped** on PostgreSQL 17, and 569 passed / 57 Postgres-only skipped on SQLite. Ruff check/format, `pip check` and `pip_audit` clean | Live deployment and real-client acceptance remain separate |
| Credits, payments, events and refund ledger | Complete in SQLite/Postgres adapters; migration `013` and seed exist | The 626-test PostgreSQL run covers charge, per-attempt refund and worker failure parity; migration 013 has historical live probes | Live state is not re-verified by the hosted database |
| Android user journeys | B-01 through B-07 source-complete; real repositories are bound | Gate rerun 2026-09-03 at `8c77b6f`: **129 unit tests**, 0 failures; debug APK built and installed on the `Pixel_10_Pro` emulator against the live backend | Emulator journeys captured; see the definition of done |
| Android admin console | B-08 through B-13 source-complete against real endpoints | Included in the final compile/test/lint gate | Emulator acceptance, light/dark screenshots and live-endpoint walkthrough |
| Prompt LLM | Qwen/Ollama adapter plus explicit fallback implemented | Historical live FastAPI evidence selected Qwen; not re-run in this audit | Re-run with `usedFallback=false` before the demo if Ollama is part of the demo |
| Free generative video | Wan2.1 T2V 1.3B two-phase Kaggle notebook proven to generate | 4/4 distinct 832×480, 81-frame clips; mean 48.6 min/clip on 2×T4 | Reviewed 2026-09-02: **demo-adequate, quality unverified**. The two-reviewer blind protocol was descoped and no numeric score is claimed. Direction and camera motion are ignored in all four clips, so demo prompts must not depend on either (section 5) |
| Real video in the app | External `kaggle` provider, least-privilege worker, lease heartbeat, Storage upload and atomic completion/refund exist in source | **S-14 accepted 2026-09-01:** an Android-submitted job completed through the worker; the MP4 is in Storage and parses as avc1 832x480, 65 frames, 4.06 s, and it played in the app. See [S14_FIRST_LIVE_CLIP_2026-09-01.md](evidence/S14_FIRST_LIVE_CLIP_2026-09-01.md) | S-14 ran on the **pre-015** completion path. Migration 015 has since changed it; see the gallery-thumbnail row |
| Gallery thumbnails (MIG-015) | Worker extracts and uploads a JPEG; completion refuses without both objects; three lease-scoped `uploads` policies | Migration live and verified read-only 2026-09-02 ([record](evidence/LIVE_SUPABASE_MIGRATION_015_2026-09-02.md)). `create_thumbnail` proven on all four real Wan2.1 clips (40–56 KB valid JPEGs). The refusal branch is covered against PostgreSQL 17.6 in both directions | **Accepted 2026-09-02.** Project `46b6d55d…` completed with `video.mp4` (405,459 B) in `videos` and `thumbnail.jpg` (40,696 B) in `uploads`; `thumbnail_path` is populated and the ledger holds exactly one −1 charge with no refund. See [MIG015_FIRST_THUMBNAIL_JOB_2026-09-02.md](evidence/MIG015_FIRST_THUMBNAIL_JOB_2026-09-02.md) |

## 3. Bruce lane

| Ticket | Current source status |
|---|---|
| B-01 camera capture | Source complete |
| B-02 credit contracts and repository seam | Source complete; real repository now bound |
| B-03 Credits screen | Source complete |
| B-04 simulated purchase flow | Source complete; retry key is stable |
| B-05 real credit balance/cost on Home | Source complete; the quota reset time now renders in the device timezone with a readable fallback, closing FR-QUOTA-003 |
| B-06 402 routing | Source complete; remains distinct from 429 quota |
| B-07 text, image and text+image contract modes | Source complete; unsupported image providers fail honestly. Remix restores prompt, aspect ratio, duration and provider only — style and camera motion are folded into the stored prompt and are deliberately outside the contract (`SRS.md` FR-MEDIA-003) |
| B-08 Manage navigation | Source complete; dashboard list replaces a wide tab row |
| B-09 admin videos | Source complete |
| B-10 user events | Source complete |
| B-11 admin credits/transactions | Source complete |
| B-12 admin events/packages/settings | Source complete |
| B-13 dashboard credit/revenue/event tiles | Source complete |
| B-14 screenshot pass | Two real defects fixed: `2>&1` made adb's stderr fatal on PowerShell 5.1 even at exit 0, and a fixed 2 s wait captured the previous screen. Both user and admin sets now capture. **Open:** the `-IncludeAdmin` step still fails its own guard — the node it finds has the same bounds a manual tap succeeds at, so the cause is inside the script's navigation, not the coordinates. The admin console shot is captured by hand until that is found |
| B-16 integration defects | Source audit complete; fixed per-attempt refunds, Kaggle read/state ownership, provider duration limits and retry validation. Device/live defects remain evidence-driven |

“Source complete” does not mean device-accepted. B-14 and B-16 own that last
proof so the same UI work is not reimplemented under a new ticket.

## 4. S0ra1n0 lane

The API/database work through S-16 is present. The remaining critical path is:

1. **S-13:** complete. Five Kaggle Secrets are enabled; the revision-bound
   worker passed Supabase Auth and the empty PostgreSQL claim path live.
2. **S-14:** **accepted end to end.** Job `4ad038f6…` was submitted from
   Android on 2026-09-01, completed by the worker at 14:11 UTC, its MP4 reached
   Storage, and it played in the app — see
   [S14_FIRST_LIVE_CLIP_2026-09-01.md](evidence/S14_FIRST_LIVE_CLIP_2026-09-01.md)
   and `_test/screenshots/s14-playback.png`. This ran on the pre-015 path.
3. **S-15 (MIG-015): complete.** Migration live and verified, and project
   `46b6d55d…` completed on 2026-09-02 with both canonical objects present.
   The worker now runs from a notebook on the S0ra1n0 Kaggle account, rebuilt
   from `_test/cretona-kaggle-worker.ipynb`.
4. **S-17:** the non-device evidence and canonical docs are reconciled through
   2026-09-02. Append the post-015 live worker result when that run exists.
5. **S-18:** the bootstrap-from-empty half is **closed** — `test_fresh_bootstrap.py`
   replays the real `bootstrap.sql`, migrations 002–015 and
   `seed_credits_and_events.sql` against an empty PostgreSQL 17.6 and asserts the
   signup trigger, seed contents, private buckets and all six lease-scoped worker
   Storage policies. **Outstanding:** the secret-free report and submission
   package by 2026-09-09.

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

Evidence accumulated 2026-09-01 through 2026-09-04; hosted source verification
is current through `f6e1657`, unless a row says it is historical live evidence:

- backend hosted PostgreSQL profile: **626 passed, 0 skipped** against a
  PostgreSQL 17 service;
- backend hosted SQLite profile: 569 passed and 57 intentionally skipped. **A plain
  local `pytest` still exits 0 while skipping every Postgres-only test,
  including the fresh-bootstrap replay — a green SQLite run is not a green run**;
- backend Ruff check/format, `pip check` and `pip_audit --local` are clean;
- Android gate rerun at `8c77b6f`: **129 tests**, 0 failures/errors/skips; lint,
  debug/release assembly and debug-android-test compilation passed. The Gradle
  wrapper JAR matched its pinned checksum. Run on JDK 21 (Android Studio JBR)
  rather than CI's 17; the project targets 17 with no strict toolchain, so
  hosted CI remains the authority for the JDK 17 path;
- the release APK was scanned for server-only credential markers and is clean —
  this is now an enforced CI step, not a manual one;
- dependency workflow uses least privilege, immutable action SHAs and verified
  Gradle wrapper/distribution checksums;
- hosted CI run 33879468605 passed all Android, SQLite-backend and
  PostgreSQL-parity jobs at the baseline `f6e1657`;
- the live Supabase gate ran with `transaction_read_only=on` against PostgreSQL
  17.6: migrations 006-015 are present, the worker role has no superuser,
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

- the bootstrap-from-empty replay now runs in the suite: real `bootstrap.sql`,
  migrations 002–015 and `seed_credits_and_events.sql` against an empty
  PostgreSQL 17.6. Supabase's own `auth`/`storage` schemas are stubbed, which is
  unavoidable off-platform; the project's SQL is genuinely replayed;
- `create_thumbnail` was run against all four real Wan2.1 clips and produced
  valid 832×480 JPEGs of 40–56 KB, roughly 80× clear of the worker's 512-byte
  guard. The live run then produced a 40,696-byte JPEG, inside that range;
- **the first post-MIG-015 job completed on 2026-09-02**: 28.5 minutes cold
  (including a ~22.7 GB model download), both objects in Storage, exactly one
  −1 ledger row and no refund. `STEPS` was 25, halved from 50 to bring a
  4-second clip inside a demo-viable window.

Not run or not accepted:

- **a warm-cache generation time has not been measured.** The single observed
  run was cold at 28.5 minutes; the ~20-minute warm figure is extrapolation;
- **quality at 25 steps has not been scored against 50.** The clip was judged
  usable by eye. The accepted 25-step worker is frozen through submission;
- Android rendering *this* job's thumbnail was not separately captured;
- NFR-REL-003 (60fps during polling, download and playback) has never been
  measured either way;
- EXP-006 proved audio generation only in isolation. A rebuilt worker bundle,
  one real audio job, and the required scope amendment remain open; audio is
  disabled in the final-demo notebook;
- EXP-007's Wan2.2 image-to-video notebook is source-only and has not run on a
  real Kaggle GPU. It is stretch scope, not part of the accepted release;
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
- [x] Final backend SQLite gate is green (569 passed, 57 Postgres-only skipped).
- [x] Final Postgres gate is green (626 passed, 0 skipped, PostgreSQL 17).
- [x] Final Android source/build gate is green (129 tests at `8c77b6f`).
- [x] Hosted CI is green at the technical baseline `f6e1657`.
- [x] Live Supabase migrations 014 **and 015** pass read-only security
      verification.
- [x] Five Kaggle Secrets and the live Auth/empty-queue claim smoke pass, most
      recently against the MIG-015 bundle.
- [x] `bootstrap.sql` plus seed produce a working system from an empty
      database, replayed through migration 015 in the suite.
- [x] The release APK carries no server-only credential marker, enforced in CI.
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
- [x] The in-app progress card follows a job to the end. Polling covered only
      10 minutes against a 28.5-minute job, so the card froze mid-run; the
      budget now spans 40 minutes and the card carries a manual refresh that
      resumes polling.
- [x] An admin cannot demote or disable their own account. Both are blocked in
      the view model and hidden in the UI, because neither is recoverable from
      inside a console gated on the role being given up.
- [x] A refused completion is diagnosed correctly. Since MIG-015 the database
      also refuses completion when a canonical object is missing, which is not
      a lost lease; the worker now distinguishes the two and refunds the case
      it caused, with both branches covered by tests.
- [x] Output quality has a **recorded decision**. The two-reviewer blind
      protocol was deliberately descoped on 2026-09-02 — the brief sets no
      quality threshold — and replaced by a single-reviewer non-blind review
      in `experiments/EXP-005/QUALITY_SCORECARD.md`. Outcome:
      **demo-adequate, quality unverified.**
- [x] **One post-MIG-015 job completes with a thumbnail.** Project
      `46b6d55d…` completed 2026-09-02: a 40,696-byte JPEG reached
      `uploads/<owner>/<project>/thumbnail.jpg` through the lease-scoped
      policies, `thumbnail_path` is populated, and the ledger holds one −1
      charge with no refund.
- [x] **The system was demonstrated live at the 2026-09-03 progress review.**
      Backend running against live Supabase through a public tunnel, a real
      Kaggle job submitted from the app, and playback of a genuinely generated
      clip. Five jobs ran that day across the `kaggle`, `cloud` and `local`
      tiers; the 13:45 Kaggle job took 25.9 minutes end to end.
- [ ] **The system is demonstrated live at the 2026-09-05 final session.**
- [ ] Current screenshots, demo video, report, sample accounts and submission
      package are complete, secret-free, and submitted by **2026-09-09**.

**Score: 19 complete, 1 partial, 2 outstanding.** Every engineering item is
closed and the 09-03 progress review is done. What remains is the 2026-09-05
final demonstration and the report/submission
package, due 2026-09-09 rather than on the day of the demo. The partial is the emulator journey set, complete but with one screen
captured by hand. The pass/fail item — a real Wan2.1 clip
generated on free Kaggle and played in Android — is **done and evidenced**.

### Worker bundle hashes, `STEPS = 25` build

Verify these in the notebook before copying either file. The live 2026-09-02
job ran on exactly this bundle, and the 2026-09-05 demo stays on it:

```text
bundle        cretona-kaggle-worker-STEPS25.zip
worker        decc5f5ddddfc0af515ee3cce045e1ce97742af854303afa4c24bba2d97e3823
requirements  46263bf0527742dde0d98a5da163afc1646a53b5f6de545ad3e94da43c99c669
```

Notebook source: `_test/cretona-kaggle-worker.ipynb`. Do not raise `STEPS`,
replace the worker file, or enable audio before the final demo. Any such change
creates a new artifact and requires a separate live acceptance run.

Hashes are taken over the committed **LF** blobs, not the Windows working-tree
files; a CRLF copy hashes differently and the notebook will reject it.
