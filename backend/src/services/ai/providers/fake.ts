import { randomUUID } from 'node:crypto';
import type {
  GenerationInput,
  JobState,
  ProviderCapabilities,
  SubmitResult,
  VideoProvider,
} from '../types.js';

/**
 * In-memory provider for development and tests.
 *
 * It exists so the whole pipeline — submit, poll, re-host, complete — can be
 * exercised end to end before the real Runway adapter lands (ADR-004's
 * verification checklist is still outstanding). It is registered only when
 * NODE_ENV is not production.
 *
 * Behaviour is deterministic and driven by the prompt, so tests can request a
 * specific outcome:
 *   "fail:content_policy"  → fails with that reason
 *   "slow"                 → stays running for SLOW_POLLS polls
 *   anything else          → succeeds after one poll
 */
const SLOW_POLLS = 3;

interface FakeJob {
  polls: number;
  outcome: 'succeed' | 'slow';
  failure?: string;
}

const jobs = new Map<string, FakeJob>();

export function resetFakeProvider(): void {
  jobs.clear();
}

export const fakeProvider: VideoProvider = {
  capabilities: {
    name: 'fake',
    supportedModes: ['text', 'image', 'text_image'],
    durationRange: { min: 2, max: 10 },
    aspectRatios: ['16:9', '9:16', '1:1'],
    maxPromptLength: 1000,
    maxImageBytes: 10 * 1024 * 1024,
    acceptedImageTypes: ['image/jpeg', 'image/png', 'image/webp'],
    typicalLatencySeconds: 1,
    timeoutSeconds: 60,
  } satisfies ProviderCapabilities,

  async submit(input: GenerationInput): Promise<SubmitResult> {
    const jobId = `fake_${randomUUID()}`;
    const prompt = input.prompt ?? '';

    const failMatch = /^fail:(\w+)/.exec(prompt);

    jobs.set(jobId, {
      polls: 0,
      outcome: prompt.startsWith('slow') ? 'slow' : 'succeed',
      ...(failMatch?.[1] ? { failure: failMatch[1] } : {}),
    });

    return { jobId, rawResponse: { id: jobId, status: 'queued' } };
  },

  async getStatus(jobId: string): Promise<JobState> {
    const job = jobs.get(jobId);

    // An unknown job id is a real condition — a restart lost in-memory state.
    // Reporting it as failed rather than running stops it polling forever.
    if (!job) {
      return { status: 'failed', reason: 'unknown', message: 'Job not found.' };
    }

    job.polls += 1;

    if (job.failure) {
      return {
        status: 'failed',
        reason: job.failure as JobState extends { reason: infer R } ? R : never,
        message: `Fake provider failure: ${job.failure}`,
      };
    }

    if (job.outcome === 'slow' && job.polls < SLOW_POLLS) {
      return { status: 'running' };
    }

    return {
      status: 'succeeded',
      // A tiny valid MP4 stand-in. The re-host path only needs bytes it can
      // fetch; it does not decode them.
      videoUrl: 'data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDE=',
      durationSeconds: 5,
    };
  },

  async cancel(jobId: string): Promise<void> {
    jobs.delete(jobId);
  },
};
