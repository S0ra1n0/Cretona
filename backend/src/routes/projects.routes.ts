import { Router } from 'express';
import {
  getOneProject,
  getProjects,
  postProject,
  postRetry,
  postUploadSign,
  removeProject,
} from '../controllers/projects.controller.js';
import { requireAuth } from '../middleware/authenticate.js';
import { defaultLimiter, generationLimiter } from '../middleware/rateLimit.js';
import { validate } from '../middleware/validate.js';
import {
  createProjectSchema,
  listProjectsSchema,
  signUploadSchema,
  uuidParamSchema,
} from '../schemas/index.js';

export const projectsRouter = Router();

// The two endpoints that cost money downstream get the tighter limiter.
projectsRouter.post(
  '/projects',
  ...requireAuth,
  generationLimiter,
  validate({ body: createProjectSchema }),
  postProject,
);

projectsRouter.post(
  '/projects/:id/retry',
  ...requireAuth,
  generationLimiter,
  validate({ params: uuidParamSchema }),
  postRetry,
);

projectsRouter.get(
  '/projects',
  ...requireAuth,
  defaultLimiter,
  validate({ query: listProjectsSchema }),
  getProjects,
);

projectsRouter.get(
  '/projects/:id',
  ...requireAuth,
  defaultLimiter,
  validate({ params: uuidParamSchema }),
  getOneProject,
);

projectsRouter.delete(
  '/projects/:id',
  ...requireAuth,
  defaultLimiter,
  validate({ params: uuidParamSchema }),
  removeProject,
);

projectsRouter.post(
  '/uploads/sign',
  ...requireAuth,
  defaultLimiter,
  validate({ body: signUploadSchema }),
  postUploadSign,
);
