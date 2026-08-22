# EXP-005 host recheck — 2026-08-19

- **Document ID:** `CRETONA-EXP005-RECHECK-001`
- **Mode:** Measurement only; no inference was run
- **Observation date:** 2026-08-19
- **Supersedes the host figures in:** `docs/discovery/FREE-LOCAL-BEST-OUTPUT.md` §2
  (observed 2026-08-11) and `docs/adr/ADR-009-zero-spend-provider-gate.md` §Context

## 1. Why this recheck exists

The 2026-08-11 pre-screen recorded 4.30 GiB free physical RAM, 5.96 GiB free
VRAM and 14.62 GiB free virtual memory against the 6/6/48 GiB FramePack gate,
and noted that total virtual memory was only 43.26 GiB — so the 48 GiB gate was
unreachable without a pagefile decision.

The host has changed since. System RAM has roughly doubled and a large second
pagefile now exists on drive D. The FramePack blocker recorded in ADR-009 is no
longer present, so the rejection rationale needed remeasuring rather than
re-quoting.

## 2. Measurements

Read-only. `nvidia-smi` for the GPU; `Win32_OperatingSystem`,
`Win32_PageFileUsage`, `Win32_PageFileSetting` and `Win32_LogicalDisk` for
memory, pagefile and disk.

| Resource | 2026-08-11 | 2026-08-19 | Note |
|---|---:|---:|---|
| GPU VRAM total | 8 GiB | 8 GiB | unchanged; still the binding constraint |
| GPU VRAM free | 5.96 GiB | **6.59 GiB** | above the 6 GiB gate, but with little margin |
| Physical RAM total | ~15.3 GiB | **31.73 GiB** | roughly doubled |
| Physical RAM free | 4.30 GiB | **12.81 GiB** | transient; remeasure before any run |
| Virtual memory total | 43.26 GiB | **91.16 GiB** | commit limit = RAM + pagefiles |
| Virtual memory free | 14.62 GiB | **65.80 GiB** | above the 48 GiB gate |
| Drive D free | ~483.5 GiB | 104.19 GiB | weights and caches now occupy most of it |

### Pagefile configuration

Not system-managed (`AutomaticManagedPagefile = False`):

| File | Allocated | Setting | Peak usage |
|---|---:|---|---:|
| `C:\pagefile.sys` | 14.50 GiB | system managed | 0.73 GiB |
| `D:\pagefile.sys` | 44.92 GiB | initial 46000 MB, max 60000 MB | 1.54 GiB |

The commit *limit* is what the gate reads, not paging activity — peak usage on
both files is under 2 GiB.

### GPU identity correction

`nvidia-smi` reports **`NVIDIA GeForce RTX 3070 Laptop GPU`**. Both documents
previously said "RTX 3070 Ti Laptop". The distinction matters when citing
FramePack's author, whose published timings discuss a 3070 Ti laptop; a non-Ti
3070 laptop should be expected to be somewhat slower than that reference, not
equal to it.

## 3. Gate result

`scripts/check-exp005-preflight.ps1`, captured `2026-08-19T06:28:17Z`:

| Check | Result |
|---|---|
| `acPower` | pass |
| `freeRam` | pass |
| `freeVram` | pass |
| `freeDisk` | pass |
| `freeVirtualMemory` | pass |
| `noLoadedOllamaModel` | pass |
| **`passed`** | **true** |

## 4. Threshold discrepancy, unresolved

The script's `minimumFreeVirtualGiB` is `0`, while ADR-009 and
`FREE-LOCAL-BEST-OUTPUT.md` §8 both state a 48 GiB virtual-memory gate. The
script's virtual-memory check therefore passes trivially and is not evidence
against the documented gate.

The measured 65.80 GiB clears 48 GiB on its own, so the conclusion is unchanged
either way — but the script and the documents disagree and one of them should
be corrected before the bake-off is run.

## 5. What this does and does not establish

Establishes:

- The FramePack F1 inference blocker recorded in ADR-009 is cleared on this
  host, by measurement rather than by argument.
- The "16 GB system RAM makes offload/paging high-risk" caveat that excluded
  HunyuanVideo 1.5 no longer describes this machine.

Does not establish:

- Any quality, latency, stability or license result. No inference has run.
- Anything about VRAM-bound candidates. LTX-Video 2B was rejected on a VRAM and
  architecture basis (about 10 GiB documented, Ada-oriented acceleration);
  8 GiB of Ampere VRAM is unchanged, so that rejection stands.
- That free VRAM will still be 6.59 GiB at run time. It is transient and sits
  only 0.59 GiB above the gate; a browser or the emulator can erase that margin.

## 6. Consequence

EXP-005's pass/kill procedure in `FREE-LOCAL-BEST-OUTPUT.md` §8 is now
executable on this host. Selection still requires the recorded version, hash,
license, two consecutive runs, H.264 playback proof and blind quality scores.
