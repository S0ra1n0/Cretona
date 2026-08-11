# EXP-005: zero-spend local video feasibility gate

**Current status:** Qwen text path passed. LTX was rejected at the documented
memory-envelope pre-screen without downloading weights. The official FramePack
Windows runtime and pinned model cache are installed, but inference is blocked
by the resource preflight. No local video model has been accepted or integrated.

This folder converts ADR-009 from a recommendation into an executable decision
gate. It deliberately separates four truths:

- desired: short text/reference-image video through FastAPI;
- designed: provider-neutral jobs; the former LTX Standard/FramePack Quality
  mapping is disconfirmed and profile names remain unassigned;
- implemented: fake video adapter plus real local Qwen prompt enhancement;
- observed: Qwen has run; LTX and FramePack have not.

## Fixed benchmark input

- `inputs/paper-dragon-lantern-city.png`: synthetic fictional source image;
- `inputs/reference-image-generation-prompt.txt`: exact prompt used to create it;
- `inputs/motion-prompt.txt`: fixed video motion/camera instruction;
- seed: `18426` where the runtime exposes deterministic seeding.

The image was generated specifically for this project with OpenAI's image tool.
It contains no real people, brands, text, or copied character. The committed
file hash is recorded in `EVIDENCE_LEDGER.yaml` after the asset is copied.

## Entry gate before any video inference

Run from the repository root:

```powershell
.\scripts\check-exp005-preflight.ps1
.\scripts\check-exp005-preflight.ps1 -Profile framepack
```

The command must pass immediately before every candidate run:

- AC power is present;
- at least 6 GiB free physical RAM;
- at least 6 GiB free GPU VRAM;
- at least 100 GiB free on drive D;
- for FramePack, at least 48 GiB free Windows virtual-memory headroom;
- no Ollama model remains loaded;
- one video worker and one generation at a time.

Abort if available physical RAM falls below 1 GiB, the OS becomes unstable,
CUDA reports OOM, or a time budget is exceeded. Do not close another person's
applications or terminate processes without their permission.

## Execution order

1. Preserve the source/model revision, file hashes, license status, dependency
   lock, command, and preflight result in `MODEL_RUNTIME_MANIFEST.json`.
2. Treat the LTX pre-screen result as a rejected candidate unless a new
   Ampere-safe manifest fits both the 8 GB VRAM and system-memory boundaries.
3. Run FramePack twice in fresh worker processes only after its profile
   preflight passes. Keep both attempt records, including a failure.
4. Verify each output with `ffprobe`, normalize to H.264 MP4 if needed, and
   prove playback in the foreground Cretona Android app.
5. Blind-score the clips with `QUALITY_SCORECARD.md`.
6. Accept FramePack only as an image-conditioned profile if every blocking
   budget passes. Do not claim that this solves text-only generation.
7. Select a separate text-only candidate or a locally generated-keyframe path
   through a new evidence gate.
8. Implement a FastAPI real-provider adapter only for an accepted profile.

The authoritative thresholds and measurement method are in
`PERFORMANCE_BUDGET_CONTRACT.json`. Evidence claims belong in
`EVIDENCE_LEDGER.yaml`; generated videos and large telemetry stay out of Git.
