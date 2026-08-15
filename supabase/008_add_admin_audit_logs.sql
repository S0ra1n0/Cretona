-- =============================================================================
-- Migration 008 - admin audit log storage
--
-- STATUS: PREPARED, NOT APPLIED. Confirmed unapplied on the live project on
-- 2026-08-15 (information_schema returned zero rows for admin_audit_logs).
--
-- WHY: structured, queryable tracking of administrative actions -- role
-- changes, enable/disable, thumbnail backfills -- for compliance and
-- diagnosis (B-6).
--
-- This file was corrected before first application. The original draft
-- disagreed with both the calling code and the test schema in ways that would
-- have failed at runtime:
--
--   * target_id was NOT NULL, but the thumbnail-backfill audit has no single
--     target, so every backfill would have raised a not-null violation after
--     already doing its work;
--   * details was NOT NULL text, but the caller may pass nothing, and the read
--     path expects an object rather than a JSON string;
--   * neither RLS privileges nor Data API grants were revoked, unlike the
--     sibling internal table in 007.
--
-- Apply after 007_add_shared_rate_limits.sql. Safe to re-run.
-- =============================================================================

begin;

create table if not exists public.admin_audit_logs (
  id          uuid        primary key default gen_random_uuid(),

  -- Deliberately not a foreign key to public.users. An audit trail has to
  -- outlive the account it describes; a cascade would erase exactly the
  -- history that matters when an account is removed.
  actor_id    uuid        not null,

  action      text        not null,
  target_type text        not null,

  -- Nullable: system-wide actions such as a thumbnail backfill have no single
  -- target row.
  target_id   text,

  -- jsonb, not text, so the read path returns an object and the writer can use
  -- the same Json adapter generation_logs already uses.
  details     jsonb,

  created_at  timestamptz not null default clock_timestamp(),

  constraint chk_admin_audit_action
    check (char_length(action) between 1 and 100),
  constraint chk_admin_audit_target_type
    check (char_length(target_type) between 1 and 50)
);

create index if not exists idx_admin_audit_logs_created_at
  on public.admin_audit_logs (created_at desc, id desc);

create index if not exists idx_admin_audit_logs_action
  on public.admin_audit_logs (action, created_at desc);

create index if not exists idx_admin_audit_logs_actor
  on public.admin_audit_logs (actor_id, created_at desc);

-- Internal table, reached only through the admin API. Matching 007: RLS on,
-- no policies, and no Data API privileges, so the shipped anon key cannot see
-- it even if a policy is added carelessly later.
alter table public.admin_audit_logs enable row level security;

revoke all on table public.admin_audit_logs from anon, authenticated, service_role;

comment on table public.admin_audit_logs is
  'Administrative operation audit logs (B-6). Written by the backend only.';

commit;

-- Verify after applying:
--   select column_name, data_type, is_nullable
--   from information_schema.columns
--   where table_schema = 'public' and table_name = 'admin_audit_logs'
--   order by ordinal_position;
--   -- expect: id uuid NO, actor_id uuid NO, action text NO,
--   --         target_type text NO, target_id text YES, details jsonb YES,
--   --         created_at timestamptz NO
--
--   select relrowsecurity from pg_class
--   where oid = 'public.admin_audit_logs'::regclass;
--   -- expect: true
--
--   select grantee, privilege_type from information_schema.role_table_grants
--   where table_schema = 'public' and table_name = 'admin_audit_logs'
--     and grantee in ('anon', 'authenticated', 'service_role');
--   -- expect: zero rows
--
-- Rollback (audit history is lost, so take a copy first):
--   drop table if exists public.admin_audit_logs;
