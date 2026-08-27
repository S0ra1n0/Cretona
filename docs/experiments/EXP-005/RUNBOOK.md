# EXP-005 bake-off — runbook

- **Document ID:** `CRETONA-EXP005-RUNBOOK-001`
- **Covers:** `EXP-005_T2V_bakeoff.ipynb` (24 cells, sections 1–12)
- **Written:** 2026-08-26
- **Host:** Kaggle, GPU **T4 ×2**

Cell numbers below are zero-indexed as Kaggle shows them. Odd numbers are
markdown; even numbers are the code you actually run.

---

## 0. Before the first cell

1. **Settings → Accelerator → GPU T4 ×2.**
   Not P100 (compute capability 6.0, below what current tooling assumes), not
   None. This restarts the session and starts your GPU-hour clock.
2. **Settings → Internet → On.** Weights download at runtime.
3. Close other Kaggle sessions. Quota is shared, ~30 GPU-hours a week.

---

## 1. Install — cell 2, once per session

Uncomment the `!pip install` line, run cell 2, then **comment it back out**.

Expect ~2 minutes. Ignore `google-adk ... dependency conflicts` — unrelated
Kaggle image noise.

Success looks like:

```
torch      2.10.0+cu128
diffusers  0.36.0.dev0
dependencies present - leave the pip line commented
```

If it says `MISSING: torch, diffusers, ...` the pip line is still commented.

> **If the install upgraded a package that was already imported**, the kernel
> needs recycling before anything else. Use the **Run menu**, not the toolbar's
> circular arrow — that one is **Factory reset** and wipes the downloaded
> weights along with everything else.

---

## 2. Smoke test — the fast loop

**`SMOKE_TEST = True` is the default in cell 4.** Leave it for the first run of
any session or after any change.

Both prompts, one seed each, 8 steps, 25 frames: **~3 minutes** instead of
~50, exercising every line the full run does. That is **2 clips**, so
`distinct outputs: 2/2` is the correct result in smoke mode — 4/4 belongs to a
full run.

Run cells **4 → 22** in order. Skip cell 2.

### What each checkpoint should print

**Cell 4 — configuration**
```
*** SMOKE TEST: 2 clips, 8 steps, 25 frames. NOT scoreable. ***
model  : Wan2.1 T2V 1.3B
clip   : 25 frames at 16fps = ~1.6s
```

**Cell 8 — environment.** Must not say `NO GPU DETECTED`.

**Cell 12 — adapter.** Defines functions only; nothing loads yet.

**Cell 14 — the run.** This is where everything happens, and where to watch:

```
[phase 1] loading text encoder only
  [before] gpu0 14.4/14.6 GiB free, gpu1 14.4/14.6 GiB free | ram 29 GiB free
  [encoder loaded (cpu)] ...
  tied encoder.embed_tokens.weight -> shared.weight      <-- 1
  encoder self-test: 120/226 positions carry content
    mean |A-B| over content : 0.073210                   <-- 2
    cosine similarity       : 0.153194                   <-- 2
  encoded A: (1, 226, 4096)
  [encoder freed] ...
  cached embeddings -> embeds-a1b2c3d4e5f6a7b8.pt        <-- 3
[phase 2] loading transformer + vae, text_encoder=None
  [generator ready] gpu0 11.3/14.6 GiB free              <-- 4
  8/8 [01:12<00:00]
  ok  72.4s  peak VRAM 4.1 GiB  ...
```

| # | Line | Must be |
|---|---|---|
| 1 | the tie | either message is fine; it reports what it did |
| 2 | self-test | **cosine well below 1.0** (0.15 is healthy). The mean is measured over content only — averaging in the ~106 padding rows drags it toward zero and misleads |
| 3 | cache | written only after the checks pass |
| 4 | generator | a few GB used, not a card at `0.0` free |

**Cell 22 — download.** Run it even for a smoke test; it costs nothing and
proves the archive path works.

### The decision

**Open the clip and look at it.**

- **Flat grey, no content** → the conditioning is still broken. Stop; do not
  start a full run. Report the self-test number.
- **Recognisable content, even if crude** → the pipeline works. 8 steps looks
  rough by design. Go to stage 3.

---

## 3. Full run

In cell 4, set:

```python
SMOKE_TEST = False
```

Run cells **4 → 22** again.

Phase 1 is now **skipped** — the embeddings are cached from the smoke test and
the prompts have not changed:

```
[phase 1] SKIPPED -- reusing embeds-a1b2c3d4e5f6a7b8.pt
```

That saves ~5 minutes. Then 4 clips at ~10 minutes each — **budget 40–45
minutes** and do not close the tab.

### Reading the result — cell 20

```
4/4 clips generated, 4 distinct; peak VRAM 13.59 GiB; ...
  distinct outputs   : 4/4
```

