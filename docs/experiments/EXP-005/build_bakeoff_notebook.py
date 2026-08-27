#!/usr/bin/env python3
"""Generate the EXP-005 T2V bake-off notebook.

The notebook is the artifact; this script exists so its JSON is always valid
and the cell contents stay reviewable as plain Python in version control.

Run:  python docs/experiments/EXP-005/build_bakeoff_notebook.py
Out:  docs/experiments/EXP-005/EXP-005_T2V_bakeoff.ipynb
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "EXP-005_T2V_bakeoff.ipynb"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip("\n").splitlines(True),
    }


CELLS: list[dict] = []

CELLS.append(md(r"""
# EXP-005 — text-to-video bake-off

Measures one text-to-video model against the EXP-005 gate on a Kaggle GPU.
**Nothing here is a selection.** It produces evidence; Bruce and S0ra1n0 score it.

**What this notebook does**

1. Captures the runtime environment in the `EVIDENCE_LEDGER.yaml` schema.
2. Generates **4 clips** — 2 prompts x 2 consecutive runs — sampling peak VRAM/RAM
   and wall-clock time throughout.
3. Verifies each output is real, playable H.264.
4. Relabels the clips **blind** (`A1 A2 B1 B2`) and writes the key to a
   separate file, so scoring cannot be biased by filenames.
5. Emits a ready-to-paste ledger entry.

The model adapters were verified against the official Diffusers documentation
on 2026-08-19. If an argument name raises `TypeError`, re-check that page —
these pipelines are new and their APIs can still move.

**Before running:** Kaggle -> Settings -> Accelerator -> **GPU T4 x2**, and
Internet -> **On** (weights download at runtime).

**Section 1 is the install and runs once per session.** Everything after it can
be re-run freely. The first run also pulls tens of GB of weights, on the same
GPU-hour quota as generation — budget for it.

Memory is the whole difficulty here, so section 6 splits the work in two: the
text encoder is loaded, used, and freed before the transformer is loaded at
all. Five configurations that held both at once all ran out of memory on
2026-08-23 (`docs/evidence/EXP-005_KAGGLE_T2V_DISCONFIRMED_2026-08-23.md`).

**Scope:** text-to-video only. The backend can now pass a reference image
through to a provider (work item W4, done 2026-08-23), but no image-to-video
model has been selected, so this notebook does not exercise that path.
"""))

CELLS.append(md(r"""
## 1. Install — run once per session

Separate from everything else so the rest of the notebook can be re-run freely
without reinstalling. **The pip line is commented out on purpose.**

- **First run in a session:** uncomment it, run this cell, wait, then comment it
  back out.
- **Every run after that:** skip this cell. Run All skips it too, since it does
  nothing while commented.

