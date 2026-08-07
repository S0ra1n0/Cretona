import type { Request } from 'express';
import rateLimit, { ipKeyGenerator } from 'express-rate-limit';
import { env } from '../config/env.js';
import { AppError } from '../lib/errors.js';

/**
 * Rate limiting (P2-18), per API_CONTRACT.md §5.
 *
 * This protects against bursts. It is NOT the spend control — that is the
 * per-user generation quota (ADR-007), which is enforced separately in the
 * service layer. 5 requests/minute is still thousands of paid generations a
 * day, so rate limiting alone would not protect the budget.
 */
function keyByUserOrIp(req: Request): string {
  // Authenticated callers are limited per account, so sharing an IP (office
  // Wi-Fi, mobile carrier NAT) does not make one user throttle another.
  if (req.user?.id) return `user:${req.user.id}`;
  return `ip:${ipKeyGenerator(req.ip ?? '')}`;
}

const shared = {
  standardHeaders: 'draft-7',
  legacyHeaders: true, // X-RateLimit-* as documented in the API contract
  keyGenerator: keyByUserOrIp,
  handler: (_req: Request, _res: unknown, next: (err?: unknown) => void) => {
    next(new AppError('RATE_LIMITED', 'Too many requests. Please slow down.'));
  },
} as const;

/** Default ceiling for authenticated traffic. */
export const defaultLimiter = rateLimit({
  ...shared,
  windowMs: 60_000,
  limit: env.RATE_LIMIT_DEFAULT_PER_MIN,
});

/** Tighter ceiling on the endpoints that cost money downstream. */
export const generationLimiter = rateLimit({
  ...shared,
  windowMs: 60_000,
  limit: env.RATE_LIMIT_GENERATION_PER_MIN,
});

/** Unauthenticated traffic, keyed by IP only. */
export const publicLimiter = rateLimit({
  ...shared,
  windowMs: 60_000,
  limit: 60,
});
