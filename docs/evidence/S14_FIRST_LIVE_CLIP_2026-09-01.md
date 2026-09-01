# S-14 — first app-submitted job completed by the live Kaggle worker

- **Document ID:** `CRETONA-S14-LIVE-001`
- **Mode:** Live end-to-end execution, observed after the fact
- **Observed:** 2026-09-02, reading live Supabase Postgres and Storage
- **Supersedes the S-13 boundary** in `KAGGLE_WORKER_S13_2026-09-01.md`, which
  recorded an empty-queue connectivity smoke and explicitly claimed no
  completed job.

## 1. Result

**A job submitted from Android completed through the Kaggle worker and its MP4
is in Supabase Storage.** The chain Android → FastAPI → Supabase queue → Kaggle
worker → Storage is proven end to end for the first time.

This was already true when `ROADMAP.md` still said otherwise. The two
screenshots committed in `69a4f40` were captured at 13:38 UTC while the job was
still `pending`; the worker completed it at 14:11 UTC. The screenshots are
accurate for the moment they were taken and were read as a failure.

## 2. The row

| Field | Value |
|---|---|
| project id | `4ad038f6-081d-4e81-894a-01301391ed36` |
| owner id | `afa529c7-22c5-43ab-b9eb-ebfc5d5e6db5` |
| provider | `kaggle` |
| mode | `text` |
| requested duration | 4 s |
| status | `completed` |
| progress | 100 |
| step message | `Wan2.1 video complete` |
| error code | none |
| attempt count | 1 |
| created / submitted | 2026-09-01 06:38:25 UTC |
| started_at | 2026-09-01 06:38:26 UTC |
| completed_at | 2026-09-01 14:11:39 UTC |

**The 7h33m between `started_at` and `completed_at` is not generation time.**
For the external `kaggle` provider, `submit()` only records the row, so
`started_at` marks *submission*, not the moment a GPU began work. The interval
is queue wait plus generation, and the worker was not running for most of it.
Generation time is not derivable from these two columns; only the notebook's own
log can give it. EXP-005 measured about 49 minutes for an 81-frame clip, and
this one is 65 frames.

## 3. The object

| Field | Value |
|---|---|
| path | `afa529c7-22c5-43ab-b9eb-ebfc5d5e6db5/4ad038f6-081d-4e81-894a-01301391ed36/video.mp4` |
| bucket | `videos` (private) |
| size | 265,947 bytes |
| mimetype | `video/mp4` |
| sha256 | `54afeb83e4707184839c9b0f7b90ac80894104bd9a639ccbd583f94aa2644b1e` |

The path matches the canonical `<owner-uuid>/<project-uuid>/video.mp4` contract
in `KAGGLE_WORKER_RUNBOOK.md` §5, so the worker's Storage write went where the
lease-scoped policy from migration 014 allows and nowhere else.

## 4. It is a real Wan2.1 clip, not a placeholder

Downloaded and parsed off the platform rather than trusting the row:

```
avc1  832x480  65 frames  4.063 s  16.0 fps  265,947 B
keyframe 18,364 B | mean frame 4,066 B | min 870 B | frames < 200 B: 0
```

Three things this rules out:

- **832x480** is Wan2.1's native resolution, not the bundled demo clip's.
- **65 frames** is `4n+1` — the frame-count constraint the Wan VAE imposes
  because it compresses time by 4. A fake or re-encoded asset would not land on
  it by accident, and 65 frames at 16 fps is the 4-second profile.
- **No frame under 200 bytes.** The grey-clip failure mode recorded in
  `EXP-005_KAGGLE_T2V_WORKING_2026-08-27.md` compresses to almost nothing per
  frame. A mean of 4,066 B/frame is real, varied content.

## 5. Billing behaved

```
delta  -1   balance_after 4   reason generation   06:38   (no note)
```

One charge, no refund, `attempt_count = 1`. The ledger-drift query returns no
rows across the whole database, so `users.credit_balance` still agrees with the
sum of its transactions.

This exercises the S-05 contract on live Postgres: reserve at submit, and keep
the charge when the generation succeeds.

## 6. What this does and does not close

**Closes:** a Wan2.1 job submitted through FastAPI completes and its real video
reaches Supabase Storage.

**Does not close:** *Android playback.* Nobody has yet opened the completed
project in the app and watched the signed URL play through Media3. That is the
last unproven link in the chain and the only remaining part of the §7
definition-of-done line, and it needs a device or emulator.

Until that is observed, report this as **live generation accepted, playback not
yet accepted** — the same discipline `KAGGLE_WORKER_S13_2026-09-01.md` applied
to its own narrower claim.

## 7. How this was verified

Read-only, from the repository's pinned virtual environment:

- `public.video_projects` for the row, using the backend's own `DIRECT_URL`;
- `storage.objects` for the object metadata;
- an authenticated `GET /storage/v1/object/videos/<path>` to fetch the bytes;
- a standalone MP4 container parse for codec, resolution, frame count, duration
  and per-frame sizes — no ffmpeg, no platform metadata trusted;
- `public.credit_transactions` plus the drift query from `DATA_MODEL.md` §4.2.

Nothing was written to the live database or Storage.