If the install upgrades a package that is already imported, restart the kernel
afterwards (**Run menu -> Restart kernel**, not the toolbar's Factory reset,
which would also wipe the downloaded weights).
"""))

CELLS.append(code(r'''
# Uncomment for the first run in a session, then comment it back out.
# HunyuanVideo15Pipeline and the Wan pipelines are newer than the last diffusers
# release, so diffusers comes from git. ftfy is required by Wan specifically.

# !pip install -q "git+https://github.com/huggingface/diffusers.git" transformers accelerate sentencepiece ftfy imageio imageio-ffmpeg safetensors

import importlib.util

_missing = [
    name
    for name in ("torch", "diffusers", "transformers", "accelerate", "ftfy", "imageio")
    if importlib.util.find_spec(name) is None
]
if _missing:
    print("MISSING:", ", ".join(_missing))
    print("Uncomment the pip line above and run this cell.")
else:
    import diffusers, torch

    print(f"torch      {torch.__version__}")
    print(f"diffusers  {diffusers.__version__}")
    print("dependencies present - leave the pip line commented")
'''))

CELLS.append(md("## 2. Configuration"))

CELLS.append(code(r'''
import os

# Must be set before torch initialises its CUDA allocator, i.e. before any
# other cell imports torch. Setting it later in a live session does nothing:
# the allocator reads it once. Fragmentation is what turns a 200 MiB
# allocation into an OOM on a card that reports 14.4 of 14.56 GiB in use.
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

import pathlib, datetime

# --- what is under test -----------------------------------------------------
# One switch. The harness below is model-agnostic; only the adapter branches.
#
#   "wan21"    Wan2.1 T2V 1.3B, Apache-2.0. The name is the transformer
#              only: with its UMT5-XXL text encoder the pipeline is ~25 GB in
#              fp16 and downloads 28.4 GB, so it needs CPU offload on a T4.
#              Still ~7 GB lighter than Hunyuan, which is the difference
#              between fitting and not.
#
#   "hunyuan"  HunyuanVideo-1.5 480p. Better quality rank, but ~32 GB in fp16
#              (8.3B DiT + Qwen2.5-VL-7B + T5) against 29 GB VRAM and ~30 GB
#              RAM. Disconfirmed on free Kaggle 2026-08-19: three
#              configurations, three different out-of-memory walls. Kept here
#              so it runs unchanged on a 24 GB card or a quantized checkpoint.
MODEL_CHOICE = "wan21"

PRESETS = {
    "wan21": {
        "label": "Wan2.1 T2V 1.3B",
        "repo": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        "revision": "0fad780a534b6463e45facd96134c9f345acfa5b",
        # Frame count must satisfy 4n+1: the Wan VAE compresses time by 4x, so
        # the latent length is (num_frames - 1) / 4 + 1 and only lands on a
        # whole number when num_frames - 1 divides by 4. 64 is not valid; 65 is.
        #
        #   49 -> 3.1s    65 -> 4.1s    81 -> 5.1s (documented default)
        #
        # 81 at 16fps = 5.06s, matching the app's 5s default. Roughly 16 min
        # per clip on a T4.
        "num_frames": 81,
        "fps": 16,
        "steps": 50,
        "guidance_scale": 5.0,
    },
    "hunyuan": {
        "label": "HunyuanVideo-1.5 Diffusers 480p t2v",
        "repo": "hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_t2v",
        "revision": "286be7ce72277246578a3e3cc2487e95ddae5bcf",
        # 61 rather than the pipeline default of 121: activation memory scales
        # with frame count. ~2.5s at 24fps, short of the app's 5s -- a real
        # deviation the ledger records rather than glosses over.
        "num_frames": 61,
        "fps": 24,
        "steps": 50,
        # Not a call argument on this pipeline; it lives on a guider object.
        "guidance_scale": None,
    },
}

_P = PRESETS[MODEL_CHOICE]
MODEL_LABEL    = _P["label"]
MODEL_REPO     = _P["repo"]
MODEL_REVISION = _P["revision"]
NUM_FRAMES     = _P["num_frames"]
FPS            = _P["fps"]
STEPS          = _P["steps"]
GUIDANCE       = _P["guidance_scale"]

# None lets the checkpoint use its native resolution. Forcing a size the
# checkpoint was not trained for asks it for something it cannot produce.
WIDTH, HEIGHT = None, None
SEEDS = [1234, 5678]   # two consecutive runs per prompt -> repeatability

# --- smoke test -------------------------------------------------------------
# True: both prompts, one seed each, 8 steps, 25 frames -- so TWO clips, and
# `distinct outputs: 2/2` is the correct result here, not 4/4. Both prompts are
# kept deliberately: one clip could not show whether the prompt reaches the
# model at all, which is the thing most worth checking cheaply.
#
# Roughly 3 minutes instead of 3.3 hours, exercising every line the full run
# does. Far too coarse to judge quality; never score it.
#
# Left True on purpose. A full run is measured at ~49 min per clip -- 3.3 GPU-
# hours of a ~30-hour weekly quota -- so flipping this is a deliberate act.
SMOKE_TEST = True

if SMOKE_TEST:
    STEPS = 8
    NUM_FRAMES = 25   # 4n+1 as above: 25 = 4*6+1
    SEEDS = [1234]
    print("*** SMOKE TEST: 2 clips, 8 steps, 25 frames. NOT scoreable. ***")

# --- resuming ---------------------------------------------------------------
# Leave empty for a fresh run. Paste a previous run id here to write into that
# directory again: clips already present are skipped, so a failure in clip 4
# does not cost the three that worked.
RESUME_RUN_ID = ""

# Shared negative prompt. Wan's own documented example uses one; Hunyuan
# accepts the same argument, so both benefit from suppressing the artefacts
# the quality rubric penalises.
NEGATIVE_PROMPT = (
    "bright tones, overexposed, static, blurred details, subtitles, "
    "worst quality, low quality, JPEG compression residue, ugly, deformed, "
    "disfigured, misshapen limbs, still picture, messy background, watermark, "
    "text, logo"
)

print(f"model  : {MODEL_LABEL}")
print(f"repo   : {MODEL_REPO}")
print(f"clip   : {NUM_FRAMES} frames at {FPS}fps = ~{NUM_FRAMES / FPS:.1f}s")

RUN_ID = RESUME_RUN_ID or (
    f"exp005-t2v{'-smoke' if SMOKE_TEST else ''}-"
    f"{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}"
)
OUT_DIR = pathlib.Path("/kaggle/working") / RUN_ID

# Survives between runs in a session, unlike OUT_DIR which is per-run. Holds
# the encoded prompts so phase 1 is paid for once.
CACHE_DIR = pathlib.Path("/kaggle/working/_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = OUT_DIR / "raw"        # named by prompt+seed; NOT for reviewers
BLIND_DIR = OUT_DIR / "blind"    # A1/A2/B1/B2; this is what gets scored
for d in (RAW_DIR, BLIND_DIR):
    d.mkdir(parents=True, exist_ok=True)

print("run id :", RUN_ID)
print("output :", OUT_DIR)
'''))

CELLS.append(md(r"""
## 3. Bench prompts

**Prompt A** is the canonical EXP-005 scene, rebuilt for text-to-video from
`inputs/reference-image-generation-prompt.txt` (scene) and
`inputs/motion-prompt.txt` (motion). The I2V benchmark hands the model the
reference image; text-to-video has to describe it, so both halves are inlined.

