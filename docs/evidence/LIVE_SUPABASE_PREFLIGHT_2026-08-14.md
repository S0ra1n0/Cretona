# Live Supabase read-only preflight

**Executed:** 2026-08-14T08:38:58+07:00

**Repository snapshot:** `main` at `4463cd57938da4c70f6bea3e205d7f76e9ce56e8`

**Audit status:** `needs-decision`

**Migration gate:** `blocked` until the live baseline and backup evidence are
reconciled

## Audit contract

The question was whether the live Supabase project is ready for the prepared
MIG-007 expansion. Bruce authorized a live **read-only preflight only**. Applying
migrations, running DDL or DML, changing Auth/Storage/API configuration, reading
business rows, or exposing credentials was outside the authority envelope.

The decision owner and integrator are Bruce; S0ra1n0 is the migration reviewer.
This report classifies current disagreement. It does not authorize or perform a
remediation.

The target identity was checked by matching the project reference derived from
the ignored `SUPABASE_URL` with the ignored direct PostgreSQL DSN. The actual
reference, URL, role, password, keys, and database host are intentionally not
recorded. The connected Supabase account available at the time did not list this
project, so the direct connection was used only after the identity check.

## Read-only guard and evidence boundary

The connection used `DIRECT_URL` from the ignored root `env` file. It opened an
explicit `BEGIN TRANSACTION READ ONLY`, then required
`transaction_read_only = on` before issuing any metadata query. Statement and
lock timeouts were 10 seconds and 2 seconds respectively. The transaction was
rolled back and the connection closed after the checks.

Only catalog/configuration metadata was selected:

- PostgreSQL version;
- expected table, column, index, RLS and policy metadata;
- Data API grants for the proposed internal rate-limit table;
- Supabase CLI migration-history table presence;
- the `public` flag for the repo-defined `uploads` and `videos` buckets.

No application-table rows, user records, generation requests/responses, rate
limit identifiers, or Storage objects were selected. No credential value was
printed or persisted. No SQL mutation was executed.

## Truth sources

| Source | Truth layer | Snapshot and authority |
|---|---|---|
| User authorization in the project task | desired | Read-only preflight; no live mutation |
| `docs/migrations/MIG-007-shared-rate-limits.json` | designed | MIG-007 plan, hold points and production authority at repository snapshot |
| `docs/BACKLOG.md`, `supabase/README.md` | derived view | Claim that migrations 004-007 are all prepared and unapplied |
| `supabase/004_add_started_at.sql` through `007_add_shared_rate_limits.sql` | implemented design | Expected additive objects and execution order |
| `docs/adr/ADR-010-shared-rate-limit-store.md`, `docs/DATA_MODEL.md` | designed | Postgres shared-store decision and target schema |
| Live PostgreSQL catalog queries | observed | Exact target matched; read-only transaction; 2026-08-14T08:38:58+07:00 |
| Supabase documentation and changelog | external constraint | Current platform guidance checked on 2026-08-14 |

Supabase currently requires RLS on exposed-schema tables and least-privilege
grants. Its current backup documentation says automatic daily backups apply to
Pro, Team and Enterprise projects, while Free projects should maintain regular
off-site logical exports. A 2026 platform change is also moving new public
tables to explicit Data API grants rather than automatic exposure. These
constraints support MIG-007's RLS-plus-revoke design, but they do not prove the
live project's plan or backup state.

Official references:

- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Securing your API](https://supabase.com/docs/guides/api/securing-your-api)
- [Database Backups](https://supabase.com/docs/guides/platform/backups)
- [Local development workflow](https://supabase.com/docs/guides/local-development/cli-workflows)
- [Tables not exposed to Data and GraphQL API automatically](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically)

## Observed live baseline

| Check | Observed result |
|---|---|
| PostgreSQL | `17.6` (`server_version_num = 170006`) |
| Existing expected app tables | `roles`, `users`, `video_projects`, `generation_logs` |
| RLS | Enabled on all four existing app tables |
| Expected policies | Six app-table policies and four `storage.objects` policies observed |
| Expected buckets | `uploads` and `videos` both exist and are private |
| Supabase CLI history | `supabase_migrations.schema_migrations` does not exist |
| Backup/restore point | Unknown; not observable through this DB session and the project is not visible to the connected Management account |

The absence of the CLI history table does not prove that no migration ran. It
means the repository's numbered SQL files were not traceable through the
Supabase CLI history mechanism on this target.

## Migration object comparison

| Migration | Repository view before audit | Live observation | Evidence |
|---|---|---|---|
| MIG-004 | Prepared, not applied | **Observed applied** | `video_projects.started_at` and `idx_projects_started_at` exist with the expected type/index definition |
| MIG-005 | Prepared, not applied | **Observed applied** | `lease_owner`, `lease_expires_at`, and `idx_projects_lease` exist with the expected types/index definition |
| MIG-006 | Prepared, not applied | **Observed not applied** | `idx_logs_retention` is absent |
| MIG-007 | Prepared, not applied | **Observed not applied** | `public.rate_limit_hits` and both proposed secondary indexes are absent |

MIG-007's zero-grant and RLS postconditions cannot pass while its table is
absent; they are not recorded as successful merely because no grant rows were
returned.

## Drift register

### DRF-LIVE-001 - live migration status view is stale

- **Type / confidence / severity:** `stale-view` / confirmed / material
- **Statement:** `docs/BACKLOG.md`, `supabase/README.md`, the status comments in
  migrations 004 and 005, and the MIG-007 source-state record say 004-007 are
  all unapplied. Live metadata proves 004 and 005 are already present.
- **Affected IDs:** B-1, B-2, MIG-004, MIG-005, MIG-007-OP-01
- **Consequence:** applying the documented four-file sequence blindly would no
  longer be an execution against the documented source state. MIG-004 also
  contains a backfill `UPDATE`, so `IF NOT EXISTS` does not make the whole file
  a proof-free no-op.
- **Owner / decision owner / reviewer:** data and operations boundary / Bruce /
  S0ra1n0
- **Remediation class:** view synchronization and migration provenance repair
- **Gate effect:** block any live apply until the baseline is acknowledged and
  the intended remaining sequence is reviewed.

### DRF-LIVE-002 - approved MIG-006 and MIG-007 objects are absent live

- **Type / confidence / severity:** `unimplemented-approved` / confirmed /
  material
- **Statement:** the retention index and shared rate-limit table have local
  design and disposable-Postgres evidence but are not present in the live
  schema.
- **Affected IDs:** B-4, B-3, MIG-006, MIG-007, ADR-010, MIG-007-OP-02/03
- **Consequence:** the live Postgres profile lacks the B-4 table-wide retention
  index, and the B-3 FastAPI Postgres adapter must not be switched on against
  this target because its required table is absent.
- **Owner / decision owner / reviewer:** FastAPI/Postgres integration / Bruce /
  S0ra1n0
- **Remediation class:** separately authorized environment/operations change
- **Gate effect:** block the MIG-007 application switch. This finding is not
  evidence that any live backend currently uses the B-3 revision; deployment
  revision was outside the audit coverage.

### DRF-LIVE-003 - applied migration provenance is missing

- **Type / confidence / severity:** `missing-trace` / confirmed / moderate
- **Statement:** the Supabase CLI migration-history table is absent, and no
  reviewed source records who applied MIG-004/MIG-005, when, or through which
  approved workflow.
- **Affected IDs:** MIG-004, MIG-005, MIG-007-OP-01
- **Consequence:** object presence can be verified, but execution provenance
  and ordering cannot be reconstructed from the live target alone.
- **Owner / decision owner / reviewer:** database delivery workflow / Bruce /
  Bruce and S0ra1n0
- **Remediation class:** traceability repair
- **Gate effect:** warning that becomes blocking if the team cannot establish a
  reviewed remaining migration sequence.

### DRF-LIVE-004 - backup state is unverified

- **Type / confidence / severity:** `unverified-claim` / confirmed evidence gap /
  material for live mutation
- **Statement:** no backup listing or restore point was available through the
  read-only database connection, and the Cretona project is not visible to the
  connected Supabase Management account.
- **Affected IDs:** MIG-007-OP-01 and its backup hold point
- **Consequence:** the precondition "current backup state is available" has not
  passed. Unknown does not mean that the project lacks backups.
- **Owner / decision owner / reviewer:** Supabase project owner / Bruce /
  S0ra1n0
- **Remediation class:** environment/operations evidence
- **Gate effect:** block live migration execution until the project owner
  verifies plan, latest backup/export, and recovery evidence through the owning
  Dashboard/account.

## Clean checks and limitations

Within the inspected metadata, the existing app tables have RLS enabled, the
expected six app and four Storage policy names are present, and both expected
buckets are private. MIG-004/MIG-005 columns and indexes match their prepared
definitions. MIG-007's explicit RLS and grant-revocation design remains aligned
with current Supabase guidance and the Data API exposure change.

This audit did not evaluate policy expressions, column-level grants on the
existing tables, Auth trigger behavior, business data/backfills, deployed
FastAPI/Android revision, API configuration, logs/advisors, Storage objects,
latency, pool behavior, or restore viability. A clean check above applies only
to the named metadata, not the whole project.

## Decision required before any live mutation

1. Record and review the real live baseline: MIG-004 and MIG-005 observed
   applied; MIG-006 and MIG-007 pending.
2. Ask the owning Supabase account to verify the project plan, latest usable
   backup or off-site logical export, and recovery path. Do not paste tokens or
   passwords into chat or commit them.
3. Re-review the remaining ordered operations as a new authorized task:
   MIG-006 first, then MIG-007, then the B-3 FastAPI switch and smoke evidence.
4. Preserve this preflight as evidence only. Applying either SQL file requires
   a separate explicit approval and must not be inferred from this report.

No migration was applied by this preflight.
