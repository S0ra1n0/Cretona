# EXP-007 -> image-to-video delivery plan

Written 2026-09-04. Nothing here is committed to; phase 1 can end all of it.

## Ordering rule

**The gate runs before the integration, not after.** Cell 1 of
`EXP-007_wan22_i2v.ipynb` costs seconds and downloads nothing. Cells 2-3 cost a
34 GB download and are the first real spend. Nothing below phase 3 is worth
starting until phase 2 has produced a clip.

EXP-006 wrote the worker code ahead of its gate because that code was **inert
behind a flag**. This one is different: image-to-video changes the model the
video path runs on, so there is no inert version of it. The code is written
after the measurement, not before.

## Phases

| # | Who | What | Time | Blocks on |
|---|---|---|---|---|
| 1 | You | EXP-007 cell 1: pipeline, dtype, disk | 2 min | — |
| 2 | You | EXP-007 cells 2-7: one clip, measured | 45 min | 1 passes |
| 3 | Both | Decide: two models, one model, or neither | 30 min | 2 passes |
| 4 | Claude | Worker integration for the chosen shape | 2 h | 3 |
| 5 | You | New bundle, hashes, upload, restart | 20 min | 4 |
| 6 | You | One real image job end to end from the app | 40 min | 5 |
| 7 | Claude | Amend proposal, SRS, ADR, roadmap | 30 min | 6 passes |

Phase 2's 45 minutes is mostly download. The generation itself is what
criterion 3 measures.

## Phase 3 is a real decision, not a formality

A pass on the gate does not say which shape to ship. Three are on the table.

**Two models.** Wan2.1-1.3B keeps every text-only job; Wan2.2-5B handles jobs
that carry a reference image. Nothing already working changes, which is the
whole appeal. The cost is a second multi-gigabyte download in the same Kaggle
session and two code paths to keep alive.

**One model.** Wan2.2-TI2V-5B serves both, since it is a TI2V model and takes
text-only prompts natively. Simpler worker, one download, one set of quality
characteristics to describe in the report. The cost is that every existing T2V
result — the four reviewed clips, the recorded direction and camera-motion
limitations, the ~20-minute warm figure — becomes evidence about a model that
is no longer running.

**Neither.** Ship what exists and document the reference image as a stored
reference and thumbnail. This stays on the table through phase 3 and is not a
failure state.

## Constraints the integration inherits

**Frame rate is a contract change.** `frame_count()` computes
`duration_seconds * FPS + 1` with `FPS = 16`, and `export_to_video` writes at
16. TI2V-5B is a 24 fps model. Exporting its frames at 16 fps plays them 1.5x
slow. Moving `FPS` to 24 changes the frame count for a 4-second clip from 65 to
97, which raises both time and memory — and if both models ship, `FPS` stops
being a constant and becomes a per-provider property.

**Dimensions must stay divisible by 16.** `check_inputs` enforces it. Cretona's
`ASPECT_DIMENSIONS` — 832x480, 480x832, 640x640 — all pass. This is checked, not
assumed.

**Prompt embeddings are cached by a hash that names the model.**
`_embedding_cache` hashes `MODEL_REPO`, `MODEL_REVISION`, the negative prompt
and the job prompt. Two models means two caches, which the existing hash
already handles correctly. A revision pin is required for the new repo the same
way `MODEL_REVISION` pins Wan2.1.

**A missing reference image must not fail a text-only job.** The inverse of
EXP-006's rule. If image conditioning is unavailable for any reason, the job
falls back to text-only generation and completes, rather than refunding a
prompt the user wrote in good faith.

## What phase 7 must not skip

`PROJECT-PROPOSAL.md` and the SRS describe the generated video as text-driven.
If a reference image starts steering generation, that is a capability change
and it gets recorded as a decision with the model, its licence, and its
measured cost — the same treatment EXP-006's audio work is getting. Shipping a
capability the requirements do not describe reads as drift, not as delivery.

## Kill criteria, restated

Unchanged from `README.md`. The two worth repeating:

**Do not upgrade torch and do not unpin diffusers.** Verified: `v0.36.0`
already contains the `expand_timesteps` I2V path, so no bump should be needed.
If one appears to be needed anyway, that is a signal to stop, not a step to
take — the pin protects the only proven path to a video this project has.

**A slower job is a worse app.** Criterion 3 exists because image conditioning
bought at the cost of a forty-minute wait is not an improvement. If the clock
says 25 minutes or more, the answer is no even when everything else passes.

## Cost

Unmeasured. What is known:

| | |
|---|---|
| Download, once per Kaggle session | ~34.2 GB |
| Today's warm job, Wan2.1 + audio | ~20 min + ~3 min |
| Generation time, Wan2.2-5B at 832x480 | **this is what phase 2 measures** |

The token arithmetic in `README.md` says the 5B model carries fewer tokens at
this resolution than the 1.3B model does today, and about four times the
parameters. Those pull in opposite directions and no arithmetic here settles
which wins. That is why there is a clock in the notebook.
