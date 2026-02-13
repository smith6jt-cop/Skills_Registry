---
name: batch-staging-rsync-patterns
description: "Rsync patterns for staging CODEX raw data from orange to blue storage, avoiding cycle directory flattening and bash subshell variable loss"
author: Claude Code
date: 2026-02-11
---

# Batch Staging Rsync Patterns

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-11 |
| **Goal** | Correctly stage 34 CODEX datasets (~9.7 TB) from orange to blue via SLURM batch jobs |
| **Environment** | HiPerGator, orange→blue storage, SLURM batch scheduler |
| **Status** | Success |

## Context
Raw CODEX data on orange storage needs to be copied to blue for processing. Each dataset has cycle directories (`cyc001_reg001_YYMMDD_HHMMSS/`) containing thousands of TIF files. The staging script submits individual SLURM jobs per dataset with throttling to limit concurrent copies.

## Three Bugs Found and Fixed

### Bug 1: Rsync Glob Flattens Cycle Directories (CRITICAL)

**Wrong:**
```bash
rsync -av '${orange_path}'/*/ '${RAW_DIR}/' \
  --include='*/' --include='*.tif' --exclude='*'
```

The `*/` bash glob expands BEFORE rsync runs, producing multiple source args:
```
rsync -av /orange/.../cyc001_reg001_.../ /orange/.../cyc002_reg001_.../ /blue/.../raw/
```

Rsync with trailing `/` on source copies CONTENTS, so all cycle TIFs merge into one flat directory. Files with identical names across cycles overwrite each other silently.

**Correct:**
```bash
rsync -av '${orange_path}/' '${RAW_DIR}/' \
  --include='*/' --include='*.tif' --exclude='*'
```

Using `'${orange_path}/'` (no glob) lets rsync handle the directory tree, preserving `cyc001.../`, `cyc002.../` structure in the destination.

### Bug 2: Count Variable Lost in Pipe Subshell

**Wrong:**
```bash
count=0
tail -n +2 "$MANIFEST" | while IFS=',' read -r ...; do
    count=$((count + 1))
done
echo "Submitted ${count} jobs."  # Always prints 0!
```

`tail | while` runs the loop in a subshell. Variable changes are lost when the subshell exits.

**Correct:**
```bash
count=0
while IFS=',' read -r ...; do
    count=$((count + 1))
done < <(tail -n +2 "$MANIFEST")
echo "Submitted ${count} jobs."  # Correct count
```

Process substitution `< <(...)` keeps the loop in the main shell.

### Bug 3: squeue Wildcard Matching Doesn't Work

**Wrong:**
```bash
squeue -u $USER -n 'kintsugi_stage*' -h | wc -l
```

`squeue -n` matches exact job names, not glob patterns. The `*` is literal.

**Correct:**
```bash
squeue -u "$USER" -h 2>/dev/null | grep -c 'kintsugi_stage'
```

Use `grep -c` for pattern matching on squeue output.

## Rsync Filter Rules Explained

The include/exclude pattern `--include='*/' --include='*.tif' --exclude='*'` works because rsync processes rules in order, first match wins:

| Item | Rule 1: `*/` (dirs) | Rule 2: `*.tif` | Rule 3: `*` (exclude) | Result |
|------|---------------------|-----------------|----------------------|--------|
| `experiment.json` | No | No | **Yes** | EXCLUDED |
| `cyc001_reg001/` | **Yes** | - | - | INCLUDED |
| `cyc001/tile.tif` | No | **Yes** | - | INCLUDED |
| `cyc001/log.txt` | No | No | **Yes** | EXCLUDED |

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `rsync source/*/` with bash glob | Flattens directory structure, overwrites files | Never use bash glob expansion for rsync sources with subdirs |
| `tail \| while` pipe for loop | Variables in subshell are lost | Use process substitution `< <(...)` for loops that update variables |
| `squeue -n 'pattern*'` | `-n` flag is exact match only | Use `squeue -h \| grep -c 'pattern'` for pattern matching |
| Staging all 34 datasets at once | I/O bandwidth saturation, blue storage limits | Throttle with MAX_CONCURRENT=5 |

## SLURM Job Parameters for Staging

```bash
sbatch --job-name="kintsugi_stage_${dataset}" \
    --partition=hpg-default --account=maigan \
    --mem=4gb --cpus-per-task=2 --time=06:00:00 \
    --output="${PROJECT_DIR}/logs/stage_%j.out"
```

- 4 GB memory is sufficient for rsync
- 6-hour time limit handles datasets up to ~500 GB
- `.staged` marker file enables idempotent re-runs

## Key Files
- `/blue/maigan/smith6jt/stage_datasets.sh` — Fixed staging script
- `/blue/maigan/smith6jt/setup_all_projects.sh` — Project setup (runs before staging)
- `/blue/maigan/smith6jt/dataset_manifest.csv` — Manifest from data_discovery.py

## Trigger Conditions
This skill applies when:
- Staging raw data from orange to blue storage
- Writing rsync commands for CODEX cycle directories
- Bash script with SLURM job submission and throttling
- Counter variable unexpectedly zero after while loop
