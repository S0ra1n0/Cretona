# EXP-006: video-to-audio feasibility on free Kaggle

**Status: not started.** Nothing here is wired into the worker, the backend or
the app. This folder exists to answer one question cheaply before anyone spends
delivery time on it.

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
