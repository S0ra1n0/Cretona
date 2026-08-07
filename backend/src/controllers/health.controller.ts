import type { Request, Response } from 'express';
import { checkDatabase } from '../lib/prisma.js';

const VERSION = '0.1.0';

/**
 * GET /health (P2-8).
 *
 * Liveness only, per API_CONTRACT.md §2.1 — kept unauthenticated and free of
 * dependencies so a platform health check does not fail because the database
 * is briefly unavailable.
 */
export function health(_req: Request, res: Response): void {
  res.status(200).json({ status: 'ok', version: VERSION });
}

/**
 * GET /health/ready — readiness, including the database.
 *
 * Separate from liveness on purpose: a failing dependency should stop traffic
 * being routed here, not cause the process to be restarted.
 */
export async function ready(_req: Request, res: Response): Promise<void> {
  const database = await checkDatabase();

  res.status(database ? 200 : 503).json({
    status: database ? 'ok' : 'degraded',
    version: VERSION,
    checks: { database },
  });
}
