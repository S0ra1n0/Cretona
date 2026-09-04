# EXP-006 → audio delivery plan

Decided 2026-09-03. Audio moves from experiment to candidate feature.

## Ordering rule

**The gate runs before the integration, not after.** Cell 1 of
`EXP-006_v2a.ipynb` costs five minutes and can end this whole plan. Nothing
below is worth starting until it passes.

The worker code in phase 3 is written **ahead** of the gate deliberately: it is
inert until a flag is set, so writing it early costs nothing and removes an hour
from the critical path if the gate passes. If the gate fails, the code ships
disabled and the proposal's non-scope line stands.

## Phases

| # | Who | What | Time | Blocks on |
|---|---|---|---|---|
| 1 | You | EXP-006 cell 1: torch ≥ 2.5.1 | 5 min | ✅ **2.10.0+cu128** |
| 2 | You | EXP-006 cells 2–5 on an existing clip | 25 min | ✅ **passed, 3 runs** |
| 3 | Claude | Worker integration, flag off by default | done | ✅ **tuned to 50/6.0** |
| 4 | You | New bundle, hashes, upload, restart | 20 min | 2 passes |
| 5 | You | One real job with audio end to end | 35 min | ✅ **two jobs, 09-03** |
| 6 | Claude | Amend proposal scope, SRS, roadmap | 20 min | ✅ **`DEC-014`, 09-05** |

Phase 3 is already complete; see below.

## The rule that governs the integration

**A missing audio track must never fail a finished video.**

Migration 015 made completion fail closed on a missing thumbnail, and that was
right: a gallery card with no preview is a defect. Audio is not in that
category. It is an enhancement on top of the one thing this project is graded
on, so the failure mode is a **silent video**, logged, uploaded, and completed
normally.

Concretely this means audio generation is:

- wrapped so that any exception is caught and logged, never re-raised;
- placed after the video file exists and before the thumbnail, so a failure
  leaves a complete, uploadable clip behind;
- off unless `CRETONA_WORKER_AUDIO=1` is set, so an older bundle and a
  notebook that never sets the flag behave exactly as they do today.

## Phase 6, done 2026-09-05

`PROJECT-PROPOSAL.md` listed audio mixing under **explicit non-scope**. That
line is now narrowed to mixing alone, the generated soundtrack is named in
`P0`, and the change is recorded as **`DEC-014`** with the CC-BY-NC checkpoint
constraint, the measured evidence and the measured cost. Shipping a feature the
proposal says is out of scope, without amending the proposal, would have read
as scope drift rather than a decision.

## Kill criteria, restated

Unchanged from `README.md`. The one worth repeating: **do not upgrade torch to
make MMAudio run.** The Wan2.1 worker depends on the CUDA build Kaggle ships.
Trading a proven video path for an unproven audio one is the single worst
outcome available here.

## Cost

Measured today: a 4-second clip is 28.5 minutes cold, ~20 warm.

Measured in phase 2 at the accepted settings: **~180 seconds per clip**, plus a
one-off 6.0 GB download per Kaggle session. A warm job therefore goes from about
20 minutes to about 23.

The pre-measurement estimate of 3–5 minutes came from a third-party RTX 4050
report and happened to land close. The number that did not survive contact was
**file size**: the composited clip is several times larger than the silent one,
which is now the largest open cost of shipping audio.
