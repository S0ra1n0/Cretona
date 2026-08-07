import { Router } from 'express';
import { getStatistics, getUsers, patchUser } from '../controllers/admin.controller.js';
import { requireAuth } from '../middleware/authenticate.js';
import { requireAdmin } from '../middleware/authorize.js';
import { defaultLimiter } from '../middleware/rateLimit.js';
import { validate } from '../middleware/validate.js';
import {
  adminUserListSchema,
  patchAdminUserSchema,
  statsQuerySchema,
  uuidParamSchema,
} from '../schemas/index.js';

/**
 * Every route here is admin-only. The gate is applied per route rather than
 * with router.use() so it is visible at each definition — a route added later
 * cannot silently inherit or miss it.
 */
export const adminRouter = Router();

adminRouter.get(
  '/admin/users',
  ...requireAuth,
  requireAdmin,
  defaultLimiter,
  validate({ query: adminUserListSchema }),
  getUsers,
);

adminRouter.patch(
  '/admin/users/:id',
  ...requireAuth,
  requireAdmin,
  defaultLimiter,
  validate({ params: uuidParamSchema, body: patchAdminUserSchema }),
  patchUser,
);

adminRouter.get(
  '/admin/stats',
  ...requireAuth,
  requireAdmin,
  defaultLimiter,
  validate({ query: statsQuerySchema }),
  getStatistics,
);
