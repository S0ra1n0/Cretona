import jwt from 'jsonwebtoken';
import request from 'supertest';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const userFindMany = vi.fn();
const userCount = vi.fn();
const roleFindUnique = vi.fn();
const projectFindMany = vi.fn();

vi.mock('../src/lib/prisma.js', () => ({
  prisma: {
    user: {
      findUnique: (...a: unknown[]) => userFindUnique(...a),
      update: (...a: unknown[]) => userUpdate(...a),
      findMany: (...a: unknown[]) => userFindMany(...a),
      count: (...a: unknown[]) => userCount(...a),
    },
    role: { findUnique: (...a: unknown[]) => roleFindUnique(...a) },
    videoProject: { findMany: (...a: unknown[]) => projectFindMany(...a) },
  },
  checkDatabase: async () => true,
  disconnectPrisma: async () => {},
}));

const { createApp } = await import('../src/app.js');

const app = createApp();
const SECRET = 'test-jwt-secret-not-a-real-key';

const USER_ID = '11111111-1111-1111-1111-111111111111';
const ADMIN_ID = '22222222-2222-2222-2222-222222222222';

function token(sub: string): string {
  return jwt.sign({ sub, aud: 'authenticated' }, SECRET, {
    algorithm: 'HS256',
    expiresIn: '1h',
  });
}

const row = (over: Record<string, unknown> = {}) => ({
  id: USER_ID,
  email: 'user@cretona.test',
  username: null,
  roleId: 1,
  isDisabled: false,
  createdAt: new Date('2026-07-14T02:11:05Z'),
  role: { id: 1, name: 'user' },
  _count: { projects: 0 },
  ...over,
});

const adminRow = () =>
  row({ id: ADMIN_ID, email: 'admin@cretona.test', roleId: 2, role: { id: 2, name: 'admin' } });

beforeEach(() => {
  for (const m of [
    userFindUnique,
    userUpdate,
    userFindMany,
    userCount,
    roleFindUnique,
    projectFindMany,
  ]) {
    m.mockReset();
  }
  projectFindMany.mockResolvedValue([]);
});

describe('GET /api/v1/me', () => {
  it('returns the profile with quota, per API_CONTRACT §2.2', async () => {
    userFindUnique.mockResolvedValue(row());

    const res = await request(app).get('/api/v1/me').set('Authorization', `Bearer ${token(USER_ID)}`);

    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({
      id: USER_ID,
      email: 'user@cretona.test',
      role: 'user',
      isDisabled: false,
      quota: { limit: expect.any(Number), used: 0, remaining: expect.any(Number) },
    });
    expect(res.body.createdAt).toBe('2026-07-14T02:11:05.000Z');
  });

  it('requires authentication', async () => {
    const res = await request(app).get('/api/v1/me');

    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('UNAUTHENTICATED');
  });
});

describe('PATCH /api/v1/me', () => {
  it('rejects an invalid username with field-level detail', async () => {
    userFindUnique.mockResolvedValue(row());

    const res = await request(app)
      .patch('/api/v1/me')
      .set('Authorization', `Bearer ${token(USER_ID)}`)
      .send({ username: 'no spaces!' });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
    expect(res.body.error.details[0].field).toBe('body.username');
  });

  it('rejects an empty body', async () => {
    userFindUnique.mockResolvedValue(row());

    const res = await request(app)
      .patch('/api/v1/me')
      .set('Authorization', `Bearer ${token(USER_ID)}`)
      .send({});

    expect(res.status).toBe(400);
  });

  it('maps a unique-constraint violation to 409, not 500', async () => {
    userFindUnique.mockResolvedValue(row());
    const { Prisma } = await import('@prisma/client');
    userUpdate.mockRejectedValue(
      new Prisma.PrismaClientKnownRequestError('dup', {
        code: 'P2002',
        clientVersion: '7',
      }),
    );

    const res = await request(app)
      .patch('/api/v1/me')
      .set('Authorization', `Bearer ${token(USER_ID)}`)
      .send({ username: 'taken' });

    expect(res.status).toBe(409);
    expect(res.body.error.code).toBe('CONFLICT');
  });
});

describe('admin routes', () => {
  it('refuse a non-admin', async () => {
    userFindUnique.mockResolvedValue(row());

    for (const path of ['/api/v1/admin/users', '/api/v1/admin/stats']) {
      const res = await request(app).get(path).set('Authorization', `Bearer ${token(USER_ID)}`);
      expect(res.status).toBe(403);
      expect(res.body.error.code).toBe('FORBIDDEN');
    }
  });

  it('list users for an admin', async () => {
    userFindUnique.mockResolvedValue(adminRow());
    userFindMany.mockResolvedValue([row()]);

    const res = await request(app)
      .get('/api/v1/admin/users')
      .set('Authorization', `Bearer ${token(ADMIN_ID)}`);

    expect(res.status).toBe(200);
    expect(res.body.items[0]).toMatchObject({ email: 'user@cretona.test', projectCount: 0 });
    expect(res.body.page).toEqual({ nextCursor: null, hasMore: false });
  });

  it('cap the page size — an unbounded limit is a DoS vector', async () => {
    userFindUnique.mockResolvedValue(adminRow());

    const res = await request(app)
      .get('/api/v1/admin/users?limit=5000')
      .set('Authorization', `Bearer ${token(ADMIN_ID)}`);

    expect(res.status).toBe(400);
    expect(res.body.error.details[0].field).toBe('query.limit');
  });

  it('stop an admin disabling their own account (FR-4.6)', async () => {
    userFindUnique.mockResolvedValue(adminRow());

    const res = await request(app)
      .patch(`/api/v1/admin/users/${ADMIN_ID}`)
      .set('Authorization', `Bearer ${token(ADMIN_ID)}`)
      .send({ isDisabled: true });

    expect(res.status).toBe(403);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it('allow an admin to disable someone else', async () => {
    userFindUnique.mockResolvedValue(adminRow());
    userUpdate.mockResolvedValue(row({ isDisabled: true }));

    const res = await request(app)
      .patch(`/api/v1/admin/users/${USER_ID}`)
      .set('Authorization', `Bearer ${token(ADMIN_ID)}`)
      .send({ isDisabled: true });

    expect(res.status).toBe(200);
    expect(res.body.isDisabled).toBe(true);
  });

  it('reject a non-UUID user id', async () => {
    userFindUnique.mockResolvedValue(adminRow());

    const res = await request(app)
      .patch('/api/v1/admin/users/not-a-uuid')
      .set('Authorization', `Bearer ${token(ADMIN_ID)}`)
      .send({ isDisabled: true });

    expect(res.status).toBe(400);
  });

  it('reject an unknown role value', async () => {
    userFindUnique.mockResolvedValue(adminRow());

    const res = await request(app)
      .patch(`/api/v1/admin/users/${USER_ID}`)
      .set('Authorization', `Bearer ${token(ADMIN_ID)}`)
      .send({ role: 'superuser' });

    expect(res.status).toBe(400);
  });
});
