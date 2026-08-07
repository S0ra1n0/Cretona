import type { NextFunction, Request, Response } from 'express';
import type { ZodType } from 'zod';
import { validationError, type ErrorDetail } from '../lib/errors.js';

/**
 * Request validation (P2-19).
 *
 * Every route declares its shape. Parsed output replaces the raw input, so
 * handlers work with coerced, trusted values and never re-check them.
 */
interface Schemas {
  body?: ZodType;
  query?: ZodType;
  params?: ZodType;
}

export function validate(schemas: Schemas) {
  return function validateRequest(req: Request, _res: Response, next: NextFunction): void {
    const details: ErrorDetail[] = [];

    for (const key of ['body', 'query', 'params'] as const) {
      const schema = schemas[key];
      if (!schema) continue;

      const result = schema.safeParse(req[key]);

      if (!result.success) {
        for (const issue of result.error.issues) {
          details.push({
            field: [key, ...issue.path.map(String)].join('.'),
            issue: issue.message,
          });
        }
        continue;
      }

      if (key === 'query') {
        // Express 5 exposes req.query via a getter, so assignment is rejected.
        Object.defineProperty(req, 'query', { value: result.data, writable: true });
      } else {
        req[key] = result.data as never;
      }
    }

    if (details.length > 0) {
      return next(validationError('The request could not be processed.', details));
    }

    next();
  };
}
