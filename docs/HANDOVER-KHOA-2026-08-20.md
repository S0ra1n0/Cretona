# Cretona temporary handover to Khoa — 2026-08-20

> **Superseded historical handover.** Its branch, cached remote, CI token and
> test-count statements no longer describe the repository. Khoa should pull
> current `main`, verify the revision in [ROADMAP.md](ROADMAP.md), and execute
> the live acceptance sequence in
> [KAGGLE_WORKER_RUNBOOK.md](KAGGLE_WORKER_RUNBOOK.md).

This is a temporary continuation note, not a permanent ownership transfer.
It is revision-bound to audited source commit
`0617bae0e6152aab0380e27299bb4560feddc232`; the commit containing this note is
the next local commit. Re-read Git history rather than trusting test counts if
the source has moved.

## 1. Repository state at handover

- Working branch: `main`.
- Cached `origin/main`: `142e5a1b8b0601bcfe573de9682cc552c38f8bbe`.
- Local `main` is five commits ahead and the worktree was clean before this
  file was added.
- Live GitHub verification was blocked because the local `gh` token is invalid
  and Git Credential Manager returned `SEC_E_NO_CREDENTIALS`. The owner said
  they will push the local commits themselves.
- Cached `origin/khoa` is `637c0ee408e5cf6ea43dd14049f00c3590f3569c`
  and is already an ancestor of `main`; do not merge it back into `main`.

Local commits waiting for the owner to push, oldest first:

1. `7a129331be3728bd6295b2c0d026f7a2e8da9177` — Android cursor pagination end to end.
2. `b3b70df54d80c15a5a19a2b83f0b134442b63c9f` — PostgreSQL 17 parity CI job.
3. `048d737d781f80de2731142a5730e8484c8093e5` — pip/pytest security upgrades and `pip-audit` CI gate.
4. `6a133e391e0da45d68850a0dc9fe4feace2921d2` — SRS/architecture/configuration truth reconciliation.
5. `0617bae0e6152aab0380e27299bb4560feddc232` — preserve Android `cancelled` project state.

First receiver commands:

```powershell
git status --short --branch
git fetch origin
git log --oneline --decorate --graph -12
git log --oneline origin/main..main
```

Coordinate with the owner before pushing. If the commits are still local,
follow the repository rule: `git pull --rebase origin main` immediately before
`git push origin main`, then compare `git rev-parse HEAD` with
`git ls-remote origin refs/heads/main`.

## 2. What is proven

### Android

- 104 JVM tests passed, zero failures/skips.
- `lintDebug` passed with zero errors and one intentional `OldTargetApi`
  warning (`targetSdk=36` while compiling API 37).
- Debug APK and minified unsigned release APK assembled.
- Debug instrumented-test Kotlin compiled.
- The release APK remains unsigned.
- No device/emulator was attached for this audit. Keystore session persistence,
  rendered Compose UX, gallery save/share, and actual app-to-FastAPI behavior
  are not receiver/device-proven.

### FastAPI and Postgres

- `pip check`, Ruff check, and Ruff format check passed.
- 365 tests pass in the default credential-free profile; 31 Postgres-specific
  tests are skipped there by design.
- The complete 396-test suite passed against disposable PostgreSQL 17.6.
- After upgrading to pytest 9.1.1, the default suite passed and the focused
  Postgres parity suite passed again.
- `pip-audit 2.10.1` first found seven advisories in old pip/pytest; after
  upgrading to pip 26.2.1 and pytest 9.1.1 it reports zero known
  vulnerabilities. The exact constraint file matches 65 installed
  distributions.
- Disposable Postgres containers were stopped with `--rm`; bounded pytest QA
  directories were removed. No live Supabase data was mutated.

### Product truth

- Supabase Android Auth now uses the SDK and encrypted Android Keystore-backed
  session persistence.
- History, admin users, and audit logs now preserve cursor metadata and expose
  safe load-more flows.
- `cancelled` is a real terminal Android state, no longer displayed as an
  unknown failure.
- `mock` serves a bundled video. `cloud` and `local` may obtain one hosted still
  and render ffmpeg pan/zoom. No temporal text/image-to-video model runs.
- Qwen3-4B previously passed the local prompt-enhancement path; that does not
  prove video generation.

## 3. Next actions, in order

1. **Push and inspect CI.** Confirm all three jobs are green: Windows FastAPI,
   PostgreSQL parity, and Android. The latest Android CI SDK-manager fix has not
   been observed live because GitHub authentication expired. Fix only evidenced
   runner failures; keep each fix in its own commit.
2. **Run a device/emulator acceptance pass.** Verify cold-start session restore,
   sign-in/sign-up confirmation behavior, profile setup, mock create/poll/cancel,
   history load-more, admin load-more/filter reset, playback, gallery save, and
   share. Record package/window/device evidence rather than relying on compile.
3. **Run live Supabase read-only preflight.** Use the migration `status` gate and
   advisors. Do not apply a migration, create QA rows, rotate credentials, or
   call a paid provider without a new explicit owner confirmation and the
   backup/apply/verify protocol.
4. **Run a bounded live fake-provider smoke only after preflight.** Prove
   Android/FastAPI/Auth/Postgres/Storage behavior without spending provider
   money. Clean every QA object/row according to the approved script contract.
5. **Close or accept release gaps.** There is no Gradle dependency-verification
   metadata yet, the release is unsigned, and target API 37/device behavior is
   not accepted. The temporal-video provider remains a product decision, not a
   hidden code-complete feature.

## 4. Do-not-cross boundaries

- Never print or commit `.env`, `local.properties`, access tokens, service-role
  keys, JWT secrets, or database URLs.
- Android must never receive provider credentials, service-role access, raw
  model IDs, or billable retry authority.
- Do not edit an already executed migration; add the next numbered migration
  with a pinned hash and separate confirmation.
- Do not treat cached `origin/main`, a green unit suite, or a schema query as
  live runtime acceptance.
- Do not describe the still-plus-pan artifact as temporal AI video.

## 5. Current quality assessment

Pre-device, pre-live-refresh assessment: **7.9/10 overall**.

| Dimension | Score | Reason |
|---|---:|---|
| FastAPI/backend correctness | 9.0 | Strong state machine, auth, quota, leases, storage, observability, and 396-test Postgres evidence. |
| Android architecture/correctness | 8.4 | Persisted auth, provider-neutral API, pagination and media hardening; no runtime device evidence. |
| Database/data safety | 8.8 | Ordered migrations, hashes, RLS-aware design, destructive-test guard, disposable Postgres parity. |
| Security/privacy | 8.7 | Fail-closed auth/transport, secret boundaries, zero current Python advisories; Gradle verification metadata still absent. |
| CI/reproducibility | 8.2 | Pinned actions, wrapper checksum, exact Python constraints and Postgres job; newest remote runs not observed. |
| Testing/evidence | 8.6 | Broad JVM/backend/Postgres coverage and release builds; missing instrumented/device and current live smoke. |
| UX/accessibility | 7.7 | Compose semantics/static lint improved; no rendered accessibility or device walkthrough in this audit. |
| AI output/product differentiation | 5.0 | Prompt LLM path exists, but the core temporal video model is not implemented. |
| Documentation/traceability | 8.6 | Active docs now separate desired/implemented/observed truth; older evidence remains intentionally historical. |

The project is a strong Mobile 1 engineering submission and a credible
provider-neutral AI-media platform baseline. It is not yet a complete AI video
generator, signed release, or device/live-accepted release candidate.
