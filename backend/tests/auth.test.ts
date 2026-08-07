import express from 'express';
import jwt from 'jsonwebtoken';
import request from 'supertest';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The auth chain hits the database, so the client is mocked. These tests are
// about the middleware's decisions, not about Prisma.
const findUnique = vi.fn();
vi.mock('../src/lib/prisma.js', () => ({
  prisma: { user: { findUnique: (...args: unknown[]) => findUnique(...args) } },
  checkDatabase: async () => true,
  disconnectPrisma: async () => {},
}));

const { requireAuth } = await import('../src/middleware/authenticate.js');
const { requireAdmin } = await import('../src/middleware/authorize.js');
const { errorHandler } = await import('../src/middleware/errorHandler.js');
const { requestId } = await import('../src/middleware/requestId.js');

const SECRET = 'test-jwt-secret-not-a-real-key';

function token(sub: string, overrides: Record<string, unknown> = {}): string {
  return jwt.sign({ sub, email: 'x@example.com', aud: 'authenticated', ...overrides }, SECRET, {
    algorithm: 'HS256',
    expiresIn: '1h',
  });
}

function buildApp() {
  const app = express();
  app.use(requestId);
  app.get('/me', ...requireAuth, (req, res) => res.json({ role: req.user?.role }));
  app.get('/admin', ...requireAuth, requireAdmin, (_req, res) => res.json({ ok: true }));
  app.use(errorHandler);
  return app;
}

const app = buildApp();

const dbUser = (over: Record<string, unknown> = {}) => ({
  id: 'user-1',
  email: 'x@example.com',
  username: null,
  roleId: 1,
  isDisabled: false,
  role: { id: 1, name: 'user' },
  ...over,
});

beforeEach(() => findUnique.mockReset());

describe('authenticate', () => {
  it('rejects a missing Authorization header', async () => {
    const res = await request(app).get('/me');
    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('UNAUTHENTICATED');
  });

  it('rejects a non-Bearer scheme', async () => {
    const res = await request(app).get('/me').set('Authorization', 'Basic abc');
    expect(res.body.error.code).toBe('UNAUTHENTICATED');
  });

  it('rejects a token signed with the wrong secret', async () => {
    const forged = jwt.sign({ sub: 'user-1', aud: 'authenticated' }, 'wrong-secret');
    const res = await request(app).get('/me').set('Authorization', `Bearer ${forged}`);

    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('TOKEN_INVALID');
  });

  it('rejects an expired token', async () => {
    const expired = jwt.sign({ sub: 'user-1', aud: 'authenticated' }, SECRET, { expiresIn: -60 });
    const res = await request(app).get('/me').set('Authorization', `Bearer ${expired}`);

    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('TOKEN_INVALID');
  });

  it('rejects the "none" algorithm', async () => {
    const header = Buffer.from(JSON.stringify({ alg: 'none', typ: 'JWT' })).toString('base64url');
    const payload = Buffer.from(JSON.stringify({ sub: 'user-1', aud: 'authenticated' })).toString(
      'base64url',
    );
    const res = await request(app)
      .get('/me')
      .set('Authorization', `Bearer ${header}.${payload}.`);

    expect(res.status).toBe(401);
  });

  it('accepts a valid token', async () => {
    findUnique.mockResolvedValue(dbUser());
    const res = await request(app).get('/me').set('Authorization', `Bearer ${token('user-1')}`);

    expect(res.status).toBe(200);
    expect(res.body.role).toBe('user');
  });
});

describe('loadUser', () => {
  it('rejects a valid token with no profile row', async () => {
    findUnique.mockResolvedValue(null);
    const res = await request(app).get('/me').set('Authorization', `Bearer ${token('ghost')}`);

    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('TOKEN_INVALID');
  });

  it('takes the role from the database, not from the token', async () => {
    findUnique.mockResolvedValue(dbUser());

    // The token claims admin. The database says otherwise, and wins.
    const res = await request(app)
      .get('/admin')
      .set('Authorization', `Bearer ${token('user-1', { role: 'admin', user_role: 'admin' })}`);

    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe('FORBIDDEN');
  });
});

describe('rejectIfDisabled', () => {
  it('refuses a disabled account', async () => {
    findUnique.mockResolvedValue(dbUser({ isDisabled: true }));
    const res = await request(app).get('/me').set('Authorization', `Bearer ${token('user-1')}`);

    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe('ACCOUNT_DISABLED');
  });

  it('refuses a disabled admin too — the check runs before authorization', async () => {
    findUnique.mockResolvedValue(
      dbUser({ isDisabled: true, roleId: 2, role: { id: 2, name: 'admin' } }),
    );
    const res = await request(app).get('/admin').set('Authorization', `Bearer ${token('admin-1')}`);

    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe('ACCOUNT_DISABLED');
  });
});

describe('requireRole', () => {
  it('allows an admin through', async () => {
    findUnique.mockResolvedValue(dbUser({ roleId: 2, role: { id: 2, name: 'admin' } }));
    const res = await request(app).get('/admin').set('Authorization', `Bearer ${token('admin-1')}`);

    expect(res.status).toBe(200);
  });
});
