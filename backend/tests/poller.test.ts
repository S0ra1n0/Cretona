import { beforeEach, describe, expect, it, vi } from 'vitest';

const queryRaw = vi.fn();
const update = vi.fn();
const updateMany = vi.fn();
const logCreate = vi.fn();
const rehostVideo = vi.fn();

vi.mock('../src/lib/prisma.js', () => ({
  prisma: {
    $queryRaw: (...a: unknown[]) => queryRaw(...a),
    videoProject: {
      update: (...a: unknown[]) => update(...a),
      updateMany: (...a: unknown[]) => updateMany(...a),
    },
    generationLog: { create: (...a: unknown[]) => logCreate(...a) },
  },
  checkDatabase: async () => true,
  disconnectPrisma: async () => {},
}));

vi.mock('../src/services/storage.service.js', () => ({
  rehostVideo: (...a: unknown[]) => rehostVideo(...a),
  signedUploadRead: async () => 'https://signed/image.jpg',
  signedVideoRead: async () => 'https://signed/video.mp4',
  removeObjects: async () => {},
  assertOwnsPath: () => {},
  createSignedUpload: async () => ({}),
}));

const { runPollCycle } = await import('../src/jobs/poller.js');
const { clearRegistry, registerProvider } = await import('../src/services/ai/registry.js');
const { fakeProvider, resetFakeProvider } = await import(
  '../src/services/ai/providers/fake.js'
);

const NOW = new Date('2026-08-07T12:00:00Z');

function job(over: Record<string, unknown> = {}) {
  return {
    id: 'project-1',
    user_id: 'user-1',
    provider: 'fake',
    provider_job_id: 'fake_job',
    created_at: new Date(NOW.getTime() - 20_000),
    updated_at: new Date(NOW.getTime() - 20_000),
    ...over,
  };
}

beforeEach(() => {
  for (const m of [queryRaw, update, updateMany, logCreate, rehostVideo]) m.mockReset();
  clearRegistry();
  resetFakeProvider();
  registerProvider(fakeProvider);
  updateMany.mockResolvedValue({ count: 1 });
  update.mockResolvedValue({});
  logCreate.mockResolvedValue({});
});

describe('runPollCycle', () => {
  it('does nothing when no jobs are due', async () => {
    queryRaw.mockResolvedValue([]);

    expect(await runPollCycle(NOW)).toBe(0);
    expect(updateMany).not.toHaveBeenCalled();
  });

  it('claims with FOR UPDATE SKIP LOCKED so two workers cannot poll one job', async () => {
    queryRaw.mockResolvedValue([]);

    await runPollCycle(NOW);

    const sql = queryRaw.mock.calls[0]?.[0].join(' ').toLowerCase();
    expect(sql).toContain('for update skip locked');
    expect(sql).toContain("status = 'generating'");
  });

  it('re-hosts the video BEFORE marking the project completed', async () => {
    queryRaw.mockResolvedValue([job()]);
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'a city' });
    queryRaw.mockResolvedValue([job({ provider_job_id: jobId })]);
    rehostVideo.mockResolvedValue('user-1/project-1/video.mp4');

    await runPollCycle(NOW);

    expect(rehostVideo).toHaveBeenCalled();
    const completion = updateMany.mock.calls.at(-1)?.[0];
    expect(completion.data.status).toBe('completed');
    // The stored path is ours, never the provider's expiring URL.
    expect(completion.data.videoPath).toBe('user-1/project-1/video.mp4');
  });

  it('fails the project when re-hosting fails, rather than completing it', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'a city' });
    queryRaw.mockResolvedValue([job({ provider_job_id: jobId })]);
    rehostVideo.mockRejectedValue(new Error('storage down'));

    await runPollCycle(NOW);

    const call = updateMany.mock.calls.at(-1)?.[0];
    expect(call.data.status).toBe('failed');
    expect(call.data.errorCode).toBe('provider_error');
  });

  it('leaves a running job alone but touches it so it is not re-claimed', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'slow' });
    queryRaw.mockResolvedValue([job({ provider_job_id: jobId })]);

    await runPollCycle(NOW);

    expect(update).toHaveBeenCalled();
    expect(updateMany).not.toHaveBeenCalled();
    expect(rehostVideo).not.toHaveBeenCalled();
  });

  it('records the provider failure reason on the project', async () => {
    const { jobId } = await fakeProvider.submit({
      mode: 'text',
      prompt: 'fail:content_policy',
    });
    queryRaw.mockResolvedValue([job({ provider_job_id: jobId })]);

    await runPollCycle(NOW);

    const call = updateMany.mock.calls.at(-1)?.[0];
    expect(call.data.status).toBe('failed');
    expect(call.data.errorCode).toBe('content_policy');
    // The user sees prose, never the provider's own message.
    expect(call.data.errorMessage).not.toMatch(/fake provider/i);
  });

  it('times out a job that never reaches a terminal state (NFR-3.3)', async () => {
    const stale = job({
      created_at: new Date(NOW.getTime() - 3_600_000), // an hour old, timeout is 60s
    });
    queryRaw.mockResolvedValue([stale]);

    await runPollCycle(NOW);

    const call = updateMany.mock.calls.at(-1)?.[0];
    expect(call.data.status).toBe('failed');
    expect(call.data.errorCode).toBe('timeout');
  });

  it('only ever transitions a job that is still generating', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'a city' });
    queryRaw.mockResolvedValue([job({ provider_job_id: jobId })]);
    rehostVideo.mockResolvedValue('p');

    await runPollCycle(NOW);

    // The guard is in the WHERE clause, so a concurrently-deleted or already
    // completed project cannot be overwritten.
    expect(updateMany.mock.calls.at(-1)?.[0].where.status).toBe('generating');
  });

  it('one failing job does not stop the batch', async () => {
    const { jobId } = await fakeProvider.submit({ mode: 'text', prompt: 'a city' });
    queryRaw.mockResolvedValue([
      job({ id: 'bad', provider: 'nonexistent' }),
      job({ id: 'good', provider_job_id: jobId }),
    ]);
    rehostVideo.mockResolvedValue('p');

    expect(await runPollCycle(NOW)).toBe(2);
    expect(rehostVideo).toHaveBeenCalledTimes(1);
  });
});
