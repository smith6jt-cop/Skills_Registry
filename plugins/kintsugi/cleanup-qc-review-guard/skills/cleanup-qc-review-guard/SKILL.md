---
name: cleanup-qc-review-guard
description: "Guard pattern for cleanup scripts: verify QC sentinel files and prompt for human review before destructive operations"
author: Claude Code
date: 2026-02-16
triggers:
  - cleanup
  - delete intermediates
  - delete raw data
  - QC sentinel check
  - batch cleanup safety
  - destructive operations guard
---

# Cleanup QC Review Guard

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-16 |
| **Goal** | Prevent premature deletion of intermediate/raw data before QC has been reviewed |
| **Environment** | HiPerGator, KINTSUGI batch processing pipeline |
| **Status** | Implemented |

## Context
The batch processing pipeline produces hundreds of GB of intermediate files (stitched/, deconvolved/) per dataset. After EDF outputs are verified, `cleanup_datasets.sh` deletes these intermediates and the staged raw data. Without a guard, cleanup could proceed before QC reports have been reviewed — meaning processing errors would only be discovered after the data needed to reprocess has been deleted.

## The Problem

`cleanup_datasets.sh` originally only checked:
1. EDF output files exist (count matches expected)
2. Not already cleaned (`.complete` sentinel)

Missing check: whether QC reports had been **generated** and **reviewed** by a human.

## Solution: Three-Layer Guard

### Layer 1: QC Sentinel Verification
Check that all 3 Snakemake QC rules have completed:

```bash
check_qc_sentinels() {
    local project_dir="$1"
    local qc_dir="${project_dir}/qc_plots"
    local missing=()

    for stage in stitch decon edf; do
        if [ ! -f "${qc_dir}/.snakemake_complete_${stage}" ]; then
            missing+=("${stage}")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        echo "  QC incomplete — missing sentinels: ${missing[*]}"
        return 1
    fi
    return 0
}
```

Sentinel files checked:
- `qc_plots/.snakemake_complete_stitch`
- `qc_plots/.snakemake_complete_decon`
- `qc_plots/.snakemake_complete_edf`

### Layer 2: Interactive Review Prompt
After sentinel verification, prompt the user to confirm they've reviewed the QC reports:

```bash
if [ "${FORCE}" = false ]; then
    echo "  QC reports: ${PROJECT_DIR}/qc_plots/"
    read -p "  Have you reviewed the QC reports? [y/N] " -r response
    if [[ ! "${response}" =~ ^[Yy]$ ]]; then
        skipped=$((skipped + 1))
        echo "  Skipped (QC not reviewed)"
        continue
    fi
fi
```

### Layer 3: --force Flag for Re-runs
After initial review, subsequent runs can use `--force` to skip prompts:

```bash
./cleanup_datasets.sh --force      # Skip prompts (QC sentinels still checked!)
./cleanup_datasets.sh --dry-run    # Preview without deleting (prompts shown but don't block)
```

**Important**: `--force` only skips the interactive prompt. QC sentinel verification (Layer 1) is ALWAYS enforced — datasets with missing QC sentinels are always skipped.

## Option Parsing Pattern

```bash
DRY_RUN=false
FORCE=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --force)   FORCE=true ;;
        *)         echo "Unknown option: $arg"; echo "Usage: $0 [--dry-run] [--force]"; exit 1 ;;
    esac
done
```

## Summary Tracking

Track separate counters for each skip reason:

```bash
cleaned=0
not_ready=0        # No EDF outputs yet
qc_incomplete=0    # Missing QC sentinel files
skipped=0          # User declined review prompt
errors=0           # EDF count mismatch after cleanup

echo "Cleanup summary:"
echo "  Cleaned:       ${cleaned}"
echo "  Not ready:     ${not_ready} (no EDF outputs yet)"
echo "  QC incomplete: ${qc_incomplete} (missing QC sentinels)"
echo "  Skipped:       ${skipped} (QC not reviewed)"
echo "  Errors:        ${errors}"
```

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| No QC check at all (original script) | Could delete intermediates before QC reports even existed, let alone reviewed | Always verify QC completion before destructive operations |
| Checking only for QC PDFs (not sentinels) | PDFs may exist from a partial/failed QC run | Sentinel files are authoritative — only created on successful completion |
| Making `--force` skip sentinel checks too | Would defeat the purpose entirely | `--force` should only skip human-in-the-loop prompts, never safety checks |

## Key Insights
- **Sentinel files are authoritative** — they're created by Snakemake only on rule success, unlike output files which may be partial
- **Separate "not ready" from "QC incomplete"** — users need to know whether processing or QC needs to run
- **`--force` must not bypass sentinel checks** — it only removes the interactive prompt for efficiency on re-runs
- **`--dry-run` shows what would be prompted** — helps users verify the guard logic without risk
- **Default-deny** (`[y/N]`) — empty input or anything other than `y`/`Y` skips the dataset

## Related Skills
- `batch-staging-rsync-patterns` - Staging scripts that feed into cleanup
- `qc-plot-pdf-export` - QC report generation that must complete before cleanup
- `snakemake-workflow-architecture` - QC aggregate rules that create sentinel files

## References
- `/blue/maigan/smith6jt/cleanup_datasets.sh` — Cleanup script with QC guard
- `workflow/CLAUDE.md` — Sentinel file reference, pipeline lifecycle
- `notebooks/Kprocess.py` — `run_stitched_qc()`, `run_decon_qc()`, `run_edf_qc()` generate QC reports
