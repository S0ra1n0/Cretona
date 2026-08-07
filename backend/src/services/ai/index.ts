import { env, isProduction } from '../../config/env.js';
import { logger } from '../../lib/logger.js';
import { fakeProvider } from './providers/fake.js';
import { registerProvider, registeredProviders } from './registry.js';

/**
 * Provider bootstrap. Called once at startup.
 *
 * Each provider is registered only if its API key is present, so an
 * unconfigured provider cannot be selected by a request.
 */
export function registerProviders(): void {
  if (!isProduction) {
    registerProvider(fakeProvider);
  }

  if (env.RUNWAY_API_KEY) {
    // P3-3. Blocked on the ADR-004 verification checklist: the adapter needs
    // the real request shape, status vocabulary, and error format confirmed
    // against live documentation before it can be written honestly.
    logger.warn('RUNWAY_API_KEY is set but the Runway adapter is not implemented yet (P3-3)');
  }

  const available = registeredProviders();
  logger.info({ providers: available, default: env.DEFAULT_AI_PROVIDER }, 'AI providers registered');

  if (!available.includes(env.DEFAULT_AI_PROVIDER)) {
    logger.warn(
      { configured: env.DEFAULT_AI_PROVIDER, available },
      'DEFAULT_AI_PROVIDER is not registered — generation requests will be rejected until it is',
    );
  }
}

export * from './types.js';
export * from './registry.js';
export * from './failures.js';
