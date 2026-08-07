import { Router } from 'express';
import { adminRouter } from './admin.routes.js';
import { healthRouter } from './health.routes.js';
import { meRouter } from './me.routes.js';
import { projectsRouter } from './projects.routes.js';

/**
 * API v1 router (API_CONTRACT.md §6 — the path carries the major version).
 *
 * Still to mount: POST /webhooks/providers/:provider, once a provider we
 * accept webhooks from is implemented (ADR-003 defers this).
 */
export const apiRouter = Router();

apiRouter.use(healthRouter);
apiRouter.use(meRouter);
apiRouter.use(projectsRouter);
apiRouter.use(adminRouter);
