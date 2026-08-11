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
