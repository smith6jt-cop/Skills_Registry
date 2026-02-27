---
name: stale-script-remediation
description: "Bulk-update stale workflow scripts across KINTSUGI projects. Trigger: scripts not propagating, QC failures, batch stalls after code updates."
author: smith6jt
date: 2026-02-27
---

# Stale Script Remediation

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-27 |
| **Goal** | Fix stale workflow scripts across all 35 configured KINTSUGI projects and clear stale locks to unblock batch processing |
| **Environment** | HiPerGator HPC, KINTSUGI Snakemake workflow, 47 total projects |
| **Status** | Success |

## Context

`kintsugi workflow config` only copies `workflow/scripts/*.py` to projects **if they don't already exist**. This means updates to scripts in the repo (e.g., adding signal isolation support to `qc_report.py`, updating `log_utils.py` with SI directory logging) never propagate to existing projects. This caused `qc_signal_isolation` failures in production (1901CC2A) and would affect all future processing.

## The Problem

| Script | Stale Count | Impact |
|--------|-------------|--------|
| `log_utils.py` | 35 / 35 | Missing SI directory logging — affects all QC reports |
| `registration.py` | 15 / 35 | Older non-rigid params (completed projects only) |
| `vessel3d.py` | 8 / 35 | Older vessel3d script |
| `edf.py` | 2 / 35 | Older EDF code |
| `stitch.py` | 2 / 35 | Older stitch code |
| `Snakefile` | 6 / 41 | Different architecture (empty `src_CX_21-*` projects) |

**Detection method**: MD5 comparison loop between repo source and deployed copies:
```bash
for proj_scripts in ../KINTSUGI_Projects/*/workflow/scripts/; do
    [ -d "$proj_scripts" ] || continue
    proj=$(basename "$(dirname "$(dirname "$proj_scripts")")")
    for script in deconvolve.py edf.py log_utils.py qc_report.py registration.py \
                  signal_isolation.py spillover_correction.py stitch.py vessel3d.py; do
        repo_md5=$(md5sum workflow/scripts/"$script" | awk '{print $1}')
        dep_md5=$(md5sum "$proj_scripts/$script" 2>/dev/null | awk '{print $1}')
        [ "$repo_md5" != "$dep_md5" ] && echo "STALE: $proj/$script"
    done
done
```

## Verified Workflow

### Step 1: Bulk-copy ALL scripts
```bash
for proj_scripts in ../KINTSUGI_Projects/*/workflow/scripts/; do
    [ -d "$proj_scripts" ] || continue
    for script in deconvolve.py edf.py log_utils.py qc_report.py registration.py \
                  signal_isolation.py spillover_correction.py stitch.py vessel3d.py; do
        cp workflow/scripts/"$script" "$proj_scripts/$script"
    done
done
```

### Step 2: Update stale Snakefiles (if applicable)
```bash
for proj in src_CX_21-012_LN_n3 src_CX_21-012_SP-CC3-A ...; do
    cp workflow/Snakefile ../KINTSUGI_Projects/$proj/workflow/Snakefile
done
```

### Step 3: Clear stale Snakemake locks
```bash
# First verify no snakemake processes running
ps aux | grep snakemake
squeue -u $USER

# Then clear locks
for proj in project1 project2; do
    rm -rf ../KINTSUGI_Projects/$proj/workflow/.snakemake/locks
    rm -rf ../KINTSUGI_Projects/$proj/.snakemake/locks
done

# Verify
find ../KINTSUGI_Projects -path '*/.snakemake/locks/*' -type f
```

### Step 4: Verify with MD5 loop
Re-run the detection loop — should report `Total stale scripts: 0`.

### Step 5: Launch batch processing
```bash
kintsugi workflow batch ../KINTSUGI_Projects --dry-run  # Confirm eligibility
kintsugi workflow batch ../KINTSUGI_Projects --detach -p 2
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Copying only the one failing script (qc_report.py) | Other scripts also stale — next failure on different script | Always copy ALL scripts, not just the one that failed |
| Deleting scripts and re-running `workflow config` | Config also regenerates Snakefile/profiles — may overwrite customizations | Direct `cp` is safer and more targeted |
| Expecting `workflow config` to update scripts | By design it only copies if missing (`[ -f target ] || cp`) | This is a feature, not a bug — prevents accidental overwrites of user customizations |
| Not checking for stale locks after clearing scripts | Locks from previous failed runs block new batch | Always check for and clear stale locks as part of remediation |

## Final Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Scripts to copy | All 9 Python scripts | Complete remediation, not incremental |
| Copy method | Direct `cp` (overwrites) | Faster than delete+reconfig, preserves other config |
| Lock detection | `find -path '*/.snakemake/locks/*'` | Catches both workflow/ and project-root locks |
| Lock safety check | `ps aux | grep snakemake` + `squeue` | Prevents removing locks from active processes |
| Verification | MD5 comparison loop | Cryptographic proof of exact match |

## Key Insights

- `workflow config` is conservative by design — it protects user customizations by not overwriting existing scripts
- This creates a maintenance burden: every script update requires a bulk-copy pass
- The MD5 detection loop should be run periodically (or before batch launches) to catch drift
- Lock files in TWO locations: `workflow/.snakemake/locks/` AND `project-root/.snakemake/locks/`
- Stale `log_utils.py` was universal (35/35) because it was updated after all projects were configured
- Snakefile staleness was limited to 6 empty projects with a different workflow architecture

## Results

| Metric | Before | After |
|--------|--------|-------|
| Stale scripts | 62 across 9 types | 0 |
| Stale Snakefiles | 6 | 0 |
| Stale locks | 3 projects | 0 |
| Batch-eligible datasets | 8 (blocked) | 8 (processing) |
| GPU utilization | 0% (idle) | 100% (2 running + 6 queued) |

## References

- `workflow/CLAUDE.md` — "Stale script deployment hazard" section
- MEMORY.md — "Stale Script Deployment & Bulk Remediation" section
- Skill `old-code-data-detection` — related pattern for detecting stale processed data
