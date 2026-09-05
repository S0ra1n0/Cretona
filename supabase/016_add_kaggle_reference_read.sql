-- Prepare the Kaggle worker to read a job's reference image. Preparation only:
-- after this migration the worker still claims exactly the jobs it claims
-- today, and the observable behaviour of the system is unchanged.
--
-- Two things block image-to-video at the database, and this migration removes
-- one of them.
--
-- 1. STORAGE (removed here). Migration 015 gave the worker a lease-scoped grant
--    on `uploads`, but that grant is gated by
--    `private.cretona_kaggle_can_write_thumbnail`, whose predicate is an exact
--    match on `<user_id>/<project_id>/thumbnail.jpg`. Reference images are
--    stored under a different shape entirely -- `<user_id>/<yyyy-mm-dd>/<uuid>`
--    -- so the worker cannot read them. A second, read-only predicate fixes it.
--
-- 2. THE CLAIM FILTER (deliberately left in place). `cretona_kaggle_claim_job`
--    carries `and vp.image_path is null`, so image jobs are never handed to a
--    Kaggle worker at all. That line is the reason an uploaded image cannot be
--    silently ignored, and it must outlive this migration: the worker has no
--    image-conditioned model yet, and a bundle that claimed an image job today
--    would produce a text-only clip while the user believes their picture was
--    used. Removing it belongs with the worker that can honour it.
--
-- So this migration is safe to apply before the model question is settled. It
-- widens no behaviour; it removes a blocker that would otherwise have to be
-- discovered later, live, with less time.

begin;

-- ---------------------------------------------------------------------------
-- 1. The worker may read the reference image of the project it is holding.
-- ---------------------------------------------------------------------------
--
-- The predicate is narrower than a path pattern on purpose. It compares the
-- object name against `video_projects.image_path` of the leased row, so the
-- worker can read the one image belonging to the job it currently owns and
-- nothing else: no prefix match, no wildcard, and no way to enumerate another
-- account's uploads by guessing a date folder.
--
-- Nothing here widens write access. `uploads_worker_insert_leased` and
-- `uploads_worker_update_leased` keep pointing at the thumbnail predicate, so
-- the worker still cannot modify or delete a user's own upload.

create or replace function private.cretona_kaggle_can_read_reference(p_name text)
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
        and vp.image_path is not null
        and p_name = vp.image_path
    );
$$;

revoke all on function private.cretona_kaggle_can_read_reference(text) from public;
grant execute on function private.cretona_kaggle_can_read_reference(text) to authenticated;

-- A second SELECT policy is OR-ed with the existing one, so thumbnail reads
-- keep working unchanged.
drop policy if exists uploads_worker_select_reference on storage.objects;
create policy uploads_worker_select_reference on storage.objects
  for select to authenticated
  using (
    bucket_id = 'uploads'
    and private.cretona_kaggle_can_read_reference(name)
  );

-- ---------------------------------------------------------------------------
-- 2. The claim result carries `image_path`.
-- ---------------------------------------------------------------------------
--
-- `create or replace` cannot change a function's return type, so the function
-- is dropped and recreated. Both statements are inside this transaction, so no
-- concurrent session ever sees the function missing -- it sees the old
-- signature or the new one. The grant is re-issued because `drop function`
-- discards it.
--
-- The body is unchanged except for the added output column. In particular
-- `and vp.image_path is null` stays, so this column is `null` on every row the
-- function returns until a later migration removes that filter. That is the
-- intended state: the column exists so a worker can be written and tested
-- against it before the switch is thrown.

drop function if exists private.cretona_kaggle_claim_job(uuid, integer);

create function private.cretona_kaggle_claim_job(
  p_owner uuid,
  p_lease_seconds integer default 180
)
returns table(
  project_id uuid,
  user_id uuid,
  prompt text,
  duration_seconds smallint,
  aspect_ratio text,
  image_path text
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
      -- Keep refusing image jobs until a worker exists that can honour them.
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
            coalesce(vp.aspect_ratio, '16:9'),
            vp.image_path;
end
$$;

revoke all on function private.cretona_kaggle_claim_job(uuid, integer) from public;
grant execute on function private.cretona_kaggle_claim_job(uuid, integer)
  to cretona_kaggle_worker;

commit;
