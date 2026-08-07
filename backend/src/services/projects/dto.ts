import type { Prisma } from '@prisma/client';
import { signedUploadRead, signedVideoRead } from '../storage.service.js';

/**
 * Project wire shape (API_CONTRACT.md §3.1).
 *
 * Media URLs are signed here, per response, rather than stored — they expire,
 * so a persisted URL is a broken link waiting to happen.
 */
export const projectSelection = {
  id: true,
  userId: true,
  title: true,
  prompt: true,
  imagePath: true,
  videoPath: true,
  thumbnailPath: true,
  status: true,
  provider: true,
  errorMessage: true,
  errorCode: true,
  durationSeconds: true,
  createdAt: true,
  updatedAt: true,
  completedAt: true,
} satisfies Prisma.VideoProjectSelect;

export type ProjectRow = Prisma.VideoProjectGetPayload<{ select: typeof projectSelection }>;

export interface ProjectDto {
  id: string;
  title: string;
  prompt: string | null;
  imageUrl: string | null;
  videoUrl: string | null;
  thumbnailUrl: string | null;
  status: string;
  provider: string;
  errorMessage: string | null;
  errorCode: string | null;
  durationSeconds: number | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
}

export async function toProjectDto(row: ProjectRow): Promise<ProjectDto> {
  const [imageUrl, videoUrl, thumbnailUrl] = await Promise.all([
    signedUploadRead(row.imagePath),
    signedVideoRead(row.videoPath),
    signedVideoRead(row.thumbnailPath),
  ]);

  return {
    id: row.id,
    title: row.title,
    prompt: row.prompt,
    imageUrl,
    videoUrl,
    thumbnailUrl,
    status: row.status,
    provider: row.provider,
    errorMessage: row.errorMessage,
    errorCode: row.errorCode,
    durationSeconds: row.durationSeconds,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
    completedAt: row.completedAt?.toISOString() ?? null,
  };
}

export const toProjectDtos = (rows: ProjectRow[]) => Promise.all(rows.map(toProjectDto));
