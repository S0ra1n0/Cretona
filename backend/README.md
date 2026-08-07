# Cretona Backend

Node.js 20+ · Express 5 · TypeScript (ESM) · Prisma 7 · Supabase Postgres

The core scaffold is in place (**P2-1 … P2-8**). Route handlers land next — see
[the roadmap](../Cretona_Roadmap.md).

## Setup

```bash
npm install
```

```bash
cp .env.example .env
```

Fill in `.env` — every key is commented there, and where to find each value is in
[docs/SETUP.md](../docs/SETUP.md) §4. Then:

```bash
npm run prisma:generate
```

```bash
npm run dev
```

The API listens on `http://localhost:3000/api/v1`. Confirm it:

```bash
curl http://localhost:3000/api/v1/health
```

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Watch mode via tsx |
| `npm run build` | Compile to `dist/` |
| `npm start` | Run the compiled build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest |
| `npm run prisma:generate` | Regenerate the client after a schema change |
| `npm run prisma:pull` | Introspect the live database and report schema drift |

## Layout

```text
src/
├── config/env.ts        environment validation — process exits on a bad value
├── lib/
│   ├── errors.ts        AppError + the error-code table
│   ├── logger.ts        pino, with redaction configured centrally
│   └── prisma.ts        client singleton over the pg driver adapter
├── middleware/
│   ├── requestId.ts     assigns and echoes X-Request-Id
│   ├── authenticate.ts  verify JWT → load user → reject if disabled
│   ├── authorize.ts     requireRole / requireAdmin
│   ├── validate.ts      zod schemas per route
│   ├── rateLimit.ts     per-user and per-IP ceilings
│   └── errorHandler.ts  the ONLY place an error becomes a response
├── controllers/         parse request → call service → shape response
├── routes/              routing only, no logic
└── app.ts               middleware assembly, in pipeline order
```

## Rules that keep this maintainable

- **Controllers hold no business logic and no Prisma calls.** Services do the work.
- **Only `errorHandler` writes an error body.** Throw `AppError`; it does the rest, so the client has one envelope to parse.
- **Roles come from the database, never from a token claim.** A JWT proves identity; the `users` row decides authority. There is a test asserting a token claiming `admin` still gets 403.
- **`rejectIfDisabled` runs before authorization**, so a disabled admin is stopped too.
- **Redaction is configured in `logger.ts`**, not at call sites — no code path can leak a credential by forgetting.

## Endpoints

| Route | Status |
|---|---|
| `GET /api/v1/health` | live — liveness, unauthenticated, no dependencies |
| `GET /api/v1/health/ready` | live — readiness, 503 when the database is unreachable |
| `/me`, `/uploads` | P2-9, P2-14 |
| `/projects` | P2-10 … P2-13 |
| `/admin/*` | P2-15 … P2-17 |

Liveness and readiness are separate on purpose: a failing database should stop
traffic being routed here, not cause the platform to restart the process.

## Prisma 7 notes

Two things changed from earlier Prisma versions and will bite if you assume otherwise:

- **Connection URLs are no longer in `schema.prisma`.** The CLI reads them from `prisma.config.ts`; the runtime client gets one through a driver adapter in `src/lib/prisma.ts`.
- **There is no bundled query engine.** `@prisma/adapter-pg` over `pg` provides the connection, which is why `pg` is a runtime dependency.

`prisma.config.ts` prefers `DIRECT_URL` because introspection and migrations must
bypass the pgbouncer pool — it does not support the prepared statements and
advisory locks they need.

Migrations stay owned by SQL in [`supabase/`](../supabase/). **Do not run
`prisma migrate`** — it does not know about the RLS policies, the `auth.users`
trigger, or the partial indexes, and will try to drop them. Use
`npm run prisma:pull` to check for drift instead.
