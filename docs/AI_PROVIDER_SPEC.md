# AI Provider Integration Spec

**Version:** 0.2 · **Status:** Contract accepted; one deterministic FastAPI adapter implemented

Defines the boundary between Cretona and any third-party AI video API. Satisfies NFR-5.2: adding a provider means implementing one interface and registering it — nothing above `services/ai` changes.

The TypeScript below is the original executable reference contract. The active
Python equivalent lives in `backend-fastapi/app/providers.py`; names differ by
language, but capabilities, normalized states, and secret boundaries must stay
behaviorally compatible. A fake adapter is currently selected. It returns a
bundled synthetic MP4 and must never be presented as AI-generated evidence.

---

## 1. The Interface

```ts
export type GenerationMode = 'text' | 'image' | 'text_image';

export interface GenerationInput {
  mode: GenerationMode;
  prompt?: string;              // present for 'text' and 'text_image'
  imageUrl?: string;            // signed, provider-readable, short-lived
  durationSeconds?: number;
  aspectRatio?: '16:9' | '9:16' | '1:1';
  seed?: number;
}

export interface SubmitResult {
  jobId: string;
  rawResponse: unknown;         // logged verbatim (redacted) to generation_logs
}

export type JobState =
  | { status: 'running' }
  | { status: 'succeeded'; videoUrl: string; thumbnailUrl?: string; durationSeconds?: number }
  | { status: 'failed'; reason: ProviderFailure; message: string };

export interface ProviderCapabilities {
  name: string;
  supportedModes: GenerationMode[];
  durationRange: { min: number; max: number };
  aspectRatios: string[];
  maxPromptLength: number;
  maxImageBytes: number;
  acceptedImageTypes: string[];
  typicalLatencySeconds: number;
  timeoutSeconds: number;
}

export interface VideoProvider {
  readonly capabilities: ProviderCapabilities;
  submit(input: GenerationInput): Promise<SubmitResult>;
  getStatus(jobId: string): Promise<JobState>;
  cancel?(jobId: string): Promise<void>;
  verifyWebhook?(headers: Record<string, string>, rawBody: Buffer): boolean;
}
```

`cancel` and `verifyWebhook` are optional because not every provider offers them. Callers must feature-detect rather than assume.

---

## 2. Normalization Rules

Providers disagree about almost everything. The adapter absorbs the differences so the rest of the system sees one model.

| Concern | Rule |
|---|---|
| **Image delivery** | Cretona always passes a **signed URL** to our Storage object. An adapter for a provider that requires raw upload or base64 does that fetch-and-forward itself. |
| **Prompt limits** | The adapter truncates to `maxPromptLength` only if the provider hard-fails otherwise; otherwise it rejects up front with a validation error so the user sees a clear message rather than a silently altered prompt. |
| **Unsupported mode** | Validated before submit against `supportedModes`, returning `400 VALIDATION_ERROR` — never a `502` after the fact. |
| **Duration / aspect ratio** | Clamped into the provider's range and recorded on the project as the value actually used. |
| **Status vocabulary** | Every provider's status strings map into exactly the three `JobState` variants. An unrecognized status is treated as `running` until the timeout, then `failed`. |
| **Result URL** | Always transient. The caller re-hosts; the adapter never persists anything. |

### 2.1 Failure taxonomy

```ts
export type ProviderFailure =
  | 'content_policy'    // prompt or image rejected by provider moderation
  | 'invalid_input'     // provider says the request was malformed
  | 'quota'             // our provider account is out of credit or rate-limited
  | 'timeout'           // exceeded capabilities.timeoutSeconds
  | 'provider_error'    // upstream 5xx or internal failure
  | 'unknown';
```

Each maps to a user-readable `error_message` on the project. Users see the mapped text; raw provider payloads go to `generation_logs` only (NFR-4.2).

| Failure | Message shown to the user | Retryable |
|---|---|---|
| `content_policy` | "This prompt or image was rejected by the content filter. Try rewording it." | no |
| `invalid_input` | "That combination of settings isn't supported. Adjust and try again." | no |
| `quota` | "Generation is temporarily unavailable. Please try again later." | yes, later |
| `timeout` | "This generation took too long and was cancelled." | yes |
| `provider_error` | "The video service had a problem. Please try again." | yes |
| `unknown` | "Something went wrong generating this video." | yes |