**Prompt B** is a *proposed* second case, added so the result is not a judgement
about one subject. Swap it for anything the team prefers — but change it
**before** the run, not after seeing the clips.
"""))

CELLS.append(code(r'''
PROMPT_A = (
    "A handcrafted origami paper dragon glides smoothly from left to right above "
    "a hilltop city of glowing paper lanterns at night. Its wings flap slowly once "
    "while lanterns drift upward and the camera makes a gentle forward dolly. "
    "Cinematic handcrafted paper-diorama style, crisp coherent geometry, warm "
    "lantern glow against a cool moonlit sky, stable horizon, 16:9 wide shot. "
    "One continuous shot; no cuts, no morphing, one dragon only, "
    "no text, no logos, no watermark."
)

PROMPT_B = (
    "A small wooden sailboat crosses a calm sea at dawn while the camera slowly "
    "orbits to the right. Gentle swells move under the hull and the sail luffs "
    "once in the breeze. Photorealistic, soft golden backlight, stable horizon, "
    "16:9 wide shot. One continuous shot; no cuts, no morphing, "
    "no text, no logos, no watermark."
)

PROMPTS = {"A": PROMPT_A, "B": PROMPT_B}

for key, text in PROMPTS.items():
    print(f"--- prompt {key} ({len(text)} chars) ---\n{text}\n")
'''))

CELLS.append(md("## 4. Environment capture (for the evidence ledger)"))

CELLS.append(code(r'''
import subprocess, sys, platform, json, shutil

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as ex:
        return f"<{type(ex).__name__}>"

ENV = {
    "captured_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
    "platform": platform.platform(),
    "python": sys.version.split()[0],
    "gpu": sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader"),
    "cpu_count": os.cpu_count(),
    "ffmpeg": (sh("ffmpeg -version") or "").splitlines()[0] if shutil.which("ffmpeg") else "MISSING",
}

try:
    import torch
    ENV["torch"] = torch.__version__
    ENV["cuda"] = torch.version.cuda
    ENV["gpu_torch"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO CUDA"
except Exception as ex:
    ENV["torch"] = f"<not importable: {ex}>"

total_ram_gib = None
try:
    import psutil
    total_ram_gib = round(psutil.virtual_memory().total / 1024**3, 2)
except Exception:
    pass
ENV["total_ram_gib"] = total_ram_gib

print(json.dumps(ENV, indent=2))
(OUT_DIR / "environment.json").write_text(json.dumps(ENV, indent=2), encoding="utf-8")

if "NO CUDA" in str(ENV.get("gpu_torch", "")) or not ENV["gpu"]:
    print("\n*** NO GPU DETECTED — set Accelerator to GPU in Kaggle settings. ***")
'''))

CELLS.append(md(r"""
## 5. Resource sampler

EXP-005 section 8 requires peak RAM/VRAM and wall-clock time per run. Peak is
sampled on a background thread, because the interesting number is the spike
during denoising, not the value before or after.
"""))

CELLS.append(code(r'''
import threading, time

class ResourceSampler:
    """Samples peak VRAM/RAM on a thread while a block of work runs."""

    def __init__(self, interval=0.5):
        self.interval = interval
        self.peak_vram_gib = 0.0
        self.peak_ram_gib = 0.0
        # None until a sample is actually taken. A sampler that could not
        # import its dependencies must report "not measured", never 0.0 --
        # a fabricated zero in the evidence ledger is worse than a gap.
        self.sampled = False
        self.unavailable = None
        self._stop = threading.Event()
        self._thread = None

    def _sample(self):
        try:
            import torch, psutil
        except Exception as ex:
            self.unavailable = f"{type(ex).__name__}: {ex}"
            return
        proc = psutil.Process()
        while not self._stop.is_set():
            try:
                if torch.cuda.is_available():
                    used = torch.cuda.memory_reserved() / 1024**3
                    self.peak_vram_gib = max(self.peak_vram_gib, used)
                self.peak_ram_gib = max(self.peak_ram_gib, proc.memory_info().rss / 1024**3)
                self.sampled = True
            except Exception:
                pass
            time.sleep(self.interval)

    def __enter__(self):
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except Exception:
            pass
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.perf_counter() - self.t0, 2)
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        try:
            import torch
            if torch.cuda.is_available():
                self.peak_vram_gib = max(self.peak_vram_gib,
                                         torch.cuda.max_memory_reserved() / 1024**3)
        except Exception:
            pass
        if self.sampled:
            self.peak_vram_gib = round(self.peak_vram_gib, 2)
            self.peak_ram_gib = round(self.peak_ram_gib, 2)
        else:
            # Explicitly unmeasured, so nothing downstream can mistake a
            # failed sampler for a real observation.
            self.peak_vram_gib = None
            self.peak_ram_gib = None
            print(f"  !! resource sampling unavailable ({self.unavailable}) "
                  f"-- peaks recorded as null, not zero")
        return False

print("sampler ready")
'''))

CELLS.append(md(r"""
## 6. Model adapter — two phases

Every out-of-memory failure on 2026-08-23 came from holding the text encoder
and the transformer at the same time. For Wan2.1 that is a ~22 GB UMT5-XXL
encoder next to a 2.6 GB transformer; the encoder is two thirds of the
pipeline and it runs **once**, before the first denoising step.

So it is never loaded next to the transformer here:

| Phase | Loads | Frees |
|---|---|---|
| 1 | text encoder + tokenizer | encoder, before phase 2 starts |
| 2 | transformer + VAE, `text_encoder=None` | — |

