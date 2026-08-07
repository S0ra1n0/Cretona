import { validationError } from './errors.js';

/**
 * Cursor pagination (API_CONTRACT.md §1.4).
 *
 * Keyset, not OFFSET: rows inserted while a user pages would shift an offset
 * window and duplicate or skip items. The cursor carries the sort key plus the
 * id as a tie-breaker, because created_at is not unique.
 *
 * Cursors are opaque by contract, so clients cannot depend on the encoding and
 * we can change it without a version bump.
 */
export interface Cursor {
  createdAt: Date;
  id: string;
}

export interface Page<T> {
  items: T[];
  page: {
    nextCursor: string | null;
    hasMore: boolean;
  };
}

export function encodeCursor(cursor: Cursor): string {
  const payload = JSON.stringify({ c: cursor.createdAt.toISOString(), i: cursor.id });
  return Buffer.from(payload, 'utf8').toString('base64url');
}

export function decodeCursor(value: string | undefined): Cursor | null {
  if (!value) return null;

  try {
    const parsed = JSON.parse(Buffer.from(value, 'base64url').toString('utf8')) as {
      c?: string;
      i?: string;
    };

    if (!parsed.c || !parsed.i) throw new Error('missing fields');

    const createdAt = new Date(parsed.c);
    if (Number.isNaN(createdAt.getTime())) throw new Error('bad date');

    return { createdAt, id: parsed.i };
  } catch {
    // A malformed cursor is the client's error, not a server fault. Reporting
    // it as 400 stops a stale bookmark producing a confusing 500.
    throw validationError('The pagination cursor is not valid.', [
      { field: 'query.cursor', issue: 'malformed' },
    ]);
  }
}

/**
 * Fetch `limit + 1` rows, then call this: the extra row is what tells us
 * whether another page exists, without a second COUNT query.
 */
export function buildPage<T extends { id: string; createdAt: Date }>(
  rows: T[],
  limit: number,
): Page<T> {
  const hasMore = rows.length > limit;
  const items = hasMore ? rows.slice(0, limit) : rows;
  const last = items.at(-1);

  return {
    items,
    page: {
      nextCursor: hasMore && last ? encodeCursor({ createdAt: last.createdAt, id: last.id }) : null,
      hasMore,
    },
  };
}

/** Keyset predicate for a newest-first listing. */
export function cursorFilter(cursor: Cursor | null) {
  if (!cursor) return {};

  return {
    OR: [
      { createdAt: { lt: cursor.createdAt } },
      { createdAt: cursor.createdAt, id: { lt: cursor.id } },
    ],
  };
}
