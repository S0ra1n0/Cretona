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

The model adapter was verified against the official Diffusers documentation on
2026-08-19. If an argument name raises `TypeError`, re-check that page — the
pipeline is new and its API can still move.

**Before running:** Kaggle -> Settings -> Accelerator -> **GPU T4 x2**, and
Internet -> **On** (weights download at runtime).

The first run installs diffusers from git and pulls tens of GB of weights, on
the same GPU-hour quota as generation. Budget for it.

**Scope:** text-to-video only. Image-to-video waits on backend work item W4
(`del image_path` currently discards the reference image).
"""))

CELLS.append(md("## 1. Configuration"))

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
        # 81 frames at 16fps is the documented default: a ~5.1s clip, which
        # happens to match the app's 5s default almost exactly.
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

RUN_ID  = f"exp005-t2v-{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}"
OUT_DIR = pathlib.Path("/kaggle/working") / RUN_ID
RAW_DIR = OUT_DIR / "raw"        # named by prompt+seed; NOT for reviewers
BLIND_DIR = OUT_DIR / "blind"    # A1/A2/B1/B2; this is what gets scored
for d in (RAW_DIR, BLIND_DIR):
    d.mkdir(parents=True, exist_ok=True)

print("run id :", RUN_ID)
print("output :", OUT_DIR)
'''))

CELLS.append(md(r"""
## 2. Bench prompts

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

CELLS.append(md("## 3. Environment capture (for the evidence ledger)"))

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
## 4. Resource sampler

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
## 5. Model adapter

Verified 2026-08-19 against the official Diffusers pipeline documentation
(`huggingface.co/docs/diffusers/main/en/api/pipelines/hunyuan_video15`).
The API can still move between releases: if a call below raises `TypeError` on
an argument name, re-check that page first.

Everything else in this notebook talks to the model through one function:

```python
generate(prompt: str, seed: int, out_path: pathlib.Path) -> None
```

It must write a playable video file to `out_path`. Nothing outside this cell
knows which model is being used, so swapping in Wan2.1, LTX, or anything else
means editing only here.

**Four things that differ from a generic Diffusers pipeline.** Each is a
`TypeError` or an OOM if reverted:

1. `HunyuanVideo15Pipeline`, not `DiffusionPipeline`. Needs diffusers from git
   — the pipeline is newer than the last release.
2. **No `guidance_scale` argument.** It lives on a guider object; change it
   with `pipe.guider = pipe.guider.new(guidance_scale=...)`.
3. **`float16`, not `bfloat16`.** T4 and P100 are pre-Ampere with no usable
   bf16. The docs example assumes a newer card.
4. **`device_map="balanced"`, not `enable_model_cpu_offload()`.** The offload
   path is single-GPU and keeps the whole model in system RAM: ~32 GB in fp16
   against Kaggle's ~30 GB. It restarts the kernel mid-load, *after* the ~48 GB
   download is already spent. `balanced` spreads components across both T4s
   instead (~30 GB VRAM) and is faster besides.

**If it still runs out of memory**, the documented next step is group
offloading to disk rather than to RAM — replace the `device_map` entry with:

```py
pipe = HunyuanVideo15Pipeline.from_pretrained(MODEL_REPO, dtype=torch.float16)
pipe.transformer.enable_group_offload(
    onload_device=torch.device("cuda"),
    offload_device=torch.device("cpu"),
    offload_type="leaf_level",
    offload_to_disk_path="/kaggle/temp/offload",
)
```

