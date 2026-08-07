import { Router } from 'express';
import { adminRouter } from './admin.routes.js';
import { healthRouter } from './health.routes.js';
import { meRouter } from './me.routes.js';

/**
 * API v1 router (API_CONTRACT.md §6 — the path carries the major version).
 *
 * Still to mount:
 *   /uploads/sign       P2-14
 *   /projects           P2-10 … P2-13
 */
export const apiRouter = Router();

apiRouter.use(healthRouter);
apiRouter.use(meRouter);
apiRouter.use(adminRouter);
