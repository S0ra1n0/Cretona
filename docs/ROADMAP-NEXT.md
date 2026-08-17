# Cretona — next roadmap

Written 2026-08-15 after reviewing the 23 commits that landed on `main`, and
verifying the branch directly rather than trusting its documentation.

## Verified state

Measured, not claimed:

| | |
|---|---|
| Backend suite | **303 passed, 23 skipped**, Ruff clean |
| Auth | ES256 via JWKS, proven against a real Supabase token |
| Persistence | Postgres proven live for reads; migrations 002–009 exist |
| Android | compiles; 12 unit tests |
| Dependencies | lock matches `pyproject.toml`; no drift |

Still unverified: **Supabase Storage** (mock transport only) and **live project
creation** (no write has ever gone to live Postgres).

**Migrations 006–009 are all applied and verified on live** as of 2026-08-17.
See T1-3 for what 009 needed and for the gate bug found in the process.

---

## Tier 0 — Integrity

The gap between what the code does and what it says it does. Partly fixed
already; the rest is unresolved.

### T0-1 — Video generation is a still image with a camera move ✅ documented

`_render_kenburns_from_ai_still` fetches one frame from a hosted text-to-image
endpoint and applies ffmpeg `zoompan`. There is no temporal model. All three
provider tiers call it, so Mock, Cloud AI and Local produce identical output
and differ only in wording and timing.

Renamed and re-documented on 2026-08-15, and the fabricated progress messages
("Local diffusion denoising latents (steps 1-10/20)") now describe the real
work. **The remaining question is a product one:** the UI still presents three
tiers as though they were different engines. Either give them genuinely
different behaviour, or collapse them to one until a real model exists.

### T0-2 — Decide what the demo claims

EXP-005 and ADR-009 gate a real video provider, and neither has passed. The
current output is a defensible zero-spend placeholder; describing it as AI
video generation is not. Agree the wording used in the app, the report, and any
demo before someone else has to defend it.

---

## Tier 1 — Unverified against reality

Ordered by how much they can still invalidate finished work.

### T1-1 — Supabase Storage

The last adapter that has never met a real bucket. Confirm `uploads` and
`videos` exist, set `CRETONA_STORAGE_BACKEND=supabase`, then sign an upload,
PUT an object, read it through a signed URL, delete it. Expect trouble around
bucket existence, service-role permissions, and the signed-URL response shape.

### T1-2 — First live project create

The first write to live Postgres. Re-enable the poller first, and know which
row you created — projects soft-delete, so they persist.

### T1-3 — Migration 009 ✅ applied and verified on live 2026-08-17

`verify-009` passes against the live project. 006, 007, 008 and 009 are all
applied.

**What was actually missing was one half of it.** 009 changes two things, and
only the constraint half was outstanding: `chk_error_code` listed the six
pre-009 codes and rejected the `cancelled` code that `ProjectService.cancel`
writes. `apply-009` fixed that; the constraint now carries `cancelled`.

The columns half was already in place before today — and the first run of this
gate reported it as absent, wrongly. `state_009` asserted `progress_percent`
was `smallint`, the type the migration declares. Live has it as `integer`: the
column pre-dated 009 there, so `add column if not exists` left the existing
width alone. A type-exact check turned "wider than declared" into "missing".

Two conclusions drawn from that false negative are withdrawn:

- **The backend could always boot against live.** `SELECTED_COLUMNS` selects
  these columns by name, not by type, so the startup check was never going to
  fail on an int4 `progress_percent`.
- **T1-2 does not need re-checking on this account.** The reason given for
  doubting it — that a live create was impossible — was not true.

The check now accepts any integer width for `progress_percent` and reports the
observed type alongside `progress_percent_matches_migration`, so the remaining
drift stays visible instead of being either fatal or invisible:

| | `progress_percent` |
|---|---|
| `supabase/009_add_progress_tracking.sql` | `smallint` |
| `backend/tests/postgres_schema.sql` | `smallint` |
| **live** | **`integer`** |

Harmless — the column holds 0–100 and int4 stores that exactly — but it means
the local Postgres test schema does not model live precisely. Worth reconciling
if `supabase/drift_check.sql` is ever pointed at this table.

Both gates now cover 009:

- `backend/app/postgres.py` checks the columns and the constraint separately, so
  a half-applied 009 names itself instead of surfacing as the old, misleading
  "apply 002–005" message. This is the check that would have caught the real
  problem: a database that takes the columns but keeps the old constraint
  accepts every progress update and rejects every cancellation.
- `scripts/live-supabase-migration-gate.py` gained `apply-009` / `verify-009`,
  plus a `status` action that reports what is applied without asserting.

**The lesson is the one this file already states, aimed at itself.** A gate is
also code, and its expectations can be wrong in the same way the code's can.
This one failed closed, which is the right direction to fail — but it still
produced a confident, specific, wrong answer, and the correction came from
querying the live schema directly rather than from trusting the tool.

---

## Tier 2 — Debt from this review

Done 2026-08-17 unless marked otherwise. 324 backend tests pass, Ruff check and
format clean, Android compiles and its unit tests pass.

