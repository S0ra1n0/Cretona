import type { Request, Response } from 'express';
import { unauthenticated } from '../lib/errors.js';
import { getStats, listUsers, updateUser } from '../services/admin.service.js';

export async function getUsers(req: Request, res: Response): Promise<void> {
  const query = req.query as unknown as Parameters<typeof listUsers>[0];

  res.status(200).json(await listUsers(query));
}

export async function patchUser(req: Request, res: Response): Promise<void> {
  if (!req.user) throw unauthenticated();

  res.status(200).json(await updateUser(req.user.id, req.params['id'] as string, req.body));
}

export async function getStatistics(req: Request, res: Response): Promise<void> {
  const { days } = req.query as unknown as { days: number };

  res.status(200).json(await getStats(days));
}
