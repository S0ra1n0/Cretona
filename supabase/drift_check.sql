-- =============================================================================
-- Schema drift check
--
-- Run in the Supabase SQL Editor after applying a migration, and compare the
-- output against backend/prisma/schema.prisma.
--
-- WHY NOT `prisma db pull`: public.users.id is a foreign key into auth.users
-- (ADR-002). Prisma refuses cross-schema references unless `auth` is added to
-- the datasource's `schemas`, which would pull Supabase's ~16 auth tables into
-- our model. `db pull` also overwrites schema.prisma, discarding the comments
-- and the deliberate partial-index note. The Prisma schema is hand-maintained
-- alongside the SQL here; this query is how you confirm the two still agree.
-- =============================================================================

-- 1. Columns ------------------------------------------------------------------
select
  table_name || '.' || column_name
    || ' : ' || data_type
    || case when is_nullable = 'YES' then ' null' else ' NOT NULL' end
    || coalesce(' default ' || column_default, '') as column_signature
from information_schema.columns
where table_schema = 'public'
  and table_name in ('roles', 'users', 'video_projects', 'generation_logs')
order by table_name, ordinal_position;

-- 2. Constraints --------------------------------------------------------------
select
  conrelid::regclass::text as table_name,
  conname                  as constraint_name,
  case contype
    when 'c' then 'check'
    when 'f' then 'foreign key'
    when 'p' then 'primary key'
    when 'u' then 'unique'
    else contype::text
  end                      as kind
from pg_constraint
where connamespace = 'public'::regnamespace
  and conrelid::regclass::text in ('roles', 'users', 'video_projects', 'generation_logs')
order by 1, 3, 2;

-- 3. Indexes ------------------------------------------------------------------
select tablename, indexname, indexdef
from pg_indexes
where schemaname = 'public'
  and tablename in ('roles', 'users', 'video_projects', 'generation_logs')
order by tablename, indexname;

-- 4. RLS and policies ---------------------------------------------------------
select relname as table_name, relrowsecurity as rls_enabled
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in ('users', 'video_projects', 'generation_logs')
order by relname;

select schemaname, tablename, policyname, cmd
from pg_policies
where (schemaname = 'public' and tablename in ('users', 'video_projects', 'generation_logs'))
   or (schemaname = 'storage' and tablename = 'objects')
order by schemaname, tablename, policyname;

-- =============================================================================
-- What to check
--
--   * Every column in section 1 has a matching field in schema.prisma, with the
--     same nullability. A column present here but missing there means Prisma
--     will silently ignore it on reads and fail on required-column writes.
--   * Section 4 must show rls_enabled = true on all three tables, and 10
--     policies total (6 on the app tables, 4 on storage.objects).
--
-- After adding a column in SQL, add the field to schema.prisma by hand, then
-- run `npm run prisma:generate`.
-- =============================================================================
