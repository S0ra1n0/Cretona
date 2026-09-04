# First worker jobs with audio — accepted, 2026-09-03

## Scope

This record closes EXP-006 phase 5: **a real Android-submitted Kaggle job
completing with a contextual soundtrack**, not an isolated notebook run. It
contains no credential values, connection strings or generated media.

Read back from the live database and private Storage on 2026-09-04 against
worker bundle SHA-256 `04d3e70b…` (commit `56654cd`) with
`CRETONA_WORKER_AUDIO=1`.

## Result

**Accepted, twice.** Both jobs generated the clip, produced a soundtrack,
composited it, extracted a thumbnail, uploaded both canonical objects through
the lease-scoped Storage policies, and completed. Neither refunded.

| | Job A | Job B |
|---|---|---|
| Project | `ab3d3d9e-1fce-4a17-bca4-ecf6a24ea2f5` | `9e2c812f-1795-4c4e-ba1a-a57ac1092eea` |
| Owner | `046ea264-dd97-448e-9483-a1549664baae` | same |
| Request | `kaggle`, 4 s, 16:9, text-only | same |
| Attempts | 1 | 1 |
| Started | 2026-09-03 16:55:55 UTC | 2026-09-03 17:27:32 UTC |
| Completed | 2026-09-03 17:25:32 UTC | 2026-09-03 17:55:15 UTC |
| Wall clock | **1778 s = 29.6 min** | **1664 s = 27.7 min** |
| Status | `completed`, 100 % | `completed`, 100 % |
| Ledger | one `-1 generation`, balance 27 | one `-1 generation`, balance 26 |

## The audio track is real, and it is audible

`ffprobe` on the objects downloaded from the `videos` bucket:

| | Job A | Job B | `46b6d55d` (silent baseline) |
|---|---|---|---|
| Video stream | h264, 4.0625 s | h264, 4.0625 s | h264, 4.0625 s |
| **Audio stream** | **aac, stereo, 44.1 kHz, 4.040 s** | **aac, stereo, 44.1 kHz, 4.040 s** | **none** |
| Audio bitrate | — | 127,623 bps | — |
| `volumedetect` mean | **−31.3 dB** | **−31.9 dB** | n/a |
| `volumedetect` max | **−5.2 dB** | **−4.7 dB** | n/a |

The peak levels matter more than the presence of a stream. A digitally silent
AAC track would report roughly −91 dB mean and −91 dB max; both clips peak near
−5 dB, which is an ordinary programme level. The container carries sound, not a
placeholder.

## Objects in private Storage

| Job | `videos/…/video.mp4` | `uploads/…/thumbnail.jpg` |
|---|---|---|
| A | 5,107,212 B | 145,423 B |
| B | 2,931,539 B | 59,784 B |

`thumbnail_path` is populated on both, so migration 015's fail-closed
completion accepted them on the normal path.

## Cost, measured against the silent runs

Every completed `kaggle` job on this database, oldest first:

| Project | Completed | Wall clock | MP4 bytes | Audio |
|---|---|---|---|---|
| `4ad038f6` | 09-01 14:11 | 453.2 min ¹ | 265,947 | no |
| `46b6d55d` | 09-02 18:53 | 28.5 min | 405,459 | no |
| `3047c9c0` | 09-02 20:00 | 38.4 min | 751,958 | no |
| `3c0d74f1` | 09-03 07:11 | 25.9 min | 300,080 | no |
| **`ab3d3d9e`** | 09-03 17:25 | **29.6 min** | **5,107,212** | **yes** |
| **`9e2c812f`** | 09-03 17:55 | **27.7 min** | **2,931,539** | **yes** |

¹ `started_at` is stamped at submission, so this row includes queue time before
a worker claimed it. It is not a generation measurement.

**Time: audio is not the dominant term.** 27.7 and 29.6 minutes sit inside the
25.9–38.4 minute band the silent jobs already spanned. These are end-to-end
figures on a shared free GPU with a variable session, not an isolated
benchmark, so they cannot be subtracted to yield a clean audio cost. They are
enough to say the feature did not change the order of magnitude.

**File size: this is the real cost, and EXP-006 predicted it.** The experiment
measured a 769,231 B input growing to 5,096,424 B and flagged the growth as
"the largest open cost of shipping audio", asking for a measurement on a real
worker clip rather than on the experiment's own input. That measurement is
here: **405,459 B → 2.9–5.1 MB**, a 7–12× increase. MMAudio re-encodes on
composite with more generous settings than Wan2.1 writes with; job B's video
stream alone runs at 5.64 Mbps against a 128 kbps audio track, so **the growth
is the video re-encode, not the sound**.

That lands on Supabase Storage, on signed-URL download, and on how quickly
playback starts over a tunnel.

**Fixed in source on 2026-09-05, not yet proven on Kaggle.** `add_audio` now
copies MMAudio's audio stream onto Wan2.1's original picture rather than
accepting the re-encode: no stream is encoded twice. Run against these exact
files, job A comes back at **472,018 B** — 10.8x smaller — with all 65 frames,
the picture at its original 798 kbps, and the soundtrack bit-identical at
−31.3 dB mean / −5.2 dB peak. That measurement was taken on a workstation. **No
worker job has produced a muxed clip yet**, so this is verified code, not
verified delivery.

## What this record does not establish

- **Whether the audio suits the video** was judged by ear during EXP-006, not
  scored here. This record establishes that a track exists, is audible, and
  survives the full worker path.
- **Android playback of these two clips** was not separately captured.
- **A warm-cache generation time** is still unmeasured, with or without audio.
- **The scope amendment was open when this record was written and is now
  closed.** `PROJECT-PROPOSAL.md` narrowed its non-scope line to audio *mixing*
  and names the generated soundtrack in `P0`; the CC-BY-NC 4.0 checkpoint
  constraint is recorded in `DEC-014`. Done 2026-09-05.

## Bearing on the final-demo notebook

`_test/cretona-kaggle-worker.ipynb` briefly pinned the silent `decc5f5d…`
worker with `ENABLE_AUDIO = False`, on the stated grounds that a real audio
worker job had not run. This record supersedes that premise, and on 2026-09-05
the notebook was moved to the `04d3e70b…` audio bundle with
`ENABLE_AUDIO = True`.

The two knobs are not independent. The silent worker contains no audio code and
ignores `CRETONA_WORKER_AUDIO` entirely, so setting the flag against the silent
hash downloads MMAudio and still produces a silent clip **with no error**. The
flag and the bundle hash move together or not at all.

`cretona-kaggle-worker-STEPS25.zip` (`decc5f5d…`) remains the fallback if audio
misbehaves during the session.
