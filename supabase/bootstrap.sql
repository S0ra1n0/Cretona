-- =============================================================================
-- Cretona — database bootstrap
-- Roadmap: P1-2 … P1-8 · Spec: docs/DATA_MODEL.md
--
-- Apply once, in the Supabase SQL editor, as the project owner.
-- Re-running is safe: every statement is guarded.
-- =============================================================================

begin;

-- -----------------------------------------------------------------------------
-- 1. Enums (P1-2)
-- -----------------------------------------------------------------------------

do $$
begin
  if not exists (select 1 from pg_type where typname = 'project_status') then
    create type public.project_status as enum ('pending', 'generating', 'completed', 'failed');
  end if;
end
$$;

-- -----------------------------------------------------------------------------
-- 2. Tables (P1-2)
-- -----------------------------------------------------------------------------

create table if not exists public.roles (
  id   smallserial primary key,
  name text        not null unique
);

-- users.id IS auth.users.id — one row per identity, never a separate key.
create table if not exists public.users (
  id          uuid        primary key references auth.users (id) on delete cascade,
  role_id     smallint    not null default 1 references public.roles (id),
  username    text        unique,
  email       text        not null unique,
  is_disabled boolean     not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint chk_users_username_format
    check (username is null or username ~ '^[A-Za-z0-9_]{3,30}$')
);

create table if not exists public.video_projects (
  id               uuid           primary key default gen_random_uuid(),
  user_id          uuid           not null references public.users (id) on delete cascade,
  title            text           not null,
  prompt           text,
  image_path       text,
  video_path       text,
  thumbnail_path   text,
  status           project_status not null default 'pending',
  provider         text           not null,
  provider_job_id  text,
  error_message    text,
  duration_seconds smallint,
  idempotency_key  text,
  attempt_count    smallint       not null default 0,
  created_at       timestamptz    not null default now(),
  updated_at       timestamptz    not null default now(),
  completed_at     timestamptz,
  deleted_at       timestamptz,

  constraint chk_title_length  check (char_length(title) between 1 and 120),
  constraint chk_prompt_length check (prompt is null or char_length(prompt) between 1 and 1000),

  -- A project must carry at least one input. This is what makes the three
  -- generation modes (text / image / text+image) representable in one table.
  constraint chk_has_input
    check (prompt is not null or image_path is not null),

  -- A completed project must have a video.
  constraint chk_completed_has_video
    check (status <> 'completed' or video_path is not null),

  -- A failed project must say why.
  constraint chk_failed_has_reason
    check (status <> 'failed' or error_message is not null)
);

create table if not exists public.generation_logs (
  id          bigserial   primary key,
  project_id  uuid        not null references public.video_projects (id) on delete cascade,
  provider    text        not null,
  request_id  text,
  event       text        not null,
  request     jsonb,
  response    jsonb,
  http_status integer,
  created_at  timestamptz not null default now(),

  constraint chk_log_event
    check (event in ('submit', 'poll', 'webhook', 'download', 'error'))
);

-- -----------------------------------------------------------------------------
-- 3. Seed roles (P1-3)
-- -----------------------------------------------------------------------------

insert into public.roles (id, name) values (1, 'user'), (2, 'admin')
on conflict (id) do nothing;

-- Keep the sequence ahead of the explicit ids we just inserted.
select setval(
  pg_get_serial_sequence('public.roles', 'id'),
  greatest((select max(id) from public.roles), 1)
);

-- -----------------------------------------------------------------------------
-- 4. Triggers (P1-4)
-- -----------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_users_updated_at on public.users;
create trigger trg_users_updated_at
  before update on public.users
  for each row execute function public.set_updated_at();

drop trigger if exists trg_projects_updated_at on public.video_projects;
create trigger trg_projects_updated_at
  before update on public.video_projects
  for each row execute function public.set_updated_at();

-- Mirror auth.users -> public.users on signup, defaulting to role 'user'.
-- Application code never inserts into public.users directly, so an account can
-- never exist in auth without a profile.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email, role_id)
  values (new.id, new.email, 1)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Keep the denormalized email in sync when the user changes it in auth.
create or replace function public.handle_user_email_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.email is distinct from old.email then
    update public.users set email = new.email where id = new.id;
  end if;
  return new;
end;
$$;

drop trigger if exists on_auth_user_email_changed on auth.users;
create trigger on_auth_user_email_changed
  after update of email on auth.users
  for each row execute function public.handle_user_email_change();

-- -----------------------------------------------------------------------------
-- 5. Indexes (P1-7)
-- -----------------------------------------------------------------------------

-- History list (FR-3.1).
create index if not exists idx_projects_user_created
  on public.video_projects (user_id, created_at desc)
  where deleted_at is null;

-- Poller scan (FR-2.7). Partial on purpose: it stays small no matter how many
-- completed projects accumulate.
create index if not exists idx_projects_status_created
  on public.video_projects (status, created_at)
  where status in ('pending', 'generating');

create index if not exists idx_projects_provider_job
  on public.video_projects (provider, provider_job_id);

