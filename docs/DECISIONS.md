# Cretona — Project decisions

This is the short decision surface for Bruce and S0ra1n0. The instructor only
requires FastAPI to call model services and has suggested familiar AI products
such as ChatGPT or Gemini. No other product or stack constraint is currently
known. The team authorized decisions `DEC-001` through `DEC-004`, `DEC-006`,
`DEC-007`, and `DEC-009` as the build baseline on 2026-08-10. Remote integration
evidence later superseded `DEC-003`, refined `DEC-006`, and expanded `DEC-009`
through `DEC-011`. Paid activation
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
| `DEC-008` | Experiment required | Bruce + S0ra1n0 | For a zero-additional-spend build, run `EXP-005`; use local Qwen3-4B + LTX-Video 2B Q8 as the Standard candidate and retain FramePack F1 only if it passes the Quality threshold | Not selected | The measured host has RTX 3070 Ti Laptop 8 GB and 16 GB RAM; local quality and latency remain untested |
| `DEC-009` | Expanded by `DEC-011` | Bruce + S0ra1n0 | Python/FastAPI is the final model-orchestration backend | Port the tested Express behavior to FastAPI before feature expansion | Matching Express/Prisma/Supabase implementation now exists; its contracts and tests are migration evidence, not authority to waive the instructor's FastAPI requirement |
| `DEC-010` | Accepted during remote integration 2026-08-10 | Bruce + S0ra1n0 | Preserve the existing coherent Android implementation | Root Kotlin/Compose/MVVM project; remove the duplicate local `android/` scaffold | Existing codebase and build configuration outrank an unshared alternative; Android remains provider-neutral |
| `DEC-011` | Accepted migration default 2026-08-10; S0ra1n0 review required | Bruce + S0ra1n0 | Change one major boundary at a time | Express → FastAPI while retaining the existing Supabase Auth/Postgres/Storage contracts initially | Minimizes blast radius and preserves teammate work; SQLite remains a future offline alternative, not a simultaneous migration |

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
