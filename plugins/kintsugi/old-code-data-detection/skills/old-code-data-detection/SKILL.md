---
name: old-code-data-detection
description: "Detect processed data produced with old/buggy KINTSUGI code via timestamp forensics"
author: smith6jt
date: 2026-02-22
---

# Old-Code Data Detection

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-22 |
| **Goal** | Identify and delete processed data produced with pre-fix KINTSUGI code across ~48 projects |
| **Environment** | HiPerGator, Python 3.11, KINTSUGI conda env |
| **Status** | Success — 590 GB old-code data identified and deleted across 4 projects |

## Context

KINTSUGI had several critical bugs fixed in Jan–Feb 2026 (deconvolution Tukey window, intensity scaling, BaSiC flatfield, EDF sigma, registration non-rigid params, Frangi Ra formula). Some projects had processed data that was bulk-copied from a local workstation where the old code ran, mixed in with data freshly processed on HiPerGator with the fixed code. No processing version metadata existed in sentinel files or manifests, so provenance had to be inferred from file timestamps.

## Verified Workflow

### Step 1: Establish Fix Dates

```bash
git log --oneline --format='%ai %s' --all | grep -iE '(tukey|apodiz|intensity.scal|flatfield|edf.*sigma|edf.*variance|fallback.copy|non.rigid|frangi)'
```

Critical fix dates:
| Bug | Fix Date | Affected Stage |
|-----|----------|---------------|
| BaSiC negative flatfield | Jan 14, 2026 | stitched/ |
| Decon Tukey apodization + raw_max scaling | Jan 17, 2026 | deconvolved/ |
| EDF sigma on variance map | Jan 21, 2026 | edf/ |
| Registration non-rigid params unpacking | Feb 18, 2026 | registered/ |
| Frangi Ra formula | Feb 21, 2026 | vessel_3d/ |

### Step 2: Timestamp Forensics — Detect Bulk Copies vs Real Processing

**Key insight**: Real HPC processing produces files over hours (decon: 22h for 624 files). Bulk copies (Globus/rsync) produce hundreds of files within seconds.

```bash
# Measure time span of all TIFs in a stage directory
find "$dir" -name "*.tif" -printf '%T@\n' | sort -n | \
  awk 'NR==1{first=$1} END{print NR " files, span = " $1-first " seconds"}'
```

**Thresholds**:
- < 120 seconds for 100+ files → **bulk copy** (provenance unknown)
- Minutes to hours → **real HPC processing** (timestamp = processing date)

### Step 3: Cross-Reference Timestamps Against Fix Dates

For each project+stage combination:
1. If timestamp span indicates bulk copy → **flag as unknown provenance** (assume old code)
2. If real processing AND all files dated after the relevant fix → **clean**
3. If real processing AND some files before fix date → **flag specific pre-fix files**

### Step 4: Check Re-Registration Status

Registration had a specific fix date (Feb 18). Cross-check registered projects against the known re-registration list:

```bash
# List projects validated with re-registration
# From memory: CX_19-001, CX_19-002_R1, CX_19-002_R3, CX_19-003_R1
# Any project NOT in this list with registered/ timestamps as bulk copies = old registration
```

### Step 5: Generate Deletion Script

```bash
#!/usr/bin/env bash
# Pattern: dry-run first, then execute
delete_dir() {
    local dir="$1" reason="$2"
    if [[ -d "$dir" ]]; then
        local human=$(du -sh "$dir" | awk '{print $1}')
        if $DRY_RUN; then
            echo "  WOULD DELETE: $dir ($human) — $reason"
        else
            echo "  DELETING: $dir ($human) — $reason"
            rm -rf "$dir"
        fi
    fi
}
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Checking only file modification dates against fix dates | Bulk-copied files have the COPY timestamp, not processing timestamp | Must first distinguish copies from real processing via time-span analysis |
| Assuming all Feb 2026 data is post-fix | Legacy projects were bulk-copied TO HiPerGator in Feb 2026, but processed locally months earlier | Copy timestamp ≠ processing timestamp — check span pattern |
| Proposing deletion of ALL intermediate data | User only wanted old-code data deleted, NOT general cleanup | Stay focused on the specific ask — old-code detection, not disk cleanup |
| Looking for version metadata in sentinel files | No processing version metadata exists in sentinels or manifests | Sentinel files only record completion, not code version — timestamp forensics is the only option |

## Final Parameters

```bash
# Timestamp span thresholds
BULK_COPY_THRESHOLD=120  # seconds — 100+ files in <2 min = copy

# Fix dates (epoch seconds for comparison)
FIX_BASIC=$(date -d '2026-01-14' +%s)
FIX_DECON=$(date -d '2026-01-17' +%s)
FIX_EDF=$(date -d '2026-01-21' +%s)
FIX_REGISTRATION=$(date -d '2026-02-18' +%s)
FIX_FRANGI=$(date -d '2026-02-21' +%s)

# Stage-to-fix mapping
# stitched/     → FIX_BASIC
# deconvolved/  → FIX_DECON
# edf/          → FIX_EDF
# registered/   → FIX_REGISTRATION
# vessel_3d/    → FIX_FRANGI
# signal_isolated/ → depends on registered/ (if registered is old, signal isolation is invalid)
```

## Key Insights

- **590 GB of old-code data found across 3 legacy projects** (1904CC1-1L, 1901CC2A, 1901CC3C) — all bulk-copied from local workstation
- **Timestamp span is the definitive signal**: 469 files in 59 seconds = copy; 624 files in 22 hours = real processing
- **Signal isolation built on old registered data is also invalid** — cascading invalidation
- **No version metadata exists in KINTSUGI sentinels** — future improvement would be to add `algorithm_version` and `git_commit` fields to all sentinel files
- **Legacy project names (1901CC2A, 1904CC1-1L) vs CX_ naming** helped identify likely locally-processed datasets
- **Mixed timestamps within registered/** indicate partial re-registration — check individual files, not just the directory

## Results

| Project | Deleted | Size | Reason |
|---------|---------|------|--------|
| 1904CC1-1L | stitched, deconvolved, edf, registered, signal_isolated | 333G | All stages bulk-copied, old code |
| 1901CC2A | stitched, deconvolved | 256G | Bulk-copied, old code |
| 1901CC3C | stitched (partial) | 4.7G | Partial bulk copy |
| src_CX_19-002_spleen_CC3-C | 3 registered TIFs (cyc09) | 432M | Pre-registration-fix (Feb 15) |

**Total deleted: 590 GB**

## References

- KINTSUGI `CLAUDE.md` Critical Fixes table — lists all bug fixes with dates
- `scripts/reprocess_striped_zplanes.py` — targeted reprocessing for stripe artifacts
- `reregister_all.sh` — batch re-registration with tuned non-rigid parameters
- `multi-project-batch-isolation` skill — multi-project signal isolation after clean reprocessing