That is slow, but it bounds system RAM instead of the model size dictating it.
"""))

CELLS.append(code(r'''
# ---------------------------------------------------------------------------
# Install. HunyuanVideo15Pipeline is newer than the last diffusers release, so
# this installs from git. Run once per session; it is slow.
# ---------------------------------------------------------------------------
# !pip install -q "git+https://github.com/huggingface/diffusers.git" transformers accelerate sentencepiece ftfy imageio imageio-ffmpeg safetensors
#
# ftfy is required by the Wan pipeline specifically.

import pathlib

_PIPE = None

def _load_wan21():
    """Wan2.1 T2V 1.3B. Verified against the Diffusers Wan pipeline docs."""
    import torch
    from diffusers import AutoModel, WanPipeline
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler

    rev = {"revision": MODEL_REVISION} if MODEL_REVISION else {}

    # The Wan VAE is loaded separately and stays float32 -- the docs are
    # explicit about it, and running it in fp16 degrades the decode.
    vae = AutoModel.from_pretrained(
        MODEL_REPO, subfolder="vae", dtype=torch.float32, **rev
    )
    # float16, not the bfloat16 in the docs example: T4 and P100 are
    # pre-Ampere and have no usable bf16.
    pipe = WanPipeline.from_pretrained(
        MODEL_REPO, vae=vae, dtype=torch.float16, **rev
    )
    pipe.scheduler = UniPCMultistepScheduler.from_config(
        pipe.scheduler.config, flow_shift=5.0
    )

    # NOT pipe.to("cuda"). The "1.3B" names the transformer only -- Wan2.1
    # pairs it with a UMT5-XXL text encoder of roughly 11B, so the pipeline
    # is about 25 GB in fp16 and downloads 28.4 GB. Moving all of it onto one
    # 14.56 GB card OOMs before the first step.
    #
    # Offload is what Wan's own documented example uses: the text encoder
    # stays in CPU RAM and only the active component occupies the GPU. It
    # costs speed, which the recorded latency reflects honestly.
    pipe.enable_model_cpu_offload()

    # AutoencoderKLWan supports neither tiling nor slicing; calling them raises.
    return pipe


def _load_hunyuan():
    """HunyuanVideo-1.5. Does not fit free Kaggle -- see the config cell.

    Left runnable for a 24 GB card or a quantized checkpoint. On 2x T4 every
    split failed: whole-model CPU offload exhausted RAM, plain balanced
    packed GPU 0 and died on activations, and capping GPU 0 pushed enough
    back to CPU to exhaust RAM again.
    """
    import torch
    from diffusers import HunyuanVideo15Pipeline

    kwargs = {
        "dtype": torch.float16,
        "device_map": "balanced",
        "max_memory": {0: "10GiB", 1: "13GiB", "cpu": "22GiB"},
    }
    if MODEL_REVISION:
        kwargs["revision"] = MODEL_REVISION

    pipe = HunyuanVideo15Pipeline.from_pretrained(MODEL_REPO, **kwargs)
    # No .to("cuda"): device_map already placed every component.
    pipe.vae.enable_tiling()
    return pipe


def load_model():
    """Load once and cache."""
    global _PIPE
    if _PIPE is not None:
        return _PIPE

    import torch

    _PIPE = _load_wan21() if MODEL_CHOICE == "wan21" else _load_hunyuan()

    try:
        print("device map:", _PIPE.hf_device_map)
    except Exception:
        pass

    # Free VRAM per card after loading. A card already near full here will
    # fail on activations whatever the prompt is -- better to see it now than
    # after a five minute load.
    try:
        for i in range(torch.cuda.device_count()):
            free_b, total_b = torch.cuda.mem_get_info(i)
            print(f"  gpu{i}: {free_b / 1024**3:.2f} GiB free of "
                  f"{total_b / 1024**3:.2f} GiB")
    except Exception:
        pass

    # The docs recommend `sage_hub` for GPUs that are not H100/A100/4090.
    # Needs sageattention installed; skipped cleanly when unavailable.
    try:
        _PIPE.transformer.set_attention_backend("sage_hub")
        print("attention backend: sage_hub")
    except Exception as ex:
        print(f"attention backend: default ({type(ex).__name__})")

    return _PIPE


def generate(prompt: str, seed: int, out_path: pathlib.Path) -> None:
    """Generate one clip. The only function the rest of the notebook calls."""
    import torch
    from diffusers.utils import export_to_video

    pipe = load_model()
    generator = torch.Generator(device="cuda").manual_seed(seed)

    call = {
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "num_frames": NUM_FRAMES,
        "num_inference_steps": STEPS,
        "generator": generator,
    }
    # Hunyuan takes guidance from a guider object and rejects the argument.
    if GUIDANCE is not None:
        call["guidance_scale"] = GUIDANCE
    if WIDTH and HEIGHT:
        call["height"], call["width"] = HEIGHT, WIDTH

    frames = pipe(**call).frames[0]
    export_to_video(frames, str(out_path), fps=FPS)

print("adapter ready — the model loads lazily on the first generate() call")
'''))

CELLS.append(md(r"""
## 6. Run the bake-off

4 clips: 2 prompts x 2 seeds. The two seeds per prompt are the *two consecutive
runs* the gate asks for — they show whether the model is repeatable or whether
one good clip was luck.

A failure is a result. If a run raises, it is recorded and the notebook
continues rather than losing the runs that did work.
"""))

CELLS.append(code(r'''
import traceback, hashlib

def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

RESULTS = []

for prompt_key, prompt_text in PROMPTS.items():
    for run_index, seed in enumerate(SEEDS, start=1):
        name = f"{prompt_key}{run_index}_seed{seed}.mp4"
        target = RAW_DIR / name
        print(f"\n=== prompt {prompt_key} | run {run_index} | seed {seed} ===")

        record = {
            "prompt_key": prompt_key, "run_index": run_index, "seed": seed,
            "file": name, "status": "failed",
        }
        try:
            with ResourceSampler() as rs:
                generate(prompt_text, seed, target)
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
        except Exception as ex:
            record["error"] = f"{type(ex).__name__}: {ex}"
            print("  FAILED:", record["error"])
            traceback.print_exc(limit=3)

        RESULTS.append(record)

ok = [r for r in RESULTS if r["status"] == "ok"]
print(f"\n{len(ok)}/{len(RESULTS)} clips generated")
(OUT_DIR / "results.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
'''))

CELLS.append(md(r"""
## 7. Playback proof

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
## 8. Blind relabel

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

CELLS.append(md("## 9. Ledger entry and summary"))

CELLS.append(code(r'''
ok = [r for r in RESULTS if r["status"] == "ok"]
_vram = [r["peak_vram_gib"] for r in ok if r.get("peak_vram_gib") is not None]
_ram  = [r["peak_ram_gib"] for r in ok if r.get("peak_ram_gib") is not None]
peak_vram = max(_vram) if _vram else "not measured"
peak_ram  = max(_ram) if _ram else "not measured"
times     = [r["seconds"] for r in ok if "seconds" in r]
avg       = round(sum(times) / len(times), 2) if times else None
all_h264  = bool(ok) and all(r.get("playable_h264") for r in ok)

# Resolution comes from ffprobe on a real output, not from the request: the
# checkpoint chooses its own when WIDTH/HEIGHT are left as None.
_dims = next((r.get("dims") for r in ok if r.get("dims")), None)
_res = _dims or (f"{WIDTH}x{HEIGHT}" if WIDTH and HEIGHT else "native resolution")
_secs = round(NUM_FRAMES / FPS, 1)

summary = (
    f"{len(ok)}/{len(RESULTS)} clips generated; "
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
    status: "{'passed' if ok and all_h264 else 'failed'}"
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
print(f"  H.264 playback     : {'yes' if all_h264 else 'NO'}")
print("  quality            : not measured here — blind scoring decides")
'''))

CELLS.append(md(r"""
## 10. Download before the session ends

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
## 11. After the run

1. **Download the archive from section 10** if you have not already. Kaggle
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
