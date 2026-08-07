/**
 * The provider boundary (P3-1), per docs/AI_PROVIDER_SPEC.md.
 *
 * Nothing above services/ai may know which provider is in use. If adding a
 * provider requires a change outside this folder, the abstraction has leaked
 * and the interface is what needs fixing.
 */

export type GenerationMode = 'text' | 'image' | 'text_image';

export interface GenerationInput {
  mode: GenerationMode;
  /** Present for 'text' and 'text_image'. */
  prompt?: string;
  /** Signed, provider-readable, short-lived. Present for the image modes. */
  imageUrl?: string;
  durationSeconds?: number;
  aspectRatio?: AspectRatio;
  seed?: number;
}

export type AspectRatio = '16:9' | '9:16' | '1:1';

export interface SubmitResult {
  jobId: string;
  /** Logged verbatim (after redaction) to generation_logs. */
  rawResponse: unknown;
}

export type JobState =
  | { status: 'running' }
  | {
      status: 'succeeded';
      videoUrl: string;
      thumbnailUrl?: string;
      durationSeconds?: number;
    }
  | { status: 'failed'; reason: ProviderFailure; message: string };

/**
 * Failure taxonomy (AI_PROVIDER_SPEC §2.1). Stored on the project as
 * `error_code`, because quota accounting has to distinguish our failures from
 * the user's (ADR-007).
 */
export type ProviderFailure =
  | 'content_policy'
  | 'invalid_input'
  | 'quota'
  | 'timeout'
  | 'provider_error'
  | 'unknown';

export interface ProviderCapabilities {
  name: string;
  supportedModes: GenerationMode[];
  durationRange: { min: number; max: number };
  aspectRatios: AspectRatio[];
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
  /** Optional: not every provider supports cancellation. Feature-detect. */
  cancel?(jobId: string): Promise<void>;
  /** Optional: only providers we accept webhooks from implement this. */
  verifyWebhook?(headers: Record<string, string>, rawBody: Buffer): boolean;
}

/** Thrown by adapters; carries the taxonomy so callers need not parse messages. */
export class ProviderError extends Error {
  readonly reason: ProviderFailure;
  readonly httpStatus?: number;

  constructor(reason: ProviderFailure, message: string, httpStatus?: number) {
    super(message);
    this.name = 'ProviderError';
    this.reason = reason;
    this.httpStatus = httpStatus;
  }
}
