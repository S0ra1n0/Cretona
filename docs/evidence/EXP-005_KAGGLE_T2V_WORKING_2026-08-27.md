# EXP-005 — text-to-video generating on free Kaggle, 2026-08-27

- **Document ID:** `CRETONA-EXP005-KAGGLE-002`
- **Mode:** Live model execution
- **Observation date:** 2026-08-26 / 2026-08-27
- **Host:** Kaggle, 2x NVIDIA T4 (14.56 GiB VRAM each), ~31.3 GB system RAM
- **Model:** `Wan-AI/Wan2.1-T2V-1.3B-Diffusers`
  @ `0fad780a534b6463e45facd96134c9f345acfa5b`
- **Supersedes:** `EXP-005_KAGGLE_T2V_DISCONFIRMED_2026-08-23.md`

## 1. Result

**Free Kaggle generates real text-to-video.** The 2026-08-23 conclusion — that
the host could not run a current pipeline at all — was wrong. It was a
consequence of *how* the pipeline was loaded, not of the hardware.

Clips contain actual animated content, driven by the prompt. A full
scoreable run followed the same day: **4/4 distinct clips at 832x480, 81
frames, 5.06 s each — and 48.6 minutes of T4 time per clip.** See §5 and §8.

## 2. What made the difference: never hold both models at once

The text encoder is two thirds of the pipeline and runs **once**, before the
first denoising step. Every failed configuration on 2026-08-23 held it in
memory alongside the transformer.

| | Text encoder | Transformer | Peak |
|---|---:|---:|---:|
| Before (5 configs, all failed) | 22.7 GB | 2.8 GB | **~25 GB together** |
| Phase 1 | 22.7 GB (CPU) | — | 22.7 GB |
| Phase 2 | — | 2.8 GB + VAE (GPU) | **~4 GB** |

Peak becomes `max(component)` instead of `sum`. Phase 2 is then small enough
to sit on one card with a plain `.to("cuda")` — no offload, no `device_map`,
no `max_memory`. Every memory flag that failed became unnecessary rather than
better tuned.

`WanPipeline.__call__` accepts `prompt_embeds` in place of `prompt`, which is
what makes the split possible without touching the model.

**Phase 1 runs on CPU deliberately.** A 22.7 GB encoder does not fit a 14.6 GB
card, and `device_map="balanced"` — which does fit the weights across two
cards — claims all available VRAM and leaves nothing for cuBLAS handles, so
the first matmul dies with `CUBLAS_STATUS_ALLOC_FAILED` while both cards read
zero free. RAM has room the GPUs do not, and phase 1 is immune to anything a
previous attempt left resident on a card.

`bfloat16`, not `float16`, for the CPU encode: CPU fp16 matmul raises
`addmm_impl_cpu_ not implemented for 'Half'` on some builds. Same memory.

## 3. The second bug: silent, and worse than a crash

The first successful run produced **four files that were two videos**, each a
flat grey field. Every log line said success: `4/4 clips generated`,
`status: "passed"`, plausible timings and memory.

Root cause, from the load report the harness had been printing all along:

```
UMT5EncoderModel LOAD REPORT
encoder.embed_tokens.weight | MISSING | newly initialized
```

`shared.weight` loaded; `encoder.embed_tokens.weight` did not, and was left
randomly initialised rather than tied to it. Every token embedded to noise, so
the model received meaningless conditioning and denoised toward the dataset
mean — a featureless grey clip, identical for every prompt.

**Fix:** re-point `encoder.embed_tokens.weight` at `shared.weight` after
loading, guarded by a `data_ptr()` comparison so it is a no-op when the tie
already holds.

This warning was visible in three separate runs and dismissed as benign each
time. The lesson is recorded in §6.

## 4. Measuring the fix: a metric that lied

The self-test added to catch bug §3 compares two unrelated prompts. It first
reported `mean |A-B| = 0.001976` — alarmingly close to the zero that means
"broken".

It was not broken. Both prompts pad to `max_sequence_length` (226), and only
**120 of 226 positions carry content**; averaging over 106 identical padding
rows drags the mean toward zero regardless of how different the real content
is. Measured on content positions only:

| Metric | Value | Reading |
|---|---:|---|
| mean \|diff\| including padding | 0.038872 | diluted, misleading |
| mean \|diff\| over content | 0.073210 | healthy |
| **cosine similarity** | **0.153194** | strongly different (1.0 = identical) |

The self-test now excludes padding and gates on **cosine > 0.999** rather than
a diluted mean. A threshold measured over the wrong population is a test that
fails safe in the wrong direction.

## 5. Verified numbers

From the full run of 2026-08-27, `EVD-EXP005-011` — **50 steps, 81 frames**:

| | |
|---|---|
| Clips generated | 4/4, **4 distinct digests** |
| Time per clip | **2901.9 – 2952.1 s, mean 2918.8 s (48.6 min)** |
| GPU time for the set | 11675.3 s (3.24 h) |
| Peak VRAM | **12.45 GiB** |
| Peak RAM | **29.13 GiB of 31.35 available** |
| Resolution / length | 832x480, 81 frames, 5.063 s at 16 fps, avc1 |
| Encoder self-test cosine | 0.153194 |

