from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
SUPABASE = ROOT / "supabase"

SUPABASE_STUBS = """
drop schema if exists private cascade;
drop schema if exists storage cascade;
drop schema if exists auth cascade;
drop schema if exists public cascade;
create schema public;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin;
  end if;
end
$$;

create schema auth;
create table auth.users (
  id uuid primary key,
  email text not null unique
);
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
create table storage.buckets (
  id text primary key,
  name text not null unique,
  public boolean not null default false
);
create table storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text not null references storage.buckets(id),
  name text not null,
  unique (bucket_id, name)
);
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[]
language sql immutable
as $$
  select string_to_array(name, '/')[1:greatest(array_length(string_to_array(name, '/'), 1) - 1, 0)];
$$;
grant usage on schema auth, storage to authenticated;
grant select, insert, update, delete on storage.objects to authenticated;
"""


def test_bootstrap_migrations_and_product_seed_from_empty(postgres_url: str) -> None:
    psycopg = __import__("psycopg")
    migration_files = sorted(SUPABASE.glob("[0-9][0-9][0-9]_*.sql"))
    assert [path.name[:3] for path in migration_files] == [
        f"{number:03d}" for number in range(2, 16)
    ]

    with psycopg.connect(postgres_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute(SUPABASE_STUBS)
        connection.execute((SUPABASE / "bootstrap.sql").read_text(encoding="utf-8"))
        for migration in migration_files:
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute((SUPABASE / "seed_credits_and_events.sql").read_text(encoding="utf-8"))

        connection.execute(
            "insert into auth.users (id, email) values (%s, %s)",
            ("10000000-0000-4000-8000-000000000001", "fresh@example.com"),
        )
        profile = connection.execute(
            "select email, role_id, credit_balance from public.users where email = %s",
            ("fresh@example.com",),
        ).fetchone()
        assert profile == ("fresh@example.com", 1, 0)

        connection.execute(
            "update auth.users set email = %s where id = %s",
            ("updated@example.com", "10000000-0000-4000-8000-000000000001"),
        )
        assert connection.execute(
            "select email from public.users where id = %s",
            ("10000000-0000-4000-8000-000000000001",),
        ).fetchone() == ("updated@example.com",)

        assert connection.execute("select count(*) from public.credit_packages").fetchone() == (3,)
        assert connection.execute("select count(*) from public.events").fetchone() == (5,)
        assert connection.execute(
            "select value from public.settings where key = 'generation_cost_credits'"
        ).fetchone() == ("1",)
        assert connection.execute(
            "select count(*) from storage.buckets where id in ('uploads', 'videos') and not public"
        ).fetchone() == (2,)
        assert connection.execute(
            """
            select count(*)
            from pg_policies
            where schemaname = 'storage'
              and tablename = 'objects'
              and policyname in (
                'uploads_worker_insert_leased',
                'uploads_worker_select_leased',
                'uploads_worker_update_leased',
                'videos_worker_insert_leased',
                'videos_worker_select_leased',
                'videos_worker_update_leased'
              )
            """
        ).fetchone() == (6,)