Peak memory becomes `max(encoder, transformer)` rather than their sum. The
pipeline accepts `prompt_embeds` in place of `prompt`, which is what makes the
split possible without touching the model.

Phase 1 puts the encoder on GPU when both cards are visible (~29 GB of VRAM,
plenty) and falls back to CPU otherwise. Phase 2 needs one card and very
little of it.
"""))

CELLS.append(code(r'''
import gc
import pathlib


def _free() -> None:
    """Drop anything unreferenced and hand the VRAM back."""
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def _report_memory(tag: str) -> None:
    import torch

    try:
        parts = []
        for i in range(torch.cuda.device_count()):
            free_b, total_b = torch.cuda.mem_get_info(i)
            parts.append(f"gpu{i} {free_b / 1024**3:.1f}/{total_b / 1024**3:.1f} GiB free")
        ram = ""
        try:
            import psutil

            ram = f" | ram {psutil.virtual_memory().available / 1024**3:.1f} GiB free"
        except Exception:
            pass
        print(f"  [{tag}] " + ", ".join(parts) + ram)
    except Exception:
        pass


# --- phase 1 ---------------------------------------------------------------

def _embeds_cache_path(prompts: dict, negative: str) -> pathlib.Path:
    """A cache file keyed by everything that changes the embeddings."""
    import hashlib

    material = "|".join([MODEL_REPO, MODEL_REVISION, negative]
                        + [f"{k}={v}" for k, v in sorted(prompts.items())])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"embeds-{digest}.pt"


def encode_all_prompts(prompts: dict, negative: str) -> dict:
    """Encode every prompt, then free the text encoder before returning.

    Returns {key: (prompt_embeds, negative_prompt_embeds)} as CPU tensors.
    They are small -- a sequence of hidden states, not weights -- so keeping
    all of them costs far less than keeping the encoder that made them.

    Cached to disk. Loading a 22.7 GB encoder to re-encode two unchanged
    prompts costs five minutes and buys nothing; the cache key covers the
    model, the revision and the prompt text, so editing a prompt invalidates
    it automatically.
    """
    import torch

    cache = _embeds_cache_path(prompts, negative)
    if cache.exists():
        print(f"[phase 1] SKIPPED -- reusing {cache.name}")
        loaded = torch.load(cache, map_location="cpu")
        for key in sorted(loaded):
            print(f"  cached {key}: {tuple(loaded[key][0].shape)}")
        return loaded

    if MODEL_CHOICE != "wan21":
        raise NotImplementedError(
            "Two-phase encoding is wired for wan21. The Hunyuan pipeline takes "
            "four embedding tensors rather than two; see its __call__ signature."
        )

    from diffusers import WanPipeline

    rev = {"revision": MODEL_REVISION} if MODEL_REVISION else {}

    print("[phase 1] loading text encoder only")

    # Drop whatever a previous attempt left resident before measuring. Phase 1
    # no longer needs the GPU, but phase 2 does, and a card still holding an
    # earlier encoder is worth seeing in the line below.
    _free()
    _report_memory("before")

    # Phase 1 runs on the CPU, deliberately.
    #
    # The encoder is ~22.7 GB and a T4 is 14.6 GB, so it never fits on one
    # card. Splitting it across both with device_map="balanced" does fit the
    # weights, but balanced claims all available VRAM by default and leaves
    # nothing for activations or cuBLAS handles -- both cards end at zero free
    # and the first matmul dies with CUBLAS_STATUS_ALLOC_FAILED.
    #
    # RAM has room the GPUs do not, this runs once for a handful of prompts,
    # and it is immune to anything a previous attempt left resident on a card.
    # Slower, and worth it.
    #
    # bfloat16 rather than float16: CPU fp16 matmul support is patchy and
    # raises "addmm_impl_cpu_ not implemented for 'Half'" on some builds,
    # while bf16 is supported. Same memory either way.
    device = "cpu"
    pipe = WanPipeline.from_pretrained(
        MODEL_REPO, transformer=None, dtype=torch.bfloat16, **rev
    )
    _report_memory("encoder loaded (cpu)")

    # Repair the tied embedding.
    #
    # The load report prints:
    #     encoder.embed_tokens.weight | MISSING | newly initialized
    # while `shared.weight` loads fine. UMT5 ties those two, but the tie is
    # not re-applied here, so embed_tokens keeps random values and every token
    # embeds to noise. The model then denoises toward the dataset mean: a flat
    # grey clip, identical for every prompt, which is what the 2026-08-23 run
    # produced four of.
    te = getattr(pipe, "text_encoder", None)
    try:
        if te is not None and hasattr(te, "shared") and hasattr(te, "encoder"):
            shared_w = te.shared.weight
            embed_w = te.encoder.embed_tokens.weight
            if embed_w.data_ptr() != shared_w.data_ptr():
                te.encoder.embed_tokens.weight = shared_w
                print("  tied encoder.embed_tokens.weight -> shared.weight")
            else:
                print("  embed_tokens already tied")
    except Exception as ex:
        print(f"  could not inspect the embedding tie ({type(ex).__name__})")

    # Self-test before spending an hour of GPU time.
    #
    # The 2026-08-23 run produced two distinct clips from four, because both
    # prompts reached the transformer as the same embedding -- the output
    # tracked the seed and nothing else. That is indistinguishable from
    # success in every log line the harness prints, so it is checked here
    # instead: two obviously unrelated strings must not encode alike.
    probe_a, _ = pipe.encode_prompt(
        prompt="a red cube on a table",
        negative_prompt="",
        do_classifier_free_guidance=True,
        device=torch.device(device),
        dtype=torch.bfloat16,
    )
    probe_b, _ = pipe.encode_prompt(
        prompt="an astronaut riding a horse on mars",
        negative_prompt="",
        do_classifier_free_guidance=True,
        device=torch.device(device),
        dtype=torch.bfloat16,
    )
    # Measure only where there is content. Both prompts pad to
    # max_sequence_length (226), and short prompts leave most of that identical
    # -- averaging over the padding drags the number toward zero and makes a
    # healthy encoder look broken. 0.001976 on 2026-08-26 was exactly this.
    _a, _b = probe_a.float()[0], probe_b.float()[0]
    _live = (_a.abs().sum(-1) > 1e-6) | (_b.abs().sum(-1) > 1e-6)
    delta_all = (_a - _b).abs().mean().item()
    delta = (_a[_live] - _b[_live]).abs().mean().item() if int(_live.sum()) else 0.0
    _cos = torch.nn.functional.cosine_similarity(
        _a[_live].flatten(), _b[_live].flatten(), dim=0
    ).item() if int(_live.sum()) else 1.0
    print(f"  encoder self-test: {int(_live.sum())}/{_a.shape[0]} positions carry content")
    print(f"    mean |A-B| over content : {delta:.6f}   <-- the number that matters")
    print(f"    mean |A-B| incl padding : {delta_all:.6f}   (diluted, ignore)")
    print(f"    cosine similarity       : {_cos:.6f}   (1.0 would mean identical)")
    if _cos > 0.999:
        raise RuntimeError(
            f"the text encoder returns near-identical embeddings for unrelated "
            f"prompts (cosine {_cos:.6f}), so nothing downstream can be "
            f"prompt-driven. Check the UMT5 load report above for a MISSING "
            f"weight -- a randomly initialised or zeroed embed_tokens produces "
            f"exactly this."
        )
    del probe_a, probe_b

    out = {}
    for key, text in prompts.items():
        pos, neg = pipe.encode_prompt(
            prompt=text,
            negative_prompt=negative,
            do_classifier_free_guidance=True,
            device=torch.device(device),
            dtype=torch.bfloat16,
        )
        # Cast to fp16 for phase 2, which runs the transformer in fp16, and
        # keep them on the CPU so they pin no VRAM while it loads.
        out[key] = (pos.to("cpu", torch.float16), neg.to("cpu", torch.float16))
        print(f"  encoded {key}: {tuple(pos.shape)}")

    del pipe
    _free()
    _report_memory("encoder freed")

    # The bench prompts themselves must also be distinguishable, not just the
    # self-test pair.
    keys = sorted(out)
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            _x, _y = out[ka][0].float()[0], out[kb][0].float()[0]
            _lv = (_x.abs().sum(-1) > 1e-6) | (_y.abs().sum(-1) > 1e-6)
            d = (_x[_lv] - _y[_lv]).abs().mean().item() if int(_lv.sum()) else 0.0
            c = torch.nn.functional.cosine_similarity(
                _x[_lv].flatten(), _y[_lv].flatten(), dim=0
            ).item() if int(_lv.sum()) else 1.0
            print(f"  prompt {ka} vs {kb}: mean |diff| = {d:.6f}, cosine = {c:.6f}")
            if c > 0.999:
                raise RuntimeError(
                    f"prompts {ka} and {kb} encode identically; the clips "
                    f"would differ only by seed."
                )

    # Only cached once the checks above pass, so a broken encode is never
    # persisted and silently reused.
    torch.save(out, cache)
    print(f"  cached embeddings -> {cache.name}")
    return out


# --- phase 2 ---------------------------------------------------------------

_PIPE = None


def load_generator():
    """Load the transformer and VAE with no text encoder at all."""
    global _PIPE
    if _PIPE is not None:
        return _PIPE

    import torch
    from diffusers import AutoModel, WanPipeline
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler

    rev = {"revision": MODEL_REVISION} if MODEL_REVISION else {}

    print("[phase 2] loading transformer + vae, text_encoder=None")
    _report_memory("before")

    # The Wan VAE stays float32; the docs are explicit and fp16 degrades decode.
    vae = AutoModel.from_pretrained(
        MODEL_REPO, subfolder="vae", dtype=torch.float32, **rev
    )
    # text_encoder=None is the point of the exercise: ~22 GB never loads.
    pipe = WanPipeline.from_pretrained(
        MODEL_REPO,
        vae=vae,
        text_encoder=None,
        tokenizer=None,
        dtype=torch.float16,
        **rev,
    )
    pipe.scheduler = UniPCMultistepScheduler.from_config(
        pipe.scheduler.config, flow_shift=5.0
    )
    pipe.to("cuda")   # ~4 GB total; no offload needed once the encoder is gone

    _PIPE = pipe
    _report_memory("generator ready")
    return _PIPE


def generate_from_embeds(embeds, seed: int, out_path: pathlib.Path) -> None:
    """Generate one clip from pre-computed embeddings."""
    import torch
    from diffusers.utils import export_to_video

    pipe = load_generator()
    pos, neg = embeds
    generator = torch.Generator(device="cuda").manual_seed(seed)

    frames = pipe(
        prompt_embeds=pos.to("cuda"),
        negative_prompt_embeds=neg.to("cuda"),
        num_frames=NUM_FRAMES,
        num_inference_steps=STEPS,
        guidance_scale=GUIDANCE,
        generator=generator,
    ).frames[0]
    export_to_video(frames, str(out_path), fps=FPS)


print("adapter ready - phase 1 encodes, phase 2 generates, neither holds both")
'''))

CELLS.append(md(r"""
## 7. Prepare the run

