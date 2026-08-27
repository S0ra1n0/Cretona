-- =============================================================================
-- Cretona — seed data for credits, packages and events
--
-- Apply after bootstrap.sql (or after 013_add_credits_and_events.sql on an
-- existing database). Re-running is safe: every insert is keyed and guarded.
--
-- Contract: docs/API_CONTRACT.md Part II §7, §8.
--
-- TIMES ARE LOCAL VIETNAM (UTC+7), stored as minutes from midnight:
--   1200 = 20:00, 1320 = 22:00.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Settings — the admin-configurable generation cost (§3 of the brief)
-- -----------------------------------------------------------------------------

insert into public.settings (key, value) values
  ('generation_cost_credits', '1')
on conflict (key) do nothing;

-- -----------------------------------------------------------------------------
-- 2. Credit packages
--
-- Prices are VND as integers. No real money moves — see ADR-010; the purchase
-- flow, its state machine and its ledger entry are real, the gateway
-- confirmation is stubbed.
-- -----------------------------------------------------------------------------

insert into public.credit_packages (name, credits, price_vnd, sort_order)
select v.name, v.credits, v.price_vnd, v.sort_order
from (values
  ('Starter',  10,  20000, 1),
  ('Creator',  50,  90000, 2),
  ('Studio',  150, 250000, 3)
) as v(name, credits, price_vnd, sort_order)
where not exists (
  select 1 from public.credit_packages p where p.name = v.name
);

-- -----------------------------------------------------------------------------
-- 3. Events
--
-- Five rows covering every shape the product needs, so the admin screens and
-- the Events screen both have something real to render on day one.
--
--   SIGNUP_BONUS  grant · once   · auto — applied at first sign-in, no button
--   HOT_HOURS     discount · daily · 20:00-22:00, half price
--   WEEKEND_GIFT  grant · weekly · Sat and Sun, +10, capped at 500 claims
--   NATIONAL_DAY  grant · once   · 2026-09-02, +20
--   WELCOME_BACK  grant · once   · an admin-style surprise drop
--
-- `ends_at` on the recurring rows is the end of the campaign, not the end of
-- one occurrence. A daily event runs its minute-window every day until then.
-- -----------------------------------------------------------------------------

insert into public.events (
  code, name, description, kind, bonus_credits, discount_percent,
  recurrence, active_days, active_from_minute, active_to_minute,
  starts_at, ends_at, max_claims, auto_grant
)
select
  v.code, v.name, v.description, v.kind, v.bonus_credits, v.discount_percent,
  v.recurrence, v.active_days, v.active_from_minute, v.active_to_minute,
  v.starts_at, v.ends_at, v.max_claims, v.auto_grant
from (values
  ('SIGNUP_BONUS', 'Welcome bonus',
   'Five credits to get you started, added when you first sign in.',
   'grant', 5, null, 'once', null, null, null,
   timestamptz '2026-08-01 00:00+07', timestamptz '2027-01-01 00:00+07',
   null, true),

  ('HOT_HOURS', 'Hot Hours',
   'Half price on every generation, 20:00-22:00 every day.',
   'discount', null, 50, 'daily', null, 1200, 1320,
   timestamptz '2026-08-01 00:00+07', timestamptz '2027-01-01 00:00+07',
   null, false),

  ('WEEKEND_GIFT', 'Weekend Gift',
   'Ten free credits every weekend. Claim once per weekend.',
   'grant', 10, null, 'weekly', 'sat,sun', null, null,
   timestamptz '2026-08-01 00:00+07', timestamptz '2027-01-01 00:00+07',
   500, false),

  ('NATIONAL_DAY', 'Quoc khanh 2/9',
   'Twenty credits to celebrate National Day.',
   'grant', 20, null, 'once', null, null, null,
   timestamptz '2026-09-01 00:00+07', timestamptz '2026-09-04 00:00+07',
   1000, false),

  ('WELCOME_BACK', 'Surprise drop',
   'A thank-you from the Cretona team. Limited to the first 100 people.',
   'grant', 15, null, 'once', null, null, null,
   timestamptz '2026-08-28 00:00+07', timestamptz '2026-09-30 00:00+07',
   100, false)
) as v(code, name, description, kind, bonus_credits, discount_percent,
       recurrence, active_days, active_from_minute, active_to_minute,
       starts_at, ends_at, max_claims, auto_grant)
where not exists (
  select 1 from public.events e where e.code = v.code
);

-- =============================================================================
-- Verification
--
--   select code, kind, recurrence, bonus_credits, discount_percent, max_claims
--   from public.events order by code;
--   -- expect: 5 rows
--
--   select name, credits, price_vnd from public.credit_packages order by sort_order;
--   -- expect: 3 rows
--
--   select * from public.settings;
--   -- expect: generation_cost_credits = 1
-- =============================================================================
