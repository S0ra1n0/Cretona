import jwt from 'jsonwebtoken';
import { env, isProduction } from '../config/env.js';
import { prisma } from '../lib/prisma.js';

/**
 * Mints a backend access token for a seeded user, without going through
 * Supabase Auth.
 *
 * Useful when you want to exercise the API directly. It signs with
 * SUPABASE_JWT_SECRET using HS256 — exactly what src/middleware/authenticate.ts
 * verifies — so a token from here is indistinguishable from a real one as far
 * as the backend is concerned.
 *
 * It does NOT prove Supabase Auth works end to end. If the project has moved
 * to asymmetric JWT signing keys, real app tokens will not be HS256 and the
 * middleware will need a JWKS lookup instead.
 *
 *   npm run token -- user@cretona.test
 */
async function main(): Promise<void> {
  if (isProduction) {
    console.error('Refusing to mint tokens in production.');
    process.exit(1);
  }

  const email = process.argv[2] ?? 'user@cretona.test';

  const user = await prisma.user.findUnique({
    where: { email },
    include: { role: true },
  });

  if (!user) {
    console.error(`No user with email "${email}".`);
    console.error('Run supabase/seed_dev_users.sql first, or pass a different email.');
    process.exit(1);
  }

  const token = jwt.sign(
    {
      sub: user.id,
      email: user.email,
      aud: 'authenticated',
      role: 'authenticated',
    },
    env.SUPABASE_JWT_SECRET,
    { algorithm: 'HS256', expiresIn: '2h' },
  );

  console.error(`# ${user.email} · role=${user.role.name} · valid 2h`);
  // Token alone on stdout, so it can be captured: TOKEN=$(npm run -s token)
  console.log(token);

  await prisma.$disconnect();
}

void main().catch(async (error: unknown) => {
  console.error(error);
  await prisma.$disconnect();
  process.exit(1);
});
