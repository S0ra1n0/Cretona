import { z } from 'zod';

/**
 * Request schemas. Rules mirror docs/API_CONTRACT.md and the CHECK constraints
 * in docs/DATA_MODEL.md — if these disagree with the database, the database
 * wins and this is the bug.
 */

export const usernameSchema = z
  .string()
  .min(3, 'must be at least 3 characters')
  .max(30, 'must be at most 30 characters')
  .regex(/^[A-Za-z0-9_]+$/, 'may only contain letters, numbers, and underscores');

/** An unbounded page size is a denial-of-service vector (SECURITY.md §5). */
export const paginationSchema = z.object({
  limit: z.coerce.number().int().min(1).max(50).default(20),
  cursor: z.string().optional(),
});

export const patchMeSchema = z
  .object({
    username: usernameSchema.optional(),
  })
  .refine((v) => Object.keys(v).length > 0, {
    message: 'Provide at least one field to update.',
  });

export const adminUserListSchema = paginationSchema.extend({
  q: z.string().trim().min(1).max(120).optional(),
  role: z.enum(['user', 'admin']).optional(),
  isDisabled: z
    .union([z.boolean(), z.enum(['true', 'false'])])
    .transform((v) => (typeof v === 'boolean' ? v : v === 'true'))
    .optional(),
});

/**
 * Deliberately NOT z.string().uuid().
 *
 * Zod 4's .uuid() enforces the RFC 4122 version and variant bits, but Postgres
 * accepts any 128-bit value in a `uuid` column. Being stricter than the
 * database means an id that exists and is queryable would be rejected at the
 * API — so this validates the format only, which is all that is needed to keep
 * malformed input out of a query.
 */
const uuidLike = z
  .string()
  .regex(/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/, {
    message: 'must be a UUID',
  });

export const uuidParamSchema = z.object({
  id: uuidLike,
});

export const patchAdminUserSchema = z
  .object({
    isDisabled: z.boolean().optional(),
    role: z.enum(['user', 'admin']).optional(),
  })
  .refine((v) => Object.keys(v).length > 0, {
    message: 'Provide at least one field to update.',
  });

export const statsQuerySchema = z.object({
  days: z.coerce.number().int().min(1).max(90).default(30),
});

// --- Projects ---------------------------------------------------------------

export const createProjectSchema = z
  .object({
    title: z.string().trim().max(120).optional(),
    prompt: z.string().trim().min(1).max(1000).optional(),
    imagePath: z.string().min(1).max(300).optional(),
    provider: z.string().min(1).max(40).optional(),
    options: z
      .object({
        durationSeconds: z.coerce.number().int().min(1).max(60).optional(),
        aspectRatio: z.enum(['16:9', '9:16', '1:1']).optional(),
      })
      .optional(),
  })
  // This is what distinguishes the three generation modes (FR-2.1 – FR-2.3).
  // The same rule exists as a CHECK constraint in the database.
  .refine((v) => Boolean(v.prompt) || Boolean(v.imagePath), {
    message: 'Provide a prompt, an image, or both.',
  });

export const listProjectsSchema = paginationSchema.extend({
  status: z.enum(['pending', 'generating', 'completed', 'failed']).optional(),
});

// --- Uploads ----------------------------------------------------------------

export const signUploadSchema = z.object({
  contentType: z.enum(['image/jpeg', 'image/png', 'image/webp']),
  sizeBytes: z.coerce
    .number()
    .int()
    .positive()
    .max(10 * 1024 * 1024, 'Images must be 10 MB or smaller'),
});
