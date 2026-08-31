-- Migration 014: least-privilege Kaggle Wan2.1 worker
--
-- The worker has two independent credentials:
--   1. a LOGIN role that can execute only the four private queue functions;
--   2. a dedicated Supabase Auth user whose app_metadata.cretona_worker is true.
-- It never receives service_role and has no direct table privileges.

begin;

create schema if not exists private;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'cretona_kaggle_worker') then
    create role cretona_kaggle_worker
      login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls;
  end if;
end
$$;

-- Re-asserted so a role that already existed with looser attributes is
-- normalised. `nosuperuser` is deliberately absent here even though CREATE
-- above sets it: PostgreSQL treats *any* mention of SUPERUSER/NOSUPERUSER in
-- ALTER ROLE as changing the superuser attribute, which only a superuser may
-- do -- and Supabase's `postgres` is not one. CREATE ROLE ... NOSUPERUSER is
-- allowed, so the role still cannot be created with superuser, and `postgres`
-- has no way to grant it afterwards either.
alter role cretona_kaggle_worker
  login nocreatedb nocreaterole noinherit noreplication nobypassrls;
alter role cretona_kaggle_worker set statement_timeout = '15s';

revoke all on schema private from public;
grant usage on schema private to cretona_kaggle_worker;

create or replace function private.cretona_kaggle_claim_job(
  p_owner uuid,
  p_lease_seconds integer default 180
)
returns table (
  project_id uuid,
  user_id uuid,
  prompt text,
  duration_seconds smallint,
  aspect_ratio text
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_lease_seconds not between 120 and 600 then
    raise exception 'lease_seconds must be between 120 and 600';
  end if;

  return query
  with candidate as (
    select vp.id
    from public.video_projects vp
    where vp.provider = 'kaggle'
      and vp.prompt is not null
      and vp.image_path is null
      and vp.status in ('pending', 'generating')
      and vp.deleted_at is null
      and (vp.lease_expires_at is null or vp.lease_expires_at < clock_timestamp())
    order by vp.updated_at, vp.id
    limit 1
    for update skip locked
  )
  update public.video_projects vp
  set status = 'generating',
      lease_owner = p_owner::text,
      lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
      started_at = coalesce(vp.started_at, clock_timestamp()),
      progress_percent = greatest(vp.progress_percent, 1::smallint),
      step_message = 'Kaggle worker claimed job',
      updated_at = clock_timestamp()
  from candidate c
  where vp.id = c.id
  returning vp.id, vp.user_id, vp.prompt,
            coalesce(vp.duration_seconds, 5::smallint),
            coalesce(vp.aspect_ratio, '16:9');
end
$$;

create or replace function private.cretona_kaggle_heartbeat(
  p_owner uuid,
  p_project_id uuid,
  p_lease_seconds integer,
  p_progress integer,
  p_message text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_updated integer;
begin
  if p_lease_seconds not between 120 and 600 then
    raise exception 'lease_seconds must be between 120 and 600';
  end if;
  if p_progress not between 1 and 95 then
    raise exception 'progress must be between 1 and 95';
  end if;

  update public.video_projects vp
  set lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
      progress_percent = p_progress::smallint,
      step_message = left(coalesce(p_message, 'Generating video'), 200),
      updated_at = clock_timestamp()
  where vp.id = p_project_id
    and vp.provider = 'kaggle'
    and vp.status = 'generating'
    and vp.deleted_at is null
    and vp.lease_owner = p_owner::text;

  get diagnostics v_updated = row_count;
  return v_updated = 1;
end
$$;

create or replace function private.cretona_kaggle_complete(
  p_owner uuid,
  p_project_id uuid,
  p_sha256 text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_path text;
begin
  if p_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'sha256 must be lowercase hexadecimal';
  end if;

  select vp.user_id
  into v_user_id
  from public.video_projects vp
  where vp.id = p_project_id
    and vp.provider = 'kaggle'
    and vp.status = 'generating'
    and vp.deleted_at is null
    and vp.lease_owner = p_owner::text
  for update;

  if not found then
    return false;
  end if;

  v_path := v_user_id::text || '/' || p_project_id::text || '/video.mp4';
  if not exists (
    select 1
    from storage.objects so
    where so.bucket_id = 'videos'
      and so.name = v_path
  ) then
    return false;
  end if;

  update public.video_projects
  set status = 'completed',
      video_path = v_path,
      progress_percent = 100,
      step_message = 'Wan2.1 video complete',
      error_code = null,
      error_message = null,
      completed_at = clock_timestamp(),
      updated_at = clock_timestamp(),
      lease_owner = null,
      lease_expires_at = null
  where id = p_project_id;

  insert into public.generation_logs (
    project_id, provider, request_id, event, response, http_status
  ) values (
    p_project_id, 'kaggle', p_owner::text, 'download',
    jsonb_build_object('storagePath', v_path, 'sha256', p_sha256), 200
  );
  return true;
end
$$;

create or replace function private.cretona_kaggle_fail(
  p_owner uuid,
  p_project_id uuid,
  p_error_code text,
  p_message text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_charge_id uuid;
  v_charge_delta integer;
  v_charge_count bigint;
  v_refund_count bigint;
  v_balance integer;
begin
  if p_error_code not in ('invalid_input', 'quota', 'timeout', 'provider_error', 'unknown') then
    raise exception 'unsupported worker error code';
  end if;

  select vp.user_id
  into v_user_id
  from public.video_projects vp
  where vp.id = p_project_id
    and vp.provider = 'kaggle'
    and vp.status = 'generating'
    and vp.deleted_at is null
    and vp.lease_owner = p_owner::text
  for update;

  if not found then
    return false;
  end if;

  select count(*) filter (where ct.reason = 'generation'),
         count(*) filter (where ct.reason = 'refund')
  into v_charge_count, v_refund_count
  from public.credit_transactions ct
  where ct.user_id = v_user_id
    and ct.ref_type = 'project'
    and ct.ref_id = p_project_id::text;

  if v_charge_count > v_refund_count then
    select ct.id, ct.delta
    into v_charge_id, v_charge_delta
    from public.credit_transactions ct
    where ct.user_id = v_user_id
      and ct.ref_type = 'project'
      and ct.ref_id = p_project_id::text
      and ct.reason = 'generation'
      and ct.delta < 0
    order by ct.created_at desc, ct.id desc
    limit 1;

    update public.users
    set credit_balance = credit_balance - v_charge_delta
    where id = v_user_id
    returning credit_balance into v_balance;

    insert into public.credit_transactions (
      user_id, delta, balance_after, reason, ref_type, ref_id,
      note, idempotency_key
    ) values (
      v_user_id, -v_charge_delta, v_balance, 'refund', 'project',
      p_project_id::text, left('Kaggle worker failure: ' || coalesce(p_message, ''), 500),
      'refund:charge:' || v_charge_id::text
    );
  end if;

  update public.video_projects
  set status = 'failed',
      error_code = p_error_code,
      error_message = left(coalesce(nullif(p_message, ''), 'Video generation failed.'), 500),
      progress_percent = 0,
      step_message = 'Wan2.1 generation failed',
      completed_at = clock_timestamp(),
      updated_at = clock_timestamp(),
      lease_owner = null,
      lease_expires_at = null
  where id = p_project_id;

  insert into public.generation_logs (
    project_id, provider, request_id, event, response, http_status
  ) values (
    p_project_id, 'kaggle', p_owner::text, 'error',
    jsonb_build_object('errorCode', p_error_code), 500
  );
  return true;
end
$$;

revoke all on function private.cretona_kaggle_claim_job(uuid, integer) from public;
revoke all on function private.cretona_kaggle_heartbeat(uuid, uuid, integer, integer, text)
  from public;
revoke all on function private.cretona_kaggle_complete(uuid, uuid, text) from public;
revoke all on function private.cretona_kaggle_fail(uuid, uuid, text, text) from public;

grant execute on function private.cretona_kaggle_claim_job(uuid, integer)
  to cretona_kaggle_worker;
grant execute on function private.cretona_kaggle_heartbeat(uuid, uuid, integer, integer, text)
  to cretona_kaggle_worker;
grant execute on function private.cretona_kaggle_complete(uuid, uuid, text)
  to cretona_kaggle_worker;
grant execute on function private.cretona_kaggle_fail(uuid, uuid, text, text)
  to cretona_kaggle_worker;

-- Storage writes use the worker's normal Auth JWT. The policy binds that JWT
-- to the exact canonical object of a currently leased project. An arbitrary
-- authenticated account cannot upload to the videos bucket.
create or replace function private.cretona_kaggle_can_write_object(p_name text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(auth.jwt() -> 'app_metadata' ->> 'cretona_worker', '') = 'true'
    and exists (
      select 1
      from public.video_projects vp
      where vp.provider = 'kaggle'
        and vp.status = 'generating'
        and vp.deleted_at is null
        and vp.lease_owner = auth.uid()::text
        and vp.lease_expires_at > now()
        and p_name = vp.user_id::text || '/' || vp.id::text || '/video.mp4'
    );
$$;

revoke all on function private.cretona_kaggle_can_write_object(text) from public;
grant usage on schema private to authenticated;
grant execute on function private.cretona_kaggle_can_write_object(text) to authenticated;

drop policy if exists videos_worker_insert_leased on storage.objects;
create policy videos_worker_insert_leased on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'videos'
    and private.cretona_kaggle_can_write_object(name)
  );

drop policy if exists videos_worker_select_leased on storage.objects;
create policy videos_worker_select_leased on storage.objects
  for select to authenticated
  using (
    bucket_id = 'videos'
    and private.cretona_kaggle_can_write_object(name)
  );

drop policy if exists videos_worker_update_leased on storage.objects;
create policy videos_worker_update_leased on storage.objects
  for update to authenticated
  using (
    bucket_id = 'videos'
    and private.cretona_kaggle_can_write_object(name)
  )
  with check (
    bucket_id = 'videos'
    and private.cretona_kaggle_can_write_object(name)
  );

commit;

-- Operator-only setup after this migration:
--   alter role cretona_kaggle_worker password '<strong generated password>';
-- Create one Auth user, set raw_app_meta_data.cretona_worker=true, then store
-- both credentials in Kaggle Secrets. Never paste service_role into Kaggle.
