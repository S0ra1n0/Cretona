import { beforeEach, describe, expect, it } from 'vitest';
import {
  assertTransition,
  canTransition,
} from '../src/services/projects/transitions.js';
import { failureMessage, isRetryable } from '../src/services/ai/failures.js';
import {
  clearRegistry,
  getProvider,
  normalizeInput,
  registerProvider,
  registeredProviders,
} from '../src/services/ai/registry.js';
import { fakeProvider, resetFakeProvider } from '../src/services/ai/providers/fake.js';
import { redact } from '../src/services/generationLog.service.js';

beforeEach(() => {
  clearRegistry();
  resetFakeProvider();
  registerProvider(fakeProvider);
});

describe('project state machine', () => {
  it('allows the documented transitions', () => {
    expect(canTransition('pending', 'generating')).toBe(true);
    expect(canTransition('generating', 'completed')).toBe(true);
    expect(canTransition('generating', 'failed')).toBe(true);
    expect(canTransition('failed', 'pending')).toBe(true); // retry, FR-2.11
  });

  it('refuses everything else', () => {
    expect(canTransition('completed', 'generating')).toBe(false);
    expect(canTransition('completed', 'failed')).toBe(false);
    expect(canTransition('pending', 'completed')).toBe(false); // must pass through generating
    expect(canTransition('failed', 'completed')).toBe(false);
  });

  it('throws CONFLICT rather than silently allowing an illegal move', () => {
    expect(() => assertTransition('completed', 'pending')).toThrowError(
      expect.objectContaining({ code: 'CONFLICT', status: 409 }),
    );
  });
});

describe('registry', () => {
  it('resolves a registered provider', () => {
    expect(getProvider('fake').capabilities.name).toBe('fake');
    expect(registeredProviders()).toContain('fake');
  });

  it('rejects an unknown provider as 400, not 500', () => {
    expect(() => getProvider('nonexistent')).toThrowError(
      expect.objectContaining({ code: 'VALIDATION_ERROR' }),
    );
  });

  it('an unregistered provider cannot be selected even if named', () => {
    clearRegistry();

    expect(() => getProvider('fake')).toThrowError(
      expect.objectContaining({ code: 'VALIDATION_ERROR' }),
    );
  });
});

describe('normalizeInput', () => {
  it('rejects a mode the provider does not support, before submitting', () => {
    const textOnly = {
      ...fakeProvider,
      capabilities: { ...fakeProvider.capabilities, supportedModes: ['text' as const] },
    };

    expect(() => normalizeInput(textOnly, { mode: 'image' })).toThrowError(
      expect.objectContaining({ code: 'VALIDATION_ERROR' }),
    );
  });

  it('rejects an over-long prompt instead of truncating it', () => {
    expect(() =>
      normalizeInput(fakeProvider, { mode: 'text', prompt: 'x'.repeat(1001) }),
    ).toThrowError(expect.objectContaining({ code: 'VALIDATION_ERROR' }));
  });

  it('rejects an unsupported aspect ratio', () => {
    const wide = {
      ...fakeProvider,
      capabilities: { ...fakeProvider.capabilities, aspectRatios: ['16:9' as const] },
    };

    expect(() => normalizeInput(wide, { mode: 'text', aspectRatio: '1:1' })).toThrowError(
      expect.objectContaining({ code: 'VALIDATION_ERROR' }),
    );
  });

  it('clamps duration rather than rejecting it — a preference, not a mistake', () => {
    expect(normalizeInput(fakeProvider, { mode: 'text', durationSeconds: 999 }).durationSeconds)
      .toBe(10);
    expect(normalizeInput(fakeProvider, { mode: 'text', durationSeconds: 1 }).durationSeconds)
      .toBe(2);
  });

  it('leaves duration unset when not requested', () => {
    expect(normalizeInput(fakeProvider, { mode: 'text' }).durationSeconds).toBeUndefined();
  });
});

describe('failure taxonomy', () => {
  it('never surfaces a raw provider message', () => {
    for (const reason of [
      'content_policy',
      'invalid_input',
      'quota',
      'timeout',
      'provider_error',
      'unknown',
    ] as const) {
      expect(failureMessage(reason)).toMatch(/^[A-Z]/);
      expect(failureMessage(reason).length).toBeGreaterThan(10);
    }
  });

  it('only offers retry where retrying could plausibly work', () => {
    expect(isRetryable('provider_error')).toBe(true);
    expect(isRetryable('timeout')).toBe(true);
    expect(isRetryable('quota')).toBe(true);

    // These fail identically on a retry, and a retry costs the user an
    // allowance — offering one would be dishonest.
    expect(isRetryable('content_policy')).toBe(false);
    expect(isRetryable('invalid_input')).toBe(false);
    expect(isRetryable(null)).toBe(false);
  });
});

describe('generation log redaction', () => {
  it('redacts anything key-shaped, at any depth', () => {
    const out = redact({
      apiKey: 'sk-secret',
      nested: { authToken: 'abc', password: 'hunter2', safe: 'keep' },
      list: [{ secretValue: 'x' }],
    }) as Record<string, never>;

    expect(JSON.stringify(out)).not.toContain('sk-secret');
    expect(JSON.stringify(out)).not.toContain('hunter2');
    expect(JSON.stringify(out)).toContain('keep');
  });

  it('strips signature params from signed URLs', () => {
    const out = redact('https://x.supabase.co/storage/v1/object/sign/videos/a.mp4?token=eyJhb');

    expect(out).not.toContain('eyJhb');
    expect(out).toContain('/videos/a.mp4');
  });

  it('leaves ordinary values alone', () => {
    expect(redact({ status: 'running', count: 3, ok: true })).toEqual({
      status: 'running',
      count: 3,
      ok: true,
    });
  });
});

describe('fake provider', () => {
  it('completes after a poll', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'a city' });

    await expect(fakeProvider.getStatus(jobId)).resolves.toMatchObject({ status: 'succeeded' });
  });

  it('stays running for a slow job', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'slow please' });

    await expect(fakeProvider.getStatus(jobId)).resolves.toMatchObject({ status: 'running' });
  });

  it('reports the requested failure', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'fail:content_policy' });

    await expect(fakeProvider.getStatus(jobId)).resolves.toMatchObject({
      status: 'failed',
      reason: 'content_policy',
    });
  });

  it('reports an unknown job as failed rather than running forever', async () => {
    await expect(fakeProvider.getStatus('fake_missing')).resolves.toMatchObject({
      status: 'failed',
    });
  });
});
