# Supabase

Database and storage setup for Cretona. Specified in [docs/DATA_MODEL.md](../docs/DATA_MODEL.md).

## Applying the schema

1. **Create the project** (P1-1) at [supabase.com](https://supabase.com). Pick the region closest to your users.
2. **Run [`bootstrap.sql`](bootstrap.sql)** — open the SQL Editor, paste the whole file, execute. It is one transaction and safe to re-run.

   Then apply the numbered migrations in order. The current sequence is
   `002_add_error_code.sql` through `007_add_shared_rate_limits.sql`; never
   skip a number. Live Supabase was observed with migrations 004 and 005
   already present, then migrations 006 and 007 were applied and verified on
   2026-08-14. The `PREPARED, NOT APPLIED` headers remain unchanged because
   editing an executed migration would invalidate its pinned execution hash;
   live status belongs in this README and the evidence ledger.
3. **Run the verification queries** at the bottom of that file. All must pass before moving on.

   > The RLS check filters on `relnamespace = 'public'::regnamespace` deliberately. `auth.users` is *also* called `users` and has RLS off, so an unfiltered query returns two `users` rows and looks like a failure when nothing is wrong.
4. **Create a test user** under Authentication → Users, then confirm the signup trigger fired:
   ```sql
   select id, email, role_id, is_disabled from public.users;
   ```
   One row, `role_id = 1`. If it's empty, the trigger on `auth.users` didn't fire — nothing downstream will work.
5. **Make yourself an admin** once you have a real account:
   ```sql
   update public.users set role_id = 2 where email = 'you@example.com';
   ```
6. **Copy the keys** (Settings → API and Settings → Database) into
   `local.properties` and the active `backend-fastapi/.env`, as described in
   [docs/SETUP.md](../docs/SETUP.md).

> Only the **anon** key goes in `local.properties`. The `service_role` key bypasses RLS entirely and belongs in the backend environment alone.

## Verification status

`bootstrap.sql` has been executed end to end against Postgres 16 in Docker, with `auth` and `storage` stubbed to match Supabase's real shape (`auth.uid()`, `storage.foldername()`, and Supabase's default grants on `storage.objects`). It applies cleanly in one transaction.

Behaviour confirmed, not just syntax:

| Check | Result |
|---|---|
| Signup trigger creates a `public.users` row with `role_id = 1` | pass |
| Email change in `auth.users` syncs to `public.users` | pass |
| All three CHECK constraints reject their bad case | pass |
| Duplicate `(user_id, idempotency_key)` rejected; multiple NULLs allowed | pass |
| A user sees only their own projects; soft-deleted rows hidden | pass |
| An admin sees all projects, including soft-deleted | pass |
| A user **cannot** set their own `role_id` — blocked by the column grant | pass |
| A user can still update their own `username` | pass |
| A user cannot read another user's row | pass |
| Storage: upload allowed under own prefix, denied under another user's | pass |
| Storage: `videos` bucket write denied to clients, read allowed for own objects | pass |

The 2026-08-14 live database verification additionally proved the 004–007
column/index contracts, MIG-007 constraints and RLS state, and zero table or
sequence privileges for `anon`, `authenticated`, and `service_role`. It did not
deploy or smoke-test FastAPI, read business rows, test Storage object bytes, or
prove restore viability. See
[`LIVE_SUPABASE_MIGRATIONS_006_007_2026-08-14.md`](../docs/evidence/LIVE_SUPABASE_MIGRATIONS_006_007_2026-08-14.md).

## Live operator commands

These commands read the ignored root `env` file, validate that its project URL
and direct database URL identify the same project, and suppress credential
values from output:

```powershell
# Protected logical export outside the repository; requires Docker Desktop.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup-live-supabase.ps1

# Current post-migration catalog/security verification.
backend-fastapi/.venv/Scripts/python.exe scripts/live-supabase-migration-gate.py verify-007

# Official Supabase Security and Performance Advisors.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-live-supabase-advisors.ps1
```

The migration gate also contains narrowly allowlisted apply actions, but they
refuse a changed file hash, a mismatched explicit project reference, or an
already-present target. Do not use them to invent a new migration workflow;
prepare and review a new numbered migration instead.

## What `bootstrap.sql` creates

| Section | Contents | Roadmap |
|---|---|---|
| 1–2 | `project_status` enum; `roles`, `users`, `video_projects`, `generation_logs` with CHECK constraints | P1-2, P1-8 |
| 3 | `roles` seeded with `user` (1) and `admin` (2) | P1-3 |
| 4 | `updated_at` triggers; `auth.users` → `public.users` signup mirror; email-change sync | P1-4 |
| 5 | Six indexes, three of them partial | P1-7 |
| 6 | RLS enabled on all three tables, plus `is_admin()` and seven policies | P1-5 |
| 7 | Column-level grants — the reason a client cannot promote itself to admin | P1-5 |
| 8 | Private `uploads` and `videos` buckets with owner-scoped object policies | P1-6 |

## Two layers, both required

RLS is **not** the authorization system. The backend connects with `service_role`, which bypasses RLS completely, so every read and write must still filter by owner in the service layer. RLS exists to contain the blast radius of the anon key that ships inside the APK — which is what makes shipping that key safe at all ([ADR-002](../docs/adr/ADR-002-auth-strategy.md), [ADR-005](../docs/adr/ADR-005-secrets-management.md)).

Policies decide which *rows* a client may touch. Grants decide which *columns*. `users_update_self` has no `role_id` guard, so the `grant update (username)` in section 7 is the only thing stopping self-promotion to admin. Removing it silently opens a privilege-escalation hole — nothing else in the system would catch it.

## Changing the schema later

Add a numbered file (`002_add_x.sql`) rather than editing `bootstrap.sql`, so an existing database can be brought forward. Then update:

- [docs/DATA_MODEL.md](../docs/DATA_MODEL.md) — the spec
- [backend/prisma/schema.prisma](../backend/prisma/schema.prisma) — the client model

`prisma db pull` reports drift between the schema file and the live database. Do **not** use `prisma migrate` — it does not know about the RLS policies, the `auth.users` trigger, or the partial indexes, and will try to remove them.

The B-3 rate-limit table is an exception to the Prisma-model update rule: it is
an internal concern of the active FastAPI adapter, while `backend/` is retained
only as Express migration evidence under ADR-008.
