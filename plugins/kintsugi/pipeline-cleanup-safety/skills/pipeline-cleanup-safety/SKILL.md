---
name: pipeline-cleanup-safety
description: "Pipeline-aware cleanup of intermediate data with dependency graph validation, QC gating, and staged deletion with trash recovery"
author: smith6jt
date: 2026-02-19
---

# Pipeline-Aware Cleanup Safety

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-19 |
| **Goal** | Prevent data loss when deleting intermediate pipeline data by tracking multi-consumer dependencies and optional stages |
| **Environment** | KINTSUGI v1.3.0, Python 3.11, Snakemake 9.x, SLURM 24.11, HiPerGator (UF) |
| **Status** | Success |

## Context

KINTSUGI's image processing pipeline produces large intermediate data at each stage: `raw/` (~50 GB) -> `stitched/` (~40 GB) -> `deconvolved/` (~40 GB) -> `edf/` (~5 GB) -> `registered/`. With 47 datasets, disk pressure requires cleaning intermediates after downstream stages complete.

**The data loss incident**: 14 datasets lost their deconvolved z-stacks when `cleanup_datasets.sh` deleted `deconvolved/` after EDF completed. The script only checked EDF as a consumer, but `vessel3d` (3D vessel segmentation) also consumes deconvolved data. Vessel3d was added later as an optional stage, and the cleanup script was never updated.

**Why this is hard**: Optional pipeline stages create invisible dependencies. The cleanup logic must know about ALL consumers of each intermediate directory, including stages that may not be configured for every dataset.

## Verified Workflow

### 1. Define the dependency graph as a single source of truth

```python
# In cleanup.py — central registry of what consumes what
PIPELINE_STAGES = {
    "stitch": PipelineStage("stitch", "stitched", is_optional=False,
                            sentinel_pattern="cyc{cycle}/.snakemake_complete"),
    "deconvolve": PipelineStage("deconvolve", "deconvolved", is_optional=False,
                                sentinel_pattern="cyc{cycle}/.snakemake_complete"),
    "edf": PipelineStage("edf", "edf", is_optional=False,
                         sentinel_pattern="cyc{cycle}/.snakemake_complete"),
    "vessel3d": PipelineStage("vessel3d", "vessel_3d", is_optional=True,
                              sentinel_pattern="cyc{cycle}/.snakemake_complete",
                              config_key="vessel3d"),
    "registration": PipelineStage("registration", "registered", is_optional=False,
                                  sentinel_pattern=".snakemake_complete"),
}

DATA_DEPENDENCIES = [
    DataDependency(source_dir="stitched", consumers=["deconvolve"]),
    DataDependency(source_dir="deconvolved", consumers=["edf", "vessel3d"]),  # DUAL CONSUMER
]
```

### 2. Check ALL consumers before allowing deletion

```python
def assess_cleanup_safety(project_dir, config=None):
    """Returns CleanupManifest with safe/blocked entries."""
    # Load config for optional stage declarations
    cfg = _load_workflow_config(project_dir) if config is None else config
    optional = _get_optional_stages(cfg)
    cycles = _get_cycles(cfg, project_dir)

    # QC gate: block everything if QC incomplete
    qc_ok, qc_missing = _check_qc_sentinels(project_dir)
    if not qc_ok:
        # Return manifest with ALL entries blocked
        ...

    for dep in DATA_DEPENDENCIES:
        blocking_consumers = []
        for consumer_name in dep.consumers:
            stage = PIPELINE_STAGES[consumer_name]
            if stage.is_optional:
                # Conservative: if optional_stages section absent, BLOCK
                if optional is None:
                    blocking_consumers.append(consumer_name)
                elif not optional.get(stage.config_key, {}).get("enabled", False):
                    continue  # Disabled = not blocking
                else:
                    # Enabled: check sentinels
                    ok, missing = _check_stage_sentinels(stage, project_dir, cycles, ...)
                    if not ok:
                        blocking_consumers.append(consumer_name)
            else:
                # Required stage: always check sentinels
                ok, missing = _check_stage_sentinels(stage, project_dir, cycles)
                if not ok:
                    blocking_consumers.append(consumer_name)

        status = "safe" if not blocking_consumers else "blocked"
        manifest.add(CleanupEntry(dir_name=dep.source_dir, status=status, ...))
```

### 3. Staged deletion with trash recovery

```python
def _move_to_trash(dir_path, project_dir, manifest=None):
    """Atomic move to data/.trash/ with JSON receipt."""
    trash_dir = project_dir / "data" / ".trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / f"{dir_path.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.move(str(dir_path), str(dest))
    receipt = {"original_path": str(dir_path), "timestamp": ..., "size_bytes": ...}
    (dest / "receipt.json").write_text(json.dumps(receipt))
    return TrashReceipt(...)

def recover_trash(project_dir, entry_name):
    """Restore from trash with conflict detection."""
    trash_entry = project_dir / "data" / ".trash" / entry_name
    receipt = json.loads((trash_entry / "receipt.json").read_text())
    original = Path(receipt["original_path"])
    if original.exists():
        raise FileExistsError(f"Cannot restore: {original} already exists")
    (trash_entry / "receipt.json").unlink()
    shutil.move(str(trash_entry), str(original))
```

### 4. Config integration for optional stages

