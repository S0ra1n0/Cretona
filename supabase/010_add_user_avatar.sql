-- Migration 010: Add profile avatar to public.users
--
-- Adds:
--  - avatar_path (text, nullable) -- storage object key, not a URL
--
-- The column holds the object key returned by the uploads endpoint
-- (`<user_id>/<date>/<uuid>.<ext>`), never a signed URL: signed URLs expire,
-- so persisting one guarantees a broken image within the hour. The read URL is
-- minted per response, exactly as video_path and thumbnail_path already are.
--
-- Safe to re-run. Does not drop existing data.

alter table public.users
  add column if not exists avatar_path text;
