import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '@prisma/client';
import { env } from '../config/env.js';
import { logger } from './logger.js';

/**
 * Prisma client singleton.
 *
 * Prisma 7 has no built-in Rust query engine, so the connection is supplied by
 * a driver adapter over `pg`. DATABASE_URL is the pooled (pgbouncer) string —
 * migrations and introspection use DIRECT_URL instead, configured separately
 * in prisma.config.ts.
 *
 * Construction does not open a connection; the pool is created lazily on first
 * query. That is deliberate: the server boots and serves /health even when the
 * database is unreachable, so a platform health check can tell "starting" from
 * "crashed".
 */
const adapter = new PrismaPg({ connectionString: env.DATABASE_URL });

export const prisma = new PrismaClient({
  adapter,
  log: ['warn', 'error'],
});

export async function disconnectPrisma(): Promise<void> {
  try {
    await prisma.$disconnect();
  } catch (error) {
    logger.warn({ err: error }, 'Error while disconnecting Prisma');
  }
}

/** Used by the readiness endpoint and by startup diagnostics. */
export async function checkDatabase(): Promise<boolean> {
  try {
    await prisma.$queryRaw`select 1`;
    return true;
  } catch {
    return false;
  }
}
