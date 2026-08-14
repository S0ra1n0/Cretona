# Live Supabase migrations 006 and 007

**Executed:** 2026-08-14 (final verification recorded at
2026-08-14T09:42:31+07:00)

**Repository candidate:** `main` at
`1e4786e1879abf51457cc31802f68caf2c112c86`

**Result:** `pass` for the live schema expansion; FastAPI deployment remains
outside this execution

## Authority and scope

Bruce, the recorded production execution authority and Supabase project
administrator, explicitly authorized the live execution. The repository named
S0ra1n0 as reviewer, but no source-backed evidence of that review was found.
Bruce accepted that residual risk as an authority override. This report does
not state or imply that S0ra1n0 reviewed the migration.

The authorized sequence was deliberately narrow:

1. pull and pin the current remote candidate;
2. re-verify the off-site logical backup;
3. run an explicit read-only live preflight;
4. apply and independently verify MIG-006;
5. only after MIG-006 passed, apply and independently verify MIG-007;
6. run the Supabase Security and Performance Advisors;
7. reconcile repository status and preserve non-secret evidence.

No Auth, Storage, API, network, or project configuration changed. No business
row, user record, caller key, generated media, or Storage object was read. No
FastAPI or Android revision was deployed.

## Pinned inputs

Immediately before candidate pinning, `git pull --rebase origin main` returned
`up-to-date`. The candidate and immutable execution hashes were:

| Input | SHA-256 / Git hash |
|---|---|
| Repository snapshot | `1e4786e1879abf51457cc31802f68caf2c112c86` |
| `006_add_generation_log_retention_index.sql` | `76ece1e4e7c9361902451d656350a154eeaf9db21a5c56d59543b852a001e401` |
| `007_add_shared_rate_limits.sql` | `c698312bbc36474113b9ae529f57bff6fcfc32241cc87dbf44c45b7d33e14d63` |

The historical `PREPARED, NOT APPLIED` comments inside the two SQL files were
not edited after execution because doing so would change those hashes. This
report, `supabase/README.md`, and `docs/BACKLOG.md` are the current live-status
views.

## Recovery evidence

The Supabase Dashboard identified the target as a Free-plan production project;
the plan does not provide platform project backups. Before DDL, a logical export
was created outside the Git repository with Supabase CLI `2.114.0` and Docker
server `29.6.2`. Its directory ACL disables inheritance and grants full control
only to the current Windows user, local SYSTEM, and builtin Administrators.

The artifact was re-hashed immediately before the migration:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `roles.sql` | 370 | `168a95a9c745af5ed4679751f90419ac9dc434240a213b03e32a06d5664c2308` |
| `schema.sql` | 14,564 | `f78ee407ab8a88528df5806b00f1d06cf9ce2a5cb27abafcd21148de848b9974` |
| `data.sql` | 13,834 | `faa39bd49627c3bd26d454754d4b1faeadb52944c177e83f33163a34620cdaeb` |
| `manifest.json` | 1,369 | `a93d66c36c9354374afcf644dd0deac203e6aebfd6e017f34e3f29c361b8dc5f` |

The export contains database roles, schema, application data, and Storage
metadata. It does **not** include the Storage object bytes, and no restore drill
was performed. It is recovery material, not proof that restoration will
succeed. The reusable command is `scripts/backup-live-supabase.ps1`; it refuses
an output path inside the repository, validates the project identity, pins the
CLI version, scans artifacts for connection strings/passwords, emits hashes,
and locks down the output ACL.

Official backup guidance:

- https://supabase.com/docs/guides/platform/backups
- https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore

## Guarded execution method

`scripts/live-supabase-migration-gate.py` used the ignored root `env` file and
required the project reference derived from `SUPABASE_URL` to match the direct
PostgreSQL DSN. Apply operations additionally required an exact, explicit
project-reference confirmation and refused any migration whose SHA-256 differed
from the allowlist above. Credential values were neither printed nor written to
evidence.

Every preflight and verification ran in a new `BEGIN TRANSACTION READ ONLY`,
required `transaction_read_only = on`, used 10-second statement and 2-second
lock timeouts, selected catalog metadata only, and closed the connection after
the check. MIG-006 ran in autocommit mode because `CREATE INDEX CONCURRENTLY`
cannot run inside a transaction. MIG-007 retained its own short transaction.

The first local run of the new gate correctly stopped before DDL because the
gate itself expected `lease_owner uuid`; the committed MIG-005 source declares
`lease_owner text`. The verifier was corrected to match the pinned SQL and its
partial `lease_expires_at` index, then linted and rerun. This was a verifier
defect, not live schema drift, and no migration had run at that point.

## Final preflight

The corrected preflight passed with:

