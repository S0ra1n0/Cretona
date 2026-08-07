import { Router } from 'express';
import { healthRouter } from './health.routes.js';

/**
 * API v1 router (API_CONTRACT.md §6 — the path carries the major version).
 *
 * Routers are mounted here as each phase lands:
 *   /me, /uploads       P2-9, P2-14
 *   /projects           P2-10 … P2-13
 *   /admin              P2-15 … P2-17
 */
export const apiRouter = Router();

apiRouter.use(healthRouter);
