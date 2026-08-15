-- =============================================================================
-- Migration 008 - admin audit log storage
--
-- STATUS: PREPARED, NOT APPLIED.
--
-- WHY: Provides structured, persistent, and queryable tracking of administrative
-- actions (user role changes, disable/enable, thumbnail backfills) for compliance
-- and diagnosis (B-6).
-- =============================================================================

begin;

create table if not exists public.admin_audit_logs (
  id          text        primary key,
  actor_id    text        not null,
  action      text        not null,
  target_type text        not null,
  target_id   text        not null,
  details     text        not null,
  created_at  timestamptz not null default clock_timestamp()
);

create index if not exists idx_admin_audit_logs_created_at
  on public.admin_audit_logs (created_at desc, id desc);

create index if not exists idx_admin_audit_logs_action
  on public.admin_audit_logs (action, created_at desc);

create index if not exists idx_admin_audit_logs_actor
  on public.admin_audit_logs (actor_id, created_at desc);

alter table public.admin_audit_logs enable row level security;

-- Only service_role can read/write directly; clients access via authenticated admin API
create policy "Service role full access on admin audit logs"
  on public.admin_audit_logs
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.admin_audit_logs is
  'Administrative operation audit logs (B-6).';

commit;
