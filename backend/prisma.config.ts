import 'dotenv/config';
import { defineConfig } from 'prisma/config';

/**
 * Prisma CLI configuration.
 *
 * Prisma 7 removed `url` / `directUrl` from schema.prisma, so CLI commands
 * (`db pull`, `migrate`) read the connection string from here. The runtime
 * client is configured separately, in src/lib/prisma.ts, via a driver adapter.
 *
 * DIRECT_URL is preferred: introspection and migrations must not go through
 * the pgbouncer pool, which does not support the prepared statements and
 * advisory locks they rely on. DATABASE_URL is the fallback so the CLI still
 * works when only the pooled URL is configured.
 */
export default defineConfig({
  schema: 'prisma/schema.prisma',
  datasource: {
    url: process.env.DIRECT_URL ?? process.env.DATABASE_URL ?? '',
  },
});
