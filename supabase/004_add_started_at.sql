-- =============================================================================
-- Migration 004 — per-attempt clock for the generation timeout
--
-- STATUS: PREPARED, NOT APPLIED. Do not run this against the remote Supabase
-- project without Bruce's approval. It is additive and re-runnable.
--
-- WHY: the generation timeout measures how long a project has been in flight.
-- It measured from `created_at`, which is the wrong clock for a retry: a
-- project created an hour ago and retried ten seconds ago would be failed
-- immediately as "timed out", making retry useless for exactly the transient
-- failures retry exists to handle.
--
-- `started_at` records when the current attempt was submitted to the provider.
-- It is set on submit and reset on every retry, so each attempt gets the full
-- timeout budget.
--
-- Nullable on purpose: rows written before this migration have no attempt
-- clock, and the backend falls back to `created_at` for them rather than
-- treating a NULL as "started at the epoch" and failing every old project.
--
-- Apply after 003_add_fastapi_parity_columns.sql. Safe to re-run.
-- =============================================================================

begin;

alter table public.video_projects
  add column if not exists started_at timestamptz;

-- Backfill the existing rows that are still in flight, so the deploy does not
-- immediately time out work that is legitimately running. Terminal rows are
-- left alone: their clock no longer matters.
update public.video_projects
   set started_at = created_at
 where started_at is null
   and status in ('pending', 'generating');

-- The poller scans in-flight work by age.
create index if not exists idx_projects_started_at
  on public.video_projects (started_at)
  where status in ('pending', 'generating');

commit;

-- Verify:
--   select column_name from information_schema.columns
--   where table_name = 'video_projects' and column_name = 'started_at';
--   -- expect: one row
--
--   select count(*) from public.video_projects
--   where status in ('pending', 'generating') and started_at is null;
--   -- expect: 0
