-- Require every Kaggle completion to publish a gallery thumbnail beside its MP4.
-- The worker keeps least privilege: its Auth JWT may write only the canonical
-- thumbnail for the project whose active lease it owns.

begin;

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
  v_video_path text;
  v_thumbnail_path text;
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

  v_video_path := v_user_id::text || '/' || p_project_id::text || '/video.mp4';
  v_thumbnail_path := v_user_id::text || '/' || p_project_id::text || '/thumbnail.jpg';
  if not exists (
    select 1
    from storage.objects so
    where so.bucket_id = 'videos'
      and so.name = v_video_path
  ) or not exists (
    select 1
    from storage.objects so
    where so.bucket_id = 'uploads'
      and so.name = v_thumbnail_path
  ) then
    return false;
  end if;

  update public.video_projects
  set status = 'completed',
      video_path = v_video_path,
      thumbnail_path = v_thumbnail_path,
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
    jsonb_build_object(
      'storagePath', v_video_path,
      'thumbnailPath', v_thumbnail_path,
      'sha256', p_sha256
    ),
    200
  );
  return true;
end
$$;

revoke all on function private.cretona_kaggle_complete(uuid, uuid, text) from public;
grant execute on function private.cretona_kaggle_complete(uuid, uuid, text)
  to cretona_kaggle_worker;

create or replace function private.cretona_kaggle_can_write_thumbnail(p_name text)
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
        and p_name = vp.user_id::text || '/' || vp.id::text || '/thumbnail.jpg'
    );
$$;

revoke all on function private.cretona_kaggle_can_write_thumbnail(text) from public;
grant usage on schema private to authenticated;
grant execute on function private.cretona_kaggle_can_write_thumbnail(text) to authenticated;

drop policy if exists uploads_worker_insert_leased on storage.objects;
create policy uploads_worker_insert_leased on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'uploads'
    and private.cretona_kaggle_can_write_thumbnail(name)
  );

drop policy if exists uploads_worker_select_leased on storage.objects;
create policy uploads_worker_select_leased on storage.objects
  for select to authenticated
  using (
    bucket_id = 'uploads'
    and private.cretona_kaggle_can_write_thumbnail(name)
  );

drop policy if exists uploads_worker_update_leased on storage.objects;
create policy uploads_worker_update_leased on storage.objects
  for update to authenticated
  using (
    bucket_id = 'uploads'
    and private.cretona_kaggle_can_write_thumbnail(name)
  )
  with check (
    bucket_id = 'uploads'
    and private.cretona_kaggle_can_write_thumbnail(name)
  );

commit;
