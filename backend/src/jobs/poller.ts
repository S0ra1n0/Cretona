import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { failureMessage } from '../services/ai/failures.js';
import { getProvider } from '../services/ai/registry.js';
import { recordGenerationLog } from '../services/generationLog.service.js';
import { failProject } from '../services/projects/projects.service.js';
import { rehostVideo } from '../services/storage.service.js';

/**
 * Generation job runner (P3-6, ADR-003).
 *
 * All state lives in Postgres, so a restart resumes cleanly (NFR-3.1) and
 * more than one instance can run safely — claiming uses FOR UPDATE SKIP
 * LOCKED, so two workers never poll the same job.
 */
interface ClaimedJob {
  id: string;
  user_id: string;
  provider: string;
  provider_job_id: string;
  created_at: Date;
  updated_at: Date;
}

const BATCH_SIZE = 10;

/**
 * Claims jobs that are due a poll. Interval widens after the backoff
 * threshold, so a long generation is not polled every 10 seconds for minutes
 * (ADR-003).
 */
async function claimDueJobs(now: Date): Promise<ClaimedJob[]> {
  const fastCutoff = new Date(now.getTime() - env.POLL_INTERVAL_MS);
  const slowCutoff = new Date(now.getTime() - env.POLL_BACKOFF_INTERVAL_MS);
  const backoffAfter = new Date(now.getTime() - env.POLL_BACKOFF_AFTER_MS);

  return prisma.$queryRaw<ClaimedJob[]>`
    select id, user_id, provider, provider_job_id, created_at, updated_at
    from public.video_projects
    where status = 'generating'
      and provider_job_id is not null
      and deleted_at is null
      and (
        (created_at > ${backoffAfter} and updated_at <= ${fastCutoff})
        or
        (created_at <= ${backoffAfter} and updated_at <= ${slowCutoff})
      )
    order by updated_at asc
    limit ${BATCH_SIZE}
    for update skip locked
  `;
}

/** Marks progress so the job is not re-claimed on the next tick. */
async function touch(projectId: string): Promise<void> {
  await prisma.videoProject.update({
    where: { id: projectId },
    data: { updatedAt: new Date() },
  });
}

async function pollOne(job: ClaimedJob, now: Date): Promise<void> {
  const provider = getProvider(job.provider);
  const ageSeconds = (now.getTime() - job.created_at.getTime()) / 1000;

  // A job with no terminal state by its deadline is failed rather than polled
  // forever (NFR-3.3).
  if (ageSeconds > provider.capabilities.timeoutSeconds) {
    await recordGenerationLog({
      projectId: job.id,
      provider: job.provider,
      event: 'error',
      requestId: job.provider_job_id,
      response: { timedOutAfterSeconds: Math.round(ageSeconds) },
    });
    await failProject(job.id, 'timeout', failureMessage('timeout'));
    return;
  }

  let state;
  try {
    state = await provider.getStatus(job.provider_job_id);
  } catch (error) {
    // A transient poll failure is not a generation failure. Touch and retry on
    // the next tick; the timeout above is the backstop.
    logger.warn({ err: error, projectId: job.id }, 'Poll failed, will retry');
    await recordGenerationLog({
      projectId: job.id,
      provider: job.provider,
      event: 'error',
      requestId: job.provider_job_id,
      response: { message: (error as Error).message },
    });
    await touch(job.id);
    return;
  }

  await recordGenerationLog({
    projectId: job.id,
    provider: job.provider,
    event: 'poll',
    requestId: job.provider_job_id,
    response: state,
  });

  if (state.status === 'running') {
    await touch(job.id);
    return;
  }

  if (state.status === 'failed') {
    await failProject(job.id, state.reason, failureMessage(state.reason));
    return;
  }

  // Succeeded: re-host before completing. The provider URL expires, so the
  // project must not be marked completed while pointing at a link that dies
  // (C-3, P3-8).
  try {
    const videoPath = await rehostVideo(job.user_id, job.id, state.videoUrl);

    await recordGenerationLog({
      projectId: job.id,
      provider: job.provider,
      event: 'download',
      requestId: job.provider_job_id,
      response: { videoPath },
    });

    await prisma.videoProject.updateMany({
      where: { id: job.id, status: 'generating' },
      data: {
        status: 'completed',
        videoPath,
        durationSeconds: state.durationSeconds ?? undefined,
        completedAt: new Date(),
        errorCode: null,
        errorMessage: null,
      },
    });

    logger.info({ projectId: job.id }, 'Generation completed');
  } catch (error) {
    logger.error({ err: error, projectId: job.id }, 'Re-hosting the result failed');
    await failProject(job.id, 'provider_error', failureMessage('provider_error'));
  }
}

export async function runPollCycle(now = new Date()): Promise<number> {
  const jobs = await claimDueJobs(now);

  for (const job of jobs) {
    try {
      await pollOne(job, now);
    } catch (error) {
      // One bad job must not stop the batch.
      logger.error({ err: error, projectId: job.id }, 'Unhandled error polling job');
    }
  }

  return jobs.length;
}

let timer: NodeJS.Timeout | null = null;

export function startPoller(): void {
  if (timer) return;

  timer = setInterval(() => {
    void runPollCycle().catch((error: unknown) => {
      logger.error({ err: error }, 'Poll cycle failed');
    });
  }, env.POLL_INTERVAL_MS);

  // Must not hold the process open during shutdown.
  timer.unref();

  logger.info({ intervalMs: env.POLL_INTERVAL_MS }, 'Generation poller started');
}

export function stopPoller(): void {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}
