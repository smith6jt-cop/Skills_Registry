# Batch Orchestration Script (process_remaining.sh)

## Goal

Orchestrate full pipeline processing (stitch -> decon -> EDF -> registration + QC) for 21 remaining KINTSUGI datasets across two SLURM accounts (clive + maigan, 5 GPU slots total), handling heterogeneous project states: stale old-pipeline outputs, unstaged raw data, partially-completed Snakemake runs.

## Context

After completing 13 datasets (4 spleen + 9 thymus batches), 21 datasets remained in mixed states:
- **Group A** (7): Raw staged, need Snakemake config + full pipeline
- **Group B** (6): Raw on /orange, need rsync staging + config + pipeline
- **Stale** (6): Old pipeline outputs (pre-bug-fix), no Snakemake sentinels — must delete processed data and reprocess
- **Resume** (3): Partial Snakemake sentinels — Snakemake will auto-resume

## What Worked

### 5-Phase Architecture

**Phase 1: Clean stale outputs** — Delete `processed/` dirs for 6 old-pipeline projects so Snakemake starts fresh. Creates `.staged` sentinels for projects with raw data but no sentinel.

**Phase 2: Generate configs** — Runs `kintsugi workflow config` for all 21 projects. Idempotent: always overwrites Snakefile + profiles (propagates fixes).

**Phase 3: Stage raw data** — Submits SLURM rsync jobs for Group B (6 datasets, /orange -> /blue). Waits for staging completion before proceeding.

**Phase 4: Process** — Runs Snakemake sequentially for each dataset. Phase 4a processes 15 ready-now datasets; Phase 4b processes 6 Group B datasets after staging.

**Phase 5: Report** — Summary of completed/failed/skipped datasets.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Sequential processing (not parallel) | All datasets share 5 GPU slots — parallel Snakemake instances cause SLURM contention |
| `--phase N` resume | Long-running (~2 days); restart from any phase after interruption |
| `--dataset NAME` filter | Test a single dataset without affecting others |
| `--dry-run` preview | Shows all actions (rm, kintsugi workflow config, snakemake) without executing |
| Per-dataset `snakemake --unlock` before run | Stale locks from killed coordinators block re-runs |
| Project groups (A/B/stale/resume) | Different project states need different preparation steps |
| tmux requirement | Snakemake coordinator is foreground; SSH disconnect kills it |

### Idempotency

- Snakemake sentinel files: skip completed rules automatically
- Per-channel skip-existing: wrapper scripts check individual output files
- `--phase N`: skip already-completed phases on re-run
- Group B staging: checks `.staged` sentinel before rsync

### Snakemake Lock Recovery

When a coordinator dies (tmux detach, OOM, Ctrl-C), the Snakemake lock file persists:
```
LockException: Error: Directory cannot be locked.
```

Fix: `snakemake --unlock` in the project's workflow directory before re-running:
```bash
cd /path/to/project/workflow
snakemake --unlock --profile profiles/slurm
```

The script runs `snakemake --unlock` for each dataset before `snakemake --profile profiles/slurm` to handle this automatically.

## Failed Attempts

| Attempt | Problem | Fix |
|---------|---------|-----|
| Running without tmux | SSH disconnect killed coordinator mid-dataset | Always run in `tmux new -s batch` |
| Parallel Snakemake instances | GPU contention: 5 slots shared across all datasets | Sequential: one dataset at a time |
| Not unlocking before re-run | `LockException` after coordinator death | Pre-run `snakemake --unlock` for each dataset |
| Not cleaning stale projects first | Snakemake saw existing files, skipped rules (old broken outputs) | Phase 1 deletes `processed/` for stale projects |
| Not creating `.staged` sentinel | Snakemake skip logic checks `.staged` — old projects didn't have it | Phase 1 creates `.staged` for projects with raw data |
| Forgetting `--profile profiles/slurm` | Snakemake ran locally instead of submitting to SLURM | Always use `--profile profiles/slurm` |

## Key Files

| File | Purpose |
|------|---------|
| `/blue/maigan/smith6jt/process_remaining.sh` | Master orchestration (5 phases, 21 datasets) |
| `/blue/maigan/smith6jt/run_all_workflows.sh` | Simpler sequential Snakemake runner (no phases/staging) |
| `/blue/maigan/smith6jt/dataset_manifest.csv` | Central registry of all 47 datasets |
| `/blue/maigan/smith6jt/stage_datasets.sh` | SLURM rsync staging (wave-based) |
| `workflow/Snakefile` | Per-project Snakemake DAG |
| `workflow/profiles/slurm/config.yaml` | SLURM executor profile |

## Final Parameters

```bash
# Usage
tmux new -s batch
bash /blue/maigan/smith6jt/process_remaining.sh              # Full run (all 5 phases)
bash /blue/maigan/smith6jt/process_remaining.sh --phase 4    # Resume from processing
bash /blue/maigan/smith6jt/process_remaining.sh --dataset 1901CC2A --dry-run  # Test one
bash /blue/maigan/smith6jt/process_remaining.sh --dry-run    # Preview all

# Snakemake per-dataset (what Phase 4 runs internally)
cd /path/to/project/workflow
snakemake --unlock --profile profiles/slurm    # Clear stale lock
snakemake --profile profiles/slurm -j 5        # Run pipeline (-j = GPU slots)

# Monitor
squeue -u $USER                                # Check SLURM jobs
tail -f /blue/maigan/smith6jt/logs/batch_*/process_remaining.log  # Master log
```

## Environment

- HiPerGator SLURM cluster, 5 GPU slots (3 clive + 2 maigan), B200/Turin GPUs
- Bash 5.x, Snakemake 8.x, KINTSUGI conda env
- ~2 days continuous runtime for 21 datasets (~22 min/cycle GPU)
- Must run inside tmux/screen session
- Estimated total: ~21 datasets x ~9 cycles x ~22 min/cycle = ~69 hours

## Verified On

- Dry-run validated for all 21 datasets (phase 1-5 preview)
- Individual dataset testing via `--dataset` flag
- Lock recovery tested after simulated coordinator kill
