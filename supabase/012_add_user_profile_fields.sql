-- Migration 012: Add optional profile details to public.users
--
-- Adds:
--  - gender   (text, nullable) -- 'male' | 'female' | 'other'
--  - birthday (text, nullable) -- ISO calendar date, 'YYYY-MM-DD'
--
-- Both are nullable and stay that way: only the username is required to
-- finish profile setup, so an account that has not chosen either reads as
-- null rather than as an empty string. The app renders null as "--".
--
-- `birthday` is text rather than `date` so the column round-trips as the same
-- ISO string on both database backends. The SQLite mirror in app/database.py
-- has no date type, and a Postgres `date` would come back as a Python
-- `datetime.date` that the `str | None` response field would then have to
-- special-case. The format is enforced by the check below and again by
-- MeUpdate before the value is ever written.
--
-- Safe to re-run. Does not drop existing data.

alter table public.users
  add column if not exists gender text;

alter table public.users
  add column if not exists birthday text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'users_gender_allowed'
  ) then
    alter table public.users
      add constraint users_gender_allowed
      check (gender is null or gender in ('male', 'female', 'other'));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'users_birthday_iso_date'
  ) then
    alter table public.users
      add constraint users_birthday_iso_date
      check (birthday is null or birthday ~ '^\d{4}-\d{2}-\d{2}$');
  end if;
end $$;
