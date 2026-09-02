# Live Supabase migration 015 and Kaggle worker smoke — 2026-09-02

## Scope

This record covers the guarded live deployment of MIG-015 and the matching
private Kaggle worker smoke. It contains no credential values, connection
strings, prompts, user records or generated media.

## Revision-bound inputs

- repository revision: `ee339afd4ebd0cad94b616b28ce5ed9ab5617826`
- hosted CI: [run 33580117770](https://github.com/S0ra1n0/Cretona/actions/runs/33580117770)
- migration SHA-256:
  `a37ef7256e4fd4fec031851b90f404ca8fd0b6a9e9ec039f09500103eb74f7a0`
- private Kaggle bundle: `cretona-kaggle-worker-ee339afd.zip`
- bundle SHA-256:
  `518a6d4b0b87a6a147218dd1695ecba7d717a3b80c8d1a76ea6add94c90aa382`
- worker SHA-256:
  `34ed79155a61bd0fd331e03207f38d946977dc3dc20ff2589586189f166428a0`
- Kaggle requirements SHA-256:
  `46263bf0527742dde0d98a5da163afc1646a53b5f6de545ad3e94da43c99c669`

The 6,809-byte bundle contained exactly `backend/kaggle_worker.py` and
`backend/requirements-kaggle.txt`. Kaggle stored it as a private dataset input.

## Preflight and apply

Before the live write, CI passed all three jobs: Android/JVM 17,
FastAPI/Python 3.12 and FastAPI/PostgreSQL 17 parity. The guarded gate then ran:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py verify-014
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py apply-015 --confirm-project-ref <exact-project-ref>
.\backend\.venv\Scripts\python.exe .\scripts\live-supabase-migration-gate.py verify-015
```

The apply action reported `applied: true`. The final verification ran in a
read-only transaction and reported `verified: true` against PostgreSQL 17.6.

## Observed security contract

- `private.cretona_kaggle_can_write_thumbnail(text)` is a security-definer
  helper scoped to a currently leased Kaggle job and its canonical
  `<user>/<project>/thumbnail.jpg` object.
- The `uploads` bucket has worker `INSERT`, `SELECT` and `UPDATE` policies;
  each policy delegates to that lease-scoped helper.
- `private.cretona_kaggle_complete(...)` requires both the canonical MP4 in
  `videos` and the canonical JPEG in `uploads` before it can set a project to
  `completed`.
- Completion persists both `video_path` and `thumbnail_path` and records both
  paths in the generation log.
- The pre-existing worker role remained non-superuser, non-inheriting and
  without direct table access or `BYPASSRLS`.

## Matching Kaggle smoke

The private `bruce335/cretona-wan2-1` notebook was updated to verify the exact
bundle and file hashes before copying either source file. Kaggle mounted the
new input under its nested dataset path, so two earlier attempts that assumed a
flat or ZIP-preserving mount stopped at file-presence assertions before reading
any secret or invoking the worker. The final cell resolved the one named
private input, verified both source hashes, loaded the same five existing
worker secrets without printing their values, installed the pinned
requirements and ran:

```text
python backend/kaggle_worker.py --once
exit code: 0
queue result: no claimable job
```

The cell printed `MIG-015 worker smoke finished`. Kaggle Version #1,
`MIG-015 thumbnail worker`, was quick-saved successfully.

## Evidence boundary

This proves the reviewed migration is live, its least-privilege contract is
present, the matching worker bundle is durable in Kaggle, and the worker can
authenticate and query an empty queue. It does **not** prove a post-MIG-015
Wan2.1 run uploaded a JPEG or that Android rendered that JPEG. That final
runtime claim requires one new app-submitted Kaggle job and device inspection;
the source and database now fail closed if the worker omits the thumbnail.
