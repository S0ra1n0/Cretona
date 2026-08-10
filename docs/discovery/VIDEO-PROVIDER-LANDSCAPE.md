# Cretona — Video provider landscape and benchmark proposal

- **Document ID:** `CRETONA-VID-LANDSCAPE-001`
- **Mode:** Landscape/select
- **Observation date:** 2026-08-06
- **Status:** Decision support; no paid call has been run

## 1. Decision being supported

Choose a video API strategy that gives a two-developer Mobile 1 project strong
visual results without making cost, vendor integration, or live-demo failure
the dominant risk.

“Best result” is defined as:

1. strong visual quality and coherent motion;
2. adherence to the approved prompt;
3. useful reference-image consistency;
4. good audio/dialogue when enabled;
5. a reliable, documented API with trackable jobs;
6. a price low enough to test and demonstrate repeatedly.

Price alone is not a quality metric. A premium rate may pay for higher
resolution, longer duration, native audio, more compute, or provider markup.
The team has not run a controlled output benchmark, so all model-quality
statements below remain provider-stated or inferred.

## 2. Bounded current landscape

Prices are public API prices observed on 2026-08-06. They can change and must be
queried or rechecked before any live run.

| Model/API option | Publicly documented capability relevant to Cretona | Example public API cost | Practical note |
|---|---|---:|---|
| Luma Ray3.2 | Text/image-to-video, 5/10s, 720p/1080p; no native audio in the quoted generation table | USD 0.30 for 5s 720p | Very inexpensive direct API candidate; separate vendor integration |
| Hailuo-02 Pro via fal | Text/image-to-video, 1080p | USD 0.48 for 6s | Budget quality candidate; fal documentation, not an independent benchmark |
| Kling 3 Pro via fal | Text/image-to-video, cinematic motion, multi-shot, optional native audio | USD 0.56 for 5s without audio; USD 0.84 with audio | Strong initial `Standard` candidate |
| Runway Gen-4.5 direct | Text/image-to-video through Runway API | USD 0.12/s, about USD 0.60 for 5s | Mature creative API, but separate credential/account and no quoted audio claim here |
| Veo 3.1 Fast via fal | Text/image-to-video, 720p/1080p, optional audio | USD 0.50 for 5s silent; USD 0.75 with audio | Fast quality/cost challenger |
| Seedance 2.0 Fast via fal | Rich reference inputs and native audio, up to 15s | About USD 1.21 for 5s 720p | Useful when reference control matters more than price |
| Veo 3.1 Standard via fal | Text/image/reference-to-video, 720p/1080p/4K, native audio | USD 1.00 for 5s silent; USD 2.00 with audio | Strong `Premium` candidate |
| Sora 2 Pro direct/fal | Text/image-to-video with synchronized audio | USD 1.20 for 4s 720p; USD 2.00 for 4s higher resolution | Premium challenger; current OpenAI model page labels Sora 2 Pro legacy/deprecated, so lifecycle risk must be checked |
| Kling V3 4K via fal | Text/image-to-video at native 4K | USD 2.10 for 5s | Expensive resolution showcase, not necessary for the Android MVP |

First-party/platform sources:

- Kling VIDEO 3.0 guide and credit pricing:
  https://app.klingai.com/cn/quickstart/klingai-video-3-model-user-guide
- fal text-to-video catalog and common SDK/billing claim:
  https://fal.ai/explore/text-to-video-apis
- fal image-to-video catalog and per-model price comparison:
  https://fal.ai/explore/image-to-video-apis
- fal Kling 3 Pro endpoint:
  https://fal.ai/models/fal-ai/kling-video/v3/pro/text-to-video
- fal Veo 3.1 endpoint:
  https://fal.ai/models/fal-ai/veo3.1
- fal Seedance 2.0 reference endpoint:
  https://fal.ai/models/bytedance/seedance-2.0/reference-to-video
- OpenAI Sora 2 Pro model and pricing:
  https://developers.openai.com/api/docs/models/sora-2-pro
- Runway API pricing:
  https://docs.dev.runwayml.com/guides/pricing/
- Luma API pay-as-you-go pricing:
  https://lumalabs.ai/api

## 3. Why existing apps do not invalidate Cretona

Kling, Runway, CapCut, Canva, Luma, and other apps already generate AI video.
Cretona should therefore not claim that text/image-to-video is novel.

Its defensible academic scope is the orchestration and mobile-engineering layer:

- explicit text-LLM prompt improvement and user approval;
- server-enforced identity, ownership, role, quota, and cost controls;
- stable `Standard`/`Premium` quality profiles rather than raw model IDs;
- one canonical asynchronous job state machine across model endpoints;
- cost estimate before submission and actual cost metadata after completion;
- deterministic fake provider for testability and demo recovery;
- transparent history of prompt, settings, status, and output.

