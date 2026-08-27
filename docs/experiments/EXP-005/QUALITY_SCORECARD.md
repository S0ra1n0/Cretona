# EXP-005 blind quality scorecard

Score only after two complete runs from a candidate have passed the technical
checks. Rename the clips to neutral labels before Bruce and S0ra1n0 score them
independently. Do not reveal the model name until both score sheets are locked.

## Rubric

| Dimension | Weight | 0 points | Full points |
|---|---:|---|---|
| Composition | 20 | Main subject or scene is unusable | Clear subject, stable framing, readable scene |
| Motion coherence | 25 | Static, chaotic, or severe temporal drift | Intentional smooth motion with stable geometry |
| Prompt adherence | 20 | Motion/camera request is ignored | Dragon, flight direction, lantern motion, and camera intent are present |
| Reference consistency | 20 | Subject/scene identity is lost | Dragon, moon, lighting, and city remain recognizably consistent |
| Artifact control | 15 | Severe morphing, duplication, tearing, or flicker | No distracting temporal or structural artifact |

Use whole-number scores from zero up to each dimension's weight. The total is
the sum, out of 100. Reviewers may add observations but may not change weights
after seeing outputs.

## Run under review

| | |
|---|---|
| Run id | `exp005-t2v-20260827T104718Z` |
| Ledger entry | `EVD-EXP005-011` |
| Model | Wan2.1 T2V 1.3B (`Wan-AI/Wan2.1-T2V-1.3B-Diffusers@0fad780a`) |
| Clips | `blind/A1.mp4 A2.mp4 B1.mp4 B2.mp4` — 832x480, 81 frames, 5.06 s, H.264 |
| Settings | 50 steps, 81 frames, seeds 1234 / 5678 |
| Technical status | **passed** — 4/4 generated, 4 distinct digests |
| Quality status | **unscored** |

Clips are in the gitignored
`docs/experiments/EXP-005/runs/exp005-t2v-20260827T104718Z/blind/`. The second
reviewer needs the archive sent directly. **Do not open `BLIND_KEY.json`
until both sheets below are filled in.**

**Reference consistency, for text-to-video.** The 20-point *Reference
consistency* dimension assumes a reference image, and this run is text-only.
Score it as **identity stability across the clip** — does the subject stay the
same subject from first frame to last — and say so in the notes column.

**One model, so no delta.** The `Delta over Standard` and `Quality pass (>=8
delta)` columns in the locked result cannot be filled from this run: there is
no second passing candidate to compare against. Record them as `n/a` and judge
against the `>= 65` standard bar alone, noting that `PB-FRAMEPACK-QUALITY` sets
73/100 for the local FramePack path.

## Reviewer sheets

| Neutral clip | Reviewer | Composition /20 | Motion /25 | Prompt /20 | Reference /20 | Artifacts /15 | Total /100 | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A1 | Bruce |  |  |  |  |  |  |  |
| A2 | Bruce |  |  |  |  |  |  |  |
| B1 | Bruce |  |  |  |  |  |  |  |
| B2 | Bruce |  |  |  |  |  |  |  |
| A1 | S0ra1n0 |  |  |  |  |  |  |  |
| A2 | S0ra1n0 |  |  |  |  |  |  |  |
| B1 | S0ra1n0 |  |  |  |  |  |  |  |
| B2 | S0ra1n0 |  |  |  |  |  |  |  |

## Locked result

| Candidate revealed after scoring | Mean score | Standard pass (>=65) | Delta over Standard | Quality pass (>=8 delta) |
|---|---:|---|---:|---|
|  |  |  |  |  |

Both reviewers sign/date the locked result in the pull request or submission
record. An unscored model is `unverified`, not `passed`.
