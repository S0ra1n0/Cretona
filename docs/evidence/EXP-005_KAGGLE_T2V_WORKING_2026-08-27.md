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

Clips contain actual animated content, driven by the prompt. Roughly
10 minutes per clip at 50 frames / 50 steps.

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

| | |
|---|---|
| Clips generated | 4/4 |
| Time per clip | ~10.4 min (50 frames, 50 steps) |
| Peak VRAM | 13.2 – 13.6 GiB |
| Peak RAM | 19.4 – 25.7 GiB |
| Resolution | 832x480, native |
| Encoder self-test cosine | 0.153194 |

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

- **No quality claim.** The runs so far were smoke tests or invalidated by the
  grey-clip bug. `QUALITY_SCORECARD.md` stays empty until a full run with
  `distinct outputs: 4/4` is scored blind by both reviewers.
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
