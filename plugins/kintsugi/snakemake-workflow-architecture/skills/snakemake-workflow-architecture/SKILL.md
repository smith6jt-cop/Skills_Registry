---
name: snakemake-workflow-architecture
description: "Snakemake workflow design for KINTSUGI SLURM processing: lambda resource routing, GPU-only cycle pre-assignment, multi-account scheduling, registration + QC aggregate rules. Trigger: Snakemake rules, workflow config, ruleorder, cycle assignment, DAG design, sentinel files, workflow run/check, registration, VALIS, QC reports."
author: KINTSUGI Team
date: 2026-02-14
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

### 3 Per-Cycle Rules with Lambda Resources + 1 Aggregate Rule (NOT 6 rules + ruleorder)

Each per-cycle processing step (stitch, deconvolve, edf) is a single rule. Account, partition, and resource allocation are set per-wildcard via lambda functions in the `resources:` block. Registration is an aggregate rule with static resources (see below).

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

### Cycle Pre-Assignment (`_build_cycle_assignment()`) — GPU-Only

Cycles are assigned to accounts at DAG creation time (not runtime). **All cycles route through GPU** — CPU fallback was removed because GPU is 15-20x faster (see `gpu-only-scheduling` skill).

1. **GPU queue**: Each account contributes `gpu_slots` entries
2. **Overflow**: Round-robin across GPU accounts (still GPU mode, cycles queue in SLURM)

No CPU queue — overflow cycles wait for GPU slots to free up, which is dramatically faster than running on CPU.

### Sentinel Files for Outputs

Rules use `.snakemake_complete/stitch_cyc{cycle}` sentinel files because:
- Stitching/deconvolution produce hundreds of files (channels x z-planes)
- EDF produces marker-named files that vary per cycle
- Declaring every output would create an enormous, fragile DAG

A separate `validate` rule checks that all expected files exist.

### Per-Cycle Pipeline Dependencies

Dependencies flow per-cycle, enabling pipelining:
```
stitch cyc01 → decon cyc01 → edf cyc01 ─┐
stitch cyc02 → decon cyc02 → edf cyc02 ─┼─→ registration (all cycles)
stitch cyc03 → decon cyc03 → edf cyc03 ─┘
```
Cycle 1's deconvolution starts the moment cycle 1's stitching finishes.

### Rule 4: Registration (Aggregate, No Cycle Wildcard)

Registration (multi-cycle alignment via VALIS) processes ALL cycles in a single SLURM job. Unlike rules 1-3, it has no `{cycle}` wildcard — resources are static, not lambda-driven.

### Rule 5: Signal Isolation (Aggregate, CPU-Only)

Added 2026-02-24. Signal isolation (autofluorescence subtraction) runs after registration, processing all registered channels. CPU-only (numpy/scipy), uses `_QC_CPU_ASSIGN` for partition routing (same as QC rules). See `snakemake-signal-isolation` skill for details.

Full pipeline: `stitch → decon → edf` (per-cycle) → `registration` → `signal_isolation` (both aggregate) + 5 QC rules.

```python
_REG_ASSIGN = _registration_assignment()  # Computed once at DAG creation

rule registration:
    input: all_edf_sentinels(),  # Depends on ALL EDF cycles completing
    output: sentinel="{project}/data/processed/registered/.snakemake_complete",
    resources:
        slurm_partition=_REG_ASSIGN["partition"],  # Static, not lambda
        slurm_account=_REG_ASSIGN["account"],
        gres="gpu:1" if _REG_ASSIGN["mode"] == "gpu" else "",
    script: "scripts/registration.py"
```

Key design decisions:
- **`_registration_assignment()`**: Prefers first account with `gpu_slots > 0` (for VggFD feature detector). Falls back to CPU with OrbFD.
- **Static resources**: No lambda wildcards because there's no `{cycle}` wildcard to dispatch on.
- **Single-cycle handling**: If `len(CYCLES) < 2`, copies EDF → registered without VALIS (no alignment needed).
- **Error fallback**: On VALIS failure, copies EDF images unchanged (graceful degradation).
- **f-string output**: Uses `f"{PROJECT}/..."` since there's no wildcard — same pattern as QC rules.

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

Registration parameters are also in `config.yaml`:
```yaml
registration:
  reference_cycle: 1
  max_image_dim: 2048
  rigid_only: false
  feature_detector: "VggFD"

resources:
  mem_registration: 64000
  time_registration: 120
  cpu_mem_registration: 64000
```

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
| CPU fallback for overflow cycles | 15-20x slower — BaSiC `fit()` bottleneck (500 DCT iterations/z-plane) | Route ALL cycles through GPU; queue in SLURM (see `gpu-only-scheduling` skill) |
| Hardcoded `max_workers=4` in wrapper scripts | Wasted half of 8 allocated CPU cores | Read from `snakemake.resources.cpus_per_task` dynamically |

### Per-Channel Skip-Existing (Inside Wrapper Scripts)

Snakemake controls the DAG at the **cycle** level via sentinel files. If a sentinel is missing, Snakemake reruns the entire cycle. But if a job was interrupted after completing 3 of 4 channels, wrapper scripts now skip completed channels internally:

| Script | Completeness Check | What Counts as "Complete" |
|--------|-------------------|--------------------------|
| `stitch.py` | `channel_complete(ch)` | All z-plane TIFs exist + `result_df.pkl` for CH1 |
| `deconvolve.py` | `channel_decon_complete(ch)` | Decon TIF count >= stitched input TIF count |
| `edf.py` | `channel_edf_complete(ch)` | Marker-named output file exists |

