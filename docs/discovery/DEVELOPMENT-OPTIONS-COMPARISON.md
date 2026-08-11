# Cretona development options: free to USD 25

- **Document ID:** `CRETONA-DEV-OPTIONS-001`
- **Observation date:** 2026-08-11 (free-local evidence refreshed; paid prices remain the 2026-08-06 snapshot)
- **Decision owner:** Bruce and S0ra1n0
- **Status:** Decision support; no paid generation has been run

## 1. Comparison boundary

This document compares ways to deliver the same selected product direction:
an Android application that sends text and an optional reference image to a
FastAPI backend, improves the prompt through a text LLM, creates an
asynchronous video job, and returns a playable result.

The budget means the team's total provider spend for development, verification,
and the graded demonstration. It is not a monthly production budget. Hardware,
electricity, taxes, payment fees, and future public usage are not included.

Published API prices are source-stated facts as observed on the date above.
Quality ratings are hypotheses until the team runs the proposed blind
benchmark.

## 2. Technology common to every option

| Layer | Technology and boundary |
|---|---|
| Android | Kotlin, Jetpack Compose, MVVM, Retrofit/OkHttp, Coroutines/StateFlow, Media3 |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, SQLite, JWT, pytest |
| Text LLM | `PromptEnhancer` boundary: Gemini 2.5 Flash for API-backed options; local Qwen3-4B for the strict zero-paid option |
| Video domain | `VideoProvider` adapter, canonical job states, server-owned model mapping, deterministic `FakeVideoProvider` |
| Core business | Register/login, user/admin roles, prompt enhancement and approval, optional reference image, cost confirmation, asynchronous status, playback, history, ownership checks, quota and failure handling |
| Security boundary | Provider keys exist only on FastAPI; Android receives no provider key or raw endpoint ID |

## 3. Options matrix

| ID | Provider budget | Video technology | Real business capability delivered | Expected output quality | Demo reliability | Two-developer effort/risk | Evidence confidence |
|---|---:|---|---|---|---|---|---|
| `OPT-0A` Free deterministic demo | USD 0 | Gemini free-tier text enhancement + `FakeVideoProvider` + bundled/synthetic MP4 fixtures | The complete app workflow can be implemented and tested, including auth, roles, prompt approval, job lifecycle, history, playback, quota and errors; it does **not** perform live AI video generation | UI/demo can look polished and deterministic; generated-video quality is `not applicable` because the result is a fixture | Very high | Lowest delivery risk; fails the stronger interpretation that Cretona itself must call a live video model | High for feasibility; no claim of real video quality |
| `OPT-0B` Free local AI | USD 0 API spend, conditional on owned hardware | Proven local Qwen3-4B prompt LLM + provider-neutral video worker + fake fallback; LTX 2B rejected; FramePack F1 installed but blocked | Real prompt enhancement plus the common business workflow; real text-to-video is unselected and image-to-video remains an unexecuted candidate | No real local video output may be rated yet; FramePack has a plausible I2V ceiling but no run or blind score | High for prompt/fake demo; low for a real video demo until one candidate passes | High setup, host-memory, license and inference-time risk; bounded by manifest/preflight gates | High for Qwen and installed-artifact evidence; no confidence claim for unobserved video quality/latency |
| `OPT-1` Minimal live API | Up to USD 5 | Gemini free tier + fal adapter + one economical endpoint, initially Hailuo-02 Pro or Kling 3 Pro + fake fallback | Real text-to-video and image-to-video, canonical async jobs, cost guard, history and playback; only one live quality profile is validated | Good potential at 1080p with Hailuo Pro or stronger controls/audio with Kling; selection would rely mostly on provider claims and a very small spike | Medium to high with recorded/fake fallback | Low integration complexity, but too little budget for a defensible multi-model quality comparison | High for published price and API shape; low for comparative quality |
| `OPT-2` Balanced mini-benchmark | USD 10-15 | Gemini free tier + fal router; compare Kling 3 Pro and Veo 3.1 Fast; map one winner to `STANDARD` + fake fallback | All MVP business capabilities and a benchmark-backed Standard profile; Premium may exist in the API contract but should not be promised as independently validated | High potential: Kling emphasizes motion/control and optional audio; Veo Fast adds native audio at a moderate rate; only two model families are compared | High if final demo uses a pre-verified prompt and fallback | Balanced workload; enough for six comparison runs, integration checks and a small demo reserve, but limited retry headroom | Medium after the mini-benchmark; currently low before it is run |
| `OPT-3` Recommended quality-first | Maximum USD 25 | Gemini free tier + fal router; blind benchmark Kling 3 Pro, Veo 3.1 Fast, Veo 3.1 Standard and one eligible challenger; backend maps winners to `STANDARD` and `PREMIUM` + fake fallback | Complete selected MVP: both input modes, two quality profiles, pre-generation price estimate, explicit Premium confirmation, actual cost metadata, quota, admin visibility, history and deterministic fallback | Highest evidence-backed quality ceiling within scope: Standard must pass 70/100; Premium must pass 80/100, both input modes and USD 2.50/clip cap | Highest realistic live-demo confidence, while still retaining a deterministic fallback | Moderate and bounded; no additional Android provider UI and no second provider contract, but the team must execute and document the benchmark | Medium only after the benchmark; currently published capabilities/prices are high-confidence but output quality remains untested |