Only retryable failures are offered a retry button (FR-2.11), and retrying consumes quota.

---

## 3. Registry

```ts
const registry = new Map<string, VideoProvider>();

export function registerProvider(p: VideoProvider) {
  registry.set(p.capabilities.name, p);
}

export function getProvider(name?: string): VideoProvider {
  const key = name ?? config.DEFAULT_AI_PROVIDER;
  const provider = registry.get(key);
  if (!provider) throw new AppError('VALIDATION_ERROR', `Unknown provider: ${key}`);
  return provider;
}
```

Registration happens once at boot, gated on the presence of that provider's API key — a provider whose key is absent is simply not registered, so it can never be selected. `GET /me` can expose the registered set later so the app's provider picker (FR-2.12) is driven by the server, not hardcoded.

---

## 4. Retry and Timeout Policy

| Situation | Behaviour |
|---|---|
| Submit fails with 5xx / network error | 3 attempts, exponential backoff (1 s, 4 s, 16 s) with jitter |
| Submit fails with 4xx | no retry — it will fail identically |
| Poll fails transiently | logged, retried on the next tick; 5 consecutive failures ⇒ `failed` |
| No terminal state by `timeoutSeconds` | `failed` with `timeout` |
| Result download fails | 3 attempts, then `failed` with `provider_error` |

Retries are counted in `video_projects.attempt_count`. Every attempt writes a `generation_logs` row so cost is reconcilable against the provider's own billing.

---

## 5. Logging and Redaction

Every provider interaction writes one `generation_logs` row (`event` = `submit` · `poll` · `webhook` · `download` · `error`).

Redaction happens **in the adapter, before the row is built** — not at the logger — so a key cannot leak through a code path that skips the logger:

- Strip `Authorization`, `X-Api-Key`, and any header matching `/key|token|secret/i`.
- Strip query parameters matching the same pattern from logged URLs.
- Replace signed URLs with their object path.
- Truncate `response` to 32 KB.

---

## 6. Adding a Provider — Checklist

1. Create `backend-fastapi/app/providers/<name>.py` implementing the normalized provider protocol. Keep a TypeScript adapter only when maintaining the Express reference.
2. Fill in `capabilities` honestly — the values are used for validation, not documentation.
3. Map the provider's statuses to `JobState` and its errors to `ProviderFailure`.
4. Add `<NAME>_API_KEY` to config validation and `.env.example`.
5. Register it at boot, gated on the key being present.
6. Write unit tests with recorded HTTP fixtures covering: successful submit, running poll, succeeded poll, each failure mode, and a malformed response.
7. Run the end-to-end path once against the real API with a throwaway prompt, and confirm the log rows contain no credentials.

Nothing in `controllers/`, `routes/`, or the Android app changes. If it does, the abstraction leaked and the interface needs fixing instead.

---

## 7. Provider Notes

Filled in as each is integrated. Capability values must be verified against live documentation at implementation time rather than assumed — providers change limits and pricing frequently.

| Provider | Status | Modes | Notes |
|---|---|---|---|
| Cretona fake | integrated | deterministic test fixture | Contract/runtime evidence only; not AI output |
| Ollama + Qwen3-4B | live prompt proof passed | text | FastAPI returned `usedFallback=false`; this enhances prompts and does not generate video |
| LTX-Video 2B Q8 | rejected by EXP-005 pre-screen | text, image | Official dependency/runtime envelope does not fit the measured Ampere 8 GB VRAM/16 GB RAM host; weights were intentionally not downloaded |
| FramePack F1 | runtime installed; inference blocked | image | Exact source and weights are pinned; resource preflight and weight-license review must pass before the first run or profile selection |
| Real local text-to-video | unselected | text | Wan2.1 1.3B and CogVideoX 2B are research candidates only; neither is an accepted adapter |
| Runway | not selected | text, image, text+image | Paid path; superseded as launch default by ADR-009 |
| Kling | not selected | text, image, text+image | Paid path; not compatible with the chosen zero-additional-spend baseline |
| Pika | not started | text, image | |
| Luma | not started | text, image | |
| Google Veo | not started | text, image | |

The old paid launch assumption in ADR-004 is superseded by the evidence gate in
[ADR-009](adr/ADR-009-zero-spend-provider-gate.md). Qwen is the proven prompt
LLM, but no real video model is selected until EXP-005 succeeds on the actual
laptop.