Encodes the prompts and defines `run_one()`. Cheap and safe to re-run — phase 1
is cached, and `RESULTS` survives because this cell only creates it when it does
not already exist.

Three checkpoints keep a retry cheap:

| Checkpoint | Saves |
|---|---|
| `SMOKE_TEST = True` in section 2 | the whole run: ~3 min instead of ~3.3 h |
| Encoded prompts cached to disk | ~5 min of encoder loading per retry |
| Existing clips skipped | ~49 min per clip already generated |

Set `RESUME_RUN_ID` in section 2 to a previous run id to write into that same
directory, and any clip already there is left alone.
"""))

CELLS.append(code(r'''
import traceback, hashlib

def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

# Created once and kept. Re-running this cell must not discard clips that
# earlier cells already produced, so it is only initialised when absent.
try:
    RESULTS
except NameError:
    RESULTS = []

# Phase 1 for every prompt, once. If this fails there is no point loading the
# transformer, so it is deliberately outside the per-clip error handling.
EMBEDS = encode_all_prompts(PROMPTS, NEGATIVE_PROMPT)


def run_one(prompt_key: str, run_index: int, seed: int) -> None:
    """Generate exactly one clip.

    One clip per cell, deliberately. A single generation is ~49 minutes and a
    stray Ctrl-C or a browser hiccup takes the whole cell with it -- on
    2026-08-27 an interrupt during clip 4 ended a loop that had already spent
    2.6 hours on clips 1-3. Separate cells contain the blast radius to one clip,
    and the resume check below means even that one is usually recoverable.

    Idempotent: re-running a cell replaces that clip's record rather than
    appending a duplicate.
    """
    name = f"{prompt_key}{run_index}_seed{seed}.mp4"
    target = RAW_DIR / name
    print(f"=== prompt {prompt_key} | run {run_index} | seed {seed} ===")

    record = {
        "prompt_key": prompt_key, "run_index": run_index, "seed": seed,
        "file": name, "status": "failed",
    }

    def _store(rec):
        # Replace any earlier record for this file, then append.
        RESULTS[:] = [r for r in RESULTS if r.get("file") != name]
        RESULTS.append(rec)
        (OUT_DIR / "results.json").write_text(
            json.dumps(RESULTS, indent=2), encoding="utf-8"
        )

    # Resume. A clip that already exists is ten minutes already spent.
    if target.exists() and target.stat().st_size > 1024:
        record.update(
            status="ok",
            bytes=target.stat().st_size,
            sha256=sha256_of(target),
            reused=True,
        )
        print(f"  reused existing file ({record['bytes']:,} bytes)")
        _store(record)
        return

    try:
        with ResourceSampler() as rs:
            generate_from_embeds(EMBEDS[prompt_key], seed, target)
        record.update(
            status="ok",
            seconds=rs.seconds,
            peak_vram_gib=rs.peak_vram_gib,
            peak_ram_gib=rs.peak_ram_gib,
            bytes=target.stat().st_size,
            sha256=sha256_of(target),
        )
        print(f"  ok  {rs.seconds}s  peak VRAM {rs.peak_vram_gib} GiB  "
              f"peak RAM {rs.peak_ram_gib} GiB  {record['bytes']:,} bytes")
    except KeyboardInterrupt:
        # Named separately so an accidental stop reads as what it is, rather
        # than as a model or memory failure.
        record["error"] = "KeyboardInterrupt: run cancelled"
        print("  INTERRUPTED -- re-run this cell to retry just this clip")
        _store(record)
        raise
    except Exception as ex:
        record["error"] = f"{type(ex).__name__}: {ex}"
        print("  FAILED:", record["error"])
        traceback.print_exc(limit=3)

    _store(record)


def progress() -> None:
    done = [r for r in RESULTS if r["status"] == "ok"]
    want = len(PROMPTS) * len(SEEDS)
    print(f"  -> {len(done)}/{want} clips done so far")


print(f"ready: {len(PROMPTS)} prompts x {len(SEEDS)} seeds = "
      f"{len(PROMPTS) * len(SEEDS)} clips, one per cell below")
'''))

CELLS.append(md(r"""
## 8. Generate — one clip per cell

