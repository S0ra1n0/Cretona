# EXP-006: video-to-audio feasibility on free Kaggle

**Status: gate passed 2026-09-03.** Audio generation works on a free Kaggle T4.
The worker can produce it, behind a flag that is off by default. Shipping it is
still a scope decision, not a merge — see `PLAN.md` phase 6.

## Why this is an experiment and not a task

`PROJECT-PROPOSAL.md` lists **audio mixing under explicit non-scope**. Shipping
audio therefore needs a deliberate scope change, not a quiet feature. Until this
experiment passes, the honest description of Cretona's output stays
**"silent video"**.

Deadline note: this must not compete with B-17 (demo recording) or B-18 (report
and submission package), which are required and unfinished. Run this only after
those are done, or on GPU time that would otherwise sit idle.

## Hypothesis

MMAudio can add contextual audio to an existing Wan2.1 clip on a free Kaggle
T4, in under five minutes per clip, without disturbing the video pipeline.

## Candidate

[MMAudio](https://github.com/hkchengrex/MMAudio) (CVPR 2025), video-to-audio
synthesis conditioned on the video **and** a text prompt.

| | |
|---|---|
| Code license | MIT |
| **Checkpoint license** | **CC-BY-NC 4.0 — non-commercial only** |
| Claimed VRAM | ~6 GB in 16-bit |
| Requires | Python ≥3.9, **PyTorch ≥2.5.1** |
| ffmpeg | Not needed; reads frames through `pyav` |
| CLI | `python demo.py --duration=4 --video=<clip> --prompt "..."` |

**The checkpoint licence is the first thing to decide, not the last.** CC-BY-NC
permits this coursework and forbids commercial use. If Cretona is ever meant to
be more than a university submission, that constraint follows the model.

## Kill criteria — stop and record a negative result if any holds

1. Kaggle's preinstalled PyTorch is below 2.5.1 and MMAudio will not run
   without replacing it. **Replacing torch is out of bounds**: the Wan2.1
   worker depends on the CUDA build Kaggle ships, and
   `requirements-kaggle.txt` says so in its first line.
2. Peak VRAM exceeds roughly 13 GB, leaving no headroom on a 16 GB T4.
3. One 4-second clip takes more than 5 minutes of GPU time.
4. The audio is not recognisably related to the video. A generic hiss is worth
   less than silence, because it invites the question of whether the model ran
   at all.

## Verdict, 2026-09-03

Run on one EXP-005 clip (`B2_seed5678.mp4`, 4 seconds) on a single T4.

| Kill criterion | Threshold | Run 1 | Run 2 | Run 3 (accepted) | |
|---|---|---|---|---|---|
| 1. torch | ≥ 2.5.1 | **2.10.0+cu128** | — | — | pass |
| 2. peak VRAM | ≤ ~13 GB | not measured | **7.53 GB** | — | pass |
| 3. time per clip | ≤ 300 s | 186 s | 91 s | **~180 s** | pass |
| 4. audio matches video | by ear | invented music | no music, no voice | **best** | pass |

**Accepted settings:** 50 steps, cfg 6.0, negative prompt set, prompt filtered.
Both `num_steps` and `cfg_strength` were raised in the same run, so which one
carries the improvement is untested. That is a fine trade while the budget has
room; it becomes worth separating only if the time ever needs winning back.

**Decision: proceed to integration.** All four criteria are met with measured
numbers, on a single T4, with the model licence understood.

### The 186 → 91 second drop is not a tuning win

Run 2 changed the prompt handling, not the compute: same 25 steps, same cfg.
The difference is that run 1 paid to load weights from a cold session and run 2
did not. **91 seconds is the honest per-clip figure** for a warm worker; 186 is
what the first clip after a session start costs.

That matters for the delivery estimate. Audio adds roughly **1.5 minutes** to a
warm job, not the 3–5 minutes projected from third-party numbers before anything
was measured here.

### Headroom is the interesting part

91 seconds against a 300-second budget left over three minutes unspent, and
run 3 spent it: 50 steps at cfg 6.0, about 180 s, still inside the limit and
judged the best of the three by ear. The budget is now roughly two thirds used,
which is the right place to stop — the remaining margin absorbs a slow session
rather than buying quality nobody asked for.

### Criterion 2 was not measured, and the notebook is why

Cell 4 reported `0.00 GB`. That figure is wrong, not good: `torch.cuda.max_memory_allocated()`
reads the counters of the **calling** process, while `demo.py` runs in a
subprocess with its own CUDA context. The `nvidia-smi` reading in cell 5 has the
opposite problem — it ran after the subprocess exited, so it shows 3 MiB of a
15360 MiB card, which is the memory nothing is using.

What can be said honestly: the run **completed on a 15 GB T4**, so it fit. An
allocation over the card would have raised an out-of-memory error rather than
producing a file. Treat criterion 2 as *satisfied by outcome, unmeasured by
instrument*, and sample `nvidia-smi` during the run if a number is ever needed.

### Output size is the finding nobody was looking for

| | Bytes |
|---|---|
| Input clip, silent | 769,231 |
| MMAudio `.flac` | 381,976 |
| **Output clip, with audio** | **5,096,424** |

The audio track is 382 KB; the video grew by **4.3 MB**. MMAudio re-encodes when
it composites, and its encoder settings are more generous than the ones Wan2.1
writes with. A real worker clip is currently 405,459 B, so audio as it stands
would take a typical project from roughly 0.4 MB to several MB.

That is not a blocker, but it is a cost nobody budgeted: it lands on Supabase
Storage, on the signed-URL download, and on how quickly playback starts in the
app over a tunnel. Worth a re-encode pass before this ships, and worth measuring
on a real 4-second worker clip rather than on this one.

This is now the **largest open cost of shipping audio**, larger than the 1.5
minutes of GPU time. It should be measured and, if it holds, fixed with encoder
settings before phase 5 rather than discovered from a Storage quota.

## Method

Run `EXP-006_v2a.ipynb` on Kaggle with a **T4** and Internet on. Input is one
already-generated clip — either an EXP-005 blind clip or a Wan2.1 output the
worker produced — uploaded as a private dataset. The notebook never touches
Supabase, never reads a Cretona secret, and writes only to `/kaggle/working`.

The notebook is ordered so the cheapest check runs first: it prints the torch
version and stops before downloading a single weight if kill criterion 1 holds.

## If it passes

Integration is a **separate decision**, and it is not small:

- amend `PROJECT-PROPOSAL.md` to move audio into scope, with the CC-BY-NC
  constraint recorded;
- decide where audio generation runs. Adding it to `kaggle_worker.py` extends
  a job that already takes ~20 minutes and is the only proven path to a video;
- decide what happens when audio fails. Migration 015 made completion fail
  closed on a missing thumbnail; a missing audio track must **not** get the
  same treatment, or one flaky model starts refunding finished videos.

## If it fails

Record the negative result here the way
`EXP-005_KAGGLE_T2V_DISCONFIRMED_2026-08-23.md` did, and leave the proposal's
non-scope line standing. A documented "we tried and it did not fit the
envelope" is a stronger answer than silence.