| Check | Observed result |
|---|---|
| PostgreSQL | `17.6` (`server_version_num = 170006`) |
| Read-only guard | `transaction_read_only = on` |
| MIG-004 | `started_at` and `idx_projects_started_at` matched |
| MIG-005 | `lease_owner text`, `lease_expires_at timestamptz`, and the partial lease index matched |
| MIG-006 before apply | `idx_logs_retention` absent |
| MIG-007 before apply | `public.rate_limit_hits` absent |
| Public invalid/unready/non-live indexes | zero |
| Supabase CLI migration-history table | absent |

The missing `supabase_migrations.schema_migrations` table remains a provenance
limitation: object state and this execution are now evidenced, but earlier
MIG-004/MIG-005 execution provenance cannot be reconstructed from the live
target.

## MIG-006 result

MIG-006 created `public.idx_logs_retention` concurrently. A separate read-only
verification then observed:

- exact target table `public.generation_logs`;
- btree key order `(created_at, id)`;
- `indisvalid = true`;
- `indisready = true`;
- `indislive = true`;
- zero invalid/unready/non-live indexes in `public`;
- MIG-007 still absent.

Only after this gate passed was MIG-007 allowed to run.

## MIG-007 result

MIG-007 committed successfully. A separate read-only verification proved:

| Contract | Observed result |
|---|---|
| Columns | `id bigint`, `caller_key text`, `bucket text`, `occurred_at timestamptz`; all `NOT NULL` |
| Constraints | primary key plus `chk_rate_limit_caller_key` and `chk_rate_limit_bucket` |
| Indexes | primary key, `(caller_key, bucket, occurred_at, id)`, and `(occurred_at, id)` |
| Index health | all three valid, ready, and live |
| RLS | enabled |
| RLS policies | zero, by design for an internal direct-Postgres table |
| Data API table privileges | all seven privilege types false for each of `anon`, `authenticated`, and `service_role` |
| Data API sequence privileges | `USAGE`, `SELECT`, and `UPDATE` false for each of the three roles |
| Public invalid/unready/non-live indexes | zero |

This is stronger than checking explicit grant rows: the 30
`has_table_privilege`/`has_sequence_privilege` checks also reject effective
privileges inherited through another grant path.

## Supabase Advisors

Because the interactive browser connector was unavailable and the connected
Management API account did not own this project, the official Supabase CLI
`db advisors` command was run against the validated direct DSN with version
`2.114.0`, `--type all`, `--level info`, and a read-only reporting contract.
Supabase documents that the Advisors check security and performance issues:

- https://supabase.com/docs/guides/database/database-advisors
- https://supabase.com/docs/reference/cli/supabase-db-advisors

The run returned 19 findings: zero `ERROR`, seven `WARN`, and twelve `INFO`.
No warning or error identified a MIG-006/MIG-007 contract failure.

- Six performance warnings were pre-existing RLS policies that call
  `auth.<function>()` per row.
- One security warning was the pre-existing `set_updated_at` function with a
  mutable search path.
- One info finding identified the pre-existing unindexed `users.role_id`
  foreign key.
- Nine info findings identified unused indexes. The three new indexes are
  expected to be unused immediately before the corresponding live workers are
  deployed; unused-index findings are not deletion authorization.
- Two security info findings identified RLS-enabled tables with no policies.
  For `rate_limit_hits`, this is intentional: it is backend-only and all
  effective Data API table/sequence privileges independently verified false.
  The other finding concerns the pre-existing `roles` table.

The unrelated warnings are recorded follow-up work; they were not silently
fixed inside this bounded live-migration task.

## Repository validation

After reconciling the live-status views and adding the reusable operator tools:

- the standard FastAPI suite passed `241 passed, 20 skipped`; the skipped tests
  are the environment-gated Postgres cases already covered by the earlier
  disposable-Postgres `261 passed, 0 skipped` run;
- Ruff passed for `backend-fastapi/app`, `backend-fastapi/tests`, and the live
  migration gate;
- the migration gate compiled with Python 3.12;
- both PowerShell operator scripts parsed successfully;
- the migration plan parsed as JSON;
- `git diff --check` passed;
- an intentionally wrong project confirmation was rejected before connection;
- an intentionally repository-local backup output path was rejected before
  Docker or dump execution;
- the changed evidence/scripts contained no detected PostgreSQL URL, Supabase
  access-token prefix, JWT-shaped value, or hard-coded project reference.

## Outcome and remaining gates

The live schema expansion is complete and internally consistent. MIG-006 and
MIG-007 are present with the exact pinned definitions and their security
postconditions pass. No rollback was triggered.

The following claims remain unproven and must stay separate:

1. the pinned B-3 FastAPI revision is deployed/configured against live
   Supabase;
2. health, startup-schema, CRUD, and shared multi-instance rate-limit smoke
   tests pass in the deployed environment;
3. backup restoration and Storage object recovery work end to end;
4. advisor warnings have been triaged in separate reviewed changes;
5. S0ra1n0 has reviewed the migration after the fact.

The next deployment gate is therefore the FastAPI switch/smoke operation in
`docs/migrations/MIG-007-shared-rate-limits.json`, not another schema apply.
