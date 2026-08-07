import { beforeEach, describe, expect, it, vi } from 'vitest';

const findMany = vi.fn();
vi.mock('../src/lib/prisma.js', () => ({
  prisma: { videoProject: { findMany: (...a: unknown[]) => findMany(...a) } },
  checkDatabase: async () => true,
  disconnectPrisma: async () => {},
}));

const { getQuota, assertQuotaAvailable } = await import('../src/services/quota.service.js');
const { parseIsoDurationMs } = await import('../src/lib/duration.js');

beforeEach(() => findMany.mockReset());

describe('parseIsoDurationMs', () => {
  it('parses the forms a quota window uses', () => {
    expect(parseIsoDurationMs('P1D')).toBe(86_400_000);
    expect(parseIsoDurationMs('PT12H')).toBe(43_200_000);
    expect(parseIsoDurationMs('P1DT6H')).toBe(108_000_000);
    expect(parseIsoDurationMs('PT30M')).toBe(1_800_000);
  });

  it('rejects months and years — they have no fixed length', () => {
    expect(parseIsoDurationMs('P1M')).toBeNull();
    expect(parseIsoDurationMs('P1Y')).toBeNull();
  });

  it('rejects nonsense and empty durations', () => {
    expect(parseIsoDurationMs('1D')).toBeNull();
    expect(parseIsoDurationMs('P')).toBeNull();
    expect(parseIsoDurationMs('PT0S')).toBeNull();
  });
});

describe('getQuota', () => {
  it('reports a full allowance when nothing has been used', async () => {
    findMany.mockResolvedValue([]);

    const quota = await getQuota('user-1');

    expect(quota.used).toBe(0);
    expect(quota.remaining).toBe(quota.limit);
  });

  it('counts generations in the window', async () => {
    findMany.mockResolvedValue([{ createdAt: new Date() }, { createdAt: new Date() }]);

    const quota = await getQuota('user-1');

    expect(quota.used).toBe(2);
    expect(quota.remaining).toBe(quota.limit - 2);
  });

  it('excludes infrastructure failures from the count', async () => {
    findMany.mockResolvedValue([]);

    await getQuota('user-1');

    const where = findMany.mock.calls[0]?.[0].where;
    expect(where.NOT.errorCode.in).toEqual(['provider_error', 'timeout']);
    // content_policy is absent on purpose: the provider call was made and billed.
    expect(where.NOT.errorCode.in).not.toContain('content_policy');
  });

  it('ignores soft-deleted projects', async () => {
    findMany.mockResolvedValue([]);

    await getQuota('user-1');

    expect(findMany.mock.calls[0]?.[0].where.deletedAt).toBeNull();
  });

  it('resets when the oldest counted generation ages out', async () => {
    const oldest = new Date('2026-08-06T00:00:00Z');
    findMany.mockResolvedValue([{ createdAt: oldest }, { createdAt: new Date() }]);

    const quota = await getQuota('user-1');

    expect(quota.resetsAt).toBe(new Date(oldest.getTime() + 86_400_000).toISOString());
  });

  it('never reports negative remaining', async () => {
    findMany.mockResolvedValue(Array.from({ length: 99 }, () => ({ createdAt: new Date() })));

    expect((await getQuota('user-1')).remaining).toBe(0);
  });
});

describe('assertQuotaAvailable', () => {
  it('passes when allowance remains', async () => {
    findMany.mockResolvedValue([]);

    await expect(assertQuotaAvailable('user-1')).resolves.toBeDefined();
  });

  it('throws QUOTA_EXCEEDED when exhausted', async () => {
    findMany.mockResolvedValue(Array.from({ length: 50 }, () => ({ createdAt: new Date() })));

    await expect(assertQuotaAvailable('user-1')).rejects.toMatchObject({
      code: 'QUOTA_EXCEEDED',
      status: 429,
    });
  });
});
