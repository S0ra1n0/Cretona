import { randomUUID } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';

/**
 * Assigns a request id and echoes it back (P2-7).
 *
 * The same value appears in every log line for the request and in the error
 * envelope, so a user-reported failure can be traced without asking them for
 * anything but that id (API_CONTRACT §1.3).
 */
export function requestId(req: Request, res: Response, next: NextFunction): void {
  const incoming = req.header('x-request-id');
  req.id = incoming && incoming.length <= 64 ? incoming : randomUUID();
  res.setHeader('X-Request-Id', req.id);
  next();
}