This is a meaningful systems project even though the foundation models are
external. Cretona independently implements the workflow and does not copy the
competitors' visual assets, editor, branding, or protected behavior.

## 4. Recommended provider architecture

Use two separate model boundaries:

1. Google Gemini text API for prompt enhancement.
2. A fal video-router adapter for paid video generation.

fal is recommended for the first benchmark because its public platform exposes
Kling, Veo, Sora, Seedance, and other models through one authentication,
queueing, and billing system. This reduces the integration cost of comparing
models. It does add fal as a data processor/vendor and does not eliminate each
underlying model's terms, moderation, or lifecycle risk.

Android shall never select an endpoint ID. It sends one stable profile:

- `STANDARD`: good quality, approximately USD 0.50–0.85 per short clip.
- `PREMIUM`: highest benchmarked quality, maximum USD 2.50 per short clip.

FastAPI maps those profiles to configured endpoint IDs. Changing a model does
not change Android DTOs, job states, or business rules.

Initial candidates, pending benchmark:

- `STANDARD`: Kling 3 Pro 720p, 5s; audio configurable.
- `PREMIUM`: Veo 3.1 Standard 1080p, 5s with audio.
- `CHALLENGERS`: Veo 3.1 Fast and Sora 2 Pro.

Luma Ray3.2, Hailuo, Runway Gen-4.5, and Seedance remain documented alternatives,
not active MVP endpoints.

## 5. Blind benchmark before final selection

### Inputs

Use only synthetic/non-personal content:

1. `BENCH-TEXT-01`: one continuous cinematic scene with significant subject
   movement and camera motion.
2. `BENCH-IMAGE-01`: one synthetic reference character/product image with a
   precise motion prompt.
3. `BENCH-AUDIO-01`: two-character or narrator scene requiring understandable
   speech and environmental sound.

Run each case once against:

- Kling 3 Pro;
- Veo 3.1 Fast;
- Veo 3.1 Standard;
- Sora 2 Pro.

Use the closest comparable duration, aspect ratio, resolution, and audio mode
that each model supports. Record deviations; do not hide them inside a score.

### Blind review rubric

Bruce and S0ra1n0 score outputs without seeing the model name:

| Axis | Weight |
|---|---:|
| Visual detail and composition | 20 |
| Motion/temporal coherence | 20 |
| Prompt adherence | 15 |
| Reference-image consistency | 10 |
| Audio/dialogue quality | 10 |
| Absence of critical artifacts/safety failure | 10 |
| API success and reproducibility | 5 |
| Latency | 5 |
| Cost | 5 |

The quality-related axes intentionally dominate the score because the team's
goal is the best result, not the cheapest output.

### Selection rule

- `STANDARD` must score at least 70/100 and have no critical artifact or failed
  required mode; choose the best score-per-dollar among passing candidates.
- `PREMIUM` must score at least 80/100, support both Cretona input modes, and
  remain at or below USD 2.50 per configured clip.
- If no model passes, do not increase spend blindly. Revise prompts/input,
  inspect failures, and rerun only the smallest disconfirming case.

The benchmark result—not marketing copy or model price—selects the endpoint.

## 6. Budget proposal

Maximum authorized envelope to propose: **USD 25 total**.

| Budget bucket | Maximum | Purpose |
|---|---:|---|
| Blind benchmark | USD 15 | Twelve planned model/case generations and limited retry headroom |
| Integration verification | USD 5 | Confirm the selected endpoints through FastAPI |
| Final demo reserve | USD 5 | One prepared `Standard`, one `Premium`, and failure/retry headroom |

The current listed prices put the initial twelve-run benchmark at roughly USD
14–15 before taxes or price changes. The account owner must configure a hard
spend limit when the platform supports it and manually stop at each bucket.

Approving this document does not itself authorize a charge. Bruce and S0ra1n0
must separately agree who owns the account and when live mode may be enabled.

## 7. Risks and stop conditions

- Model names, status, prices, regional access, and policies can change.
- Router availability adds a dependency beyond the underlying model.
- Uploaded images and prompts are sent to external processors; use synthetic
  demo assets unless explicit consent and retention rules exist.
- A high-quality playground output does not prove API reliability.
- Sora 2 Pro is currently marked legacy/deprecated on OpenAI's model page;
  exclude it if availability is not verified at benchmark time.
- Stop paid testing when the benchmark bucket reaches USD 15, credentials cannot
  be protected, account/billing ownership is unclear, or the provider cannot
  meet both text and image input paths.
