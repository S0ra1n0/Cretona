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

**One cell needs your attention: `[VERIFY]  Model adapter`.**
Everything else is standard Python and should run as-is. The model's install
and inference API changes between releases, so that cell must be reconciled
against the current official model card before the first run.

**Before running:** Kaggle -> Settings -> Accelerator -> GPU, and Internet -> On.

**Scope:** text-to-video only. Image-to-video waits on backend work item W4
(`del image_path` currently discards the reference image).
"""))

CELLS.append(md("## 1. Configuration"))

CELLS.append(code(r'''
import os, pathlib, datetime

# --- what is under test -----------------------------------------------------
MODEL_LABEL    = "HunyuanVideo-1.5"     # free text, recorded in the ledger
MODEL_REPO     = "tencent/HunyuanVideo-1.5"  # VERIFY against the model card
MODEL_REVISION = ""                     # pin a commit/revision; "" = unpinned

# --- generation settings ----------------------------------------------------
NUM_FRAMES   = 121          # ~5s at 24fps; match the app's 5s default
FPS          = 24
WIDTH, HEIGHT = 1280, 720   # 16:9, the app's default aspect ratio
SEEDS        = [1234, 5678] # two consecutive runs per prompt -> repeatability

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
## 5. `[VERIFY]` Model adapter

**This is the cell to reconcile against the official model card before running.**

Everything else in this notebook talks to the model through one function:

```python
generate(prompt: str, seed: int, out_path: pathlib.Path) -> None
```

It must write a playable video file to `out_path`. Nothing outside this cell
knows which model is being used, so swapping in Wan2.1, LTX, or anything else
means editing only here.

Install and inference APIs move between releases, and a wrong guess costs a GPU
session. Check the current model card for: the package/version to install, the
pipeline class, the argument names, and whether the output needs a separate
encode step.
"""))

CELLS.append(code(r'''
# ---------------------------------------------------------------------------
# [VERIFY] Install. Confirm package names/versions on the official model card.
# ---------------------------------------------------------------------------
# !pip install -q "diffusers>=0.36" transformers accelerate imageio imageio-ffmpeg safetensors

import pathlib

_PIPE = None

def load_model():
    """Load once and cache. VERIFY the pipeline class and loading arguments."""
    global _PIPE
    if _PIPE is not None:
        return _PIPE

    import torch
    # ---- VERIFY BLOCK -----------------------------------------------------
    # The class name below is a placeholder. Replace with the pipeline the
    # model card documents, and keep the memory-saving calls that apply.
    from diffusers import DiffusionPipeline  # noqa: F401

    kwargs = {"torch_dtype": torch.float16}
    if MODEL_REVISION:
        kwargs["revision"] = MODEL_REVISION

    pipe = DiffusionPipeline.from_pretrained(MODEL_REPO, **kwargs)
    pipe = pipe.to("cuda")
    # Kaggle GPUs are 16 GB-class; enable offload only if you hit OOM, since it
    # slows generation considerably and distorts the latency measurement.
    # pipe.enable_model_cpu_offload()
    if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
        pipe.vae.enable_tiling()
    # ---- END VERIFY BLOCK -------------------------------------------------

    _PIPE = pipe
    return _PIPE


def generate(prompt: str, seed: int, out_path: pathlib.Path) -> None:
    """Generate one clip. The only function the rest of the notebook calls."""
    import torch
    pipe = load_model()
    generator = torch.Generator(device="cuda").manual_seed(seed)

    # ---- VERIFY BLOCK -----------------------------------------------------
    # Argument names vary by pipeline (num_frames / video_length / frames).
    result = pipe(
        prompt=prompt,
        num_frames=NUM_FRAMES,
        height=HEIGHT,
        width=WIDTH,
        generator=generator,
    )
    frames = result.frames[0]
    # ---- END VERIFY BLOCK -------------------------------------------------

    from diffusers.utils import export_to_video
    export_to_video(frames, str(out_path), fps=FPS)

print("adapter defined — VERIFY the two blocks above before running section 6")
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

summary = (
    f"{len(ok)}/{len(RESULTS)} clips generated; "
    f"peak VRAM {peak_vram}{' GiB' if _vram else ''}; "
    f"peak RAM {peak_ram}{' GiB' if _ram else ''}; "
    f"mean {avg}s per {NUM_FRAMES}-frame clip; "
    f"H.264 playback {'verified' if all_h264 else 'NOT verified'}."
)

entry = f"""  - id: "EVD-EXP005-XXX"
    claim: "{MODEL_LABEL} generates a {NUM_FRAMES}-frame {WIDTH}x{HEIGHT} clip from text on a Kaggle GPU."
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
## 10. After the run

1. **Download `blind/` and `BLIND_KEY.json`** — Kaggle wipes `/kaggle/working`
   when the session ends.
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
