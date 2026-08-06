# ADR-005: Secrets never reach the device; per-machine config via `local.properties`

**Status:** Accepted · **Date:** 2026-08-06 · **Roadmap:** P0-3

## Context

The system holds secrets of very different sensitivity: AI provider keys that cost money per call, the Supabase `service_role` key that bypasses RLS entirely, database connection strings, the Supabase anon key, and a release signing keystore. Meanwhile every developer machine needs its own backend URL, and an APK is a zip file that anyone can unpack.

## Decision

Secrets are classified by whether they may exist on a device, and stored accordingly.

**May ship in the app** — Supabase project URL, Supabase anon key. Supplied per machine through git-ignored `local.properties` and exposed as `BuildConfig` fields.

**Must never ship in the app** — `service_role` key, Supabase JWT secret, all AI provider keys, database connection strings. Backend environment variables only, injected by the host platform in staging and production.

**Never in the repository at all** — the release keystore and its passwords.

`.env.example` is committed and lists every backend key with a placeholder; `.env` is git-ignored.

## Rationale

- `BuildConfig` fields are plaintext in the APK. There is no obfuscation that changes this, so the rule has to be "don't put it there" rather than "hide it well".
- The anon key is the deliberate exception: it is designed to be public and carries no authority beyond RLS. Shipping it is safe *only because* RLS is enforced, which links this decision to [DATA_MODEL.md §4](../DATA_MODEL.md).
- `local.properties` already exists in every Android project and is git-ignored by default, so it is the path of least resistance for per-machine config — no new tooling, and no plausible way to commit it by accident.
- Falling back to empty strings for absent values means a fresh clone builds and runs before Supabase exists, which keeps onboarding from being blocked on account setup.

## Consequences

- [SETUP.md](../SETUP.md) documents every `local.properties` key; adding a new one means updating that file, or the next person's build silently misconfigures.
- Editing `local.properties` requires a Gradle re-sync to take effect.
- CI supplies these as environment variables or a generated `local.properties`, never from the repo.
- Redaction is enforced where data is produced, not at the logger, so no code path can leak a key by bypassing the logging helper ([SECURITY.md §6](../SECURITY.md)).
- The pre-release checklist includes unzipping the APK and grepping for `service_role` and provider key prefixes. A rule that is never tested is a rule that quietly stops holding.
- If a provider key leaks, rotation is a backend env change and a redeploy — no app release. That property is worth preserving.
