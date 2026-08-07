import type { ProjectStatus } from '@prisma/client';
import { conflict, notFound } from '../../lib/errors.js';
import { logger } from '../../lib/logger.js';
import { prisma } from '../../lib/prisma.js';
import { buildPage, cursorFilter, decodeCursor, type Page } from '../../lib/pagination.js';
import { env } from '../../config/env.js';
import { recordGenerationLog } from '../generationLog.service.js';
import { assertQuotaAvailable } from '../quota.service.js';
import {
  assertOwnsPath,
  removeObjects,
  signedUploadRead,
} from '../storage.service.js';
import { failureMessage, isRetryable } from '../ai/failures.js';
import { getProvider, normalizeInput } from '../ai/registry.js';
import { ProviderError, type AspectRatio, type GenerationMode } from '../ai/types.js';
import { projectSelection, toProjectDto, toProjectDtos, type ProjectDto } from './dto.js';
import { assertTransition } from './transitions.js';

export interface CreateProjectInput {
  title?: string;
  prompt?: string;
  imagePath?: string;
  provider?: string;
  options?: { durationSeconds?: number; aspectRatio?: AspectRatio };
  idempotencyKey?: string;
}

/** The three generation modes are a function of which inputs are present. */
export function resolveMode(prompt?: string, imagePath?: string): GenerationMode {
  if (prompt && imagePath) return 'text_image';
  if (imagePath) return 'image';
  return 'text';
}

function deriveTitle(prompt?: string): string {
  if (!prompt) return 'Untitled generation';
  const trimmed = prompt.trim();
  return trimmed.length <= 120 ? trimmed : `${trimmed.slice(0, 117)}...`;
}

export async function createProject(
  userId: string,
  input: CreateProjectInput,
): Promise<ProjectDto> {
  // Replaying a request must not create a second project or charge quota twice
  // (API_CONTRACT §1.5). Checked before anything else so a retried submit is
  // cheap.
  if (input.idempotencyKey) {
    const existing = await prisma.videoProject.findFirst({
      where: { userId, idempotencyKey: input.idempotencyKey },
      select: projectSelection,
    });
    if (existing) return toProjectDto(existing);
  }

  if (!input.prompt && !input.imagePath) {
    throw conflict('Provide a prompt, an image, or both.');
  }

  // A path is only usable by the person who uploaded it — otherwise a user
  // could attach someone else's image to their own project.
  if (input.imagePath) assertOwnsPath(userId, input.imagePath);

  const provider = getProvider(input.provider);
  const mode = resolveMode(input.prompt, input.imagePath);

  const normalized = normalizeInput(provider, {
    mode,
    ...(input.prompt ? { prompt: input.prompt } : {}),
    ...(input.options?.durationSeconds
      ? { durationSeconds: input.options.durationSeconds }
      : {}),
    ...(input.options?.aspectRatio ? { aspectRatio: input.options.aspectRatio } : {}),
  });

  // Before the provider call, never after: checking afterwards is accounting,
  // not control (ADR-007).
  await assertQuotaAvailable(userId);

  const project = await prisma.videoProject.create({
    data: {
      userId,
      title: input.title?.trim() || deriveTitle(input.prompt),
      prompt: input.prompt ?? null,
      imagePath: input.imagePath ?? null,
      provider: provider.capabilities.name,
      status: 'pending',
      durationSeconds: normalized.durationSeconds ?? null,
      idempotencyKey: input.idempotencyKey ?? null,
    },
    select: projectSelection,
  });

  // Submission happens outside the create so a slow provider cannot hold a
  // database transaction open. The project already exists as `pending`, so a
  // crash here leaves a row the poller or the user can act on.
  void submitToProvider(project.id, userId, normalized, input.imagePath ?? null).catch(
    (error: unknown) => {
      logger.error({ err: error, projectId: project.id }, 'Background submit failed');
    },
  );

  return toProjectDto(project);
}

async function submitToProvider(
  projectId: string,
  userId: string,
  input: Parameters<typeof normalizeInput>[1],
  imagePath: string | null,
): Promise<void> {
  const project = await prisma.videoProject.findUnique({
    where: { id: projectId },
    select: { provider: true, status: true },
  });
  if (!project) return;

  const provider = getProvider(project.provider);

  try {
    // Providers fetch the image themselves, so it must be a URL they can read.
    const imageUrl = imagePath ? await signedUploadRead(imagePath) : null;

    const result = await provider.submit({
      ...input,
      ...(imageUrl ? { imageUrl } : {}),
    });

    await recordGenerationLog({
      projectId,
      provider: project.provider,
      event: 'submit',
      requestId: result.jobId,
      request: { ...input, imageUrl: imagePath },
      response: result.rawResponse,
    });

    assertTransition(project.status, 'generating');

    await prisma.videoProject.update({
      where: { id: projectId },
      data: {
        status: 'generating',
        providerJobId: result.jobId,
        attemptCount: { increment: 1 },
      },
    });
  } catch (error) {
    const reason = error instanceof ProviderError ? error.reason : 'provider_error';

    await recordGenerationLog({
      projectId,
      provider: project.provider,
      event: 'error',
      request: { ...input, imageUrl: imagePath },
      response: { message: (error as Error).message },
    });

    await failProject(projectId, reason, failureMessage(reason));
    logger.error({ err: error, projectId, userId }, 'Provider submission failed');
  }
}

