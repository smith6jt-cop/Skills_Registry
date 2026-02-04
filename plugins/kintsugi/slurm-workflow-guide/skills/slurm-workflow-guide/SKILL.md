---
name: slurm-workflow-guide
description: "Complete 10-step SLURM workflow from raw data to processed results in KINTSUGI"
author: Claude Code
date: 2026-02-02
---

# KINTSUGI SLURM Processing Workflow

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-02 |
| **Goal** | Document complete SLURM workflow from raw data to final evaluation |
| **Environment** | KINTSUGI on HiPerGator HPC cluster |
| **Status** | Success |

## Context
Users needed clear, sequential instructions for processing multiplex imaging data through the SLURM batch system. The previous README jumped directly to configuration without proper context.

## Complete 10-Step Workflow

### Step 1: Prerequisites
- Project created with `kintsugi init --slurm`
- SLURM access configured (account, partition)
- Raw microscopy data ready

### Step 2: Copy Raw Data
```bash
cp -r /path/to/cyc001 data/raw/
cp -r /path/to/cyc002 data/raw/
```
Naming: `cyc001/`, `cyc002/` or long-form `cyc001_DAPI_Blank_Blank_Blank/`

### Step 3: Create Channel Names File
Create `meta/CHANNELNAMES.txt`:
```
DAPI-01
Blank
Blank
Blank
DAPI-02
CD31
CD8
CD45
```

### Step 4: Configure Experiment Metadata
Edit `meta/experiment.json` with microscope parameters:
- tile_rows, tile_cols
- xy_pixel_size, z_step_size (nm)
- numerical_aperture, tissue_refractive_index
- wavelengths

### Step 5: Review SLURM Configuration (Optional)
Edit `slurm/config.sh` for HPC-specific settings if defaults are wrong.

### Step 6: Preview Jobs (Recommended)
```bash
kintsugi slurm submit . --dry-run
```
Verify cycles, tile grid, and wavelengths before submission.

### Step 7: Submit Processing Jobs
```bash
kintsugi slurm submit .                           # All steps
kintsugi slurm submit . --steps correction,stitching  # Specific steps
kintsugi slurm submit . --cycles 1-3              # Specific cycles
```

### Step 8: Monitor Progress
```bash
squeue -u $USER
tail -f slurm/runs/<timestamp>/logs/*.out
kintsugi slurm status .
```

### Step 9: Review QC Images
Location: `slurm/runs/<timestamp>/qc/`
- Correction: Smooth illumination profiles
- Stitching: Tile alignment, no gaps
- Deconvolution: Detail enhancement, no artifacts
- EDF: Sharp features, proper z-selection

### Step 10: Evaluate Results & Next Steps
Output locations:
- `data/processed/corrected/`
- `data/processed/stitched/`
- `data/processed/deconvolved/`
- `data/processed/edf/`

Next: Notebook 3 for signal isolation, Notebook 4 for segmentation.

## Processing Steps Reference

| Step | Script | Description |
|------|--------|-------------|
| 1 | `01_correction.sh` | Illumination correction (BaSiC) |
| 2 | `02_stitching.sh` | Tile stitching |
| 3 | `03_deconvolution.sh` | Richardson-Lucy deconvolution |
| 4 | `04_edf.sh` | Extended depth of focus |

## Key Insights
- Always run `--dry-run` first to verify configuration
- Metadata files (`experiment.json`, `CHANNELNAMES.txt`) are auto-loaded by SLURM scripts
- `slurm/config.sh` is only needed for overrides or HPC-specific settings
- The README at `slurm/README.md` is auto-generated with project name

## Key File
- `src/kintsugi/hpc.py`: `generate_slurm_readme()` function

## Trigger Conditions
This skill applies when:
- User asks how to run SLURM processing
- User needs to set up a new project for HPC
- User is confused about SLURM workflow order
- User asks about experiment.json or CHANNELNAMES.txt

## References
- Generated `slurm/README.md` in each project
- KINTSUGI CLAUDE.md "SLURM Job Submission" section
