import { createApp } from './app.js';
import { env } from './config/env.js';
import { startPoller, stopPoller } from './jobs/poller.js';
import { logger } from './lib/logger.js';
import { checkDatabase, disconnectPrisma } from './lib/prisma.js';
import { registerProviders } from './services/ai/index.js';

registerProviders();

const app = createApp();

const server = app.listen(env.PORT, () => {
  logger.info(
    { port: env.PORT, env: env.NODE_ENV, provider: env.DEFAULT_AI_PROVIDER },
    `Cretona API listening on http://localhost:${env.PORT}/api/v1`,
  );

  // Reported, not fatal: the process stays up so /health answers and the
  // platform can distinguish "starting" from "crashed".
  void checkDatabase().then((ok) => {
    if (ok) {
      logger.info('Database reachable');
      // Only started once the database answers: the poller's first act is a
      // claim query, and failing that on every tick just fills the log.
      startPoller();
    } else {
      logger.warn('Database unreachable — check DATABASE_URL in backend/.env');
    }
  });
});

/**
 * Graceful shutdown. In-flight requests finish; the pool closes; a hung
 * connection cannot block the deploy indefinitely.
 */
async function shutdown(signal: string): Promise<void> {
  logger.info({ signal }, 'Shutting down');
  stopPoller();

  const forced = setTimeout(() => {
    logger.error('Shutdown timed out after 10s, forcing exit');
    process.exit(1);
  }, 10_000);
  forced.unref();

  server.close(async () => {
    await disconnectPrisma();
    clearTimeout(forced);
    process.exit(0);
  });
}

process.on('SIGTERM', () => void shutdown('SIGTERM'));
process.on('SIGINT', () => void shutdown('SIGINT'));

process.on('unhandledRejection', (reason) => {
  logger.error({ err: reason }, 'Unhandled promise rejection');
});

process.on('uncaughtException', (error) => {
  logger.fatal({ err: error }, 'Uncaught exception — exiting');
  process.exit(1);
});