> **Correction.** This table previously read *~10.4 min per clip, peak
> 13.2–13.6 GiB VRAM, 19.4–25.7 GiB RAM*, and described those as verified.
> They were taken at **50 frames**, and from the run §3 shows was invalidated
> by the grey-clip bug — the same run that produced four files that were two
> videos. Both facts were already stated in §6; §5 contradicted them.
>
> Going 50 → 81 frames is **1.62x the frames for 4.7x the time**. Full 3D
> attention is superlinear in frame count, so *clip length*, not step count, is
> the dominant latency lever. Any estimate derived from the old figure is
> low by roughly 5x.

Generation is slow because a T4 is roughly a fifth of a current card and the
`sage_hub` attention backend is unavailable. That is the honest cost of
zero-spend hardware, recorded rather than hidden.

## 6. What this changes, and what it does not

**Changes:**

- `KAGGLE-GPU-WORKER-PLAN.md` is **unblocked**. Its premise — that Kaggle can
  supply compute the laptop cannot — is now demonstrated rather than assumed.
- `EXP-005_KAGGLE_T2V_DISCONFIRMED_2026-08-23.md` is superseded. Its
  measurements stand; its conclusion does not.

**Does not change:**

- **No quality claim.** A full run with `distinct outputs: 4/4` now exists
  (§8), so the *precondition* for scoring is met — but nothing has been scored.
  `QUALITY_SCORECARD.md` stays empty until both reviewers fill it blind. The
  model is `unverified`, not `passed`, on quality.
- **ADR-009 holds.** `FakeVideoProvider` is still the only active adapter, and
  app output remains synthetic until a candidate passes the full gate.
- HunyuanVideo 1.5 remains rejected for this host: its transformer alone is
  ~16.6 GB in fp16, above a single T4, so the two-phase split does not rescue
  it. Reopening still needs a 24 GB card or a quantized checkpoint.

## 7. Lessons worth keeping

1. **A load-time warning naming a missing weight is not noise.** Dismissed
   three times; it was the whole bug.
2. **A metric averaged over padding understates difference.** Measure where
   the content is.
3. **"It ran and produced files" is not "it worked."** The harness now checks
   distinct output digests and refuses to record `passed` otherwise — four
   files that are two videos previously reported as a clean pass.
4. **Parameter counts in model names describe the transformer, not the
   pipeline.** Wan2.1 "1.3B" downloads 28.4 GB because of an ~11B text
   encoder. Both model-size errors this week came from trusting a name.

## 8. The full scoreable run — 2026-08-27

`SMOKE_TEST = False`, one clip per notebook cell, embeddings reused from the
smoke test. Session 10:47Z – 14:41Z. Ledger entry `EVD-EXP005-011`.

| Clip | Seed | Seconds | Peak VRAM | Peak RAM | Bytes |
|---|---:|---:|---:|---:|---:|
| A1 | 1234 | 2952.10 | 12.39 | 29.13 | 347,446 |
| A2 | 5678 | 2901.86 | 12.45 | 25.58 | 454,827 |
| B1 | 1234 | 2902.60 | 12.45 | 25.40 | 784,535 |
| B2 | 5678 | 2918.72 | 12.45 | 25.33 | 769,231 |

All four digests differ, so the cell-20 duplicate check passes and the run is
scoreable. Verified independently off Kaggle by parsing the MP4 containers
directly: every file is `avc1`, 832x480, 81 frames, 5.063 s at 16 fps, with no
near-empty frames. Prompt B compresses to roughly twice the bytes per frame of
prompt A — consistent with genuinely different content, and the opposite of the
flat-grey failure mode, which compresses to almost nothing.

### What the timing costs the plan

| | |
|---|---|
| Per 5-second clip | 48.6 min |
| Free Kaggle quota | ~30 GPU-hours/week |
| **Clips per week, whole team** | **~37** |
| RAM headroom at peak | ~2.2 GiB of 31.35 |
| `poll_lease_seconds` default / ceiling | 120 s / 3600 s |

Two consequences, both recorded in `KAGGLE-GPU-WORKER-PLAN.md`:

1. **The lease must be renewed on a timer.** A 2918 s job against a 120 s
   default lease is re-claimed about 24 times; even the 3600 s ceiling leaves
   only ~11 minutes of margin over the slowest clip observed.
2. **48.6 min exceeds `PB-FRAMEPACK-LATENCY` (1800 s) by 62%.** That budget is
   written for the local FramePack path, so this is an *unbudgeted* workload
   rather than a recorded breach — but the contract has no Kaggle T2V latency
   budget, and one should be written before W3 rather than after.

The obvious lever is clip length. 50 frames (3.1 s) ran at ~10 min; 81 frames
(5.06 s) runs at ~49 min. Whether a 3-second clip is acceptable for the demo is
a product decision, not a measurement, and is left to Bruce and S0ra1n0.
