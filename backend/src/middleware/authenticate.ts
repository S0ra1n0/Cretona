import type { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import { env } from '../config/env.js';
import { accountDisabled, tokenInvalid, unauthenticated } from '../lib/errors.js';
import { prisma } from '../lib/prisma.js';
import type { RoleName } from './authorize.js';

/**
 * Supabase access-token verification (P2-4).
 *
 * The app authenticates directly against Supabase Auth; we only verify the
 * resulting token (ADR-002). Supabase's legacy signing uses HS256 with the
 * project JWT secret. If the project is migrated to asymmetric signing keys,
 * only `verifyToken` below changes — swap the secret for a JWKS lookup.
 */
interface SupabaseClaims {
  sub: string;
  email?: string;
  exp: number;
  aud?: string | string[];
}

function verifyToken(token: string): SupabaseClaims {
  try {
    const decoded = jwt.verify(token, env.SUPABASE_JWT_SECRET, {
      algorithms: ['HS256'],
      // Supabase issues `aud: "authenticated"` for signed-in users.
      audience: 'authenticated',
    });

    if (typeof decoded === 'string' || !decoded.sub) {
      throw tokenInvalid('Malformed token.');
    }

    return decoded as unknown as SupabaseClaims;
  } catch (error) {
    if (error instanceof jwt.TokenExpiredError) {
      throw tokenInvalid('Your session has expired. Please sign in again.');
    }
    if (error instanceof jwt.JsonWebTokenError || error instanceof jwt.NotBeforeError) {
      throw tokenInvalid();
    }
    throw error;
  }
}

/** Step 1: prove who the caller claims to be. */
export function authenticate(req: Request, _res: Response, next: NextFunction): void {
  const header = req.header('authorization');

  if (!header) {
    return next(unauthenticated('Missing Authorization header.'));
  }

  const [scheme, token] = header.split(' ');
  if (scheme?.toLowerCase() !== 'bearer' || !token) {
    return next(unauthenticated('Authorization header must be "Bearer <token>".'));
  }

  try {
    const claims = verifyToken(token);
    req.auth = { userId: claims.sub, email: claims.email };
    next();
  } catch (error) {
    next(error);
  }
}

/**
 * Step 2: resolve the database row.
 *
 * Roles come from here, never from a token claim. A token proves identity; the
 * database decides authority.
 */
export async function loadUser(req: Request, _res: Response, next: NextFunction): Promise<void> {
  if (!req.auth) {
    return next(unauthenticated());
  }

  try {
    const row = await prisma.user.findUnique({
      where: { id: req.auth.userId },
      include: { role: true },
    });

    if (!row) {
      // The token is valid but no profile exists — the signup trigger did not
      // fire. Treat as unauthenticated rather than crashing downstream.
      return next(tokenInvalid('Your account is not set up. Please sign in again.'));
    }

    req.user = {
      id: row.id,
      email: row.email,
      username: row.username,
      roleId: row.roleId,
      role: row.role.name as RoleName,
      isDisabled: row.isDisabled,
    };

    next();
  } catch (error) {
    next(error);
  }
}

/**
 * Step 3: refuse disabled accounts (FR-1.8).
 *
 * Deliberately ordered before authorization so a disabled admin is stopped too
 * (ARCHITECTURE.md §4.1).
 */
export function rejectIfDisabled(req: Request, _res: Response, next: NextFunction): void {
  if (req.user?.isDisabled) {
    return next(accountDisabled());
  }
  next();
}

/** The full chain. Mount this on any route that needs a signed-in caller. */
export const requireAuth = [authenticate, loadUser, rejectIfDisabled] as const;
