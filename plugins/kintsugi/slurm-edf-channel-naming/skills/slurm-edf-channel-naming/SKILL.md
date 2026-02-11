---
name: slurm-edf-channel-naming
description: "SLURM EDF job must use marker names from CHANNELNAMES.txt for output files. Trigger: EDF output naming, SLURM job producing CH#_edf.tif instead of marker names, downstream _find_edf_file failures"
author: Claude Code
date: 2026-02-11
---

# SLURM EDF Channel Naming Fix

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-11 |
| **Goal** | Fix EDF SLURM job to name output files by marker (e.g., `CD3.tif`) instead of `CH1_edf.tif` |
| **Environment** | HiperGator HPC, SLURM, Python 3.10+, KINTSUGI pipeline |
| **Status** | Success |

## Context

The notebook's `process_edf_tiff` function (Notebook 2, cell 31) names EDF output files using marker names loaded from `CHANNELNAMES.txt`:

```python
# Notebook convention (correct)
out_path = os.path.join(dest_dir, f"{channel_name}.tif")  # e.g., "CD3.tif"
```

The SLURM job script (`slurm/jobs/04_edf.sh`) was hardcoding numeric names:

```python
# SLURM script (broken)
output_file = output_path / f"CH{ch}_edf.tif"  # e.g., "CH1_edf.tif"
```

This caused two problems:
1. Only one recognizable output file (downstream code couldn't find others)
2. `_find_edf_file()` in `Kview_qc.py` has 5 search strategies and none match `CH#_edf.tif`

## Verified Workflow

### Loading Channel Names in SLURM Jobs

```python
# Add after metadata loading section in any SLURM job script
from Kio import load_channel_names

channels_per_cycle = experiment_config.get('channels_per_cycle', END_CHANNEL)
channel_name_dict = load_channel_names(
    PROJECT_DIR / 'meta',
    channels_per_cycle=channels_per_cycle
)
if channel_name_dict:
    cycle_names = channel_name_dict.get(CYCLE, [])
else:
    cycle_names = []

def get_channel_name(ch):
    """Get marker name for channel, with CH# fallback."""
    idx = ch - 1
    if cycle_names and idx < len(cycle_names):
        return cycle_names[idx]
    return f"CH{ch}"
```

### Correct EDF Output Naming

```python
# Output: edf/cyc01/CD3.tif (not CH1_edf.tif)
ch_name = get_channel_name(ch)
output_file = output_path / f"{ch_name}.tif"
```

### Downstream Compatibility

`_find_edf_file()` in `Kview_qc.py` searches in this priority:
1. `{channel_name}.tif` (Strategy 1 - preferred, matches marker-named output)
2. `CH#/edf.tif` (Strategy 2 - legacy subdirectory structure)
3. `CH#.tif` (Strategy 3 - channel-numbered files)
4. Nth file by index (Strategy 4 - positional fallback)
5. First available file (Strategy 5 - last resort)

The `CH#_edf.tif` pattern matched **none** of these strategies.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `CH{ch}_edf.tif` naming | Not recognized by any `_find_edf_file` strategy | Must match notebook naming convention exactly |
| Not loading CHANNELNAMES.txt | No marker names available for file naming | SLURM jobs need same metadata as notebooks |
| Skipping `check_cycle_complete` update | Would look for old `CH#_edf.tif` names | All file references must be updated together |
| `from Kio import` with only `PROJECT_DIR/notebooks` on sys.path | `Kio.py` lives in main repo, not synced to project notebooks | Must add `KINTSUGI_DIR/notebooks` to sys.path in SLURM jobs |
| `MEM_EDF=16` (default) for large datasets | OOM kill (exit 137) after first channel — 3.6 GB per z-stack needs ~48 GB | EDF memory must match deconvolution memory; default 16 GB only works for small tiles |

## Key Insights

- **SLURM jobs must match notebook output conventions** - downstream QC, visualization, and analysis code expects specific file naming patterns
- **`Kio.load_channel_names()` is the canonical parser** - don't reinvent channel name loading; import from `Kio.py` which handles all CHANNELNAMES.txt formats
- **`sys.path` needs both notebook dirs** - SLURM job scripts must add both `PROJECT_DIR/notebooks` and `KINTSUGI_DIR/notebooks` to `sys.path`
- **Always provide CH# fallback** - if CHANNELNAMES.txt is missing, fall back to `CH{ch}` rather than failing
- **Update ALL file references** - when changing output naming, also update `check_cycle_complete()`, QC image names, and log messages
- **SLURM sys.path must include `KINTSUGI_DIR/notebooks`** - project notebooks dirs only contain synced subset files; `Kio.py`, `Kprocess.py`, etc. live in the main repo's notebooks dir and are NOT always synced to projects
- **EDF memory must match deconvolution memory** - EDF loads the same z-stacks as decon (~3-4 GB per channel for 5x5 grids); default 16 GB causes OOM (exit 137) after the first channel

## References

- `slurm/jobs/04_edf.sh` - Fixed EDF SLURM job script
- `notebooks/2_Cycle_Processing.ipynb` cell 31 - `process_edf_tiff` reference implementation
- `notebooks/Kview_qc.py:108-184` - `_find_edf_file()` search strategies
- `notebooks/Kio.py:39-193` - `load_channel_names()` parser
- `Skills_Registry/plugins/kintsugi/channel-name-parsing/` - Channel name parsing skill