/** The single place a project becomes `failed`. */
export async function failProject(
  projectId: string,
  code: string,
  message: string,
): Promise<void> {
  await prisma.videoProject.updateMany({
    where: { id: projectId, status: { in: ['pending', 'generating'] } },
    data: {
      status: 'failed',
      errorCode: code,
      errorMessage: message,
      completedAt: new Date(),
    },
  });
}

export async function listProjects(
  userId: string,
  params: { limit: number; cursor?: string; status?: ProjectStatus },
): Promise<Page<ProjectDto>> {
  const cursor = decodeCursor(params.cursor);

  const rows = await prisma.videoProject.findMany({
    where: {
      userId,
      deletedAt: null,
      ...(params.status ? { status: params.status } : {}),
      ...cursorFilter(cursor),
    },
    select: projectSelection,
    orderBy: [{ createdAt: 'desc' }, { id: 'desc' }],
    take: params.limit + 1,
  });

  const page = buildPage(rows, params.limit);
  return { items: await toProjectDtos(page.items), page: page.page };
}

/**
 * Someone else's project reports 404, never 403 — existence is not disclosed
 * (API_CONTRACT §1.3).
 */
export async function getProject(userId: string, projectId: string): Promise<ProjectDto> {
  const row = await prisma.videoProject.findFirst({
    where: { id: projectId, userId, deletedAt: null },
    select: projectSelection,
  });

  if (!row) throw notFound('Project');

  return toProjectDto(row);
}

export async function deleteProject(userId: string, projectId: string): Promise<void> {
  const row = await prisma.videoProject.findFirst({
    where: { id: projectId, userId, deletedAt: null },
    select: { id: true, status: true, imagePath: true, videoPath: true, thumbnailPath: true },
  });

  if (!row) throw notFound('Project');

  // Deleting mid-generation would orphan a provider job that still bills us
  // and would later write to a row that no longer exists.
  if (row.status === 'generating') {
    throw conflict('This project is still generating. Wait for it to finish first.');
  }

  await prisma.videoProject.update({
    where: { id: row.id },
    data: { deletedAt: new Date() },
  });

  // Media is removed immediately even though the row is only soft-deleted:
  // storage costs money and the user asked for it to be gone.
  await Promise.all([
    removeObjects(env.SUPABASE_UPLOADS_BUCKET, [row.imagePath]),
    removeObjects(env.SUPABASE_VIDEOS_BUCKET, [row.videoPath, row.thumbnailPath]),
  ]);
}

export async function retryProject(userId: string, projectId: string): Promise<ProjectDto> {
  const row = await prisma.videoProject.findFirst({
    where: { id: projectId, userId, deletedAt: null },
    select: { ...projectSelection, attemptCount: true },
  });

  if (!row) throw notFound('Project');

  assertTransition(row.status, 'pending');

  if (!isRetryable(row.errorCode as never)) {
    throw conflict('This generation cannot be retried — the request itself was rejected.');
  }

  if (row.attemptCount >= env.MAX_GENERATION_ATTEMPTS) {
    throw conflict('This generation has been retried too many times.');
  }

  // A retry is a real provider call, so it costs an allowance (ADR-007).
  await assertQuotaAvailable(userId);

  const updated = await prisma.videoProject.update({
    where: { id: row.id },
    data: {
      status: 'pending',
      errorCode: null,
      errorMessage: null,
      completedAt: null,
      providerJobId: null,
    },
    select: projectSelection,
  });

  const provider = getProvider(updated.provider);
  const normalized = normalizeInput(provider, {
    mode: resolveMode(updated.prompt ?? undefined, updated.imagePath ?? undefined),
    ...(updated.prompt ? { prompt: updated.prompt } : {}),
    ...(updated.durationSeconds ? { durationSeconds: updated.durationSeconds } : {}),
  });

  void submitToProvider(updated.id, userId, normalized, updated.imagePath).catch(
    (error: unknown) => {
      logger.error({ err: error, projectId: updated.id }, 'Retry submit failed');
    },
  );

  return toProjectDto(updated);
}
