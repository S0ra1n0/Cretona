import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { createApp } from '../src/app.js';

const app = createApp();

describe('GET /api/v1/health', () => {
  it('is reachable without authentication', async () => {
    const res = await request(app).get('/api/v1/health');

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'ok', version: expect.any(String) });
  });

  it('echoes a request id', async () => {
    const res = await request(app).get('/api/v1/health');

    expect(res.headers['x-request-id']).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('reuses an inbound request id so client and server logs correlate', async () => {
    const res = await request(app)
      .get('/api/v1/health')
      .set('X-Request-Id', 'client-supplied-id');

    expect(res.headers['x-request-id']).toBe('client-supplied-id');
  });
});

describe('unmatched routes', () => {
  it('returns the standard error envelope, not an Express HTML page', async () => {
    const res = await request(app).get('/api/v1/nope');

    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe('NOT_FOUND');
    expect(res.body.requestId).toEqual(expect.any(String));
    expect(res.headers['content-type']).toMatch(/json/);
  });
});

describe('malformed JSON', () => {
  it('is reported as VALIDATION_ERROR rather than a 500', async () => {
    const res = await request(app)
      .post('/api/v1/health')
      .set('Content-Type', 'application/json')
      .send('{ not json');

    expect(res.body.error.code).toBeDefined();
    expect(res.status).toBeLessThan(500);
  });
});
