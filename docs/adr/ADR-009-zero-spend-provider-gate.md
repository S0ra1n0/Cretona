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

The first real local adapter will be selected only by experiment `EXP-005`:

- LTX-Video 2B distilled/Q8 is the `LOCAL_STANDARD` candidate.
- FramePack F1 is the optional `LOCAL_QUALITY` challenger for image-conditioned
  generation.
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
- FastAPI and Android remain provider-neutral, so a later accepted adapter does
  not change the mobile wire contract.
- Until EXP-005 passes, screenshots and test-pattern clips must be labelled as
  synthetic fake-provider output.

## Evidence gate

Use the procedure and pass/kill thresholds in
`docs/discovery/FREE-LOCAL-BEST-OUTPUT.md` section 8. Preserve model version,
weight license, parameters, resource measurements, two consecutive run
results, H.264 playback proof, and blind quality scores.
