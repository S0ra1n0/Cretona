import { Router } from 'express';
import { getProfile, patchProfile } from '../controllers/me.controller.js';
import { requireAuth } from '../middleware/authenticate.js';
import { defaultLimiter } from '../middleware/rateLimit.js';
import { validate } from '../middleware/validate.js';
import { patchMeSchema } from '../schemas/index.js';

export const meRouter = Router();

meRouter.get('/me', ...requireAuth, defaultLimiter, getProfile);

meRouter.patch(
  '/me',
  ...requireAuth,
  defaultLimiter,
  validate({ body: patchMeSchema }),
  patchProfile,
);