```yaml
# workflow/config.yaml
optional_stages:
  vessel3d:
    enabled: false    # Set true if vessel3d planned for this dataset
    cycles: []        # Empty = all cycles; or [2, 3] for subset
  spillover:
    enabled: false    # Placeholder for future stages
```

### 5. CLI commands

```bash
kintsugi workflow cleanup status .          # Show safe/blocked with reasons
kintsugi workflow cleanup plan .            # Dry-run
kintsugi workflow cleanup execute .         # Trash mode (default)
kintsugi workflow cleanup execute . --no-trash --force  # Permanent, no prompt
kintsugi workflow cleanup recover .         # List trash
kintsugi workflow cleanup recover . --entry deconvolved_20260219_143022
kintsugi workflow cleanup purge . --days 7  # Remove old trash
```

### 6. Snakemake DAG integration

```python
# In Snakefile — cleanup_safe rule aggregates all consumer sentinels
rule cleanup_safe:
    input:
        **_cleanup_safe_inputs(),  # QC + EDF + optional vessel3d sentinels
    output:
        sentinel=f"{PROJECT}/data/processed/.cleanup_safe",
    run:
        with open(output.sentinel, "w") as f:
            f.write(f"cleanup_safe {datetime.now().isoformat()}\n")
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| **Single-consumer cleanup script** (`cleanup_datasets.sh` v1) | Only checked EDF completion before deleting `deconvolved/`. vessel3d (added later) also consumes deconvolved data. **Lost 14 datasets.** | Always maintain a dependency graph as single source of truth. Any new consumer of intermediate data must be registered. |
| **Checking sentinels AFTER deleting stitched/** | `stitched/` contains its own `.snakemake_complete` sentinels. Deleting stitched first destroys the evidence needed to verify decon eligibility for raw deletion. | Pre-check ALL sentinel conditions BEFORE deleting anything. Order of operations matters. |
| **`ruleorder` for GPU/CPU fallback in Snakemake** | `ruleorder` does NOT fall back — it always picks the preferred rule. Six rules (3 GPU + 3 CPU) with ruleorder was fundamentally broken. | Use lambda resources within single rules for mode selection, not ruleorder between duplicate rules. |
| **Implicit "not configured = not blocking"** | If `optional_stages` section is absent from config, old logic assumed vessel3d wasn't needed. But absence means "not declared," not "not needed." | Conservative default: absent config = BLOCK with guidance to declare explicitly. Force users to opt out, not opt in. |
| **Registration QC as cleanup prerequisite** | Initially required registration QC sentinel for intermediate cleanup. But registration reads EDF outputs, not intermediates — blocking on registration QC delays cleanup unnecessarily. | Only gate on QC that validates the data being deleted (stitch/decon/edf QC), not downstream QC. |
| **Permanent deletion as default** | First implementation used `shutil.rmtree()` directly. No recovery possible if assessment logic has a bug. | Default to staged deletion (trash) with recovery window. Permanent delete requires explicit `--no-trash` flag. |

## Final Parameters

```yaml
# workflow/config.yaml — optional_stages section
optional_stages:
  vessel3d:
    enabled: false    # MUST be declared explicitly for cleanup to work
    cycles: []        # Empty = all cycles; [2, 3] = only those cycles
  spillover:
    enabled: false    # Future: spillover correction stage

# QC sentinels required for cleanup (registration NOT required):
# qc_plots/.snakemake_complete_stitch
# qc_plots/.snakemake_complete_decon
# qc_plots/.snakemake_complete_edf

# Trash retention: 7 days (configurable via --days N in purge command)
# Trash location: data/.trash/{dir_name}_{YYYYMMDD_HHMMSS}/
```

## Key Insights

- **Dual-consumer dependencies are invisible killers.** When you add an optional stage that consumes existing intermediates, the cleanup logic MUST be updated simultaneously. A dependency graph as code is the only reliable way to enforce this.
- **Conservative defaults save data.** If cleanup can't determine whether an optional stage needs the data, it should block deletion and tell the user how to configure it. Data loss is irreversible; a blocked cleanup is a minor inconvenience.
- **Pre-check before any deletion.** Sentinel files can live inside the directories being deleted. Check everything first, then delete. Don't interleave checks and deletes.
- **Trash staging is cheap insurance.** On the same filesystem, `shutil.move()` is an atomic rename — near-instant regardless of data size. The 7-day recovery window costs nothing (the data was already there) and catches edge cases in assessment logic.
- **QC gating should be minimal.** Only require QC sentinels that validate the specific data being deleted. Requiring downstream QC (registration) blocks cleanup unnecessarily.
- **Per-cycle granularity matters.** Optional stages may only apply to specific cycles (e.g., vessel3d for cycle 2 where CD31 is). The cleanup assessment must support partial cycle requirements, not just all-or-nothing.
- **pytest-asyncio version gotcha.** `pytest-asyncio>=1.0` requires `pytest>=8.0`. If stuck on pytest 7.x, use `-p no:asyncio` for tests that don't need async. The `FixtureDef` import error is the symptom.

## References

- `src/kintsugi/cleanup.py` — Core module (837 lines)
- `tests/test_cleanup.py` — 42 tests
- `src/kintsugi/cli.py` — CLI commands (lines 1654-2050)
- `workflow/Snakefile` — `cleanup_safe` rule (lines 642-689)
- Root CLAUDE.md — Pipeline-Aware Cleanup section
- workflow/CLAUDE.md — Sentinel files reference table
