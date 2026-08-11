# EXP-005: zero-spend local video feasibility gate

**Current status:** Qwen text path passed; video path blocked by the resource
preflight. No local video model has been accepted or integrated.

This folder converts ADR-009 from a recommendation into an executable decision
gate. It deliberately separates four truths:

- desired: short text/reference-image video through FastAPI;
- designed: provider-neutral jobs with LTX Standard and optional FramePack Quality;
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
```

The command must pass immediately before every candidate run:

- AC power is present;
- at least 6 GiB free physical RAM;
- at least 6 GiB free GPU VRAM;
- at least 100 GiB free on drive D;
- no Ollama model remains loaded;
- one video worker and one generation at a time.

Abort if available physical RAM falls below 1 GiB, the OS becomes unstable,
CUDA reports OOM, or a time budget is exceeded. Do not close another person's
applications or terminate processes without their permission.

## Execution order

1. Preserve the exact LTX model revision, file manifest, license, dependency
   lock, command, and preflight result.
2. Run LTX twice in fresh worker processes. Keep both attempt records, including
   a failure.
3. Verify each output with `ffprobe`, normalize to H.264 MP4 if needed, and
   prove playback in the foreground Cretona Android app.
4. Blind-score the clips with `QUALITY_SCORECARD.md`.
5. Accept LTX as `LOCAL_STANDARD` only if every blocking budget passes.
6. Only then repeat the process for FramePack. Retain it as `LOCAL_QUALITY` only
   if it completes within 30 minutes and beats Standard by at least 8 points.
7. Implement a FastAPI real-provider adapter only for an accepted profile.

The authoritative thresholds and measurement method are in
`PERFORMANCE_BUDGET_CONTRACT.json`. Evidence claims belong in
`EVIDENCE_LEDGER.yaml`; generated videos and large telemetry stay out of Git.
