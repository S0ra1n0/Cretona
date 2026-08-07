import type { NextFunction, Request, Response } from 'express';
import { z } from 'zod';
import { AppError, notFound, type ErrorCode, type ErrorDetail } from '../lib/errors.js';
import { isProduction } from '../config/env.js';
import { logger } from '../lib/logger.js';

/**
 * The single place an error becomes a response (P2-6).
 *
 * Shape is fixed by API_CONTRACT.md §1.3. Nothing else in the codebase writes
 * an error body, so the client can rely on one parser.
 */
interface ErrorBody {
  error: {
    code: ErrorCode;
    message: string;
    details?: ErrorDetail[];
  };
  requestId: string;
}

/** 404 for unmatched routes. Registered after all routers. */
export function notFoundHandler(_req: Request, _res: Response, next: NextFunction): void {
  next(notFound('Endpoint'));
}

function toAppError(error: unknown): AppError {
  if (error instanceof AppError) return error;

  if (error instanceof z.ZodError) {
    return new AppError(
      'VALIDATION_ERROR',
      'The request could not be processed.',
      error.issues.map((i) => ({ field: i.path.map(String).join('.'), issue: i.message })),
    );
  }

  // Body parser rejections arrive as generic errors with a status attached.
  if (typeof error === 'object' && error !== null && 'type' in error) {
    const type = (error as { type?: string }).type;
    if (type === 'entity.too.large') {
      return new AppError('PAYLOAD_TOO_LARGE', 'Request body is too large.');
    }
    if (type === 'entity.parse.failed') {
      return new AppError('VALIDATION_ERROR', 'Request body is not valid JSON.');
    }
  }

  return new AppError('INTERNAL_ERROR', 'Something went wrong.');
}

export function errorHandler(
  error: unknown,
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  if (res.headersSent) {
    return next(error);
  }

  const appError = toAppError(error);

  const logPayload = {
    requestId: String(req.id),
    userId: req.user?.id,
    code: appError.code,
    status: appError.status,
    method: req.method,
    path: req.originalUrl,
  };

  if (appError.expected) {
    logger.warn(logPayload, appError.message);
  } else {
    // Log the original error, not the mapped one, or the stack is lost.
    logger.error({ ...logPayload, err: error }, 'Unhandled error');
  }

  const body: ErrorBody = {
    error: {
      code: appError.code,
      // A 500's real message may name internals, so it is never sent to the
      // client in production. The requestId is how it gets correlated instead.
      message:
        appError.expected || !isProduction ? appError.message : 'Something went wrong.',
      ...(appError.details ? { details: appError.details } : {}),
    },
    requestId: String(req.id),
  };

  res.status(appError.status).json(body);
}