**Run these one at a time.** Each is **~49 minutes** at full settings
(measured 2901.9-2952.1 s on 2026-08-27). The four together are ~3.3 GPU-hours
of a ~30-hour weekly quota.

Interrupting a cell now costs only that clip; the finished ones are already on
disk and recorded. To retry one, just re-run its cell — the record is replaced
rather than duplicated, and `results.json` is rewritten after every clip so a
lost session still leaves the completed work behind.

In smoke mode there is one seed, so the `run 2` cells skip themselves.
"""))

for _pk in ("A", "B"):
    for _ri in (1, 2):
        CELLS.append(code(f'''
if len(SEEDS) >= {_ri}:
    run_one("{_pk}", {_ri}, SEEDS[{_ri - 1}])
    progress()
else:
    print("skipped: only {{}} seed(s) configured".format(len(SEEDS)))
'''))

CELLS.append(md(r"""
## 9. Playback proof

The gate requires H.264 playback proof. A file that exists is not a clip that
plays — this reads the actual stream with `ffprobe` and reports codec, duration
and resolution.
"""))

CELLS.append(code(r'''
def probe(path: pathlib.Path) -> dict:
    out = sh(f'ffprobe -v error -select_streams v:0 '
             f'-show_entries stream=codec_name,width,height,nb_frames,duration '
             f'-of json "{path}"')
    try:
        stream = json.loads(out)["streams"][0]
    except Exception:
        return {"codec_name": "UNREADABLE", "raw": out[:200]}
    return stream

print(f"{'file':28} {'codec':10} {'WxH':12} {'dur':>7}  playable")
for r in RESULTS:
    if r["status"] != "ok":
        continue
    info = probe(RAW_DIR / r["file"])
    codec = info.get("codec_name", "?")
    dims = f"{info.get('width','?')}x{info.get('height','?')}"
    dur = info.get("duration", "?")
    playable = codec.lower() in {"h264", "avc1"}
    r["codec"] = codec
    r["dims"] = dims if "?" not in dims else None
    r["playable_h264"] = playable
    print(f"{r['file']:28} {codec:10} {dims:12} {str(dur)[:6]:>7}  {'YES' if playable else 'NO'}")

if any(r.get("status") == "ok" and not r.get("playable_h264") for r in RESULTS):
    print("\nNote: not H.264. Re-encode before scoring so every reviewer sees "
          "the same thing:\n  ffmpeg -i in.mp4 -c:v libx264 -pix_fmt yuv420p out.mp4")
'''))

CELLS.append(md(r"""
## 10. Blind relabel

