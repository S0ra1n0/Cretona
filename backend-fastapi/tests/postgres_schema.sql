-- Local Postgres test schema.
--
-- ############################################################################
-- # DESTRUCTIVE. This file DROPs public.video_projects, public.users, and    #
-- # public.roles before recreating them. It is for a disposable local        #
-- # database only. tests/db_safety.py refuses to apply it to anything but a  #
-- # local host, so never point CRETONA_TEST_DATABASE_URL at Supabase.        #
-- ############################################################################
--
-- Mirrors the parts of supabase/bootstrap.sql + migrations 002 through 007
-- that app/postgres.py actually reads and writes.

drop table if exists public.admin_audit_logs cascade;
drop table if exists public.generation_logs cascade;
drop table if exists public.rate_limit_hits cascade;
drop table if exists public.video_projects cascade;
drop table if exists public.users cascade;
drop table if exists public.roles cascade;
drop type if exists public.project_status cascade;

create type public.project_status as enum ('pending', 'generating', 'completed', 'failed');

create table public.roles (
  id   smallserial primary key,
  name text        not null unique
);

insert into public.roles (id, name) values (1, 'user'), (2, 'admin');

create table public.users (
  id          uuid        primary key,
  role_id     smallint    not null default 1 references public.roles (id),
  username    text        unique,
  email       text        not null unique,
  is_disabled boolean     not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table public.video_projects (
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
  error_code       text,
  error_message    text,
  duration_seconds smallint,
  aspect_ratio     text           not null default '16:9',
  poll_count       smallint       not null default 0,
  idempotency_key  text,
  attempt_count    smallint       not null default 0,
  started_at       timestamptz,
  lease_owner      text,
  lease_expires_at timestamptz,
  created_at       timestamptz    not null default now(),
  updated_at       timestamptz    not null default now(),
  completed_at     timestamptz,
  deleted_at       timestamptz,

  constraint chk_title_length  check (char_length(title) between 1 and 120),
  constraint chk_prompt_length check (prompt is null or char_length(prompt) between 1 and 1000),
  constraint chk_has_input     check (prompt is not null or image_path is not null),
  constraint chk_completed_has_video
    check (status <> 'completed' or video_path is not null),
  constraint chk_failed_has_reason
    check (status <> 'failed' or error_message is not null),
  constraint chk_failed_has_code
    check (status <> 'failed' or error_code is not null),
  constraint chk_error_code check (
    error_code is null or error_code in (
      'content_policy', 'invalid_input', 'quota', 'timeout', 'provider_error', 'unknown'
    )
  ),
  constraint chk_aspect_ratio check (aspect_ratio in ('16:9', '9:16', '1:1')),
  constraint chk_poll_count_non_negative check (poll_count >= 0)
);

create table public.generation_logs (
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

create table public.admin_audit_logs (
  id          uuid        primary key default gen_random_uuid(),
  actor_id    uuid        not null references public.users (id) on delete cascade,
  action      text        not null,
  target_type text        not null,
  target_id   text,
  details     jsonb,
  created_at  timestamptz not null default now()
);

create index idx_admin_audit_logs_created
  on public.admin_audit_logs (created_at desc, id desc);

create table public.rate_limit_hits (
  id          bigserial   primary key,
  caller_key  text        not null,
  bucket      text        not null check (bucket in ('default', 'generation')),
  occurred_at timestamptz not null default clock_timestamp()
);

create index idx_rate_limit_caller_window
  on public.rate_limit_hits (caller_key, bucket, occurred_at, id);

create index idx_rate_limit_cleanup
  on public.rate_limit_hits (occurred_at, id);

create index idx_logs_project_created
  on public.generation_logs (project_id, created_at desc);

create index idx_logs_retention
  on public.generation_logs (created_at asc, id asc);

-- Idempotency is scoped per user (API_CONTRACT 1.5).
create unique index uq_projects_idempotency
  on public.video_projects (user_id, idempotency_key)
  where idempotency_key is not null;

create index idx_projects_user_created
  on public.video_projects (user_id, created_at desc)
  where deleted_at is null;

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_projects_updated_at
  before update on public.video_projects
  for each row execute function public.set_updated_at();
