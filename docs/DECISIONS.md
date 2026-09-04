# Cretona — Project decisions

This is the short decision surface for Bruce and S0ra1n0. The instructor only
requires FastAPI to call model services and has suggested familiar AI products
such as ChatGPT or Gemini. No other product or stack constraint is currently
known. The team authorized decisions `DEC-001` through `DEC-004`, `DEC-006`,
`DEC-007`, and `DEC-009` as the build baseline on 2026-08-10. Remote integration
evidence later superseded `DEC-003`, refined `DEC-006`, and expanded `DEC-009`
through `DEC-012`. `DEC-013` and `DEC-014` were decided against measured
evidence during the final week. Paid activation
and the final live video model remain separate decisions.

| ID | Status | Decision owner | Recommended default | Chosen value | Evidence/reason |
|---|---|---|---|---|---|
| `DEC-001` | Accepted 2026-08-10 | Bruce + S0ra1n0 | `CAND-002` final MVP; finish the `CAND-001` text path before image input | Text + one optional image → short video | Matches the original repository promise while protecting delivery order |
| `DEC-002` | Accepted 2026-08-10 | Bruce | Use five relative delivery waves; remap them when the course deadline is announced | Five waves | No feature rubric beyond FastAPI is imposed |
| `DEC-003` | Superseded by `DEC-010` | Bruce + S0ra1n0 | Kotlin + XML Views + MVVM | Not retained | The remote repository already contains a coherent Compose scaffold; introducing a second Android project would create contract and build drift |
| `DEC-004` | Accepted 2026-08-10 | Bruce + S0ra1n0 | FastAPI calls a text-capable LLM to produce a visible prompt suggestion; after user confirmation it calls a specialized video-generation model | Prompt LLM and video model are separate server-side capabilities | Makes the instructor's LLM suggestion explicit without incorrectly treating every LLM as a raw video generator |
| `DEC-005` | Deferred | Bruce + S0ra1n0 | Benchmark current server-side text and video providers within the separately approved USD 25 envelope | No paid provider selected | Provider versions, account access, regional eligibility, price, and measured quality remain unverified |
| `DEC-006` | Refined by `DEC-011` | Bruce + S0ra1n0 | Run FastAPI on a team laptop for development/final demo; public deployment is stretch scope | Local-network FastAPI; retain existing Supabase data services during migration | Keeps the required runtime local without rewriting working auth/data/storage together with the framework |
| `DEC-007` | Accepted 2026-08-10 | Bruce + S0ra1n0 | Bruce owns Android; S0ra1n0 owns FastAPI; each reviews the other boundary | Bruce: Android; S0ra1n0: backend | Separate owned paths minimize merge conflicts |
| `DEC-008` | Experiment active; Qwen passed, video unselected | Bruce + S0ra1n0 | Keep local Qwen3-4B for prompt enhancement; reject LTX 2B on the pinned host-envelope pre-screen; run FramePack F1 only after resource/license gates; separately select a text-to-video candidate | Prompt LLM selected; no video model selected | Qwen passed live FastAPI proof. FramePack runtime/weights are pinned but its 4.30 GiB RAM, 5.96 GiB VRAM and 14.62 GiB virtual-memory observation fails the 6/6/48 GiB preflight; LTX's documented route exceeds the Ampere 8 GB host envelope |
| `DEC-009` | Expanded by `DEC-011` | Bruce + S0ra1n0 | Python/FastAPI is the final model-orchestration backend | Port the tested Express behavior to FastAPI before feature expansion | Matching Express/Prisma/Supabase implementation now exists; its contracts and tests are migration evidence, not authority to waive the instructor's FastAPI requirement |
| `DEC-010` | Accepted during remote integration 2026-08-10 | Bruce + S0ra1n0 | Preserve the existing coherent Android implementation | Root Kotlin/Compose/MVVM project; remove the duplicate local `android/` scaffold | Existing codebase and build configuration outrank an unshared alternative; Android remains provider-neutral |
| `DEC-011` | Accepted migration default 2026-08-10; S0ra1n0 review required | Bruce + S0ra1n0 | Change one major boundary at a time | Express → FastAPI while retaining the existing Supabase Auth/Postgres/Storage contracts initially | Minimizes blast radius and preserves teammate work; SQLite remains a future offline alternative, not a simultaneous migration |
| `DEC-012` | Accepted local-slice exception 2026-08-10; deployment parity still required | Bruce + S0ra1n0 | Use SQLite and development identity only for the credential-free walking skeleton | FastAPI + SQLite + fake provider is the active local evidence profile | Produces a deterministic end-to-end proof without claiming Supabase or real-model parity; ADR-008 defines the migration exit gate |
| `DEC-013` | Rejected 2026-09-02 | Bruce + S0ra1n0 | Keep Wan2.1 T2V 1.3B on free Kaggle for this delivery | HunyuanVideo 1.5 not adopted | Three days from the final session, and the change is not one change. **Capacity:** DiT 8.3B is ~6.4x Wan2.1's 1.3B; fp16 weights alone are ~16.6 GB against a Kaggle T4's 16 GB, before VAE, text encoder and activations, and Wan2.1 1.3B already peaked at 12.45 GiB VRAM / 29.13 GiB RAM at 48.6 min per clip. T4 has no bf16 path, and the proposed VSR 720p->1080p pass adds a second model. The free tier cannot host it; a paid GPU is out of scope. **Blast radius:** the proposed diagram also swaps Kotlin/Compose for Flutter/React Native, the Postgres lease queue for Redis + Celery, Supabase Storage for S3/R2/MinIO, and adds Prometheus and a CDN — discarding B-01..B-13 and the live-verified migrations 014/015 RLS contract. **Standing evidence:** the current stack has already generated a real clip that played in the app. Revisit after submission |

