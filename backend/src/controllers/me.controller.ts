import type { Request, Response } from 'express';
import { unauthenticated } from '../lib/errors.js';
import { getMe, updateMe } from '../services/users.service.js';

/**
 * Controllers translate HTTP and nothing else — no business rules, no Prisma
 * (ARCHITECTURE.md §4).
 */

export async function getProfile(req: Request, res: Response): Promise<void> {
  if (!req.user) throw unauthenticated();

  res.status(200).json(await getMe(req.user.id));
}

export async function patchProfile(req: Request, res: Response): Promise<void> {
  if (!req.user) throw unauthenticated();

  res.status(200).json(await updateMe(req.user.id, req.body));
}
