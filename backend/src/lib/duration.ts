/**
 * Minimal ISO-8601 duration parser, for GENERATION_QUOTA_WINDOW (ADR-007).
 *
 * Supports the subset a quota window needs: days, hours, minutes, seconds
 * (`P1D`, `PT12H`, `P1DT6H`). Months and years are deliberately unsupported —
 * they have no fixed length, so a rolling window built on them is ambiguous.
 */
const PATTERN = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/;

export function parseIsoDurationMs(value: string): number | null {
  if (value === 'P' || value === 'PT') return null;

  const match = PATTERN.exec(value);
  if (!match) return null;

  const [, days, hours, minutes, seconds] = match;

  const ms =
    Number(days ?? 0) * 86_400_000 +
    Number(hours ?? 0) * 3_600_000 +
    Number(minutes ?? 0) * 60_000 +
    Number(seconds ?? 0) * 1000;

  return ms > 0 ? ms : null;
}
