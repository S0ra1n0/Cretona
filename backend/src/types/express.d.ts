import type { RoleName } from '../middleware/authorize.js';

/**
 * Request augmentation. `auth` is what the token asserted; `user` is what the
 * database says. Authorization always reads `user` — a role claim in a token
 * is client-influenced and is never trusted (ADR-002, SECURITY.md §2).
 */
declare global {
  namespace Express {
    interface Request {
      // `id` is intentionally not declared here — pino-http already augments
      // Express with `id: ReqId`, and a competing `string` declaration merges
      // into an error. Read it with String(req.id).

      auth?: {
        userId: string;
        email?: string;
      };

      user?: {
        id: string;
        email: string;
        username: string | null;
        roleId: number;
        role: RoleName;
        isDisabled: boolean;
      };
    }
  }
}

export {};
