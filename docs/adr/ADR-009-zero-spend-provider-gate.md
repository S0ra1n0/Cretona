# ADR-009: Gate the zero-spend video provider on local evidence

**Status:** Superseded by ADR-011 · **Date:** 2026-08-10 · **Supersedes:** ADR-004
· **Amended:** 2026-08-19 (host recheck — see §Update)

## Context

ADR-004 assumed Runway would be the launch provider. The team later selected a
zero-additional-cash-spend baseline and the instructor required model calls to
pass through FastAPI. Paid hosted products such as Runway, Kling, Gemini/Veo,
or OpenAI video can produce stronger or more convenient results, but they do
not satisfy the selected repeatable-free constraint.

Open-weight model quality and low-VRAM feasibility are different questions.
The measured laptop has an RTX 3070 Ti Laptop GPU with 8 GB VRAM and about
16 GB system RAM. Repository/model claims alone cannot establish whether a
pipeline is stable, fast enough for the demo, or visibly better on this host.

> These host figures were correct on 2026-08-10 and are now out of date. The
> machine has since gained RAM and a second pagefile, and the GPU is a 3070
> Laptop rather than a 3070 Ti. See §Update (2026-08-19) below; the decision
> itself is unchanged.

## Decision

The deterministic `FakeVideoProvider` remains the only active adapter while it
proves Android/FastAPI integration. It is test evidence, never AI-quality
evidence.

The first real local video adapter will be selected only by experiment
`EXP-005`. The 2026-08-11 pre-screen produced two different outcomes:

- LTX-Video 2B distilled/Q8 is rejected for this host before weight download.
  Its official raw dependency/runtime path totals about 25.9 GB, its current
  documented Diffusers memory route is about 10 GB VRAM, and its accelerated
  Q8/FP8 path targets Ada while this laptop is Ampere with 8 GB VRAM.
- FramePack F1 remains an image-conditioned candidate only. The official
  Windows runtime and exact pinned model snapshots are installed and verified,
  but the first inference is blocked by failed physical RAM, VRAM and virtual-
  memory preflight plus unresolved downloaded-weight license metadata.
- The text-to-video profile is unselected; a replacement must pass the same
  version, resource, repeatability, latency, playback, quality and license gate.
- Neither name appears as a guaranteed product capability until it passes the
  recorded resource, repeatability, latency, playback, and quality thresholds.

Paid providers remain an explicit later decision. Adding one requires a new
budget approval, current price/region verification, credential-safe setup, and
an opt-in integration test. It must not silently replace the free profile.

## Consequences

- The current demo is fully repeatable and does not depend on credits or a
  provider account.
- The application can honestly demonstrate job orchestration before claiming
  video-generation quality.
- A real local model may be rejected if the actual laptop cannot meet the
  thresholds; this is a valid experiment result, not an implementation bug.
- Large weight downloads and unsafe inference attempts can be rejected by a
  pinned manifest pre-screen when the documented minimum already exceeds the
  host envelope.
- FastAPI and Android remain provider-neutral, so a later accepted adapter does
  not change the mobile wire contract.
- Until EXP-005 passes, screenshots and test-pattern clips must be labelled as
  synthetic fake-provider output.

## Evidence gate

Use the procedure and pass/kill thresholds in
`docs/discovery/FREE-LOCAL-BEST-OUTPUT.md` section 8. Preserve model version,
source revision, file hashes, weight license, parameters, physical and virtual
memory measurements, two consecutive run results, H.264 playback proof, and
blind quality scores. The current pinned evidence lives in
`docs/experiments/EXP-005/MODEL_RUNTIME_MANIFEST.json`.

## Update — 2026-08-19: host recheck clears the FramePack blocker

Evidence: `docs/evidence/EXP-005_HOST_RECHECK_2026-08-19.md` (measurement only;
no inference has run).

The Context section above describes a host with about 16 GB system RAM and a
43.26 GiB commit limit, which is what made the FramePack F1 preflight
unreachable — the 48 GiB virtual-memory gate exceeded the machine's total.
Remeasured on 2026-08-19:

| Gate | 2026-08-11 | 2026-08-19 | Threshold |
|---|---:|---:|---:|
| Free physical RAM | 4.30 GiB | **12.81 GiB** | 6 GiB |
| Free VRAM | 5.96 GiB | **6.59 GiB** | 6 GiB |
| Free virtual memory | 14.62 GiB | **65.80 GiB** | 48 GiB |

System RAM is now 31.73 GiB and the commit limit 91.16 GiB, after a 44.92 GiB
pagefile was added on drive D. `scripts/check-exp005-preflight.ps1` reports
`"passed": true` on every check.

Two corrections to the Context above:

- The GPU is an **RTX 3070 Laptop**, not a 3070 Ti. FramePack's published
  timings reference a 3070 Ti laptop, so expect this host to be slower than
  that figure rather than equal to it.
- The system-RAM ceiling that excluded HunyuanVideo 1.5 as "high-risk" no
  longer describes this machine.

### What does not change

- **The decision stands.** `FakeVideoProvider` remains the only active adapter.
  A cleared preflight is permission to run EXP-005, not a selection: the
  version, hash, license, two-consecutive-run, playback and blind-quality gates
  in `FREE-LOCAL-BEST-OUTPUT.md` §8 are all still unmet.
- **LTX-Video 2B stays rejected.** That was a VRAM and architecture call —
  about 10 GiB documented and Ada-oriented acceleration against 8 GiB of
  Ampere. Neither RAM nor pagefile changes it.
- **Paid providers remain a separate budget decision** under the same terms as
  the original decision, and must not silently replace the free profile.
- **Output labelling is unchanged.** Until a candidate passes, clips remain
  synthetic fake-provider output and must be labelled as such.

### Residual risk

Free VRAM measured 6.59 GiB against a 6 GiB gate — a margin of 0.59 GiB. VRAM
is transient, and a browser or a running emulator can erase it. Remeasure
immediately before any run rather than relying on this record.

`scripts/check-exp005-preflight.ps1` sets `minimumFreeVirtualGiB` to `0` while
this ADR and `FREE-LOCAL-BEST-OUTPUT.md` §8 state 48 GiB. The measured 65.80
GiB clears the documented gate regardless, but the script and the documents
disagree and should be reconciled before the bake-off.
