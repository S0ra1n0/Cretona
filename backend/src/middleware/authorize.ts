import type { NextFunction, Request, Response } from 'express';
import { forbidden, unauthenticated } from '../lib/errors.js';

export type RoleName = 'user' | 'admin';

/**
 * Role gate (P2-5).
 *
 * Must run after `requireAuth`, which is what populates `req.user`. Hiding a
 * screen in the app is not authorization; this is (SECURITY.md §3).
 */
export function requireRole(...allowed: RoleName[]) {
  return function authorize(req: Request, _res: Response, next: NextFunction): void {
    if (!req.user) {
      return next(unauthenticated());
    }

    if (!allowed.includes(req.user.role)) {
      return next(forbidden());
    }

    next();
  };
}

export const requireAdmin = requireRole('admin');
