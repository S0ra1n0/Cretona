-- Migration 009: Add progress tracking and cancellation support to video_projects
--
-- Adds:
--  - progress_percent (smallint default 0, 0-100)
--  - step_message (text)
--  - updates chk_error_code to allow 'cancelled'
--
-- Safe to re-run. Does not drop existing data.

alter table public.video_projects
  add column if not exists progress_percent smallint not null default 0,
  add column if not exists step_message text;

-- Update error_code check constraint to include 'cancelled'
alter table public.video_projects
  drop constraint if exists chk_error_code;

alter table public.video_projects
  add constraint chk_error_code check (
    error_code is null or error_code in (
      'content_policy', 'invalid_input', 'quota', 'timeout', 'provider_error', 'cancelled', 'unknown'
    )
  );
