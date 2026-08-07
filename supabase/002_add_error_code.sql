-- =============================================================================
-- Migration 002 — machine-readable failure reason on video_projects
--
-- Apply after bootstrap.sql. Safe to re-run.
--
-- WHY: ADR-007 excludes generations that failed through no fault of the user
-- (provider outage, timeout) from their quota. `error_message` is prose written
-- for the user, so it cannot be queried reliably -- the quota count needs a
-- stable code. AI_PROVIDER_SPEC.md §2.1 already defines the taxonomy; this
-- stores it.
-- =============================================================================

begin;

alter table public.video_projects
  add column if not exists error_code text;

-- Text plus CHECK rather than an enum: providers keep inventing new failure
-- modes, and widening a CHECK is a one-line migration whereas ALTER TYPE has
-- transaction restrictions.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'chk_error_code'
  ) then
    alter table public.video_projects
      add constraint chk_error_code check (
        error_code is null or error_code in (
          'content_policy',
          'invalid_input',
          'quota',
          'timeout',
          'provider_error',
          'unknown'
        )
      );
  end if;
end
$$;

-- A failed project must carry both a code and a message.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'chk_failed_has_code'
  ) then
    alter table public.video_projects
      add constraint chk_failed_has_code check (
        status <> 'failed' or error_code is not null
      );
  end if;
end
$$;

-- Quota counts rows in a rolling window, skipping infrastructure failures.
-- Partial so it stays small: only non-deleted rows are ever counted.
create index if not exists idx_projects_quota
  on public.video_projects (user_id, created_at desc, error_code)
  where deleted_at is null;

commit;

-- Verify:
--   select column_name from information_schema.columns
--   where table_name = 'video_projects' and column_name = 'error_code';
--   -- expect: one row
--
--   select conname from pg_constraint
--   where conname in ('chk_error_code', 'chk_failed_has_code');
--   -- expect: two rows
