# Live Supabase migration 014 verification — 2026-08-31

## Scope

This record covers read-only verification of the live Cretona Supabase schema
at source revision `a7b625147cbff81ae7789e237b7300618046f376`. It contains no
project credentials, user data, passwords, connection strings or secret values.

## Commands

Run from the repository root with the ignored local environment file:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py status
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py verify-014
```

Both actions reported `transaction_read_only: on`. No migration or data change
was performed during this verification.

## Observed result

- PostgreSQL server: 17.6 (`server_version_num` 170006).
- Migrations 006 through 014: present.
- Invalid indexes: none.
- `cretona_kaggle_worker`: present and login-enabled, with no inheritance,
  superuser, role creation, database creation, bypass-RLS, replication, role
  membership or direct table access.
- Queue functions: claim, heartbeat, complete and fail are executable by the
  database worker role and not by `anon` or `authenticated`.
- Storage authorization helper: security-definer contract passed and is not
  executable by the database worker role or `anon`.
- Storage policies: lease-scoped `INSERT`, `SELECT` and `UPDATE` policies exist
  for authenticated access to the canonical object in the private `videos`
  bucket.
- Gate summary: role, work functions, Storage helper and Storage policies all
  reported secure; `verified: true`.
- A separate read-only readiness query returned a non-null password for the
  database worker role and exactly one Auth user with protected
  `app_metadata.cretona_worker=true`. It returned no email or credential value.

## Recorded drift

Live `video_projects.progress_percent` is `int4`; migration 009 originally
declared `smallint`. The progress constraint remains present and the application
contract bounds values to 0-100, so current runtime behavior is compatible.
This is schema-type drift to preserve in evidence, not proof of a failed worker
path and not a reason to mutate a working live column during release acceptance.

## Evidence boundary

This proves the live schema/security precondition for S-13. It does **not**
prove that the team still knows both password values, that Kaggle Secrets are
complete, that the worker can authenticate or generate/upload a video, or that
Android can play the signed result. Those remain S-13/S-14 live acceptance
steps in [`KAGGLE_WORKER_RUNBOOK.md`](../KAGGLE_WORKER_RUNBOOK.md).
