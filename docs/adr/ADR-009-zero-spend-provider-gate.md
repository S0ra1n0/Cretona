# ADR-009: Gate the zero-spend video provider on local evidence

**Status:** Accepted · **Date:** 2026-08-10 · **Supersedes:** ADR-004

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
