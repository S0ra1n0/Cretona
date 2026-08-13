-- =============================================================================
-- Migration 007 - shared sliding-window rate-limit storage
--
-- STATUS: PREPARED, NOT APPLIED. Do not run this against the remote Supabase
-- project without Bruce's approval. It is additive and re-runnable.
--
-- WHY: the FastAPI in-memory limiter is process-local. Two API instances can
-- each grant a full allowance, and a restart forgets every active window.
-- This internal table gives Postgres deployments one shared source of truth.
-- SQLite deliberately keeps the credential-free in-memory fallback.
--
-- SECURITY: caller_key is a one-way digest, never a bearer token, user id, or
-- IP address. The table is not a client API: RLS is enabled without policies
-- and Data API roles receive no table or sequence privileges.
--
-- Apply after 006_add_generation_log_retention_index.sql and before deploying
-- the B-3 FastAPI revision. See docs/migrations/MIG-007-shared-rate-limits.json.
-- =============================================================================

begin;

create table if not exists public.rate_limit_hits (
  id          bigserial   primary key,
  caller_key  text        not null,
  bucket      text        not null,
  occurred_at timestamptz not null default clock_timestamp(),

  constraint chk_rate_limit_caller_key
    check (char_length(caller_key) between 3 and 64),
  constraint chk_rate_limit_bucket
    check (bucket in ('default', 'generation'))
);

create index if not exists idx_rate_limit_caller_window
  on public.rate_limit_hits (caller_key, bucket, occurred_at, id);

create index if not exists idx_rate_limit_cleanup
  on public.rate_limit_hits (occurred_at, id);

alter table public.rate_limit_hits enable row level security;

revoke all on table public.rate_limit_hits from anon, authenticated, service_role;
revoke all on sequence public.rate_limit_hits_id_seq from anon, authenticated, service_role;

comment on table public.rate_limit_hits is
  'Internal ephemeral sliding-window hits for FastAPI rate limiting (B-3).';

commit;

-- Verify after applying:
--   select column_name, data_type from information_schema.columns
--   where table_schema = 'public' and table_name = 'rate_limit_hits'
--   order by ordinal_position;
--   -- expect: id, caller_key, bucket, occurred_at
--
--   select relrowsecurity from pg_class
--   where oid = 'public.rate_limit_hits'::regclass;
--   -- expect: true
--
--   select grantee, privilege_type from information_schema.role_table_grants
--   where table_schema = 'public' and table_name = 'rate_limit_hits'
--     and grantee in ('anon', 'authenticated', 'service_role');
--   -- expect: zero rows
--
--   select indexname from pg_indexes
--   where schemaname = 'public' and tablename = 'rate_limit_hits'
--   order by indexname;
--   -- expect: primary key plus idx_rate_limit_caller_window and
--   -- idx_rate_limit_cleanup
--
-- Rollback only after reverting FastAPI to the pre-B-3 revision:
--   drop table if exists public.rate_limit_hits;
-- The rows are ephemeral burst-control state, not business data.
