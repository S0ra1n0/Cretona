# Kaggle Wan2.1 worker — final connection runbook

This is the only supported real-video path for the zero-additional-spend demo:
Android → FastAPI → Supabase queue → private Kaggle worker → Supabase Storage →
FastAPI signed URL → Android Media3 playback.

The model is `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` at revision
`0fad780a534b6463e45facd96134c9f345acfa5b`. It is text-to-video only, accepts
2–5 seconds, and the measured 5-second profile takes about 49 minutes on the
Kaggle 2×T4 host. The worker is not an always-on service.

> **Live checkpoint, 2026-08-31:** migration 014 is already present on the
> Cretona Supabase project and `verify-014` passed in a read-only transaction.
> The database role has a password and exactly one Auth user is marked as a
> worker. Do not reapply the migration or create duplicate identities. Continue
> at section 3 if the team still has both credential values; otherwise reset
> only the missing password in section 2. Evidence:
> [`LIVE_SUPABASE_MIGRATION_014_2026-08-31.md`](evidence/LIVE_SUPABASE_MIGRATION_014_2026-08-31.md).

## 1. Verify migration 014; apply only if absent

Do this only from the repository root and only after reviewing the selected
Supabase project. The gate reads the ignored local env file and never prints
credential values:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py status
# Run apply-014 only when status reports migration 014 as false.
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py apply-014 `
  --confirm-project-ref <exact-project-ref>
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py verify-014
```

Migration 014 creates a login role with no table grants, four private queue
functions, and three lease-scoped Storage policies. It does **not** set a
password and does not create an Auth account.

## 2. Create the two worker identities

Skip creation when the live checkpoint above remains true. Presence does not
prove the team still knows either password, so reset only a lost value rather
than creating a second worker.

In Supabase Authentication, create one dedicated email/password user for the
worker. Do not reuse a developer or admin account. Then set only its protected
app metadata in SQL Editor:

```sql
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
                      || '{"cretona_worker": true}'::jsonb
where email = '<worker-email>';
```

Set a different strong password on the database role created by migration 014:

```sql
alter role cretona_kaggle_worker password '<generated-database-password>';
```

Do not put either password in Git, a notebook cell, chat, screenshots, or
notebook output. Revoking either identity disables half of the worker; a leaked
credential never becomes full Supabase administration.

## 3. Add five Kaggle Secrets

Open the private notebook and add these exact secret names:

| Secret | Value |
|---|---|
| `CRETONA_WORKER_DATABASE_URL` | Session-pooler PostgreSQL URL for `cretona_kaggle_worker` with `sslmode=require` |
| `CRETONA_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `CRETONA_SUPABASE_PUBLISHABLE_KEY` | Project publishable key (legacy anon key also works) |
| `CRETONA_WORKER_EMAIL` | Dedicated Auth worker email |
| `CRETONA_WORKER_PASSWORD` | Dedicated Auth worker password |

Copy the session-pooler host from Supabase **Connect → Session pooler**. For
external IPv4 environments such as Kaggle, Supabase documents session mode on
port 5432; do not invent the region/host. URL-encode the password if it contains
reserved URL characters. See the official
[connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).

Never add `service_role` or the backend database administrator URL to Kaggle.

## 4. Start the worker in the existing notebook

Use a private Kaggle notebook with Internet and a 2×T4 accelerator. Add these
cells after enabling the five secrets:

```python
from kaggle_secrets import UserSecretsClient
import os

secrets = UserSecretsClient()
for name in (
    "CRETONA_WORKER_DATABASE_URL",
    "CRETONA_SUPABASE_URL",
    "CRETONA_SUPABASE_PUBLISHABLE_KEY",
    "CRETONA_WORKER_EMAIL",
    "CRETONA_WORKER_PASSWORD",
):
    os.environ[name] = secrets.get_secret(name)
```

```bash
!git clone https://github.com/S0ra1n0/Cretona.git
%cd /kaggle/working/Cretona
!git checkout a7b625147cbff81ae7789e237b7300618046f376
!python -m pip install -q -r backend/requirements-kaggle.txt
```

Do not install or upgrade `torch`; the requirements file deliberately uses the
CUDA build already supplied by Kaggle.

For a one-job acceptance run:

```bash
!python backend/kaggle_worker.py --once
```

For the demo queue, omit `--once`. Stop the cell after all intended jobs have
completed:

```bash
!python backend/kaggle_worker.py
```

## 5. End-to-end acceptance

1. Start FastAPI in its Supabase/Postgres/Storage profile.
2. Sign in to Android, choose **Kaggle · Wan2.1**, keep the request text-only,
   choose 2–5 seconds, and press Generate.
3. Confirm the project moves `pending → generating`, progress changes while the
   notebook runs, and the worker reports only project IDs—not prompts/secrets.
4. Wait for `completed`; open the project and play the signed MP4 in Android.
5. Record the project ID, start/completion timestamps, object metadata, clip
   dimensions/frame count/duration, and a screenshot/video of playback.
6. Run the same test once with the worker stopped: the job must remain queued,
   not be completed by the FastAPI poller.
7. For a controlled failure, confirm the project becomes `failed` and the
   credit ledger receives exactly one refund for that generation charge.

Expected Storage object name inside the private `videos` bucket:

```text
<project-owner-uuid>/<project-uuid>/video.mp4
```

Storage upsert requires `INSERT`, `SELECT`, and `UPDATE`; migration 014 grants
all three only for the canonical object of a currently leased job, matching the
official [Storage access-control contract](https://supabase.com/docs/guides/storage/security/access-control).

## Evidence boundary

Source tests can prove queue ownership, lease renewal, path construction,
write-back and refund behavior. Only the live steps above prove that Kaggle can
authenticate, download weights, generate an MP4, upload it, and that Android
can play the signed result. Until one full run passes, report the feature as
**source-complete, live E2E not yet accepted**—never “100% functional.”