`QUALITY_SCORECARD.md` scores clips `A1 A2 B1 B2`, and section 8 requires
scoring **without model labels**. Filenames carrying the model name or seed
would leak that, so the clips are copied to neutral names and the mapping is
written to a separate key file.

**Give reviewers `blind/` only. Do not open the key until both have scored.**
"""))

CELLS.append(code(r'''
import shutil

key = {}
for r in RESULTS:
    if r["status"] != "ok":
        continue
    label = f"{r['prompt_key']}{r['run_index']}"          # A1, A2, B1, B2
    shutil.copy2(RAW_DIR / r["file"], BLIND_DIR / f"{label}.mp4")
    key[label] = {
        "model": MODEL_LABEL, "repo": MODEL_REPO, "revision": MODEL_REVISION or None,
        "prompt_key": r["prompt_key"], "seed": r["seed"],
        "seconds": r.get("seconds"), "peak_vram_gib": r.get("peak_vram_gib"),
        "sha256": r.get("sha256"),
    }

(OUT_DIR / "BLIND_KEY.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
print("blind clips :", sorted(p.name for p in BLIND_DIR.glob("*.mp4")))
print("key written :", OUT_DIR / "BLIND_KEY.json", "(do not open until scored)")
'''))

CELLS.append(md("## 11. Ledger entry and summary"))

CELLS.append(code(r'''
ok = [r for r in RESULTS if r["status"] == "ok"]
_vram = [r["peak_vram_gib"] for r in ok if r.get("peak_vram_gib") is not None]
_ram  = [r["peak_ram_gib"] for r in ok if r.get("peak_ram_gib") is not None]
peak_vram = max(_vram) if _vram else "not measured"
peak_ram  = max(_ram) if _ram else "not measured"
times     = [r["seconds"] for r in ok if "seconds" in r]
avg       = round(sum(times) / len(times), 2) if times else None
all_h264  = bool(ok) and all(r.get("playable_h264") for r in ok)

# Distinct outputs. Four files that are two videos is a failed experiment
# wearing a successful one's clothes: every count, timing and memory figure
# looks right while the prompts were never in play.
_digests = [r["sha256"] for r in ok if r.get("sha256")]
_distinct = len(set(_digests))
_all_distinct = _distinct == len(_digests) and bool(_digests)
if not _all_distinct:
    print(f"\n*** {_distinct} distinct clips from {len(_digests)} files ***")
    print("*** Identical outputs mean the prompts did not reach the model. ***")
    print("*** This run is NOT scoreable. Do not fill in the scorecard. ***\n")

# Resolution comes from ffprobe on a real output, not from the request: the
# checkpoint chooses its own when WIDTH/HEIGHT are left as None.
_dims = next((r.get("dims") for r in ok if r.get("dims")), None)
_res = _dims or (f"{WIDTH}x{HEIGHT}" if WIDTH and HEIGHT else "native resolution")
_secs = round(NUM_FRAMES / FPS, 1)

summary = (
    f"{len(ok)}/{len(RESULTS)} clips generated, {_distinct} distinct; "
    f"peak VRAM {peak_vram}{' GiB' if _vram else ''}; "
    f"peak RAM {peak_ram}{' GiB' if _ram else ''}; "
    f"mean {avg}s per {NUM_FRAMES}-frame clip; "
    f"H.264 playback {'verified' if all_h264 else 'NOT verified'}."
)

entry = f"""  - id: "EVD-EXP005-XXX"
    claim: "{MODEL_LABEL} generates a {NUM_FRAMES}-frame {_res} clip from text on a Kaggle GPU (~{_secs}s at {FPS}fps; the app default is 5s)."
    requirement_ids: ["FR-2.1"]
    decision_ids: ["DEC-004"]
    contract_ids: ["CRETONA-PERF-EXP-005"]
    task_ids: ["EXP-005-T2V"]
    evidence_type: "live model execution"
    observation_method: "Kaggle notebook EXP-005_T2V_bakeoff.ipynb, 2 prompts x 2 consecutive seeds."
    evidence_level: "observed runtime"
    tool_and_version: "{MODEL_LABEL}; torch {ENV.get('torch')}; cuda {ENV.get('cuda')}"
    policy_standard_or_target_revision: "{MODEL_REPO}@{MODEL_REVISION or 'UNPINNED — pin before selection'}"
    status: "{'passed' if ok and all_h264 and _all_distinct else 'failed'}"
    environment: "Kaggle; {ENV.get('gpu')}; {ENV.get('total_ram_gib')} GiB RAM"
    executed_at: "{datetime.datetime.now(datetime.UTC):%Y-%m-%d}"
    exit_code: {0 if len(ok) == len(RESULTS) else 1}
    result_summary: "{summary}"
    artifact_or_log: "{RUN_ID}/results.json, environment.json, BLIND_KEY.json, blind/*.mp4"
    executed_by: "Claude on Kaggle"
    independently_verified_by: null
