# First post-MIG-015 job — thumbnail path accepted, 2026-09-02

## Scope

This record closes the last open runtime item on the roadmap: an
Android-submitted Kaggle job completing **after** migration 015 made completion
fail closed on a missing thumbnail. It contains no credential values, connection
strings, prompts or generated media.

## Result

**Accepted.** The worker generated the clip, produced a JPEG from its first
frame, uploaded both objects through the lease-scoped Storage policies, and the
database accepted completion.

| | |
|---|---|
| Project | `46b6d55d-e9c0-435a-ac96-b2decf0c5cdf` |
| Owner | `046ea264-dd97-448e-9483-a1549664baae` |
| Provider / request | `kaggle`, 4 seconds, 16:9, text-only |
| Status | `completed`, `progress_percent = 100` |
| Step message | `Wan2.1 video complete` |
| Started | 2026-09-02 18:24:54 UTC |
| Completed | 2026-09-02 18:53:25 UTC |
| Wall clock | **1711 s = 28.5 minutes** |

## Both canonical objects exist

Read from `storage.objects` against the live project:

| Bucket | Object | Type | Size |
|---|---|---|---|
| `videos` | `<owner>/<project>/video.mp4` | `video/mp4` | 405,459 B |
| `uploads` | `<owner>/<project>/thumbnail.jpg` | `image/jpeg` | 40,696 B |

`video_projects.thumbnail_path` is populated, not `NULL`. Before this run every
worker-produced project started with a null thumbnail and the gallery card read
"Preview unavailable".

The 40,696-byte JPEG is consistent with the off-GPU rehearsal, where
`create_thumbnail` produced 39,676–55,686 B images from the four EXP-005 clips.

## Charge is correct

Exactly one ledger row references the project:

```
delta=-1  balance_after=4  reason=generation  ref_type=project
```

One charge, no refund, no duplicate. The completion path did not double-charge
and the fail-closed branch did not fire.

## Revision under test

- worker revision: `3835071` (`STEPS = 25`, halved from 50)
- worker SHA-256 (LF blob):
  `decc5f5ddddfc0af515ee3cce045e1ce97742af854303afa4c24bba2d97e3823`
- requirements SHA-256:
  `46263bf0527742dde0d98a5da163afc1646a53b5f6de545ad3e94da43c99c669`
- notebook: rebuilt on the S0ra1n0 Kaggle account from
  `_test/cretona-kaggle-worker.ipynb`, not the earlier `bruce335` notebook

## What the 28.5 minutes contains

This was a **cold** run: the Kaggle session had no cached model, so the elapsed
time includes downloading roughly 22.7 GB of text-encoder shards plus the
transformer and VAE, the CPU prompt-encoding phase, then 25 denoising steps.

A warm run — same session, model already cached — should land near 20 minutes.
**That has not been measured.** Do not quote a warm figure as observed.

## Boundaries

- One GPU is used. `kaggle_worker.py` calls `pipe.to("cuda")` with no
  `device_map`, so the second T4 stays idle by design.
- Quality at 25 steps has not been scored against 50. The clip was judged
  usable by eye; no comparison was run.
- Playback of *this* clip in Android was not separately captured. Playback
  itself is proven by S-14 and by the demo-sample clip playing on the emulator
  on 2026-09-03.
- The emulator prints `[h264 @ ...] no frame!` while decoding. Video plays
  regardless; it is host FFmpeg log noise, not an app or backend fault.
