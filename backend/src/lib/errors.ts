/**
 * Error codes and the single error envelope, per docs/API_CONTRACT.md §1.3.
 *
 * Controllers and services throw AppError; the error handler is the only place
 * that turns one into a response. Nothing else writes an error body.
 */

export const ERROR_STATUS = {
  VALIDATION_ERROR: 400,
  UNAUTHENTICATED: 401,
  TOKEN_INVALID: 401,
  ACCOUNT_DISABLED: 403,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  PAYLOAD_TOO_LARGE: 413,
  QUOTA_EXCEEDED: 429,
  RATE_LIMITED: 429,
  PROVIDER_ERROR: 502,
  INTERNAL_ERROR: 500,
} as const;

export type ErrorCode = keyof typeof ERROR_STATUS;

export interface ErrorDetail {
  field: string;
  issue: string;
}

export class AppError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details?: ErrorDetail[];

  /** Unexpected errors are logged at error level; expected ones at warn. */
  readonly expected: boolean;

  constructor(code: ErrorCode, message: string, details?: ErrorDetail[]) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.status = ERROR_STATUS[code];
    this.details = details;
    this.expected = this.status < 500;
    Error.captureStackTrace?.(this, AppError);
  }
}

/**
 * A resource that exists but belongs to someone else is reported as 404, never
 * 403 — existence is not disclosed (API_CONTRACT §1.3, SECURITY.md §3).
 */
export const notFound = (what = 'Resource') => new AppError('NOT_FOUND', `${what} not found.`);

export const unauthenticated = (message = 'Authentication required.') =>
  new AppError('UNAUTHENTICATED', message);

export const tokenInvalid = (message = 'Your session has expired. Please sign in again.') =>
  new AppError('TOKEN_INVALID', message);

export const forbidden = (message = 'You do not have access to this resource.') =>
  new AppError('FORBIDDEN', message);

export const accountDisabled = () =>
  new AppError('ACCOUNT_DISABLED', 'This account has been disabled.');

export const validationError = (message: string, details?: ErrorDetail[]) =>
  new AppError('VALIDATION_ERROR', message, details);

export const conflict = (message: string) => new AppError('CONFLICT', message);
