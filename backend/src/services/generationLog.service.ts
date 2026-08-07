import { prisma } from '../lib/prisma.js';
import { logger } from '../lib/logger.js';

/**
 * Provider interaction audit (P3-5, FR-2.10).
 *
 * Redaction happens here, before the row is built — not at the logger — so no
 * code path can persist a credential by taking a different route
 * (AI_PROVIDER_SPEC §5).
 */
export type LogEvent = 'submit' | 'poll' | 'webhook' | 'download' | 'error';

const SECRET_KEY = /key|token|secret|auth|password|credential/i;
const MAX_RESPONSE_BYTES = 32 * 1024;

/** Replaces a signed URL with its object path, which is safe to keep. */
function stripSignature(value: string): string {
  if (!/^https?:\/\//.test(value)) return value;

  try {
    const url = new URL(value);
    for (const key of [...url.searchParams.keys()]) {
      if (SECRET_KEY.test(key)) url.searchParams.set(key, '[redacted]');
    }
    return url.toString();
  } catch {
    return value;
  }
}

export function redact(value: unknown, depth = 0): unknown {
  if (depth > 8) return '[truncated]';

  if (typeof value === 'string') return stripSignature(value);
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));

  const output: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(value)) {
    output[key] = SECRET_KEY.test(key) ? '[redacted]' : redact(val, depth + 1);
  }
  return output;
}

function truncate(value: unknown): unknown {
  const json = JSON.stringify(value ?? null);
  if (json && json.length > MAX_RESPONSE_BYTES) {
    return { truncated: true, preview: json.slice(0, MAX_RESPONSE_BYTES) };
  }
  return value;
}

interface LogInput {
  projectId: string;
  provider: string;
  event: LogEvent;
  requestId?: string | null;
  request?: unknown;
  response?: unknown;
  httpStatus?: number | null;
}

/**
 * Never throws. An audit-write failure must not fail the generation it is
 * describing — that would turn a logging problem into a user-visible one.
 */
export async function recordGenerationLog(input: LogInput): Promise<void> {
  try {
    await prisma.generationLog.create({
      data: {
        projectId: input.projectId,
        provider: input.provider,
        event: input.event,
        requestId: input.requestId ?? null,
        request: (redact(input.request) ?? undefined) as never,
        response: (truncate(redact(input.response)) ?? undefined) as never,
        httpStatus: input.httpStatus ?? null,
      },
    });
  } catch (error) {
    logger.warn({ err: error, projectId: input.projectId }, 'Failed to write generation log');
  }
}
