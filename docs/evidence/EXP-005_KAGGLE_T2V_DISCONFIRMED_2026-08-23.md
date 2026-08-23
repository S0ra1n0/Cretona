# EXP-005 — text-to-video disconfirmed on free Kaggle, 2026-08-23

- **Document ID:** `CRETONA-EXP005-KAGGLE-001`
- **Mode:** Live model execution; **disconfirming result**
- **Observation date:** 2026-08-23
- **Host:** Kaggle, 2x NVIDIA T4 (14.56 GiB VRAM each), ~30 GB system RAM
- **Notebook:** `docs/experiments/EXP-005/EXP-005_T2V_bakeoff.ipynb`
- **Outcome:** **0 of 4 clips generated, in every configuration attempted.**

## 1. Claim tested

Whether a current open-weight text-to-video model can generate a clip on free
Kaggle hardware, as the compute half of the split architecture in
`KAGGLE-GPU-WORKER-PLAN.md`.

## 2. Result

It cannot. Two models, five configurations, zero clips.

**The binding constraint is system RAM, not VRAM.** This is the opposite of
the assumption the plan was built on, and it is why more VRAM did not help.

## 3. What was run

### HunyuanVideo-1.5 Diffusers 480p t2v

`hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_t2v`
@ `286be7ce72277246578a3e3cc2487e95ddae5bcf`, fp16, 61 frames, 50 steps.
Download 53.4 GB. Approx. 32 GB resident in fp16 — an 8.3B DiT plus a
Qwen2.5-VL-7B text encoder plus T5.

| # | Configuration | Failure |
|---|---|---|
| 1 | `enable_model_cpu_offload()` | Kernel killed by the RAM watchdog at ~90% of weight loading |
| 2 | `device_map="balanced"` | CUDA OOM at step 0. GPU 0 held 14.03 of 14.56 GiB in weights; a 200 MiB activation allocation failed |
| 3 | `device_map="balanced"` + `max_memory={0:"10GiB",1:"13GiB","cpu":"22GiB"}` | Kernel killed by the RAM watchdog at ~90% of weight loading. Capping GPU 0 pushed more to CPU, and CPU was the tighter resource |

### Wan2.1 T2V 1.3B

`Wan-AI/Wan2.1-T2V-1.3B-Diffusers` @ `0fad780a534b6463e45facd96134c9f345acfa5b`,
fp16 pipeline with fp32 VAE, UniPC `flow_shift=5.0`, 81 frames, 50 steps.
Download 28.4 GB.

**"1.3B" names the transformer only.** Wan2.1 pairs it with a UMT5-XXL text
encoder of roughly 11B parameters, so the pipeline is ~25 GB in fp16 — an
order of magnitude above what the parameter count suggests. Selecting this
model on the strength of "1.3B" was an error in
`FREE-LOCAL-BEST-OUTPUT.md` §3, which quotes a published 8.19 GB VRAM figure
that describes the transformer under offload, not the pipeline.

| # | Configuration | Failure |
|---|---|---|
| 4 | `pipe.to("cuda")` | CUDA OOM during load. 14.45 GiB allocated on GPU 0; a 12 MiB allocation failed |
| 5 | `enable_model_cpu_offload()` | `RuntimeError: CUBLAS_STATUS_ALLOC_FAILED when calling cublasCreate(handle)` |

## 4. The decisive observation

Configuration 5 failed with **both GPUs essentially empty**:

```
device map: None
  gpu0: 14.46 GiB free of 14.56 GiB
  gpu1: 14.46 GiB free of 14.56 GiB
attention backend: default (RuntimeError)
  FAILED: RuntimeError: CUDA error: CUBLAS_STATUS_ALLOC_FAILED
          when calling `cublasCreate(handle)`
```

29 GiB of VRAM idle, and cuBLAS could not allocate its handle. `cublasCreate`
needs pinned *host* memory; with ~25 GB of offloaded weights resident in a
~30 GB RAM budget, there was none to give.

**Reproduced on a freshly restarted kernel**, which rules out a CUDA context
poisoned by the earlier OOMs. The failure is structural, not incidental.

## 5. Why offloading cannot solve this

Every offload strategy trades VRAM for system RAM. On this host that trade has
nowhere to land:

| Resource | Available | Needed |
|---|---:|---|
| VRAM (2x T4) | 29.1 GiB | 25-32 GB, and not usable as one pool for a single transformer |
| System RAM | ~30 GB | the entire model, under any offload strategy, *plus* CUDA's own host allocations |

A model small enough to avoid offload entirely would fit. Neither candidate is.

## 6. Scope — what this does and does not disconfirm

Disconfirmed:

- HunyuanVideo 1.5 480p t2v on free Kaggle T4 x2.
- Wan2.1 T2V 1.3B on free Kaggle T4 x2.
- **Free Kaggle as the compute host** for a current local text-to-video
  pipeline. This is broader than either model and is the finding that matters.

**Not** disconfirmed:

- Either model on adequate hardware. This is a host result. A single 24 GB
  card, or 64 GB of system RAM, removes the constraint entirely.
- Either model quantized. fp8 or GGUF roughly halves the resident size and is
  the most plausible route back onto constrained hardware.
- Model quality. **No clip was produced, so nothing was scored.**
  `QUALITY_SCORECARD.md` remains empty and no quality claim may be made about
  either candidate in either direction.

## 7. Consequences

- **`KAGGLE-GPU-WORKER-PLAN.md` is blocked**, and its work items W1-W3 must not
  be started. The plan's premise was that Kaggle supplies compute the laptop
  cannot; that premise is now measured false. W4 (`del image_path`) is
  unaffected — it is app-side and needed by any provider.
- **ADR-009 is unchanged.** `FakeVideoProvider` remains the only active
  adapter, and clips remain synthetic fake-provider output.
- **`FREE-LOCAL-BEST-OUTPUT.md` §3 needs correcting**: it ranks candidates by
  VRAM alone. RAM is what actually decided this, and Wan2.1's row quotes a
  figure that describes the transformer rather than the pipeline.
- The 2026-08-19 host recheck stands. FramePack F1's preflight still passes on
  the laptop. Nothing here bears on it, and it remains the untested candidate.

## 8. Reopen only if

- a host with a single >=24 GB GPU, or >=64 GB system RAM, becomes available; or
- a version-pinned quantized checkpoint demonstrates resident size under 12 GB;
  or
- a text-to-video model is selected whose **whole pipeline**, text encoder
  included, is under 12 GB in fp16. Parameter counts in model names are not
  evidence of this — both errors above came from trusting one.