| `DEC-014` | Accepted 2026-09-05 | Bruce + S0ra1n0 | Ship the generated soundtrack and amend the proposal rather than leave it undeclared | MMAudio soundtrack on every Kaggle clip, behind `CRETONA_WORKER_AUDIO` | `PROJECT-PROPOSAL.md` listed audio under explicit non-scope, so shipping it silently would read as scope drift rather than delivery. **Evidence:** two real Android-submitted jobs completed on 2026-09-03 with an audible AAC track — mean −31.3 / −31.9 dB, peaks −5.2 / −4.7 dB against roughly −91 dB for digital silence — plus a thumbnail, one −1 ledger row and no refund ([record](evidence/EXP006_FIRST_AUDIO_JOBS_2026-09-03.md)). **Licence:** MMAudio's code is MIT but its **checkpoints are CC-BY-NC 4.0**, which permits this coursework and forbids commercial use; that constraint follows the model, not the repository. **Cost:** the composite first grew a 405,459 B clip to 2.9–5.1 MB because MMAudio re-encodes the picture; muxing the streams instead returns it to 472,018 B with the original picture intact. **Failure mode:** a missing soundtrack must never fail a finished video — the opposite of migration 015's thumbnail rule, and deliberately so |

The free-to-paid alternatives behind `DEC-005` are compared in
[`docs/discovery/DEVELOPMENT-OPTIONS-COMPARISON.md`](discovery/DEVELOPMENT-OPTIONS-COMPARISON.md).
The hardware-specific zero-paid recommendation and kill criteria are in
[`docs/discovery/FREE-LOCAL-BEST-OUTPUT.md`](discovery/FREE-LOCAL-BEST-OUTPUT.md).

## Remaining course information to record when available

1. Exact deadline and required submission artifacts.
2. Presentation/demo date and required submission format.
3. Any later constraint that conflicts with the proposed defaults above.

## Approval statement

> On 2026-08-10, Bruce authorized implementation items 1–5 from the repository
> review: credential protection, safe examples, FastAPI architecture alignment,
> a planning baseline commit, and Android/FastAPI scaffolding. This authorizes
> the accepted decisions above for the initial build. S0ra1n0 should review the
> shared API contract before feature development begins.

The baseline is build-authorized with the deterministic fake provider. Paid
provider use remains blocked until `DEC-005` is explicitly accepted.
