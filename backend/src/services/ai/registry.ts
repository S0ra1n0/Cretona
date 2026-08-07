import { env } from '../../config/env.js';
import { validationError } from '../../lib/errors.js';
import type { GenerationInput, VideoProvider } from './types.js';

/**
 * Provider registry (P3-2).
 *
 * Registration is gated on the provider's API key being present, so a provider
 * without credentials cannot be selected — it simply does not exist as far as
 * the rest of the system is concerned.
 */
const registry = new Map<string, VideoProvider>();

export function registerProvider(provider: VideoProvider): void {
  registry.set(provider.capabilities.name, provider);
}

export function clearRegistry(): void {
  registry.clear();
}

export function registeredProviders(): string[] {
  return [...registry.keys()];
}

export function getProvider(name?: string): VideoProvider {
  const key = name ?? env.DEFAULT_AI_PROVIDER;
  const provider = registry.get(key);

  if (!provider) {
    throw validationError(
      `Provider "${key}" is not available.`,
      [{ field: 'body.provider', issue: 'unknown_provider' }],
    );
  }

  return provider;
}

/**
 * Validates a request against what the provider can actually do, before
 * submitting (P3-4).
 *
 * Rejecting up front returns 400 with a clear reason. Discovering it after
 * submission would surface as a 502 and burn a paid call for a request that
 * was never going to work.
 */
export function normalizeInput(provider: VideoProvider, input: GenerationInput): GenerationInput {
  const caps = provider.capabilities;

  if (!caps.supportedModes.includes(input.mode)) {
    throw validationError(
      `${caps.name} does not support ${input.mode.replace('_', ' + ')} generation.`,
      [{ field: 'body', issue: `unsupported_mode:${input.mode}` }],
    );
  }

  if (input.prompt && input.prompt.length > caps.maxPromptLength) {
    // Rejected rather than truncated: silently altering a prompt produces a
    // video the user did not ask for and cannot explain.
    throw validationError(
      `Prompt is too long for ${caps.name} (max ${caps.maxPromptLength} characters).`,
      [{ field: 'body.prompt', issue: 'too_long' }],
    );
  }

  if (input.aspectRatio && !caps.aspectRatios.includes(input.aspectRatio)) {
    throw validationError(
      `${caps.name} does not support a ${input.aspectRatio} aspect ratio.`,
      [{ field: 'body.options.aspectRatio', issue: 'unsupported' }],
    );
  }

  // Duration is clamped rather than rejected — an out-of-range value is a
  // preference, not a mistake, and the value actually used is recorded on the
  // project so the user is never misled about what they got.
  const duration = input.durationSeconds
    ? Math.min(Math.max(input.durationSeconds, caps.durationRange.min), caps.durationRange.max)
    : undefined;

  return { ...input, ...(duration === undefined ? {} : { durationSeconds: duration }) };
}
