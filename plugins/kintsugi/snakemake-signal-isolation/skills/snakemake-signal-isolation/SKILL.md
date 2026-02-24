---
name: snakemake-signal-isolation
description: "Adding signal isolation as a Snakemake pipeline rule for end-to-end automation. Trigger: signal isolation rule, pipeline integration, batch completion sentinel, autofluorescence subtraction as workflow step."
author: KINTSUGI Team
date: 2026-02-24
---

# Signal Isolation as Snakemake Rule

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-24 |
| **Goal** | Integrate signal isolation into the Snakemake pipeline as Rule 5, eliminating manual CLI chaining after registration |
| **Environment** | HiPerGator HPC, Snakemake >= 8.0, KINTSUGI conda env |
| **Status** | Implemented, 35 projects re-configured |

## Context

Signal isolation (autofluorescence subtraction) was a separate CLI command (`kintsugi workflow isolate run`) that had to be manually invoked after the Snakemake pipeline finished registration. This broke end-to-end automation — `kintsugi workflow batch` only ran through registration, then signal isolation required a second pass. The fix was to make it a proper Snakemake rule like every other pipeline stage.

## Verified Workflow

### Pipeline After Change
```
stitch → decon → edf (per-cycle) → registration (aggregate) → signal_isolation (aggregate) → 5 QC rules
```

### Rule Design: CPU-Only Aggregate (Like Registration)

Signal isolation is an **aggregate rule** — no `{cycle}` wildcard, processes all channels at once. CPU-only (numpy/scipy, no GPU needed). Reuses `_QC_CPU_ASSIGN` for SLURM partition routing (same pattern as existing QC rules).

```python
rule signal_isolation:
    input:
        reg_done=f"{PROJECT}/data/processed/registered/.snakemake_complete",
    output:
        sentinel=f"{PROJECT}/data/processed/signal_isolated/.snakemake_complete",
    resources:
        mem_mb=RES.get("mem_signal_isolation", 32000),
        runtime=RES.get("time_signal_isolation", 120),
        slurm_partition=_QC_CPU_ASSIGN["partition"],
        slurm_account=_QC_CPU_ASSIGN["account"],
        gres="",
        cpus_per_task=RES.get("cpus_signal_isolation", 4),
    script: "scripts/signal_isolation.py"
```

### Wrapper Script Pattern (`scripts/signal_isolation.py`)

Follows the `registration.py` pattern:
1. Read `snakemake.params` and `snakemake.config`
2. Setup 3-tier sys.path (project → kintsugi notebooks → kintsugi root)
3. Import log_utils from scriptdir
4. Read `signal_isolation` config section
5. **Skip-existing**: If manifest exists and all marker TIFs present → write sentinel and exit
6. **Recipe auto-discovery**: Config `recipe_dir` → standard search paths (`Processing_parameters/`)
7. Call `process_batch()` from `kintsugi.signal.batch`
8. Write sentinel with metadata (method counts, quality, timing)

### Config Section (`config.yaml`)

```yaml
signal_isolation:
  method: auto          # auto, global, or weighted
  tissue_type: spleen   # Auto-detected from project name via parse_tissue_type()
  tile_smooth_sigma: 0.0
  recipe_dir: ""        # Empty = auto-discover in standard paths
  learn: true
  force: false

resources:
  mem_signal_isolation: 32000
  time_signal_isolation: 120
  cpus_signal_isolation: 4
  time_qc_signal_isolation: 60
```

### Tissue Type Auto-Detection

`generate_workflow_config()` calls `parse_tissue_type(project_dir.name, project_dir)` from `batch_multi.py`:
- `_SP_` or `spleen` → `"spleen"`, `_LN_` or `lymph-node` → `"lymph_node"`, `_TH_` or `thymus` → `"thymus"`
- Falls back to experiment.json name field, then `"unknown"`

### QC Integration

`qc_signal_isolation` dispatches to `generate_qc_pages()` from `signal/isolation_qc.py` via the existing `qc_report.py` dispatcher. No cache file needed — signal isolation QC is self-contained (reads manifest + registered + isolated images directly).

### Batch Completion Sentinel Change

The **batch completion sentinel** changed from `registered/.snakemake_complete` to `signal_isolated/.snakemake_complete`. This affects:
- `_discover_batch_projects()` — projects with only registration are now "eligible" (not "completed")
- `_detect_project_stage()` — signal_isolated is the new highest stage
- `rule all` target — changed from registered to signal_isolated
- `all_qc_sentinels()` — 5 sentinels instead of 4

### Files Modified

| File | Key Changes |
|------|-------------|
| `workflow/Snakefile` | Added `signal_isolation` + `qc_signal_isolation` rules, updated `rule all`, `all_qc_sentinels()`, `_cleanup_safe_inputs()` |
| `workflow/scripts/signal_isolation.py` | **NEW** wrapper script |
| `workflow/scripts/qc_report.py` | Added `signal_isolation` dispatch case |
| `workflow/scripts/log_utils.py` | Added `signal_isolation` to input/output dirs and label maps |
| `src/kintsugi/cli.py` | Config section, resources, tissue type auto-detection, `_detect_project_stage()`, `_discover_batch_projects()` |
| `tests/test_workflow_batch.py` | 3 new tests, updated `_make_project()` with `signal_isolated` param |

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Using GPU partition for signal isolation | signal/batch.py is pure numpy — no GPU needed, wastes GPU slots | Route to CPU via `_QC_CPU_ASSIGN` (same as QC rules) |
| Not updating `_discover_batch_projects()` sentinel | Tests failed — projects with only registration marked as "completed" | Batch completion check must match `rule all` target |
| Not updating `_cleanup_safe_inputs()` | registered/ data could be deleted before signal isolation runs | Add signal_isolation sentinel as cleanup gate input |
| Not adding `qc_signal_isolation` to `all_qc_sentinels()` | Signal isolation QC would never run as part of default pipeline | All QC sentinels must be listed in `all_qc_sentinels()` |

## Key Insights

- **CPU-only rules use `_QC_CPU_ASSIGN`** — same partition routing pattern as QC rules; no need for lambda resources or GPU assignment
- **Aggregate rules follow registration pattern** — static resources, f-string outputs, no `{cycle}` wildcard
- **Wrapper scripts follow 3-tier sys.path** — project notebooks → kintsugi notebooks → kintsugi root
- **Sentinel change ripples through** — batch eligibility, stage detection, rule all, QC sentinels, cleanup gate ALL need updating
- **Recipe auto-discovery** makes the rule zero-config — searches standard paths, falls back to auto-analysis
- **Tissue type auto-detection** in `generate_workflow_config()` means users don't need to manually configure tissue type
- **Re-config propagates via `workflow config`** — always overwrites Snakefile + profiles; adds new scripts per-file

## Verified On

- 35 projects re-configured via `kintsugi workflow config .` (Feb 24, 2026)
- All tissue types correctly auto-detected (spleen, lymph_node, thymus)
- 92/92 tests pass (26 workflow batch + 66 batch signal isolation)
- Two in-progress projects (1901CC2A, 1901CC3C) will pick up signal isolation after registration completes

## References

- `snakemake-workflow-architecture` skill — base workflow design
- `batch-signal-isolation` skill — process_batch() internals
- `claude-md-context-management` skill — CLAUDE.md size management