Key behaviors:
- Partially-complete channels are **fully reprocessed** (only skip when ALL expected files exist)
- If ALL channels were already complete, sentinel is still written and job exits 0
- Sentinel files include `skipped=N` for log visibility
- When the sentinel already exists, Snakemake skips the entire rule (coarser, still works)

```python
# Pattern used in all 3 wrapper scripts:
channels_to_process = []
skipped_channels = []
for ch in CHANNELS:
    if channel_X_complete(ch):
        print(f"  Channel {ch} SKIPPED (...)")
        skipped_channels.append(ch)
    else:
        channels_to_process.append(ch)

# Process only incomplete channels
successful = sum(1 for _, ok in results if ok) + len(skipped_channels)
```

## QC Report Rules (Aggregate)

Added 2026-02-13. Three aggregate rules produce rich QC reports after each processing stage completes across all cycles:

```python
rule qc_stitch:
    input:
        stitch_done=_all_stitch_sentinels(),
    output:
        sentinel=f"{PROJECT}/qc_plots/.snakemake_complete_stitch",
    params:
        stage="stitch", ...
    resources:
        mem_mb=RES.get("mem_qc", 64000),
        slurm_partition=_REG_ASSIGN["partition"],
        slurm_account=_REG_ASSIGN["account"],
        gres="gpu:1" if _REG_ASSIGN["mode"] == "gpu" else "",
    script: "scripts/qc_report.py"
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Aggregate (all cycles), not per-cycle | QC heatmaps need cross-cycle comparison — per-cycle would miss the point |
| Single dispatch script (`qc_report.py`) | Avoids duplicating GPU init, path setup, and caching logic across 3 scripts |
| Reuses `_REG_ASSIGN` from registration | QC rules have no cycle wildcard, can't use `_assign(wc)` — same pattern as registration |
| Cross-stage cache pickles (`cache/stitch_stats.pkl`) | Each stage loads prior stage's stats for comparison plots |
| Included in `rule all` via `all_qc_sentinels()` | QC runs automatically after processing; `rule qc` is standalone shortcut |
| `matplotlib.use("Agg")` before Kprocess import | Compute nodes have no display; must set headless backend first |
| f-string outputs (not wildcard) | QC sentinels use `f"{PROJECT}/..."` since there's no cycle wildcard |

### Config Resources

```yaml
resources:
  mem_qc: 64000    # 64 GB
  time_qc: 120     # 2 hours
```

## What Snakemake Replaces vs Keeps

| Replaced by Snakemake | Kept from submit.sh |
|-----------------------|---------------------|
| Orchestration & dependency wiring | Python processing scripts (`workflow/scripts/*.py`) |
| `.complete` marker polling | `KINTSUGI_DEVICE_MODE` env var pattern |
| `--array` limit calculation | Device-adaptive backends (CuPy/NumPy) |
| Dual-pool slot calculation (shared via `hpc.py`) | Per-channel skip-existing (inside wrapper scripts) |

Both systems produce files in the same `data/processed/` tree. They can coexist but should NOT run simultaneously on the same project.

**Registration** is only available via Snakemake (not in submit.sh). It runs as a single aggregate job after all per-cycle EDF processing completes.

## Key Insights

- **Lambda resources are the key mechanism** — Snakemake has no built-in multi-account concept, but lambda functions in `resources:` give per-job control
- **Pre-assignment beats runtime scheduling** — Deterministic, reproducible, and avoids race conditions
- **Sentinel files are a pragmatic compromise** — Trade strict output tracking for a manageable DAG
- **Per-channel skip-existing complements sentinel-level control** — Snakemake handles cross-rule dependencies; wrapper scripts prevent re-doing completed work within a single interrupted job
- **`sacctmgr show associations` is the correct SLURM query** — `show user` format doesn't work on all clusters
- **GPU-only scheduling** — CPU is 15-20x slower for BaSiC; overflow cycles queue for GPU instead (see `gpu-only-scheduling` skill)
- **Dynamic worker counts** — Wrapper scripts read `cpus_per_task` from Snakemake resources, not hardcoded 4
- **Always overwrite the Snakefile** — Pipeline logic changes must propagate; user customization goes in config.yaml, not the Snakefile
- **`precommand` activates the existing conda env** — Compute nodes need `module load conda && conda activate KINTSUGI` to access cupy, torch, etc.
- **SLURM_TRES_PER_TASK must be unset for jobstep srun** — SLURM >= 24.11 bug; patch survives until upstream fix in `snakemake-executor-plugin-slurm-jobstep`
- **GPU resource: use `gres="gpu:1"`** — Maps to `--gres=gpu:1`; both `gpus` and `gpu` resources trigger SLURM 24.11 TRES conflicts
- **Aggregate rules use static assignment, not lambdas** — Registration and QC rules have no `{cycle}` wildcard, so use `_REG_ASSIGN` (from `_registration_assignment()`) computed once at DAG creation
- **Per-file script copy in `workflow config`** — New scripts auto-propagate to projects without overwriting user-customized scripts

## References

- KINTSUGI CLAUDE.md - "Snakemake Workflow" and "Multi-Account Architecture" sections
- `gpu-only-scheduling` skill - Why CPU fallback was removed (15-20x performance data)
- `slurm-concurrent-processing` skill - Dual-pool resource calculation (submit.sh version, historical)
- `slurm-workflow-integration` skill - Original SLURM CLI integration
- `workflow/Snakefile` - Implementation
- `src/kintsugi/hpc.py` - `detect_multi_account_resources()`, `detect_live_multi_account()`
- `src/kintsugi/cli.py` - `workflow config/check/run` commands
