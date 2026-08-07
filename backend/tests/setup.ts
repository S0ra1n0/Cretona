/**
 * Test environment. Loaded before any module that reads config, so the strict
 * validation in src/config/env.ts is satisfied without a real .env.
 *
 * SUPABASE_JWT_SECRET here is what the auth tests sign their fixtures with.
 */
process.env.NODE_ENV = 'test';
process.env.LOG_LEVEL = 'fatal';
process.env.DATABASE_URL = 'postgresql://test:test@localhost:5432/test';
process.env.SUPABASE_URL = 'https://test.supabase.co';
process.env.SUPABASE_SERVICE_ROLE_KEY = 'test-service-role-key';
process.env.SUPABASE_JWT_SECRET = 'test-jwt-secret-not-a-real-key';
