---
name: snakemake-workflow-architecture
description: "Snakemake workflow design for KINTSUGI SLURM processing: lambda resource routing, cycle pre-assignment, multi-account scheduling. Trigger: Snakemake rules, workflow config, ruleorder, cycle assignment, DAG design, sentinel files, workflow run/check."
author: KINTSUGI Team
date: 2026-02-12
---

# Snakemake Workflow Architecture for Multi-Account SLURM

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-12 |
| **Goal** | Replace submit.sh orchestration with Snakemake while supporting multi-account GPU+CPU scheduling |
| **Environment** | HiPerGator HPC, Snakemake >= 8.0, snakemake-executor-plugin-slurm, multiple SLURM accounts |
| **Status** | Implemented |

## Context

The original `submit.sh` (~1500 lines) handled job orchestration, dependency wiring, skip-existing logic, and dual-pool slot calculation. Snakemake can handle all of this declaratively, but the multi-account GPU+CPU architecture requires careful design since Snakemake has no built-in concept of routing jobs to different accounts based on resource type.

## Verified Workflow

### 3 Rules with Lambda Resources (NOT 6 rules + ruleorder)

Each processing step (stitch, deconvolve, edf) is a single rule. Account, partition, and resource allocation are set per-wildcard via lambda functions in the `resources:` block:

```python
rule stitch:
    input: ...
    output: "{project}/.snakemake_complete/stitch_cyc{cycle}"
    resources:
        slurm_partition=lambda wc: _assign(wc)["partition"],
        slurm_account=lambda wc: _assign(wc)["account"],
        gpus=lambda wc: 1 if _is_gpu(wc) else 0,
        cpus_per_task=lambda wc: 4 if _is_gpu(wc) else CPU_CPUS,
        runtime=lambda wc: RES.get("time_stitch", 240) * (1 if _is_gpu(wc) else CPU_TIME_MULT),
    envmodules: ...
    shell: "KINTSUGI_DEVICE_MODE={params.device_mode} python workflow/scripts/stitch.py ..."
```

### Cycle Pre-Assignment (`_build_cycle_assignment()`)

Cycles are assigned to accounts/modes at DAG creation time (not runtime). Two queues are built:

1. **GPU queue**: Each account contributes `gpu_slots` entries (proportional)
2. **CPU queue**: Each account contributes `cpu_slots` entries (proportional)

Cycles are assigned in order: first through the GPU queue, then through the CPU queue, with overflow cycling round-robin across accounts.

### Sentinel Files for Outputs

Rules use `.snakemake_complete/stitch_cyc{cycle}` sentinel files because:
- Stitching/deconvolution produce hundreds of files (channels x z-planes)
- EDF produces marker-named files that vary per cycle
- Declaring every output would create an enormous, fragile DAG

A separate `validate` rule checks that all expected files exist.

### Per-Cycle Pipeline Dependencies

Dependencies flow per-cycle, enabling pipelining:
```
stitch cyc01 → decon cyc01 → edf cyc01
stitch cyc02 → decon cyc02 → edf cyc02
```
Cycle 1's deconvolution starts the moment cycle 1's stitching finishes.

### Cycle Directory Resolution

`_resolve_raw_cycle_dir()` handles multiple naming conventions at DAG creation time:
- Long-form: `cyc001_reg001_200210_170925`
- Short 3-digit: `cyc001`
- Short 2-digit: `cyc01`
- Capitalized: `Cyc01`

### Config Format (`workflow/config.yaml`)

```yaml
resources:
  accounts:
    - name: clive
      partition_gpu: "hpg-b200,hpg-turin"
      partition_cpu: hpg-default
      gpu_slots: 3
      cpu_slots: 11
    - name: maigan
      partition_gpu: "hpg-b200,hpg-turin"
      partition_cpu: hpg-default
      gpu_slots: 2
      cpu_slots: 8
  total_gpu_slots: 5
  total_cpu_slots: 19
  total_slots: 24
  cpu_utilization_cap: 0.85
  cpu_time_multiplier: 5
  cpu_cpus_per_task: 8
```

Legacy fallback: If `accounts` list is missing, reads old `account_gpu`/`account_cpu` scalars.

### CLI Commands

| Command | What it does |
|---------|-------------|
| `kintsugi workflow config .` | Discovers accounts via `sacctmgr`, generates config + copies Snakefile |
| `kintsugi workflow check .` | Shows live per-account availability (allocation, in-use, available) |
| `kintsugi workflow run .` | Submits via Snakemake with auto-calculated `-j` from live availability |

`workflow config` always overwrites the Snakefile (so pipeline updates propagate) but only copies scripts/profiles if they don't already exist.

