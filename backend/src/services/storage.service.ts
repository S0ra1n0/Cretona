import { createClient } from '@supabase/supabase-js';
import { AppError, forbidden, validationError } from '../lib/errors.js';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';

/**
 * Supabase Storage (P3-8, P2-14).
 *
 * Uses the service_role key, which bypasses RLS — so every path here is
 * checked against the caller in code. Storage policies are the second line of
 * defence, not the first (SECURITY.md §4).
 */
const storage = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
}).storage;

export const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

const EXTENSION: Record<string, string> = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
};

/**
 * Object keys embed the owner as the first segment. That is what lets Storage
 * policies authorize on the path prefix, and what makes ownership checkable
 * without a database round trip.
 */
export function uploadPath(userId: string, contentType: string): string {
  const ext = EXTENSION[contentType] ?? 'bin';
  const day = new Date().toISOString().slice(0, 10);
  return `${userId}/${day}/${crypto.randomUUID()}.${ext}`;
}

export function videoPath(userId: string, projectId: string): string {
  return `${userId}/${projectId}/video.mp4`;
}

/**
 * Rejects a path whose owner segment is not the caller.
 *
 * Without this a user could attach someone else's uploaded image to their own
 * project simply by passing its path (SECURITY.md §4).
 */
export function assertOwnsPath(userId: string, path: string): void {
  const owner = path.split('/')[0];
  if (owner !== userId) {
    throw forbidden('That file does not belong to you.');
  }
}

export interface SignedUpload {
  uploadUrl: string;
  storagePath: string;
  token: string;
  expiresAt: string;
}

export async function createSignedUpload(
  userId: string,
  contentType: string,
  sizeBytes: number,
): Promise<SignedUpload> {
  if (!ALLOWED_IMAGE_TYPES.includes(contentType as (typeof ALLOWED_IMAGE_TYPES)[number])) {
    throw validationError('That image type is not supported.', [
      { field: 'body.contentType', issue: 'unsupported_type' },
    ]);
  }

  if (sizeBytes > MAX_IMAGE_BYTES) {
    throw new AppError('PAYLOAD_TOO_LARGE', 'Images must be 10 MB or smaller.');
  }

  const path = uploadPath(userId, contentType);
  const { data, error } = await storage
    .from(env.SUPABASE_UPLOADS_BUCKET)
    .createSignedUploadUrl(path);

  if (error || !data) {
    logger.error({ err: error, path }, 'Failed to create signed upload URL');
    throw new AppError('INTERNAL_ERROR', 'Could not prepare the upload.');
  }

  return {
    uploadUrl: data.signedUrl,
    storagePath: path,
    token: data.token,
    // Supabase signed upload URLs are valid for two hours.
    expiresAt: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
  };
}

/**
 * Read URLs are minted per response and never persisted — they expire, so a
 * stored URL is a guaranteed-stale link (API_CONTRACT §3.1).
 */
export async function signedReadUrl(bucket: string, path: string | null): Promise<string | null> {
  if (!path) return null;

  const { data, error } = await storage
    .from(bucket)
    .createSignedUrl(path, env.SIGNED_URL_TTL_SECONDS);

  if (error || !data) {
    logger.warn({ err: error, bucket, path }, 'Failed to sign read URL');
    return null;
  }

  return data.signedUrl;
}

export const signedUploadRead = (path: string | null) =>
  signedReadUrl(env.SUPABASE_UPLOADS_BUCKET, path);

export const signedVideoRead = (path: string | null) =>
  signedReadUrl(env.SUPABASE_VIDEOS_BUCKET, path);

/**
 * Re-hosts a provider result (P3-8).
 *
 * Provider URLs expire, so persisting one guarantees a broken link within
 * days. The bytes are copied into our own bucket before the project is marked
 * completed.
 */
export async function rehostVideo(
  userId: string,
  projectId: string,
  sourceUrl: string,
): Promise<string> {
  const response = await fetch(sourceUrl);

  if (!response.ok) {
    throw new AppError('PROVIDER_ERROR', `Could not download the result (${response.status}).`);
  }

  const bytes = Buffer.from(await response.arrayBuffer());
  const path = videoPath(userId, projectId);

  const { error } = await storage.from(env.SUPABASE_VIDEOS_BUCKET).upload(path, bytes, {
    contentType: response.headers.get('content-type') ?? 'video/mp4',
    upsert: true,
  });

  if (error) {
    logger.error({ err: error, path }, 'Failed to store the generated video');
    throw new AppError('INTERNAL_ERROR', 'Could not store the generated video.');
  }

  return path;
}

/** Best-effort cleanup. A failure here must not block deleting the project. */
export async function removeObjects(bucket: string, paths: (string | null)[]): Promise<void> {
  const present = paths.filter((p): p is string => Boolean(p));
  if (present.length === 0) return;

  const { error } = await storage.from(bucket).remove(present);
  if (error) {
    logger.warn({ err: error, bucket, paths: present }, 'Failed to remove storage objects');
  }
}