## 4. What the published prices buy

| Endpoint example | Observed price | Approximate capacity before retry/tax | Relevant tradeoff |
|---|---:|---:|---|
| Hailuo-02 Standard image-to-video, 768p | USD 0.27 per 6s | About 18 clips per USD 5 | Cheapest live image path in the shortlist; no independent quality proof |
| Hailuo-02 Pro, 1080p | USD 0.48 per 6s | About 10 clips per USD 5 | Inexpensive resolution upgrade; provider estimates generation can take minutes |
| Kling 3 Pro, audio off | USD 0.56 per 5s | About 8 clips per USD 5 | Strong Standard candidate with text/image and motion controls |
| Kling 3 Pro, audio on | USD 0.84 per 5s | About 5 clips per USD 5 | Adds native audio but reduces test capacity |
| Veo 3.1 Fast, audio on | USD 0.75 per 5s | About 6 clips per USD 5 | Useful quality/cost challenger with audio |
| Veo 3.1 Standard, audio on | USD 2.00 per 5s | 2 clips per USD 5 | Premium candidate; unsuitable for repeated trial-and-error prompting |

Capacity is floor-rounded and intentionally excludes retries. A failed or
changed provider policy can reduce it. The team must recheck endpoint prices
immediately before enabling live mode.

## 5. Capability difference by budget

| Capability | `OPT-0A` | `OPT-0B` | `OPT-1` | `OPT-2` | `OPT-3` |
|---|:---:|:---:|:---:|:---:|:---:|
| FastAPI calls a real text LLM | Yes | Yes | Yes | Yes | Yes |
| Live text-to-video | No | Not yet; candidate unselected | Yes | Yes | Yes |
| Live reference-image-to-video | No | Not yet; FramePack must pass `EXP-005` | Yes | Yes | Yes |
| Native generated audio | No | No | Model-dependent | Yes when configured | Yes when selected by benchmark |
| Auth, roles, quota, history and ownership | Yes | Yes | Yes | Yes | Yes |
| Deterministic automated tests/fallback | Yes | Yes | Yes | Yes | Yes |
| Quality decision backed by comparison | No | No | Minimal spike only | Two-model mini-benchmark | Four-candidate blind benchmark |
| Validated Standard profile | Fake only | No real video profile yet | One provider profile | Yes | Yes |
| Validated Premium profile | No | No | No | Not promised | Yes, if threshold passes |
| Cost estimate and explicit paid confirmation | Simulated | Simulated | Yes | Yes | Yes |

## 6. Separate decision axes

