-- Local Postgres test schema.
--
-- ############################################################################
-- # DESTRUCTIVE. This file DROPs public.video_projects, public.users, and    #
-- # public.roles before recreating them. It is for a disposable local        #
-- # database only. tests/db_safety.py refuses to apply it to anything but a  #
-- # local host, so never point CRETONA_TEST_DATABASE_URL at Supabase.        #
-- ############################################################################
--
-- Mirrors the parts of supabase/bootstrap.sql + migrations 002 through 015
-- that app/postgres.py actually reads and writes.

drop schema if exists private cascade;
drop schema if exists storage cascade;
drop schema if exists auth cascade;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
end
$$;

create schema auth;
create function auth.uid() returns uuid
language sql stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
create function auth.jwt() returns jsonb
language sql stable
as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb;
$$;

create schema storage;
create table storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text not null,
  name text not null
);
alter table storage.objects enable row level security;
grant usage on schema storage to authenticated;
grant select, insert, update on storage.objects to authenticated;

-- Migration 013 tables. `drop table public.users cascade` reaches the ones
-- that reference users, but credit_packages and events have no foreign key to
-- it and would survive, so re-applying this file would fail on their CREATE.
drop table if exists public.credit_transactions cascade;
drop table if exists public.event_claims cascade;
drop table if exists public.events cascade;
drop table if exists public.payments cascade;
drop table if exists public.credit_packages cascade;
drop table if exists public.settings cascade;

drop table if exists public.admin_audit_logs cascade;
drop table if exists public.generation_logs cascade;
drop table if exists public.rate_limit_hits cascade;
drop table if exists public.video_projects cascade;
drop table if exists public.users cascade;
drop table if exists public.roles cascade;
drop type if exists public.project_status cascade;

create type public.project_status as enum ('pending', 'generating', 'completed', 'failed', 'cancelled');

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
  avatar_path text,
  gender      text,
  birthday    text,
  is_disabled boolean     not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint users_gender_allowed
    check (gender is null or gender in ('male', 'female', 'other')),
  constraint users_birthday_iso_date
    check (birthday is null or birthday ~ '^\d{4}-\d{2}-\d{2}$'),
  credit_balance integer not null default 0 check (credit_balance >= 0)
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
  progress_percent smallint       not null default 0,
  step_message     text,
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
      'content_policy', 'invalid_input', 'quota', 'timeout', 'provider_error', 'cancelled', 'unknown'
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

-- Mirrors supabase/008_add_admin_audit_logs.sql. actor_id is deliberately not
-- a foreign key: an audit trail must outlive the account it describes, and the
-- cascade this once had would have erased exactly that history.
create table public.admin_audit_logs (
  id          uuid        primary key default gen_random_uuid(),
  actor_id    uuid        not null,
  action      text        not null,
  target_type text        not null,
  target_id   text,
  details     jsonb,
  created_at  timestamptz not null default clock_timestamp()
);

create index idx_admin_audit_logs_created
  on public.admin_audit_logs (created_at desc, id desc);

create index idx_admin_audit_logs_action_created
  on public.admin_audit_logs (action, created_at desc, id desc);

create index idx_admin_audit_logs_actor_created
  on public.admin_audit_logs (actor_id, created_at desc, id desc);

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

create index idx_projects_started_at
  on public.video_projects (started_at)
  where status in ('pending', 'generating');

create index idx_projects_lease
  on public.video_projects (lease_expires_at)
  where status in ('pending', 'generating') and deleted_at is null;

create index idx_video_projects_provider_job
  on public.video_projects (provider, provider_job_id)
  where provider_job_id is not null;

create index idx_video_projects_deleted_user
  on public.video_projects (deleted_at, user_id);

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

-- ---------------------------------------------------------------------------
-- Credits, events, packages, payments and settings (migration 013).
-- Mirrors supabase/013_add_credits_and_events.sql. Contract: API_CONTRACT.md
-- Part II. RLS is omitted here on purpose: the tests connect as the owner.
-- ---------------------------------------------------------------------------

create table public.settings (
  key        text        primary key,
  value      text        not null,
  updated_by uuid        references public.users (id) on delete set null,
  updated_at timestamptz not null default now()
);