### SLURM Profile (`workflow/profiles/slurm/config.yaml`)

Account and partition are set **per-rule** in the Snakefile via lambda resources, NOT in the profile. The profile provides:
- `executor: slurm`
- `default-resources` (mem_mb, runtime, cpus_per_task)
- `latency-wait: 120` (NFS propagation tolerance)
- `retries: 2` (automatic retry)
- `keep-going: true`

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| 6 rules + `ruleorder` (stitch_gpu > stitch_cpu) | `ruleorder` always picks the preferred rule — CPU variants NEVER execute | Use lambda resources in a single rule to route per-wildcard |
| `--resources gpus=N` to limit GPU jobs | Doesn't work with multi-account routing; Snakemake can't track per-account budgets | Bake GPU budget into cycle pre-assignment |
| Runtime cycle assignment | Race conditions, no reproducibility | Pre-assign at DAG creation time for deterministic scheduling |
| Declaring all output files per rule | Hundreds of files per stitch/decon (channels x z-planes), fragile DAG | Use sentinel files + separate validation rule |
| `sacctmgr show user USERNAME format=account` | Returns empty pipe on HiPerGator | Use `sacctmgr show associations user=USERNAME format=account -n -P` |
| Including burst accounts (`-b` suffix) | Burst QOS has unreliable memory; OOM kills | Filter out accounts ending with `-b` |
| Setting account/partition in profile config.yaml | Same settings for all rules — can't route GPU vs CPU | Must be per-rule via lambda in Snakefile |
| `gpus=1` or `gpu=1` resource | Both trigger `SLURM_TRES_PER_TASK` conflict on SLURM >= 24.11 | Use `gres="gpu:1"` which maps to `--gres=gpu:1` |
| `slurm_extra="'--gres=gpu:1'"` | Plugin blocks `--gres` in slurm_extra validation | Use `gres` resource, not slurm_extra |
| No `precommand` in SLURM profile | srun on compute nodes inherits bare shell — no conda env, cupy not importable | Add `precommand: "module load conda && conda activate KINTSUGI"` to profile |
| No SLURM_TRES_PER_TASK cleanup | SLURM >= 24.11 sets this env var in GPU jobs; jobstep plugin's srun inherits it and crashes | Patch jobstep plugin `__post_init__()` to `os.environ.pop("SLURM_TRES_PER_TASK", None)` |

## What Snakemake Replaces vs Keeps

| Replaced by Snakemake | Kept from submit.sh |
|-----------------------|---------------------|
| Orchestration & dependency wiring | Python processing scripts (`workflow/scripts/*.py`) |
| `.complete` marker polling | `KINTSUGI_DEVICE_MODE` env var pattern |
| Skip-existing logic | Device-adaptive backends (CuPy/NumPy) |
| `--array` limit calculation | Quality parameters (unchanged) |
| Dual-pool slot calculation (shared via `hpc.py`) | |

Both systems produce files in the same `data/processed/` tree. They can coexist but should NOT run simultaneously on the same project.

## Key Insights

- **Lambda resources are the key mechanism** — Snakemake has no built-in multi-account concept, but lambda functions in `resources:` give per-job control
- **Pre-assignment beats runtime scheduling** — Deterministic, reproducible, and avoids race conditions
- **Sentinel files are a pragmatic compromise** — Trade strict output tracking for a manageable DAG
- **`sacctmgr show associations` is the correct SLURM query** — `show user` format doesn't work on all clusters
- **GPU and CPU partitions are independent pools** — GPU jobs on `hpg-b200` don't consume CPU allocation on `hpg-default`
- **Always overwrite the Snakefile** — Pipeline logic changes must propagate; user customization goes in config.yaml, not the Snakefile
- **`precommand` activates the existing conda env** — Compute nodes need `module load conda && conda activate KINTSUGI` to access cupy, torch, etc.
- **SLURM_TRES_PER_TASK must be unset for jobstep srun** — SLURM >= 24.11 bug; patch survives until upstream fix in `snakemake-executor-plugin-slurm-jobstep`
- **GPU resource: use `gres="gpu:1"`** — Maps to `--gres=gpu:1`; both `gpus` and `gpu` resources trigger SLURM 24.11 TRES conflicts

## References

- KINTSUGI CLAUDE.md - "Snakemake Workflow" and "Multi-Account Architecture" sections
- `slurm-concurrent-processing` skill - Dual-pool resource calculation (submit.sh version)
- `slurm-workflow-integration` skill - Original SLURM CLI integration
- `workflow/Snakefile` - Implementation
- `src/kintsugi/hpc.py` - `detect_multi_account_resources()`, `detect_live_multi_account()`
- `src/kintsugi/cli.py` - `workflow config/check/run` commands
