# S-13 live Kaggle worker connection — 2026-09-01

## Scope

This evidence closes the connectivity-only S-13 gate for the private
`bruce335/cretona-wan2-1` notebook. It proves the existing worker can obtain a
dedicated Supabase Auth session and execute the PostgreSQL queue claim path.
It does not claim video generation, Storage upload, FastAPI completion or
Android playback; those remain S-14.

## Revision-bound source

- repository revision: `73666f023d2e618b02401f62c6afe4df13513595`
- private source bundle: `cretona-kaggle-worker-73666f02.zip`
- bundle SHA-256:
  `b59aa955e6cda72932fd7956aadffe76bbb07c93a7a9a226735f53ba26f76fdd`
- bundle size: 6,507 bytes
- exact entries:
  - `backend/kaggle_worker.py`
  - `backend/requirements-kaggle.txt`

The bundle contained no environment file, credential, Android source, video,
Git history or full FastAPI application. Kaggle recomputed the same SHA-256
before extracting it under `/kaggle/working/Cretona`.

## Live configuration observed

Exactly these five Kaggle Secrets were present and enabled; their values were
not printed or committed:

1. `CRETONA_WORKER_DATABASE_URL`
2. `CRETONA_SUPABASE_URL`
3. `CRETONA_SUPABASE_PUBLISHABLE_KEY`
4. `CRETONA_WORKER_EMAIL`
5. `CRETONA_WORKER_PASSWORD`

A presence-only shape check identified that the first saved publishable key
was truncated; the Auth probe returned HTTP 401 `Invalid API key`. The saved
Kaggle secret was replaced with the complete existing publishable key from the
Cretona Supabase dashboard. Its value was not logged.

## Executed smoke

The current Kaggle session installed only the connectivity dependency needed
for this gate:

```text
psycopg 3.3.4
pip exit code 0
```

Presence-only Auth probe after the key correction:

```text
HTTP 200
access token present: true
Auth user id present: true
error: none
```

Then the revision-bound worker was executed once:

```text
python backend/kaggle_worker.py --once
exit code: 0
worker output: empty
```

At this run the queue contained no claimable job. In the current source,
`run_once()` must obtain the Auth session and call
`private.cretona_kaggle_claim_job(...)` before it can return `False`; an Auth,
database, role, TLS or function-permission failure raises and makes the process
non-zero. Exit `0` with an empty queue therefore proves the Auth and DB-claim
connection without loading Wan2.1 or spending a generation run.

## Result and remaining boundary

**S-13 connectivity gate: PASS.** Five secrets, Supabase Auth and the
least-privilege PostgreSQL claim path were observed live from Kaggle.

**Still unproven:** an app-created job being claimed, lease renewal during the
long generation, Wan2.1 model loading, MP4 generation, Storage upload,
completion/refund write-back, signed URL delivery and Android Media3 playback.
Run the S-14 steps in `../KAGGLE_WORKER_RUNBOOK.md` next.
