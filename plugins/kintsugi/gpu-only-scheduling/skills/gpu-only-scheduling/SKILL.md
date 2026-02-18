---
name: gpu-only-scheduling
description: "GPU-only SLURM scheduling for KINTSUGI: never use CPU fallback — measured speedups: stitch 25x, decon 5x, EDF 15x (~13x full cycle)"
author: KINTSUGI Team
date: 2026-02-13
---

# GPU-Only Scheduling - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-13 |
| **Goal** | Determine optimal GPU/CPU scheduling strategy for batch processing |
| **Environment** | HiPerGator: B200 + Turin GPUs, clive (3G) + maigan (2G) accounts, CODEX 9x7 datasets |
| **Status** | Success — GPU-only is dramatically faster even with queuing |

## Context
The original `_build_cycle_assignment()` in the Snakefile used a dual-pool architecture: GPU slots filled first, then overflow cycles were assigned to CPU. With 5 GPU slots and 9 cycles, cycles 6-9 would run on CPU. Investigation of CX_19-003_lymph-node_R1 revealed CPU jobs were taking 2+ hours per cycle vs ~8 minutes on GPU for stitching alone.

## Performance Data (CX_19-003_lymph-node_R1, 9x7 tiles, 20 z-planes, 4 channels)

### Stitching (per cycle)
| Node | Time | Bottleneck |
|------|------|-----------|
| GPU (Turin) | 3-8 min | BaSiC `fit()` — 500 DCT iterations per z-plane, near-instant on GPU |
| GPU (B200) | 8-11 min | Same, slightly slower on B200 for this workload |
| CPU (8 cores) | 93-127 min | BaSiC `fit()` — 1-2.5 min per z-plane via SciPy DCT |

### Full Pipeline (stitch + decon + EDF per cycle)
| Mode | Time per cycle | 9-cycle total (5 GPU slots) |
|------|---------------|---------------------------|
| GPU | ~12 min | ~24 min (2 waves × 12 min) |
| CPU | ~4 hours | ~18+ hours (4 cycles × 4 hrs) |

### Root Cause: BaSiC Illumination Correction
- BaSiC `fit()` is called **per z-plane** (not per channel) — 80 calls per cycle (4 channels × 20 z-planes)
- Each `fit()` runs 500 iterative DCT operations
- On GPU (CuPy): FFT/DCT is massively parallel → milliseconds per iteration
- On CPU (SciPy): Sequential DCT → 1-2.5 minutes per z-plane
- BaSiC caching (compute once per channel) was evaluated and **REJECTED** — causes 15-20% intensity errors for sparse markers (see `basic-caching-evaluation` skill)

## Verified Workflow

### GPU-Only Cycle Assignment (Snakefile)
```python
def _build_cycle_assignment():
    """Pre-assign each cycle to an account and mode (gpu-only).

    All cycles are assigned to GPU, round-robin across accounts proportional
    to each account's GPU slot count.  Overflow cycles queue in SLURM until
    a GPU slot frees up — this is dramatically faster than CPU fallback
    (GPU ~8 min vs CPU ~2 hours per cycle for stitching alone).
    """
    assignment = {}
    gpu_queue = []
    for acct in ACCOUNTS:
        gpu_queue.extend([{
            "account": acct["name"],
            "mode": "gpu",
            "partition": acct.get("partition_gpu", "hpg-b200,hpg-turin"),
        }] * acct.get("gpu_slots", 0))

    gpu_accounts = [acct for acct in ACCOUNTS if acct.get("gpu_slots", 0) > 0]
    for i, cyc in enumerate(CYCLES):
        cyc_key = cyc_fmt(cyc)
        if i < len(gpu_queue):
            assignment[cyc_key] = gpu_queue[i]
        else:
            acct = gpu_accounts[i % len(gpu_accounts)] if gpu_accounts else ACCOUNTS[0]
            assignment[cyc_key] = {
                "account": acct["name"],
                "mode": "gpu",
                "partition": acct.get("partition_gpu", "hpg-b200,hpg-turin"),
            }
    return assignment
```

### CLI: Set -j to GPU Slots Only
```python
# In workflow run command:
j_val = pool["total_gpu_avail"]  # NOT pool["total_avail"]
```