**`distinct` is the number that matters.** `4/4` means each prompt and seed
produced its own video. Anything less means prompts did not reach the model,
the run prints a NOT-scoreable warning, and the ledger records `failed`.

---

## 4. Download — cell 22

`/kaggle/working` is wiped when the session ends.

Click the `FileLink`, or use the **Output** panel in the right sidebar. The
archive holds `blind/`, `raw/`, `BLIND_KEY.json`, `environment.json`,
`results.json`, `ledger_entry.yaml`.

Then **stop the session** — idle time bills against the same quota.

---

## 5. Scoring — off Kaggle

Only for a full run with `4/4 distinct`.

1. Bruce and S0ra1n0 score `blind/` **independently**, in
   `QUALITY_SCORECARD.md`, **without opening `BLIND_KEY.json`**.
2. Reveal the key.
3. Paste `ledger_entry.yaml` into `EVIDENCE_LEDGER.yaml` with the next free
   `EVD-EXP005-###`.
4. Record the decision either way. A negative result is a valid outcome.

**Rubric note for text-to-video:** *Reference consistency* (20 points) assumes
a reference image, and T2V has none. Score it as **identity stability across
the clip** — does the subject stay the same subject from first frame to last —
and write that reading in the notes column.

---

## 6. Resuming after a failure

| Situation | Do this |
|---|---|
| Clip 4 failed, 1–3 worked | Copy the run id from cell 4's output into `RESUME_RUN_ID`, re-run cell 4 then 14. Existing clips print `reused existing file` |
| Changed a prompt | Nothing. The cache key covers prompt text and invalidates itself |
| Changed model or revision | Nothing. Same reason |
| Want to force a re-encode | Delete the matching file in `/kaggle/working/_cache/` |

---

## 7. Troubleshooting

Every row below is a failure that actually happened on 2026-08-23/26.

| Symptom | Cause | Fix |
|---|---|---|
| `401 ... Repository Not Found` | Wrong repo id. The Hub answers "missing" and "private" identically | Check `MODEL_REPO`. The Wan id ends `-Diffusers`, and Hunyuan's needs `-Diffusers-` in the middle |
| `Your notebook tried to allocate more memory than is available` | System **RAM**, not VRAM. Something held the encoder and transformer together | The two-phase split already prevents this. If it recurs, phase 1 loaded onto a GPU — it must stay on CPU |
| `CUBLAS_STATUS_ALLOC_FAILED` **with a card at `0.0` free** | Weights fit; nothing left for cuBLAS handles | Something is still resident from an earlier attempt. Free it (below) |
| `CUBLAS_STATUS_ALLOC_FAILED` **with cards nearly empty** | Host RAM exhausted | Reduce what phase 1 holds, or the model is too large for this host |
| `CUDA out of memory` at step 0 | Activations, not weights | Lower `NUM_FRAMES` first — activation memory scales with frame count |
| `NameError: PROMPTS is not defined` | Kernel restarted; cell 4 has not run since | Run cells 4 → 22, or Run All |
| **All clips flat grey** | Text conditioning is meaningless | The `embed_tokens` tie repair addresses this. Check self-test line 2 |
| **Clips byte-identical** | Prompts never reached the model | Cell 20 now catches it. Check the `distinct outputs` line |
| `cosine similarity: 0.999+` | Encoder cannot distinguish prompts | Raises on purpose. Do not proceed; the tie repair did not work |

### Freeing stuck GPU memory without losing the weights

IPython pins the crashed frame through the stored traceback, and that frame
holds the pipeline — so `empty_cache()` alone does nothing. New cell:

```python
import gc, sys, torch
sys.last_traceback = None
sys.last_value = None
sys.last_type = None
_PIPE = None
gc.collect()
torch.cuda.empty_cache()
for i in range(torch.cuda.device_count()):
    free_b, total_b = torch.cuda.mem_get_info(i)
    print(f"gpu{i}: {free_b/1024**3:.2f} GiB free of {total_b/1024**3:.2f} GiB")
```

Both cards should return to ~14.4 GiB free. Downloaded weights are untouched.

---

## 8. Timings to expect

| Step | Time |
|---|---|
| Install (cell 2) | ~2 min, once per session |
| Weight download | ~2–4 min first time, then cached |
| Phase 1 encode (CPU) | ~5 min, cached afterwards |
| Phase 2 load | ~1 min |
| Generation, smoke (8 steps, 25 frames) | ~1.5 min |
| Generation, full (50 steps, 81 frames) | **~10 min per clip** |
| **Full run, cold** | **~50 min** |
| **Full run, embeddings cached** | **~45 min** |
| **Smoke test, cached** | **~2 min** |

Generation is slow because a T4 is roughly a fifth of a modern card and the
`sage_hub` attention backend is unavailable. That is the honest cost of
zero-spend hardware, and the ledger records it rather than hiding it.