| Option | Product attractiveness | Current evidence confidence | Feasibility for Bruce + S0ra1n0 | Material risk |
|---|---|---|---|---|
| `OPT-0A` | Low to medium: complete software workflow but weak AI-video claim | High | High | Instructor or evaluator may reject fixture-only video generation |
| `OPT-0B` | Medium to high: real, private and locally controlled T2V/I2V | Low until `EXP-005` | Medium because the measured RTX 3070 Ti Laptop has 8 GB VRAM but only 16 GB system RAM | RAM/offload, latency, model lifecycle and lower quality than premium APIs dominate the project |
| `OPT-1` | Medium to high: real end-to-end product at low cost | Medium | High | Model selection is weakly evidenced and live credits can be exhausted by retries |
| `OPT-2` | High: real product plus a defensible Standard profile | Medium | High | Premium quality and broader comparison remain unproven |
| `OPT-3` | High: strongest classroom story and output ceiling | Medium before experiment, high for documented pricing | Medium to high | Paid access, vendor drift, benchmark discipline and external latency |

These axes are intentionally not averaged into one score.

## 7. Recommendation and dissent

Recommend `OPT-3`, but preserve the following delivery rule:

1. Build and test `OPT-0A` first so every non-AI business path is deterministic.
2. Activate `OPT-3` only after account ownership and the USD 25 envelope are
   explicitly accepted.
3. Spend no more than USD 15 on the blind benchmark, USD 5 on selected-endpoint
   integration verification, and USD 5 on the final demonstration reserve.
4. If paid access is unavailable, fall back to `OPT-1` with one verified model.
5. If all paid access is unavailable, demonstrate `OPT-0A` honestly and do not
   label fixture video as live generation.

`OPT-2` is the strongest dissenting alternative: it preserves real video and
most academic value while saving USD 10-15. It is not preferred when the stated
goal is the best result because it cannot validate a distinct Premium profile.

## 8. Quality experiment

The quality statements remain unverified until `EXP-004` is run:

- three synthetic cases: motion/cinematic text, reference-image consistency,
  and dialogue/audio;
- four eligible candidates with hidden model names during review;
- weighted score: visual detail 20, motion 20, prompt adherence 15, reference
  consistency 10, audio 10, artifacts 10, reliability 5, latency 5, cost 5;
- `STANDARD`: at least 70/100 and best score per dollar among passing models;
- `PREMIUM`: at least 80/100, both selected input modes, and at most USD 2.50
  for the configured clip;
- disconfirming result: no candidate meets quality, access, latency,
  reliability and budget thresholds.

## 9. Current first-party/platform evidence

- Gemini Developer API pricing and free-tier data-use distinction:
  https://ai.google.dev/gemini-api/docs/pricing
- Wan2.1 T2V 1.3B model card, license and stated VRAM requirement:
  https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B
- Hugging Face Inference Providers free credits:
  https://huggingface.co/docs/inference-providers/en/pricing
- fal Hailuo-02 Pro text-to-video price and queue contract:
  https://fal.ai/models/fal-ai/minimax/hailuo-02/pro/text-to-video
- fal Hailuo-02 Standard image-to-video price:
  https://fal.ai/models/fal-ai/minimax/hailuo-02/standard/image-to-video
- fal Kling 3 Pro image-to-video price and capabilities:
  https://fal.ai/models/fal-ai/kling-video/v3/pro/image-to-video
- fal Veo 3.1 Standard/Fast price and capabilities:
  https://fal.ai/models/fal-ai/veo3.1

## 10. Limits

- No paid generation, local-model spike, device GPU inventory or latency test
  has been run.
- Provider marketing is not independent proof of model quality.
- Free tiers, prices, model names, access regions, terms and data policies can
  change.
- Gemini free-tier text requests are currently documented as usable for product
  improvement; only synthetic/non-personal project data should be sent unless
  the team reviews and accepts the policy.
- Hugging Face currently documents only USD 0.10 monthly inference-provider
  credit for free users, subject to change; this is not a sustainable free
  video-generation plan.
