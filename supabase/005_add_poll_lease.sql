-- =============================================================================
-- Migration 005 — durable poller lease
--
-- STATUS: PREPARED, NOT APPLIED. Do not run this against the remote Supabase
-- project without Bruce's approval. It is additive and re-runnable.
--
-- WHY: the poller claimed work with SELECT ... FOR UPDATE SKIP LOCKED, which
-- holds the row only for the duration of that transaction. The claim committed
-- and released before any advancing happened, so the lock protected the SELECT
-- and nothing else. Two pollers could claim the same project and submit it to
-- the provider twice -- paying twice and racing each other's writes.
--
-- A row lock cannot span the work because the work is HTTP calls to a provider,
-- which must not happen inside an open transaction. So the claim has to
-- outlive the transaction, which means it has to be data.
--
-- `lease_owner` records which poller instance holds the row, and
-- `lease_expires_at` when that claim lapses. A poller that crashes or hangs
-- mid-batch stops renewing; the lease expires and another instance may take
-- the row. That is the recovery path -- an unexpiring claim would strand work
-- forever on a dead instance.
--
-- Apply after 004_add_started_at.sql. Safe to re-run.
-- =============================================================================

begin;

alter table public.video_projects
  add column if not exists lease_owner text;

alter table public.video_projects
  add column if not exists lease_expires_at timestamptz;

-- The claim query filters on this, so it is the index that matters. Partial,
-- because terminal projects are never claimed and would only bloat it.
create index if not exists idx_projects_lease
  on public.video_projects (lease_expires_at)
  where status in ('pending', 'generating') and deleted_at is null;

commit;

-- Verify:
--   select column_name from information_schema.columns
--   where table_name = 'video_projects'
--     and column_name in ('lease_owner', 'lease_expires_at');
--   -- expect: two rows
--
--   select count(*) from public.video_projects where lease_owner is not null;
--   -- expect: 0 immediately after applying
