import type { ProviderFailure } from './types.js';

/**
 * Failure presentation (AI_PROVIDER_SPEC §2.1).
 *
 * Users see these strings; raw provider payloads go to generation_logs only
 * (NFR-4.2). Keeping the mapping in one table means a new failure mode cannot
 * reach a user as an unhandled provider message.
 */
interface FailurePresentation {
  message: string;
  /** Whether offering a retry is honest. A retry consumes quota (ADR-007). */
  retryable: boolean;
}

const PRESENTATION: Record<ProviderFailure, FailurePresentation> = {
  content_policy: {
    message: 'This prompt or image was rejected by the content filter. Try rewording it.',
    retryable: false,
  },
  invalid_input: {
    message: "That combination of settings isn't supported. Adjust and try again.",
    retryable: false,
  },
  quota: {
    message: 'Generation is temporarily unavailable. Please try again later.',
    retryable: true,
  },
  timeout: {
    message: 'This generation took too long and was cancelled.',
    retryable: true,
  },
  provider_error: {
    message: 'The video service had a problem. Please try again.',
    retryable: true,
  },
  unknown: {
    message: 'Something went wrong generating this video.',
    retryable: true,
  },
};

export function failureMessage(reason: ProviderFailure): string {
  return PRESENTATION[reason].message;
}

export function isRetryable(reason: ProviderFailure | null | undefined): boolean {
  if (!reason) return false;
  return PRESENTATION[reason]?.retryable ?? false;
}

/**
 * Failures caused by our infrastructure rather than the user's request, and so
 * excluded from quota. `content_policy` is deliberately absent: the provider
 * call was made and billed.
 */
export const NOT_CHARGED_TO_QUOTA: ProviderFailure[] = ['provider_error', 'timeout'];
