import pino from 'pino';
import { env, isProduction } from '../config/env.js';

/**
 * Structured logging (P2-7).
 *
 * Redaction is configured here rather than at call sites so no code path can
 * leak a credential by forgetting to sanitise (SECURITY.md §6). Adding a new
 * header or field that carries a secret means adding it to this list.
 */
export const logger = pino({
  level: env.LOG_LEVEL,
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers.cookie',
      'req.headers["x-api-key"]',
      'res.headers["set-cookie"]',
      '*.apiKey',
      '*.api_key',
      '*.password',
      '*.encrypted_password',
      '*.token',
      '*.accessToken',
      '*.serviceRoleKey',
    ],
    censor: '[redacted]',
  },
  // Pretty output is a development nicety; production stays newline-delimited
  // JSON so the host platform can parse it.
  ...(isProduction
    ? {}
    : {
        transport: {
          target: 'pino/file',
          options: { destination: 1 },
        },
      }),
});
