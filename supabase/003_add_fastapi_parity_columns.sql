-- =============================================================================
-- Migration 003 — columns the FastAPI runtime persists that bootstrap.sql lacks
--
-- STATUS: PREPARED, NOT APPLIED. Do not run this against the remote Supabase
-- project without Bruce's approval. It is additive and re-runnable, but the
-- handoff reserves remote schema changes for an explicit decision.
--
-- WHY: the active FastAPI backend (ADR-008) persists two fields that the
-- Express/Prisma schema never had:
--
--   aspect_ratio — part of the response contract (API_CONTRACT.md, the
--     `aspectRatio` field on a project). Express accepted it as a generation
--     option and passed it to the provider without storing it, so a project
--     read back from Postgres could not report the ratio it was created with.
--
--   poll_count — job-runner state. The FastAPI service advances a project on
--     read and needs a durable poll counter; Express kept the equivalent state
--     inside a separate poller process instead of on the row.
--
-- `attempt_count` is deliberately absent from this migration: bootstrap.sql
-- already defines it, and the FastAPI SQLite adapter is being widened to match
-- rather than the other way round.
--
-- Apply after bootstrap.sql and 002_add_error_code.sql. Safe to re-run.
-- =============================================================================

begin;

alter table public.video_projects
  add column if not exists aspect_ratio text not null default '16:9';

-- Text plus CHECK rather than an enum, for the same reason 002 chose it for
-- error_code: widening a CHECK is a one-line migration, ALTER TYPE is not.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'chk_aspect_ratio'
  ) then
    alter table public.video_projects
      add constraint chk_aspect_ratio check (
        aspect_ratio in ('16:9', '9:16', '1:1')
      );
  end if;
end
$$;

alter table public.video_projects
  add column if not exists poll_count smallint not null default 0;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'chk_poll_count_non_negative'
  ) then
    alter table public.video_projects
      add constraint chk_poll_count_non_negative check (poll_count >= 0);
  end if;
end
$$;

commit;

-- Verify:
--   select column_name from information_schema.columns
--   where table_name = 'video_projects'
--     and column_name in ('aspect_ratio', 'poll_count');
--   -- expect: two rows
--
--   select conname from pg_constraint
--   where conname in ('chk_aspect_ratio', 'chk_poll_count_non_negative');
--   -- expect: two rows
