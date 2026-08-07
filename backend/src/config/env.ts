import 'dotenv/config';
import { z } from 'zod';

/**
 * Environment configuration (P2-3).
 *
 * Validated once at import time. A missing or malformed required value stops
 * the process here rather than surfacing as a confusing runtime failure three
 * layers deep. Every key is documented in .env.example.
 */
const schema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().positive().default(3000),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),

  // Database
  DATABASE_URL: z.string().min(1, 'DATABASE_URL is required (Supabase → Settings → Database)'),
  DIRECT_URL: z.string().optional(),

  // Supabase
  SUPABASE_URL: z.string().url(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(1),
  SUPABASE_JWT_SECRET: z.string().min(1, 'SUPABASE_JWT_SECRET is required to verify access tokens'),
  SUPABASE_UPLOADS_BUCKET: z.string().default('uploads'),
  SUPABASE_VIDEOS_BUCKET: z.string().default('videos'),
  SIGNED_URL_TTL_SECONDS: z.coerce.number().int().positive().default(3600),

  // AI providers (ADR-004)
  DEFAULT_AI_PROVIDER: z.string().default('runway'),
  RUNWAY_API_KEY: z.string().optional(),
  KLING_API_KEY: z.string().optional(),

  // Quota and rate limiting (ADR-007)
  GENERATION_QUOTA_LIMIT: z.coerce.number().int().positive().default(10),
  GENERATION_QUOTA_WINDOW: z.string().default('P1D'),
  RATE_LIMIT_GENERATION_PER_MIN: z.coerce.number().int().positive().default(5),
  RATE_LIMIT_DEFAULT_PER_MIN: z.coerce.number().int().positive().default(120),

  // Job runner (ADR-003)
  POLL_INTERVAL_MS: z.coerce.number().int().positive().default(10_000),
  POLL_BACKOFF_AFTER_MS: z.coerce.number().int().positive().default(120_000),
  POLL_BACKOFF_INTERVAL_MS: z.coerce.number().int().positive().default(30_000),
  GENERATION_TIMEOUT_SECONDS: z.coerce.number().int().positive().default(600),
  MAX_GENERATION_ATTEMPTS: z.coerce.number().int().positive().default(3),
});

const parsed = schema.safeParse(process.env);

if (!parsed.success) {
  const issues = parsed.error.issues
    .map((i) => `  ${i.path.join('.') || '(root)'}: ${i.message}`)
    .join('\n');

  // Deliberately console, not the logger: the logger is configured from this
  // very object, so it may not exist yet.
  console.error(`Invalid environment configuration:\n${issues}\n\nSee backend/.env.example.`);
  process.exit(1);
}

export const env = parsed.data;

export const isProduction = env.NODE_ENV === 'production';
export const isTest = env.NODE_ENV === 'test';
