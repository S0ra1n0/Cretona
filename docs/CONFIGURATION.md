# Cretona configuration and secret boundary

Status: accepted baseline on 2026-08-10.

## Authoritative configuration

- Android machine-local values belong in root `local.properties`, because the
  repository root is the Android Gradle project.
- Backend environment values belong in `backend/.env`; the committed
  `backend/.env.example` must mirror the active backend config loader without
  containing a real value.
- Only `local.properties.example` and `backend/.env.example` are safe to commit.
- Android must never receive a provider service key, JWT signing secret, or
  database administrator credential.

## Teammate-provided local files

Bruce confirmed on 2026-08-10 that S0ra1n0 supplied the untracked root files
`env` and `local.properties`. Their keys indicate a Node/Supabase/Runway
direction, and the Android SDK path in the root `local.properties` belongs to
S0ra1n0's Windows profile rather than Bruce's machine. The live remote audit on
2026-08-10 found the matching Compose, Express, Prisma, and Supabase source plus
tests in commits `ac6804d` through `2cb3d91`.

These files are therefore classified as **teammate-provided, machine-local
configuration for the remote implementation**. They remain untouched so no
team data is lost, and `.gitignore` prevents them from being staged. Values
must be copied selectively into the canonical machine-local files; SDK paths
must never be copied between developers unchanged.

## Credential verification result

- Git history contains no occurrence of the three sensitive configuration key
  names detected in the local files.
- The local values were not printed, copied into documentation, or sent to a
  provider.
- Because validity and account ownership cannot be proved safely from this
  repository, they are treated as potentially real and owned by the teammate
  who supplied them until the team records otherwise.

Rotate a credential if it has ever been pasted into chat, shared through an
unsafe channel, committed in another repository, or exposed to someone who
should not retain access. Bruce should ask S0ra1n0 whether the service-role and
JWT values are live and whether their transfer channel was appropriate.
Rotation is an external account action and is not performed by this repository
setup.

## Accepted backend direction

FastAPI is the required final model-orchestration boundary. The teammate's
Express implementation is preserved as migration evidence because it already
defines tested auth, quota, project lifecycle, storage, provider, and job-runner
behavior. The migration replaces the web framework, not those invariants.

Supabase Auth/Postgres/Storage may remain behind FastAPI during the migration so
the team does not rewrite working identity, data, and storage boundaries at the
same time. Runway remains disabled; zero-cost local video providers may be
added only behind the provider interface after `EXP-005` passes.
