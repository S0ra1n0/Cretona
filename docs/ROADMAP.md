# Cretona — current delivery roadmap

- **Last reconciled:** 2026-08-29
- **Deadline:** 2026-09-05 (2026-09-06 is buffer only)
- **Team:** Bruce — Android/admin UI · S0ra1n0 — FastAPI/database/Kaggle worker
- **Detailed tickets:** [TASK-SPLIT-2026-08-28.md](TASK-SPLIT-2026-08-28.md)
- **Containing commit:** binds this snapshot to the exact source revision

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
- `kaggle` is an external-provider queue. Its worker is the remaining execution
  component.

## 2. Audited status

| Area | Implemented | Observed evidence | Remaining boundary |
|---|---|---|---|
| FastAPI API, auth, ownership, quotas, admin | Complete in source | 537 passed, 53 Postgres-only skipped; Ruff clean on 2026-08-29 | Current Postgres parity run blocked because Docker Desktop was unavailable |
| Credits, payments, events and refund ledger | Complete in SQLite/Postgres adapters; migration `013` and seed exist | Historical 2026-08-28 evidence records 590 passed, 0 skipped and live migration probes | Re-run Postgres parity when Docker works; do not replace the historical result with the blocked current run |
| Android user journeys | B-01 through B-07 source-complete; real repositories are bound | Final full gate: 123 unit tests, lint, debug/release APK and instrumentation-test compile passed | Record emulator journeys and screenshots |
| Android admin console | B-08 through B-13 source-complete against real endpoints | Included in the final compile/test/lint gate | Emulator acceptance, light/dark screenshots and live-endpoint walkthrough |
| Prompt LLM | Qwen/Ollama adapter plus explicit fallback implemented | Historical live FastAPI evidence selected Qwen; not re-run in this audit | Re-run with `usedFallback=false` before the demo if Ollama is part of the demo |
| Free generative video | Wan2.1 T2V 1.3B two-phase Kaggle notebook proven to generate | 4/4 distinct 832×480, 81-frame clips; mean 48.6 min/clip on 2×T4 | Blind quality scorecard is empty; no quality pass may be claimed |
| Real video in the app | External `kaggle` provider contract and provider-scoped claiming exist | Contract/backend tests only | S-13 worker, S-14 first real result, storage writeback and Android playback are still required |

## 3. Bruce lane

| Ticket | Status on 2026-08-29 |
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
| B-14 screenshot pass | Pending current emulator evidence |
| B-16 integration defects | In progress; code audit fixed retry charging, refund balance refresh and provider error routing |
| B-17 demo video | Blocked on S-14 real clip |
| B-18 report/screenshots | Pending B-14/B-17 |

“Source complete” does not mean device-accepted. B-14 and B-16 own that last
proof so the same UI work is not reimplemented under a new ticket.

## 4. S0ra1n0 lane

The API/database work through S-16 is present. The remaining critical path is:

1. **S-13:** run the Kaggle worker that claims only `provider = 'kaggle'`, renews
   its lease during long inference, loads Wan2.1 in two phases, uploads the
   result, and closes the job.
2. **S-14:** submit one text job from Android, let the worker complete it, and
   play the returned real MP4 in Android. Capture IDs, timestamps and media
   metadata as evidence.
3. **S-17/S-18:** finish the evidence ledger, report and submission package.

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
- unresolved: Bruce and S0ra1n0 must score the blind clips independently in
  `experiments/EXP-005/QUALITY_SCORECARD.md` before calling output quality
  acceptable.

For the first end-to-end demo, text-to-video is the shortest valid path. Do not
spend the delivery window adding a second video model unless the worker path is
already proven and the scorecard shows Wan2.1 is unacceptable.

## 6. Current verification and blockers

Verified on 2026-08-29:

- backend: Ruff check/format clean, `pip check` clean, 537 passed and 53 skipped;
- Android final gate: 123 tests, 0 failures/errors/skips; lint 0 errors and 5
  dependency/target warnings; debug/release assembly and debug-android-test
  compilation passed;
- dependency workflow uses least privilege, immutable action SHAs and verified
  Gradle wrapper/distribution checksums;
- tracked secret-pattern scan found only the deliberate service-role placeholder
  in `backend/.env.example`, not a plaintext credential.

Blocked/not run in this audit:

- Postgres parity: Docker Desktop daemon did not become available and the retry
  was stopped instead of hanging;
- live Kaggle page: this environment could not establish the page TLS session;
  the committed 29-cell notebook and its evidence were inspected instead;
- emulator, live Supabase and hosted CI acceptance: still require a current run.

## 7. Definition of done

- [x] Eight required business tables exist in migration/bootstrap source.
- [x] User credits, events, purchase, charge and refund paths are implemented.
- [x] Admin user, project, credits, events, packages, settings and dashboard
      paths are implemented.
- [x] Final backend SQLite gate is green at the delivered revision.
- [ ] Final Postgres gate is green at the delivered revision.
- [x] Final Android source/build gate is green at the delivered revision.
- [ ] Required emulator journeys are green at the delivered revision.
- [ ] A Wan2.1 Kaggle job submitted through FastAPI completes and its real video
      plays in Android.
- [ ] Blind quality scorecard has both reviewers' entries and a recorded decision.
- [ ] Current screenshots, demo video, report, sample accounts and submission
      package are complete and secret-free.
