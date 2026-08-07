import { env } from '../config/env.js';
import { AppError } from '../lib/errors.js';
import { parseIsoDurationMs } from '../lib/duration.js';
import { prisma } from '../lib/prisma.js';

/**
 * Generation quota (ADR-007).
 *
 * This is the spend control. Rate limiting protects against bursts; only this
 * protects the budget, because 5 requests/minute is still thousands of paid
 * generations a day.
 */
export interface Quota {
  limit: number;
  used: number;
  remaining: number;
  resetsAt: string;
}

/**
 * Failures that were our problem, not the user's, and so do not consume an
 * allowance. `content_policy` is deliberately absent — the provider call was
 * made and billed, so it counts.
 */
const NOT_CHARGED = ['provider_error', 'timeout'] as const;

const WINDOW_MS = parseIsoDurationMs(env.GENERATION_QUOTA_WINDOW) ?? 86_400_000;

function windowStart(now = new Date()): Date {
  return new Date(now.getTime() - WINDOW_MS);
}

/**
 * Counts rows rather than maintaining a counter column: there is no counter to
 * drift out of sync and no reconciliation job. Indexed by
 * (user_id, created_at desc, error_code).
 */
export async function getQuota(userId: string, now = new Date()): Promise<Quota> {
  const since = windowStart(now);

  const counted = await prisma.videoProject.findMany({
    where: {
      userId,
      createdAt: { gte: since },
      deletedAt: null,
      NOT: { errorCode: { in: [...NOT_CHARGED] } },
    },
    select: { createdAt: true },
    orderBy: { createdAt: 'asc' },
  });

  const used = counted.length;
  const oldest = counted[0]?.createdAt;

  return {
    limit: env.GENERATION_QUOTA_LIMIT,
    used,
    remaining: Math.max(0, env.GENERATION_QUOTA_LIMIT - used),
    // When the oldest counted generation ages out, a slot frees up. With
    // nothing counted there is nothing to free, so report a full window ahead.
    resetsAt: new Date((oldest?.getTime() ?? now.getTime()) + WINDOW_MS).toISOString(),
  };
}

/**
 * Call before any provider request. Checking afterwards is accounting, not
 * control — it would not prevent the spend.
 */
export async function assertQuotaAvailable(userId: string): Promise<Quota> {
  const quota = await getQuota(userId);

  if (quota.remaining <= 0) {
    throw new AppError(
      'QUOTA_EXCEEDED',
      `You have used all ${quota.limit} generations for this period. More become available at ${quota.resetsAt}.`,
    );
  }

  return quota;
}
