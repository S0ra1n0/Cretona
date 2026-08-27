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

-- -----------------------------------------------------------------------------
-- 9. Credits, events, packages, payments and settings (migration 013)
--
-- Included verbatim from supabase/013_add_credits_and_events.sql so a fresh
-- install and a migrated install end at the same schema. Contract:
-- docs/API_CONTRACT.md Part II.
-- -----------------------------------------------------------------------------

-- -----------------------------------------------------------------------------
-- 1. Balance cache on users
-- -----------------------------------------------------------------------------

alter table public.users
  add column if not exists credit_balance integer not null default 0;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'users_credit_balance_non_negative'
  ) then
    alter table public.users
      add constraint users_credit_balance_non_negative
      check (credit_balance >= 0);
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- 2. Settings — admin-configurable values (§3 "cấu hình chi phí tạo video")
-- -----------------------------------------------------------------------------

create table if not exists public.settings (
  key        text        primary key,
  value      text        not null,
  updated_by uuid        references public.users (id) on delete set null,
  updated_at timestamptz not null default now()
);

insert into public.settings (key, value) values
  ('generation_cost_credits', '1')
on conflict (key) do nothing;

-- -----------------------------------------------------------------------------
-- 3. Credit packages (§5 "Credit Packages")
--
-- Never deleted, only deactivated: `payments` references them, and a purchase
-- history that loses the thing purchased is not a history.
-- -----------------------------------------------------------------------------