create table public.credit_packages (
  id         uuid        primary key default gen_random_uuid(),
  name       text        not null,
  credits    integer     not null check (credits > 0),
  price_vnd  integer     not null check (price_vnd >= 0),
  is_active  boolean     not null default true,
  sort_order integer     not null default 0,
  created_at timestamptz not null default now()
);

create table public.payments (
  id              uuid        primary key default gen_random_uuid(),
  user_id         uuid        not null references public.users (id) on delete cascade,
  package_id      uuid        not null references public.credit_packages (id),
  amount_vnd      integer     not null check (amount_vnd >= 0),
  credits_granted integer     not null check (credits_granted > 0),
  method          text        not null default 'simulated',
  status          text        not null check (status in ('pending', 'completed', 'failed')),
  idempotency_key text,
  created_at      timestamptz not null default now(),
  completed_at    timestamptz
);

create unique index uq_payments_idempotency
  on public.payments (user_id, idempotency_key)
  where idempotency_key is not null;

create index idx_payments_user_created
  on public.payments (user_id, created_at desc, id desc);

-- Minutes are local Vietnam time (UTC+7) from midnight: 1200 = 20:00.
create table public.events (
  id                 uuid        primary key default gen_random_uuid(),
  code               text        not null unique,
  name               text        not null,
  description        text,
  kind               text        not null check (kind in ('grant', 'discount')),
  bonus_credits      integer     check (bonus_credits > 0),
  discount_percent   integer     check (discount_percent between 1 and 100),
  recurrence         text        not null check (recurrence in ('once', 'daily', 'weekly')),
  active_days        text,
  active_from_minute integer     check (active_from_minute between 0 and 1440),
  active_to_minute   integer     check (active_to_minute between 0 and 1440),
  starts_at          timestamptz not null,
  ends_at            timestamptz not null,
  max_claims         integer     check (max_claims > 0),
  auto_grant         boolean     not null default false,
  is_active          boolean     not null default true,
  created_at         timestamptz not null default now(),
  constraint events_window_ordered check (ends_at > starts_at),
  constraint events_payload_matches_kind check (
        (kind = 'grant'    and bonus_credits    is not null and discount_percent is null)
     or (kind = 'discount' and discount_percent is not null and bonus_credits    is null)
  ),
  constraint events_daily_window_paired check (
    (active_from_minute is null) = (active_to_minute is null)
  )
);

create index idx_events_active_window
  on public.events (is_active, starts_at, ends_at);

-- The unique constraint is the enforcement, not a count-then-insert.
create table public.event_claims (
  id              uuid        primary key default gen_random_uuid(),
  event_id        uuid        not null references public.events (id) on delete cascade,
  user_id         uuid        not null references public.users (id) on delete cascade,
  period_key      text        not null default '',
  credits_granted integer     not null check (credits_granted > 0),
  created_at      timestamptz not null default now(),
  constraint uq_event_claims_per_period unique (event_id, user_id, period_key)
);

create index idx_event_claims_event_created
  on public.event_claims (event_id, created_at desc);

create index idx_event_claims_user_created
  on public.event_claims (user_id, created_at desc);

-- Append-only ledger. users.credit_balance is a cache written in the same
-- transaction; balance_after makes drift between the two detectable.
create table public.credit_transactions (
  id              uuid        primary key default gen_random_uuid(),
  user_id         uuid        not null references public.users (id) on delete cascade,
  delta           integer     not null check (delta <> 0),
  balance_after   integer     not null check (balance_after >= 0),
  reason          text        not null check (reason in (
                    'signup_bonus', 'event_grant', 'purchase',
                    'generation', 'refund', 'admin_adjustment')),
  ref_type        text        check (ref_type in ('project', 'payment', 'event')),
  ref_id          text,
  note            text,
  idempotency_key text,
  created_at      timestamptz not null default now()
);

create unique index uq_credit_tx_idempotency
  on public.credit_transactions (user_id, idempotency_key)
  where idempotency_key is not null;

create index idx_credit_tx_user_created
  on public.credit_transactions (user_id, created_at desc, id desc);

create index idx_credit_tx_reason_created
  on public.credit_transactions (reason, created_at desc);

create index idx_credit_tx_ref
  on public.credit_transactions (ref_type, ref_id);
