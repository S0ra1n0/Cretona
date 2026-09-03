# EXP-007: image-to-video on free Kaggle with Wan2.2-TI2V-5B

**Status: written 2026-09-04, not yet run.** This is a gate, not a plan to
ship. Nothing in `kaggle_worker.py` changes until it passes.

## Why this is an experiment and not a task

Cretona already accepts a reference image: the Android picker, the multipart
upload, private Storage persistence, and the project image-condition reference
all exist and work. What does not exist is a model that reads that image. The
Kaggle worker runs **Wan2.1-T2V-1.3B**, which is text-only, so the uploaded
picture currently steers nothing — it is the gallery thumbnail fallback and
nothing more.

That gap cannot be closed by swapping a checkpoint. Wan2.1's image-to-video
variant exists only at **14B**, and Wan2.2's only at **A14B**. There is no Wan
I2V model below 5B in existence, so the smallest real candidate is
`Wan2.2-TI2V-5B` — a different model with a different VAE, a different frame
rate, and roughly four times the parameters of what runs today.

## Candidate

[`Wan-AI/Wan2.2-TI2V-5B-Diffusers`](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers)

| | |
|---|---|
| Licence | **apache-2.0** |
| Handles | text-to-video **and** image-to-video in one model |
| Transformer | 30 layers, 24 heads x 128, ffn 14336, `image_dim: null` |
| VAE | `AutoencoderKLWan`, **16x16x4** compression, `z_dim: 48` |
| Native frame rate | 24 fps |
| Diffusers pipeline | `WanImageToVideoPipeline`, `expand_timesteps: true` |

The licence is worth stating first, because the last experiment's answer was
awkward: MMAudio's checkpoints are CC-BY-NC and forbid commercial use.
Apache-2.0 carries no such condition.

### Weights, measured from the repository index

| Component | Bytes on disk | Stored as | On a T4 |
|---|---|---|---|
| `transformer` (5 shards) | 19,999,150,848 | fp32 | **10.0 GB in fp16, on GPU** |
| `text_encoder` UMT5-XXL (3 shards) | 11,361,820,672 | bf16 | 11.4 GB, **on CPU** |
| `vae` | 2,818,777,808 | fp32 | 2.8 GB, offloaded |
| **Download total** | **~34.2 GB** | | |

The text encoder is the *same* UMT5-XXL the Wan2.1 worker already loads on CPU
today, so its 11.4 GB lands in RAM, not VRAM, and its behaviour is proven.

## The "24 GB minimum" is a claim about a different configuration

The model card says the reference command needs **at least 24 GB (RTX 4090)**.
Read the command it belongs to:

```
--size 1280*704  --offload_model True  --convert_model_dtype  --t5_cpu
```

That is **720p, 121 frames, 24 fps** — a five-second 720p clip — and it already
has model offload, fp16 conversion, and CPU text encoding switched on. There is
no cheaper configuration hiding behind that number; those savings are spent.

What is *not* fixed is the resolution, and with a 16x spatial VAE the
resolution dominates. Sequence length after patchify is
`t_lat x (h_lat/2) x (w_lat/2)`:

| Configuration | Latent grid | Tokens |
|---|---|---|
| Reference 720p: 1280x704, 121 frames | 31 x 44 x 80 | **27,280** |
| Wan2.1-1.3B today: 832x480, 65 frames | 17 x 60 x 104 | **26,520** |
| Wan2.2-5B proposed: 832x480, 97 frames | 25 x 30 x 52 | **9,750** |

The middle row is the useful one. At Cretona's own resolution the 5B model
carries **fewer than half the tokens the 1.3B model already carries today**,
because its VAE compresses 16x spatially against Wan2.1's 8x. Attention cost
goes down as parameter count goes up, and those two move in opposite
directions.

So the honest position is: the 24 GB figure is real for 720p and says almost
nothing about 480p. Whether 480p fits in 15 GB is **unmeasured**, and measuring
it is the entire point of this experiment.

## Two facts that remove the two largest risks

**The pinned diffusers already supports this.** The model card says the I2V
path needs diffusers from source. That note is from August 2025 and is now
stale: `expand_timesteps` and the `first_frame_mask` branch are present in the
released `v0.35.0` **and** in `v0.36.0`, which is what
`backend/requirements-kaggle.txt` pins. **No dependency bump is required**, so
this experiment does not put the working video path at risk.

**No CLIP image encoder is needed.** `WanImageToVideoPipeline` calls
`encode_image` only when `transformer.config.image_dim is not None`. For
TI2V-5B it is `null`, and the repository ships no `image_encoder` folder. The
reference image goes through the VAE as a single frame — with
`expand_timesteps: true` the conditioning tensor is one frame, not a
zero-padded full-length video — so image conditioning costs almost nothing.