### T2-1 — Orphaned media on delete ✅
`discard_provider_scratch` in `storage.py` deletes the provider's per-job output
once its bytes are re-hosted, in both the local and Supabase backends. It only
touches files sitting directly in the media root, so the owner-scoped copy it
just wrote can never be the thing removed, and the bundled demo clip is passed
in as a reserved name because every mock generation points at that one file
rather than producing it. Discard happens after the store succeeds — a failed
upload keeps the scratch file, which is its own test.

### T2-2 — Third-party prompt egress ✅
Now `CRETONA_IMAGE_ENDPOINT`, a real setting wired through `main.py` rather than
a constructor default the app never passed. Empty disables the egress and falls
the tiers back to the bundled clip. The call moved from `urllib` to httpx, the
spoofed `Mozilla/5.0` User-Agent is gone, and the response is refused unless it
is a JPEG, PNG, or WebP under 16 MB — it gets written into `MEDIA_DIR` and
served as user media, so an HTML error page must not land there. An ffmpeg
timeout no longer leaves the still behind either.

While documenting it, two adjacent claims in `CONFIGURATION.md` turned out to be
false and were corrected: `DEFAULT_VIDEO_PROVIDER` defaults to `mock`, not
`fake`, and accepts six values rather than "`fake` is the only accepted value".

### T2-3 — Recreate the venv ⚠️ half done
`backend/.venv` now exists, built from `constraints-windows-py312.lock`; tests
and Ruff both run in it and `pip freeze` no longer errors. **The leftover
`backend-fastapi/` has not been deleted** — that is a live-credential file and
the call is not mine to make. What remains in it is `.env`, `.venv`,
`.pytest_cache`, `.ruff_cache`, and two now-empty `app/` and `tests/`
directories; 115 MB. Its `.env` keys are a strict subset of `backend/.env`, so
nothing unique is lost.

### T2-4 — Webhook replay ✅
The signature now covers `<timestamp>.<raw body>`, sent as `X-Cretona-Timestamp`
in unix seconds, and a delivery outside `CRETONA_WEBHOOK_TOLERANCE_SECONDS`
(default 300, either direction) is refused. Because the timestamp is inside the
MAC, a captured delivery cannot be re-dated without the secret.

This narrows the window rather than closing it: a replay *within* the tolerance
is still accepted. Closing that needs a stored nonce, which needs a table, and
that is deliberately not built until a provider exists to send one. The old
bare-body signing scheme is no longer accepted at all.

### T2-5 — Audit writes are not transactional ✅
`update_user_flags` now takes an `AuditEntry` and writes the row inside the same
transaction as the mutation, on both adapters. If the audit row cannot be
written, the privilege change does not happen — proven by a test that makes the
insert fail and asserts the role is unchanged.

The thumbnail backfill deliberately still uses the old best-effort `_audit`: it
commits one project at a time, so there is no single transaction its summary row
could join. That is now stated in the docstring rather than left as a
repository-wide excuse.

### T2-6 — `AdminScreen.kt` reviewed ✅ findings below
Fixed: a hardcoded `Color.Gray` role label and two hardcoded `Color.White`
spinners, all three of which ignored the theme; and an unused destructured
`label`. Compiles clean, unit tests pass.

Three findings left as decisions, because they are product calls rather than
defects:

1. **Destructive admin actions have no confirmation.** "Demote to User" and
   "Disable" fire on a single tap, with no dialog. The backend refuses
   self-modification, but nothing stops a mis-tap on someone else's row.
2. **Pagination is ignored.** The API returns `nextCursor`/`hasMore`; neither
   `AdminUiState` nor `AdminViewModel` carries a cursor, so the users and audit
   lists silently show only the first page with no way to reach the rest.
3. **The stats chart's labels do not line up with its bars.** Bars are drawn at
   fixed 24px offsets from the left; the legend below uses `SpaceAround`, so the
   two disagree at any width.

Search is debounced in the ViewModel, so that earlier suspicion was unfounded.

---

## Tier 3 — Product

### T3-1 — A real video provider
The actual remaining feature. EXP-005 gates it: LTX-Video was rejected at
pre-screen, FramePack is blocked by the resource gate. Options are a paid
hosted video API (breaks the zero-spend baseline, needs a decision) or clearing
the hardware gate. **L**

### T3-2 — Verify the new features end to end
SSE streaming, cancel/refund, progress tracking, media gallery, style presets
and remix all landed with tests but none has run against live. **M**

---

## Suggested order

Rewritten 2026-08-17, after Tier 2 landed and 009 was applied.

1. **Delete `backend-fastapi/`** — finishes T2-3 and removes the second copy of
   live credentials. Minutes.
2. **T3-2** — verify the new features end to end. Cancellation is the one to
   start with: its constraint only began accepting `cancelled` today, so it has
   never once run against live.
3. **T1-1, T1-2** — the two remaining unverified paths.
4. **T3-1** — the real feature, once the gates are settled.

## The rule this project keeps relearning

A green suite means the code does what its author expected. It says nothing
about whether the expectation matched reality. Auth passed 24 tests for three
months while being unable to authenticate anyone; the audit migration passed
its tests against a schema that would never be deployed. Both were found by
running the real thing.

Where a doc and the code disagree, the code wins. Where the code and the live
system disagree, the live system wins.