-- Idempotency is scoped per user (API_CONTRACT §1.5).
create unique index if not exists uq_projects_idempotency
  on public.video_projects (user_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists idx_logs_project_created
  on public.generation_logs (project_id, created_at desc);

-- Oldest-first bounded retention scan (B-4). Without this, every daily sweep
-- must inspect the full audit table as it grows.
create index if not exists idx_logs_retention
  on public.generation_logs (created_at asc, id asc);

-- Admin search (FR-4.1).
create index if not exists idx_users_email_lower
  on public.users (lower(email));

-- -----------------------------------------------------------------------------
-- 6. Row Level Security (P1-5)
--
-- The backend uses the service_role key, which bypasses RLS. These policies are
-- the second line of defence for the anon key shipped in the app -- they are not
-- a substitute for authorization checks in the service layer (NFR-2.3/2.4).
-- -----------------------------------------------------------------------------

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.users u
    join public.roles r on r.id = u.role_id
    where u.id = auth.uid() and r.name = 'admin'
  );
$$;

alter table public.users           enable row level security;
alter table public.video_projects  enable row level security;
alter table public.generation_logs enable row level security;

-- users
drop policy if exists users_select_self on public.users;
create policy users_select_self on public.users
  for select using (id = auth.uid() or public.is_admin());

drop policy if exists users_update_self on public.users;
create policy users_update_self on public.users
  for update using (id = auth.uid()) with check (id = auth.uid());

-- video_projects
drop policy if exists projects_select_own on public.video_projects;
create policy projects_select_own on public.video_projects
  for select using (
    (user_id = auth.uid() and deleted_at is null) or public.is_admin()
  );

drop policy if exists projects_insert_own on public.video_projects;
create policy projects_insert_own on public.video_projects
  for insert with check (user_id = auth.uid());

drop policy if exists projects_update_own on public.video_projects;
create policy projects_update_own on public.video_projects
  for update using (user_id = auth.uid()) with check (user_id = auth.uid());

-- generation_logs: readable only through owned projects, never client-writable.
drop policy if exists logs_select_own on public.generation_logs;
create policy logs_select_own on public.generation_logs
  for select using (
    exists (
      select 1 from public.video_projects p
      where p.id = generation_logs.project_id
        and (p.user_id = auth.uid() or public.is_admin())
    )
  );

-- -----------------------------------------------------------------------------
-- 7. Column-level grants
--
-- Policies decide WHICH ROWS a client may touch; grants decide WHICH COLUMNS.
-- users_update_self has no role_id guard, so the grant is what stops a client
-- from promoting itself to admin. Both layers are required.
-- -----------------------------------------------------------------------------

revoke all on public.users           from anon, authenticated;
revoke all on public.video_projects  from anon, authenticated;
revoke all on public.generation_logs from anon, authenticated;
revoke all on public.roles           from anon, authenticated;

grant select on public.roles           to authenticated;
grant select on public.users           to authenticated;
grant update (username) on public.users to authenticated;
grant select on public.video_projects  to authenticated;
grant select on public.generation_logs to authenticated;

-- Writes to projects and logs go through the backend with the service_role key.

-- -----------------------------------------------------------------------------
-- 8. Storage buckets (P1-6)
--
-- Object names inside a bucket do NOT repeat the bucket name, so the documented
-- path `uploads/{user_id}/...` is stored as name = '{user_id}/...' in bucket
-- 'uploads'. That first segment is what the policies below authorize on.
-- -----------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('uploads', 'uploads', false), ('videos', 'videos', false)
on conflict (id) do nothing;

-- uploads: the app writes its own source images and reads them back.
drop policy if exists uploads_insert_own on storage.objects;
create policy uploads_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists uploads_select_own on storage.objects;
create policy uploads_select_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists uploads_delete_own on storage.objects;
create policy uploads_delete_own on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- videos: read-only for the owner. Only the backend (service_role) writes here.
drop policy if exists videos_select_own on storage.objects;
create policy videos_select_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'videos'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

commit;

-- =============================================================================
-- Verification — run these after applying. Each should return the noted result.
-- =============================================================================
--
--   select name from public.roles order by id;
--   -- expect: user, admin
--
--   -- The schema filter matters: auth.users is ALSO called "users" and has RLS
--   -- off, so an unfiltered query makes it look like this failed.
--   select relname, relrowsecurity from pg_class
--   where relnamespace = 'public'::regnamespace
--     and relname in ('users','video_projects','generation_logs');
--   -- expect: relrowsecurity = true for all three
--
--   select id, public from storage.buckets where id in ('uploads','videos');
--   -- expect: public = false for both
--
--   select count(*) from pg_policies
--   where (schemaname = 'public' and tablename in ('users','video_projects','generation_logs'))
--      or (schemaname = 'storage' and tablename = 'objects');
--   -- expect: 10  (6 on the app tables, 4 on storage.objects)
--
--   -- Then sign up a test user in Authentication -> Users and confirm the
--   -- trigger fired:
--   select id, email, role_id, is_disabled from public.users;
--   -- expect: one row, role_id = 1, is_disabled = false
-- =============================================================================