"""

print(summary)
print()
print("--- paste into EVIDENCE_LEDGER.yaml (renumber the id) ---")
print(entry)
(OUT_DIR / "ledger_entry.yaml").write_text(entry, encoding="utf-8")

print("=== gate reference (EXP-005 section 8) ===")
print(f"  peak VRAM observed : {peak_vram}{' GiB' if _vram else ''}")
print(f"  peak RAM observed  : {peak_ram}{' GiB' if _ram else ''}")
print(f"  repeatable         : {'yes' if len(ok) == len(RESULTS) else 'NO — a run failed'}")
print(f"  distinct outputs   : {_distinct}/{len(_digests)}"
      f"{'' if _all_distinct else '  <-- prompts did not reach the model'}")
print(f"  H.264 playback     : {'yes' if all_h264 else 'NO'}")
print("  quality            : not measured here — blind scoring decides")
'''))

CELLS.append(md(r"""
## 12. Download before the session ends

`/kaggle/working` is **wiped when the session ends**. Nothing below is
recoverable afterwards, so run this cell and download the archive before you
stop the session or switch the accelerator off.

The archive holds everything the scoring step and the ledger need: the blind
clips, the key, the raw named clips, `results.json`, `environment.json` and
`ledger_entry.yaml`.
"""))

CELLS.append(code(r'''
import shutil
from IPython.display import FileLink, display

archive = shutil.make_archive(str(OUT_DIR), "zip", root_dir=OUT_DIR)
size_mib = round(pathlib.Path(archive).stat().st_size / 1024**2, 1)

print(f"archive : {archive}")
print(f"size    : {size_mib} MiB")
print()
print("contents:")
for item in sorted(OUT_DIR.rglob("*")):
    if item.is_file():
        rel = item.relative_to(OUT_DIR)
        print(f"  {str(rel):34} {item.stat().st_size:>12,} bytes")

print()
print("Click the link below, or use the Output panel in the right sidebar.")
print("Then stop the session -- idle time bills against the same GPU quota.")
display(FileLink(pathlib.Path(archive).name))
'''))

CELLS.append(md(r"""
## 13. After the run

1. **Download the archive from section 12** if you have not already. Kaggle
   wipes `/kaggle/working` when the session ends.
2. **Score the clips** in `QUALITY_SCORECARD.md`. Bruce and S0ra1n0 score
   independently, from `blind/` only, without opening the key.
3. **Reveal the key**, paste `ledger_entry.yaml` into `EVIDENCE_LEDGER.yaml`
   with the next free `EVD-EXP005-###`.
4. **Decide**, and record the decision either way:
   - clips clearly beat the current still-pan placeholder -> the Kaggle worker
     plan (`KAGGLE-GPU-WORKER-PLAN.md`) becomes worth building;
   - they do not -> record the disconfirming result and stop. A negative result
     is a valid outcome, not a failed experiment.

**Note on the rubric for text-to-video.** `QUALITY_SCORECARD.md` allots 20
points to *Reference consistency*, which assumes a reference image. There is no
reference in T2V, so score that dimension as **identity stability across the
clip** — does the dragon stay the same dragon from first frame to last — and
write that reading in the notes column so the I2V scores stay comparable.

**Still true regardless of the result:** nothing here changes the app. The
active provider is still `fake`, and clips remain synthetic fake-provider
output until a candidate passes the full gate (ADR-009).
"""))

notebook = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "accelerator": "GPU",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(f"wrote {OUT} ({len(CELLS)} cells)")
