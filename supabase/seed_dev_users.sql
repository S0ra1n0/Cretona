-- =============================================================================
-- Cretona — development seed users
--
-- Creates two accounts:
--   user@cretona.test   role_id = 1  (normal user)
--   admin@cretona.test  role_id = 2  (admin)
--
-- DEV AND STAGING ONLY. Never run this against production.
-- Change the passwords in step 2 before running. Re-running is safe.
--
-- Requires bootstrap.sql to have been applied first.
--
-- Written to survive the Supabase SQL Editor, which may execute each statement
-- independently: every statement below stands alone and shares no session
-- state with the others. Paste the whole file and Run.
-- =============================================================================
--
-- SAFER ALTERNATIVE — if you would rather not write to the auth schema:
--
--   1. Authentication -> Users -> "Add user" twice, using the two emails below.
--      Tick "Auto Confirm User" so you can sign in immediately.
--   2. Run step 3 anyway. It skips accounts that already exist and still
--      applies the roles, so it finishes the job either way.
--
--   That path uses Supabase's own account-creation code and cannot break on a
--   schema change. Step 3 writes to auth.users directly, which depends on
--   internal columns Supabase has changed between versions -- see the note at
--   the bottom if it errors.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- STEP 1. pgcrypto, for bcrypt password hashing.
-- Already enabled on Supabase; this is a no-op there.
-- -----------------------------------------------------------------------------

create extension if not exists pgcrypto with schema extensions;


-- -----------------------------------------------------------------------------
-- STEP 2 + 3. Create the accounts and apply the roles.
--
-- One self-contained statement. The seed list is the jsonb literal at the top --
-- CHANGE THE PASSWORDS THERE.
--
-- Inserting into auth.users fires the on_auth_user_created trigger from
-- bootstrap.sql, which creates the matching public.users row with role_id = 1.
-- The auth.identities row is what makes email/password sign-in work; without it
-- the account exists but cannot log in.
--
-- Roles are applied whether or not this script created the account, so it also
-- works as a follow-up to creating the users in the dashboard.
-- -----------------------------------------------------------------------------

do $$
declare
  seed_users constant jsonb := '[
    { "email": "user@cretona.test",  "password": "usercretona", "role_id": 1 },
    { "email": "admin@cretona.test", "password": "stepbruce", "role_id": 2 }
  ]'::jsonb;

  s          jsonb;
  v_email    text;
  v_password text;
  v_role_id  smallint;
  v_id       uuid;
begin
  for s in select * from jsonb_array_elements(seed_users) loop
    v_email    := s ->> 'email';
    v_password := s ->> 'password';
    v_role_id  := (s ->> 'role_id')::smallint;

    if exists (select 1 from auth.users where email = v_email) then
      raise notice 'exists: %  (leaving credentials alone)', v_email;
    else
      v_id := gen_random_uuid();

      insert into auth.users (
        instance_id,
        id,
        aud,
        role,
        email,
        encrypted_password,
        email_confirmed_at,
        created_at,
        updated_at,
        raw_app_meta_data,
        raw_user_meta_data,
        confirmation_token,
        recovery_token,
        email_change,
        email_change_token_new
      ) values (
        '00000000-0000-0000-0000-000000000000',
        v_id,
        'authenticated',
        'authenticated',
        v_email,
        extensions.crypt(v_password, extensions.gen_salt('bf')),
        now(),   -- pre-confirmed, so no verification email is needed
        now(),
        now(),
        '{"provider":"email","providers":["email"]}'::jsonb,
        '{}'::jsonb,
        '', '', '', ''
      );

      insert into auth.identities (
        id,
        user_id,
        identity_data,
        provider,
        provider_id,
        last_sign_in_at,
        created_at,
        updated_at
      ) values (
        gen_random_uuid(),
        v_id,
        jsonb_build_object('sub', v_id::text, 'email', v_email),
        'email',
        v_id::text,
        now(),
        now(),
        now()
      );

      raise notice 'created: %', v_email;
    end if;

    -- Applied every run: the signup trigger always defaults to role_id = 1.
    update public.users
       set role_id = v_role_id
     where email = v_email
       and role_id is distinct from v_role_id;
  end loop;
end
$$;


-- -----------------------------------------------------------------------------
-- STEP 4. Verify. Run this on its own any time.
-- -----------------------------------------------------------------------------

select
  u.email,
  r.name                             as role,
  u.role_id,
  u.is_disabled,
  (a.id is not null)                 as auth_row_exists,
  (i.user_id is not null)            as can_sign_in,
  (a.email_confirmed_at is not null) as confirmed
from public.users u
join public.roles r          on r.id = u.role_id
left join auth.users a       on a.id = u.id
left join auth.identities i  on i.user_id = u.id
where u.email in ('user@cretona.test', 'admin@cretona.test')
order by u.role_id;

-- Expect two rows:
--   user@cretona.test  | user  | 1 | f | t | t | t
--   admin@cretona.test | admin | 2 | f | t | t | t
--
-- If can_sign_in is false, the identity row is missing and login will fail with
-- "Invalid login credentials" even though the account exists.


-- =============================================================================
-- If step 2/3 errors
--
-- The auth schema is Supabase's, not ours, and its columns move between
-- versions. Two failures are common:
--
--   "column ... of relation users does not exist"
--       Your Supabase version has a different auth.users shape. Use the
--       dashboard path at the top of this file instead -- it always works,
--       then re-run this file to apply the roles.
--
--   "column provider_id of relation identities does not exist"
--       Older Supabase used a text `id` on auth.identities instead of a uuid
--       `id` plus `provider_id`. Replace that insert's column list with
--       (id, user_id, identity_data, provider, last_sign_in_at, created_at,
--        updated_at) and pass v_id::text as the first value.
--
-- If only the role assignment is needed -- accounts already exist and just have
-- the wrong role -- this one statement is version-independent and always safe:
--
--   update public.users set role_id = 2 where email = 'admin@cretona.test';
--   update public.users set role_id = 1 where email = 'user@cretona.test';
-- =============================================================================

-- To remove these accounts again (cascades to public.users and their projects):
--   delete from auth.users where email in ('user@cretona.test', 'admin@cretona.test');
