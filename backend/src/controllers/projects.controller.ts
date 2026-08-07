import type { Request, Response } from 'express';
import { unauthenticated } from '../lib/errors.js';
import {
  createProject,
  deleteProject,
  getProject,
  listProjects,
  retryProject,
} from '../services/projects/projects.service.js';
import { createSignedUpload } from '../services/storage.service.js';

function callerId(req: Request): string {
  if (!req.user) throw unauthenticated();
  return req.user.id;
}

export async function postProject(req: Request, res: Response): Promise<void> {
  const idempotencyKey = req.header('idempotency-key');

  const project = await createProject(callerId(req), {
    ...req.body,
    ...(idempotencyKey ? { idempotencyKey } : {}),
  });

  res.status(201).json(project);
}

export async function getProjects(req: Request, res: Response): Promise<void> {
  const query = req.query as unknown as Parameters<typeof listProjects>[1];

  res.status(200).json(await listProjects(callerId(req), query));
}

export async function getOneProject(req: Request, res: Response): Promise<void> {
  res.status(200).json(await getProject(callerId(req), req.params['id'] as string));
}

export async function removeProject(req: Request, res: Response): Promise<void> {
  await deleteProject(callerId(req), req.params['id'] as string);

  res.status(204).send();
}

export async function postRetry(req: Request, res: Response): Promise<void> {
  const project = await retryProject(callerId(req), req.params['id'] as string);

  res.status(202).json(project);
}

export async function postUploadSign(req: Request, res: Response): Promise<void> {
  const { contentType, sizeBytes } = req.body as { contentType: string; sizeBytes: number };

  res.status(201).json(await createSignedUpload(callerId(req), contentType, sizeBytes));
}