## The plan is the worker's existing plan

The worker already does what the model card recommends, and did it before this
model was relevant: `_encode_prompt` loads UMT5-XXL **on CPU** in bfloat16,
caches the embeddings to disk, frees the pipeline, and only then brings the
transformer up on the GPU in **float16**. That is `--t5_cpu` and
`--convert_model_dtype` by another name, already proven on this exact hardware.

EXP-007 keeps that shape and adds one lever the T2V path never needed:
`enable_model_cpu_offload()`, so the VAE is not resident during the 10 GB
transformer's denoising loop and the transformer is not resident during decode.

## Kill criteria — stop and record a negative result if any holds

1. **Any of cells 1-3 fails.** Under 40 GB free where Hugging Face caches
   (cell 1), pip moves torch (cell 2), or the installed diffusers has no
   `WanImageToVideoPipeline` / no `expand_timesteps` in its `__init__`
   (cell 3). All of it is checked before a single weight downloads.
2. **Peak VRAM exceeds ~14 GB** at 832x480 on a 15.36 GB T4, after the retry
   ladder in cell 6 has been walked down.
3. **One 4-second clip takes more than 25 minutes** of GPU time at 25 steps.
   Today's Wan2.1 job is ~20 minutes warm plus ~3 minutes of audio; a video
   step above 25 minutes pushes a job past half an hour and makes the app worse
   in exchange for image conditioning.
4. **The output ignores the reference image.** If frame 0 does not visibly
   descend from the uploaded picture, this is text-to-video with a longer
   download and there is nothing to ship.
5. **fp16 produces black or NaN frames.** The model card's own example uses
   bfloat16, which **Turing cannot do**. Wan2.1's transformer survives fp16 in
   production, but that is evidence about a different model. If Wan2.2-5B needs
   bf16, a T4 cannot run it and this ends here.

### The rule carried over from EXP-006

**Do not upgrade torch, and do not unpin diffusers, to make this run.** The
Wan2.1 worker depends on the CUDA build Kaggle ships and on
`diffusers==0.36.0`. Trading a proven video path for an unproven one is the
worst outcome available here — and it is worse in this experiment than in the
last one, because this one touches video rather than sitting beside it.

## Method

Run `EXP-007_wan22_i2v.ipynb` on Kaggle with a **T4** and Internet on. Attach
one still image as a private dataset. The notebook never touches Supabase,
never reads a Cretona secret, and writes only to `/kaggle/working`.

Cells are ordered cheapest-first, as in EXP-006. Cells 1-3 cost seconds and a
pip install, and can end the experiment before 34 GB moves; cell 5 is the first
download.

VRAM is sampled by a background thread reading `nvidia-smi` **during** the run.
EXP-006 learned this the hard way: `torch.cuda.max_memory_allocated()` reported
`0.00 GB` because it reads the calling process, and an `nvidia-smi` call after
the fact reads an idle card.

## Verdict

Not yet run. Fill the table in when it is, and record a negative result as
readily as a positive one.

| Kill criterion | Threshold | Measured | |
|---|---|---|---|
| 1. pipeline + disk | present, >= 40 GB free | | |
| 2. peak VRAM | <= ~14 GB | | |
| 3. time per clip | <= 1500 s | | |
| 4. follows the image | by eye, frame 0 | | |
| 5. fp16 stability | no black/NaN frames | | |

## What a pass does and does not authorise

A pass authorises **an integration decision**, not an integration. It would
still leave open:

- **Two models or one.** Keeping Wan2.1 for text-only jobs and adding
  Wan2.2-5B for image jobs means two large downloads in one Kaggle session.
  Replacing Wan2.1 entirely means one model for both paths, but re-validates
  every existing T2V behaviour against a model nobody here has measured.
- **Frame rate.** The worker exports at 16 fps and computes `duration * 16 + 1`
  frames. TI2V-5B is a 24 fps model. Either the contract changes or the clips
  play slow.
- **Cold-start cost.** A 34 GB download per Kaggle session is a new fixed cost
  on top of the ~28-minute cold first job measured for Wan2.1.

## If it fails

Record the negative result here the way
`docs/evidence/EXP-005_KAGGLE_T2V_DISCONFIRMED_2026-08-23.md` did, and say what the
reference image is for in the shipped product: a thumbnail and a stored
reference, not a conditioning signal. A documented boundary is worth more than
an undocumented one.

The next candidate down is **LTX-Video 2B distilled** — 6.34 GB of weights, so
memory is not its problem. Its problem is that the transformer is built for
**bfloat16** and Turing has none; reports of forcing fp16 describe getting
through the sampler and then running out of memory at VAE decode. It also ships
under a bespoke "LTX-Video Open Weights License" rather than a standard one.
Open it only if Wan2.2 dies on criterion 2, and open it knowing both problems
are live.
