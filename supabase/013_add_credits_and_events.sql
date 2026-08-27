-- Migration 013: Credits, events, packages, payments and settings
--
-- Closes the six tables §5 of the exam brief names as the minimum schema and
-- which do not exist yet: Credit Transactions, Credit Packages, Payments,
-- Promotions (here: `events`), Promotion Registrations (here: `event_claims`),
-- and Settings. Contract: docs/API_CONTRACT.md Part II.
--
-- WHY `events` RATHER THAN `promotions`: one table serves every campaign the
-- product wants — a credit grant (weekend gift, holiday, admin surprise) and a
-- price discount (hot hours, -50% from 20:00 to 22:00) differ only in `kind`
-- and which of `bonus_credits` / `discount_percent` is set. Two tables would
-- have duplicated the window, recurrence and cap logic.
--
-- WHY THE LEDGER IS THE TRUTH: `users.credit_balance` is a cache. Every change
-- to it is written in the same transaction as a `credit_transactions` row, and
-- every row carries `balance_after`, so drift is detectable by a query rather
-- than by a user complaint. Never update or delete a ledger row.
--
-- Safe to re-run. Additive only: no existing column changes type and nothing
-- is dropped, so the running app is unaffected until code reads these tables.

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