create table if not exists public.credit_packages (
  id         uuid        primary key default gen_random_uuid(),
  name       text        not null,
  credits    integer     not null check (credits > 0),
  price_vnd  integer     not null check (price_vnd >= 0),
  is_active  boolean     not null default true,
  sort_order integer     not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_credit_packages_active
  on public.credit_packages (is_active, sort_order);

-- -----------------------------------------------------------------------------
-- 4. Payments (§5 "Payments")
--
-- No real money moves — see ADR-010. The row, the state machine, the
-- idempotency key and the ledger entry are all real; only the gateway
-- confirmation is stubbed.
-- -----------------------------------------------------------------------------

create table if not exists public.payments (
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

-- Partial, so many rows may carry a null key while any present key is unique
-- per user. This is what makes a retried purchase return the original payment
-- instead of granting a second time.
create unique index if not exists uq_payments_idempotency
  on public.payments (user_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists idx_payments_user_created
  on public.payments (user_id, created_at desc, id desc);

create index if not exists idx_payments_status_created
  on public.payments (status, created_at desc);

-- -----------------------------------------------------------------------------
-- 5. Events (§5 "Promotions")
--
-- `kind` decides which payload column is required; the check below enforces
-- that rather than leaving both nullable and hoping the service is careful.
--
-- Minutes are LOCAL Vietnam time (UTC+7), stored as minutes from midnight:
-- 1200 = 20:00, 1320 = 22:00. Storing minutes rather than a timestamp is what
-- lets one row mean "every day between 20:00 and 22:00" without generating a
-- row per day. The server converts; the client never computes a window.
-- -----------------------------------------------------------------------------

create table if not exists public.events (
  id                 uuid        primary key default gen_random_uuid(),
  code               text        not null unique,
  name               text        not null,
  description        text,
  kind               text        not null check (kind in ('grant', 'discount')),
  bonus_credits      integer     check (bonus_credits > 0),
  discount_percent   integer     check (discount_percent between 1 and 100),
  recurrence         text        not null check (recurrence in ('once', 'daily', 'weekly')),
  active_days        text,       -- 'sat,sun' when recurrence = 'weekly'
  active_from_minute integer     check (active_from_minute between 0 and 1440),
  active_to_minute   integer     check (active_to_minute between 0 and 1440),
  starts_at          timestamptz not null,
  ends_at            timestamptz not null,
  max_claims         integer     check (max_claims > 0),   -- null = uncapped
  auto_grant         boolean     not null default false,   -- signup bonus
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

create index if not exists idx_events_active_window
  on public.events (is_active, starts_at, ends_at);

-- -----------------------------------------------------------------------------
-- 6. Event claims (§5 "Promotion Registrations")
--
-- `period_key` is what makes a recurring event claimable once per occurrence:
-- '' for `once`, the local date ('2026-08-30') for `daily`, the ISO week
-- ('2026-W35') for `weekly`.
--
-- THE UNIQUE INDEX IS THE ENFORCEMENT. Reading a count and then inserting
-- loses to a double-tap on a phone, and the loser of that race is the campaign
-- budget. The service must insert and let a conflict mean "already claimed",
-- never check-then-write.
-- -----------------------------------------------------------------------------

create table if not exists public.event_claims (
  id              uuid        primary key default gen_random_uuid(),
  event_id        uuid        not null references public.events (id) on delete cascade,
  user_id         uuid        not null references public.users (id) on delete cascade,
  period_key      text        not null default '',
  credits_granted integer     not null check (credits_granted > 0),
  created_at      timestamptz not null default now(),
  constraint uq_event_claims_per_period unique (event_id, user_id, period_key)
);

create index if not exists idx_event_claims_event_created
  on public.event_claims (event_id, created_at desc);

create index if not exists idx_event_claims_user_created
  on public.event_claims (user_id, created_at desc);

-- -----------------------------------------------------------------------------
-- 7. Credit transactions (§5 "Credit Transactions") — the append-only ledger
--
-- `delta` is signed: positive grants, negative charges. `balance_after` is the
-- balance immediately after this row was written, which is what makes drift
-- between the ledger and users.credit_balance detectable:
--
--   select u.id from public.users u
--   where u.credit_balance <> coalesce(
--     (select sum(t.delta) from public.credit_transactions t where t.user_id = u.id), 0);
--
-- That query returning any row is a bug, not a reconciliation task.
-- -----------------------------------------------------------------------------

create table if not exists public.credit_transactions (
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

-- The §5 line "tránh trừ Credit nhiều lần khi người dùng gửi lại yêu cầu",
-- enforced by the database rather than by the service remembering to check.
create unique index if not exists uq_credit_tx_idempotency
  on public.credit_transactions (user_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists idx_credit_tx_user_created
  on public.credit_transactions (user_id, created_at desc, id desc);

create index if not exists idx_credit_tx_reason_created
  on public.credit_transactions (reason, created_at desc);

-- `ref_id` is text rather than uuid because it points at three different
-- tables. Indexed with ref_type so "every transaction for this project" stays
-- a lookup and not a scan.
create index if not exists idx_credit_tx_ref
  on public.credit_transactions (ref_type, ref_id);

-- -----------------------------------------------------------------------------
-- 8. Row-level security
--
-- Same posture as public.users and public.video_projects: a user reads only
-- their own rows, writes nothing directly, and every mutation goes through
-- FastAPI. Catalogue tables (packages, events) are readable by any signed-in
-- user because the app lists them.
-- -----------------------------------------------------------------------------

alter table public.credit_transactions enable row level security;
alter table public.event_claims        enable row level security;
alter table public.payments            enable row level security;
alter table public.credit_packages     enable row level security;
alter table public.events              enable row level security;
alter table public.settings            enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'credit_transactions'
                   and policyname = 'credit_tx_select_own') then
    create policy credit_tx_select_own on public.credit_transactions
      for select using (auth.uid() = user_id);
  end if;

  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'event_claims'
                   and policyname = 'event_claims_select_own') then
    create policy event_claims_select_own on public.event_claims
      for select using (auth.uid() = user_id);
  end if;

  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'payments'
                   and policyname = 'payments_select_own') then
    create policy payments_select_own on public.payments
      for select using (auth.uid() = user_id);
  end if;

  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'credit_packages'
                   and policyname = 'credit_packages_select_active') then
    create policy credit_packages_select_active on public.credit_packages
      for select using (is_active);
  end if;

  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'events'
                   and policyname = 'events_select_active') then
    create policy events_select_active on public.events
      for select using (is_active);
  end if;
  -- public.settings gets no policy on purpose: RLS on with no policy denies
  -- every anon/authenticated read, and only the service role needs it.
end $$;


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
