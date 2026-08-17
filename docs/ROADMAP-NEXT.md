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

Still unverified: **Supabase Storage** (mock transport only), **live project
creation** (no write has ever gone to live Postgres), and **migration 009**
(applied status unknown).

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

### T1-3 — Migration 009 status

`supabase/009_add_progress_tracking.sql` exists; whether it is applied is
unknown, and the migration gate only knows 006–008. Check with the four-boolean
query pattern, then extend the gate to cover 009.

---

## Tier 2 — Debt from this review

### T2-1 — Orphaned media on delete
Providers write `/media/{job_id}.mp4`, then re-hosting copies it to an
owner-scoped path. Delete removes only the scoped copy; the original
accumulates forever. **S**

### T2-2 — Third-party prompt egress
User prompts go to a hosted image endpoint. Now configurable via
`image_endpoint`, but still undocumented in `CONFIGURATION.md`, called through
`urllib` rather than the configured httpx client, with a spoofed User-Agent and
no content-type check on the bytes written to disk and served as user media. **M**

### T2-3 — Recreate the venv
`backend-fastapi/.venv` still exists and its editable install points at a
directory that no longer has a `pyproject.toml`, so `pip freeze` errors.
Recreate at `backend/.venv`, then delete the leftover — it also holds a
duplicate `.env` with live credentials. **S**

### T2-4 — Webhook replay
HMAC verifies authenticity, not freshness. A captured webhook can be replayed.
Needs a timestamp or nonce before any real provider posts to it. **M**

### T2-5 — Audit writes are not transactional
A failed audit row is logged and swallowed, so an admin action can succeed with
no trail. The fix is one transaction shared with the mutation. **M**

### T2-6 — `AdminScreen.kt` unreviewed
655 lines of composables. Visual risk only; its ViewModel and wiring were
reviewed. **M**

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

1. **T0-2** — decide the wording. It costs nothing and everything downstream
   inherits it.
2. **T1-1, T1-2** — the two unverified paths that can still invalidate work.
3. **T2-3** — ten minutes, removes a duplicate copy of live credentials.
4. **T1-3, T2-1** — small and contained.
5. **T3-1** — the real feature, once the gates are settled.

## The rule this project keeps relearning

A green suite means the code does what its author expected. It says nothing
about whether the expectation matched reality. Auth passed 24 tests for three
months while being unable to authenticate anyone; the audit migration passed
its tests against a schema that would never be deployed. Both were found by
running the real thing.

Where a doc and the code disagree, the code wins. Where the code and the live
system disagree, the live system wins.
