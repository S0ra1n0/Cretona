# EXP-005 blind quality scorecard

Score only after two complete runs from a candidate have passed the technical
checks. Rename the clips to neutral labels before Bruce and S0ra1n0 score them
independently. This run has one known model, so the neutral labels hide only the
seed within each prompt pair. Do not open `BLIND_KEY.json` until both score
sheets are locked.

## Rubric

| Dimension | Weight | 0 points | Full points |
|---|---:|---|---|
| Composition | 20 | Main subject or scene is unusable | Clear subject, stable framing, readable scene |
| Motion coherence | 25 | Static, chaotic, or severe temporal drift | Intentional smooth motion with stable geometry |
| Prompt adherence | 20 | Requested subject, scene motion, or camera intent is ignored | A: dragon/lanterns/dolly; B: sailboat/swells/sail/orbit are recognizably present |
| Reference consistency | 20 | Subject/scene identity is lost | Subject, background and lighting remain recognizably stable through the clip |
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

## Scope decision — 2026-09-02

**The full two-reviewer blind protocol was deliberately descoped.** The exam
brief requires that the app generates and plays a video; it sets no quality
threshold, and the delivery window closes 2026-09-05. Scoring four clips across
five dimensions with two independent reviewers was judged to cost more than the
decision it would inform.

Replaced by a **single-reviewer non-blind review**, recorded below. This is a
weaker instrument and is labelled as one. No numeric score is claimed, and
`PB-FRAMEPACK-QUALITY`'s 73/100 bar is neither met nor failed — it was not
measured.

The reviewer sheets are left empty rather than deleted, so the protocol that was
designed stays visible next to the decision not to run it.

## Abbreviated review — S0ra1n0, 2026-09-02

All four clips watched: `A1 A2 B1 B2`, 5.06 s each.

**What holds.** Subject and setting match both prompts. A1/A2 show the origami
dragon over the lantern city; B1/B2 show the wooden sailboat on a calm dawn sea.
The two seeds per prompt differ from each other, so the model is producing
genuine variation rather than one memorised output.

**What fails, and it is systematic.** Directional and camera instructions are
ignored in **all four clips**:

| Prompt asked for | Observed |
|---|---|
| A: dragon glides **left to right** | Right to left in *both* A1 and A2 |
| A: camera **dollies forward** | No forward dolly in either |
| B: camera **orbits right** | No orbit in either |
| B: (direction unspecified for the boat) | B1 and B2 travel in *opposite* directions |

Two different failure shapes: prompt A is **consistently wrong** — both seeds
picked the same incorrect direction — while prompt B is **inconsistent**, with
the two seeds disagreeing. Neither is random noise on a single clip; the model
is not honouring directional or camera-motion language at all.

**Decision: adequate for the demo, with a constraint on prompts.** The clips are
coherent, artefact-free at a glance, and recognisably the requested subject —
enough for the §6 demo video and the live walkthrough. But **demo prompts must
not depend on a direction or a camera move**, because the model will not deliver
one and the mismatch would be visible to anyone reading the prompt alongside the
result.

## Locked result

| Candidate | Instrument | Outcome | Numeric score | Notes |
|---|---|---|---|---|
| Wan2.1 T2V 1.3B @ `0fad780a` | Single-reviewer non-blind, 2026-09-02 | **Adequate for demo** | not measured | Subject and scene adhere; direction and camera motion do not, across all four clips |

`Delta over Standard` and `Quality pass (>=8 delta)` are **n/a**: only one
candidate was generated, so there is nothing to compare against.

An abbreviated review is not a blind score. The honest status of this model is
**demo-adequate, quality unverified** — and that is what any report or viva
answer should say.

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

The sheets above stay empty on purpose: they are the protocol that was designed
and deliberately not run, kept beside the decision in "Scope decision" rather
than deleted. The recorded outcome is the abbreviated review, not this table.
