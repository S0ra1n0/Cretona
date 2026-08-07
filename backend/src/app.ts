import cors from 'cors';
import express, { type Express } from 'express';
import helmet from 'helmet';
import { pinoHttp } from 'pino-http';
import { isTest } from './config/env.js';
import { logger } from './lib/logger.js';
import { errorHandler, notFoundHandler } from './middleware/errorHandler.js';
import { publicLimiter } from './middleware/rateLimit.js';
import { requestId } from './middleware/requestId.js';
import { apiRouter } from './routes/index.js';

/**
 * Express application assembly (P2-1).
 *
 * Order matters and matches ARCHITECTURE.md §4.1:
 *   requestId -> logger -> rateLimit -> routes -> 404 -> errorHandler
 *
 * Per-route auth, role, and validation middleware are attached by the routers.
 * The error handler is last, because Express selects error middleware by
 * position, not by type.
 */
export function createApp(): Express {
  const app = express();

  // Behind a platform proxy (Railway/Render/Fly), so client IPs come from
  // X-Forwarded-For. Without this, rate limiting would key every request to
  // the proxy's address and throttle all users as one.
  app.set('trust proxy', 1);
  app.disable('x-powered-by');

  app.use(requestId);

  if (!isTest) {
    app.use(
      pinoHttp({
        logger,
        // Reuse the id set by the requestId middleware so one request produces
        // one id across access logs, error logs, and the response header.
        genReqId: (req): string => (req as { id?: string }).id ?? '',
        customLogLevel: (_req, res, err): 'error' | 'warn' | 'info' => {
          if (err || res.statusCode >= 500) return 'error';
          if (res.statusCode >= 400) return 'warn';
          return 'info';
        },
      }),
    );
  }

  app.use(helmet());
  app.use(cors({ origin: true, credentials: false }));
  app.use(express.json({ limit: '1mb' }));

  app.use(publicLimiter);

  app.use('/api/v1', apiRouter);

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