### Dynamic Worker Counts (Wrapper Scripts)
```python
# stitch.py and edf.py — use SLURM allocation, not hardcoded 4
CPUS = int(getattr(snakemake.resources, "cpus_per_task", 4))
# GPU jobs get 4 cores, CPU jobs would get 8
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| CPU fallback for overflow cycles | 5-25x slower per step (~13x full cycle) — BaSiC `fit()` is GPU-bottlenecked | Queue for GPU instead; even waiting 22 min is faster than ~282 min on CPU |
| BaSiC caching (compute fit() once per channel) | 15-20% intensity errors for sparse markers (see `basic-caching-evaluation`) | Flatfield varies per z-plane for some channels — can't cache |
| Hardcoded `max_workers=4` in wrapper scripts | Wasted half of allocated CPU cores on CPU jobs (8 allocated, 4 used) | Read from `snakemake.resources.cpus_per_task` |
| Dual-pool `-j 24` (GPU + CPU slots) | Submits too many jobs; CPU jobs block GPU slots conceptually | `-j` should match GPU slots only |
| Running bare `snakemake` for registration-only work | QC rules trigger alongside registration, consuming SLURM scheduling slots and potentially blocking GPU jobs while waiting for non-GPU QC dependencies | Target specific rules: `snakemake registration --configfile config.yaml` (targets BEFORE options) |
| Not cancelling stale SLURM jobs before relaunch | Killed Snakemake coordinators leave running SLURM jobs. New launches race with old jobs writing to same output | Always `scancel` + `squeue -u $USER` check before relaunching batch workflows |

## Final Parameters

```yaml
# Snakefile: _build_cycle_assignment()
# Mode: GPU-only for ALL cycles (no CPU fallback)
# Overflow: round-robin across GPU accounts, queue in SLURM

# CLI: workflow run
# -j = total_gpu_avail (5 for clive+maigan)

# Wrapper scripts: dynamic worker counts
# CPUS = snakemake.resources.cpus_per_task (4 for GPU, 8 for CPU)
```

## Key Insights
- **Measured per-step speedups** (CX_19-003, 9x7 grid, 4ch, 20z): stitch 25x, decon 5x, EDF 15x (~13x full cycle)
- **GPU ~22 min vs CPU ~282 min per cycle**: stitch ~8 vs ~200 min, decon ~12 vs ~60 min, EDF ~1.5 vs ~22 min
- **Queuing is faster than CPU**: Even if a cycle waits 12 min for a GPU slot, total time is still ~44 min vs ~18 hours with CPU
- **Per-cycle pipeline** (`stitch→decon→edf`) means GPU slots free up incrementally — overflow cycles start as soon as one cycle's stitch finishes
- **BaSiC fit() is the bottleneck**, not stitch_images() or blending — it runs 500 DCT iterations per z-plane, 80 z-planes per cycle
- **Never cache BaSiC flatfields** — confirmed by `basic-caching-evaluation` skill (15-20% intensity errors)
- **Dynamic worker counts matter** — `max_workers=4` wasted 50% of CPU job allocation
- **Target specific Snakemake rules to avoid GPU QC contention** — Running bare `snakemake` triggers QC rules (qc_stitch, qc_decon, qc_edf, qc_registration) which don't need GPU but compete for SLURM scheduling slots. Use `snakemake registration --configfile config.yaml` to run only registration. QC can run separately without GPU allocation (16 GB RAM, 2 CPUs, 30 min)
- **Account distribution for registration** — `_registration_assignment()` picks the first GPU account in config.yaml `resources.accounts` list. Reorder accounts to control which account runs registration jobs. Useful for load balancing when one account has queued jobs

## When to Apply
- Configuring SLURM scheduling for KINTSUGI batch processing
- Investigating slow CPU stitching or deconvolution jobs
- Deciding whether to add CPU fallback for overflow cycles
- Tuning `-j` parameter for Snakemake SLURM submissions

## References
- `basic-caching-evaluation` skill — Why BaSiC caching fails
- `snakemake-workflow-architecture` skill — Snakefile design decisions
- `gpu-parallel-scheduling` skill — GPU queue pattern for notebooks
- `slurm-concurrent-processing` skill — Multi-account SLURM architecture
