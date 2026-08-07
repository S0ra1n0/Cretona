import { describe, expect, it } from 'vitest';
import { buildPage, cursorFilter, decodeCursor, encodeCursor } from '../src/lib/pagination.js';

describe('cursor encoding', () => {
  it('round-trips', () => {
    const cursor = { createdAt: new Date('2026-08-06T09:14:22Z'), id: 'abc-123' };

    expect(decodeCursor(encodeCursor(cursor))).toEqual(cursor);
  });

  it('treats an absent cursor as the first page', () => {
    expect(decodeCursor(undefined)).toBeNull();
  });

  it('reports a malformed cursor as 400, not a 500', () => {
    expect(() => decodeCursor('not-base64-json')).toThrowError(
      expect.objectContaining({ code: 'VALIDATION_ERROR', status: 400 }),
    );
  });

  it('rejects a cursor with a valid shape but an invalid date', () => {
    const bad = Buffer.from(JSON.stringify({ c: 'never', i: 'x' })).toString('base64url');

    expect(() => decodeCursor(bad)).toThrowError(
      expect.objectContaining({ code: 'VALIDATION_ERROR' }),
    );
  });
});

describe('buildPage', () => {
  const rows = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      id: `id-${i}`,
      createdAt: new Date(Date.now() - i * 1000),
    }));

  it('sets hasMore and trims the probe row when a page is full', () => {
    const page = buildPage(rows(21), 20);

    expect(page.items).toHaveLength(20);
    expect(page.page.hasMore).toBe(true);
    expect(page.page.nextCursor).toEqual(expect.any(String));
  });

  it('ends the sequence when the last page is short', () => {
    const page = buildPage(rows(5), 20);

    expect(page.items).toHaveLength(5);
    expect(page.page.hasMore).toBe(false);
    expect(page.page.nextCursor).toBeNull();
  });

  it('handles an empty result', () => {
    const page = buildPage([], 20);

    expect(page.items).toEqual([]);
    expect(page.page.nextCursor).toBeNull();
  });
});

describe('cursorFilter', () => {
  it('is empty for the first page', () => {
    expect(cursorFilter(null)).toEqual({});
  });

  it('breaks ties on id, since createdAt is not unique', () => {
    const createdAt = new Date('2026-08-06T09:14:22Z');

    expect(cursorFilter({ createdAt, id: 'abc' })).toEqual({
      OR: [{ createdAt: { lt: createdAt } }, { createdAt, id: { lt: 'abc' } }],
    });
  });
});
