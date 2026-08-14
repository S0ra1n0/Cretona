# B-3 disposable-Postgres verification

**Executed:** 2026-08-14 · **Source:** `101e16d6ac499925b0bfee3a9513a8dbbcee97a2`

## Scope

This run closes the local PostgreSQL evidence gap recorded in the B-3 commit.
It verifies the real psycopg/Postgres path and the prepared migration file; it
does not apply or prove anything against the live Supabase project.

The target was a PostgreSQL 16 Alpine container bound only to localhost port
55432, with no volume. The database name and credential were disposable test
values and are not recorded here.

## Executed evidence

1. Focused concurrency test:

   ```text
   pytest tests/test_postgres_parity.py::test_rate_limit_is_atomic_across_postgres_instances
   1 passed
   ```

   Two independent `PostgresDatabase` pools issued 20 concurrent attempts
   against one caller/bucket with a limit of five. Exactly five were accepted,
   and their remaining counts were `4, 3, 2, 1, 0`.

2. Full FastAPI suite with `CRETONA_TEST_DATABASE_URL` pointing at that local
   disposable database:

   ```text
   261 passed, 0 skipped, 1 warning in 23.14s
   ```

   The warning is the existing Starlette TestClient/httpx2 deprecation notice.

3. Migration rehearsal against a second empty database in the same container:

   - applied `supabase/007_add_shared_rate_limits.sql` with
     `ON_ERROR_STOP=1`;
   - applied the same file a second time successfully;
   - PostgreSQL reported only expected `already exists, skipping` notices on
     the second pass;
   - observed PostgreSQL version `16.14`;
   - `relrowsecurity = true`;
   - three indexes exist, including the primary key;
   - `anon`, `authenticated`, and `service_role` have no table or sequence
     access.

4. Cleanup:

   - stopped the `cretona-b3-postgres` container;
   - Docker `--rm` removed it;
   - no named or anonymous QA volume was created.

## Evidence boundary

This proves B-3 behavior and migration syntax/re-runnability on disposable
PostgreSQL 16.14. It does not prove live Supabase schema drift, backup state,
connection latency, migration ordering, Data API configuration, or
multi-instance behavior in the deployed environment. Migrations 004 through
007 remain prepared and unapplied to live Supabase, and their deployment hold
points remain in `docs/migrations/MIG-007-shared-rate-limits.json`.
