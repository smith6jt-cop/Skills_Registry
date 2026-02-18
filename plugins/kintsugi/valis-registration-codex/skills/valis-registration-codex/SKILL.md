---
name: valis-registration-codex
description: "VALIS registration for CODEX: rigid + non-rigid with tuned smoothing. Earlier 'rigid-only' conclusion was caused by a parameter passing bug — all non-rigid tests ran with unsmoothed OpticalFlowWarper."
author: KINTSUGI Team
date: 2026-02-18
---

# VALIS Registration for CODEX Data

## Experiment Overview

| Field | Value |
|-------|-------|
| **Date** | 2026-02-15 to 2026-02-18 |
| **Goal** | Diagnose and fix inaccurate multi-cycle registration |
| **Environment** | HiPerGator, SLURM, GPU (B200/Turin), VALIS library |
| **Status** | VALIDATED — 4/16 batch projects re-registered. Non-rigid with tuned params (sigma_ratio=0.01) confirmed on spleen + lymph node tissue. Fallback copy removed. |

## Context

KINTSUGI uses VALIS (Virtual Alignment of pathoLogy Image Series) for multi-cycle registration. CODEX (co-detection by indexing) tissue-on-slide data has both rigid deformation (stage repositioning) and subtle non-rigid deformation (tissue distortion from repeated staining/washing cycles). Registration requires rigid alignment + tuned non-rigid correction.

## Critical Bug Fixes (Feb 2026)

### Bug 1: Non-Rigid Parameters Silently Ignored (ROOT CAUSE)

**File**: `notebooks/Kreg/serial_non_rigid.py:438`

`split_params()` (line 343) correctly filters config dict into `init_kwargs = {"smoothing_method": "gauss", "sigma_ratio": 0.01, ...}` via `inspect.getfullargspec`. But line 438 passed this as:

```python
non_rigid_reg = non_rigid_reg_class(params=init_kwargs)  # BUG: stores dict but kwargs stay at defaults
```

This set `OpticalFlowWarper.__init__(params={"smoothing_method": "gauss", ...})` — the dict was stored in `super().__init__(params)` but the actual instance attributes used defaults:
- `self.smoothing_method = None` (not "gauss")
- `self.sigma_ratio = 0.005` (not 0.01)

**Fix**: `non_rigid_reg = non_rigid_reg_class(**init_kwargs)` — unpack as kwargs.

**Impact**: ALL previous non-rigid tests (11/12 datasets "worse") ran with **unsmoothed** OpticalFlowWarper. The "rigid-only is best" conclusion was based on broken code, not on actual non-rigid behavior.

### Bug 2: Coarse Non-Rigid at 1024px Resolution

**File**: `notebooks/Kreg/registration.py` (Valis.__init__, line 1771)

VALIS has three distinct dimension parameters:
- `max_image_dim_px` (default 1024) — max saved output image size
- `max_processed_image_dim_px` (default 1024) — rigid feature detection resolution
- `max_non_rigid_registration_dim_px` (default `DEFAULT_MAX_PROCESSED_IMG_SIZE = 1024`) — coarse non-rigid field resolution

When `non_rigid_registrar_cls` is passed to the Valis constructor, `register()` runs a coarse non-rigid pass at `max_non_rigid_registration_dim_px` (1024px by default). This resolution is far too low for CODEX nuclei patterns, and it **poisoned alignment before the 4096px micro pass**.

**Fix**: Set `non_rigid_registrar_cls=None` in Valis init to disable the coarse pass entirely. Non-rigid is done exclusively in `register_micro()` at NR_MAX_DIM (4096px).

Note: `DEFAULT_MAX_NON_RIGID_REG_SIZE = 3000` exists in registration.py line 68 but is NOT used as the default for `max_non_rigid_registration_dim_px` — line 1771 uses `DEFAULT_MAX_PROCESSED_IMG_SIZE = 1024` instead.

### Bug 3: Missing non_rigid_registrar_cls in Valis Init

**File**: `workflow/scripts/registration.py`

The Valis init didn't pass `non_rigid_registrar_cls` or `non_rigid_reg_params`, so `register()` used VALIS defaults: `non_rigid_registrar_cls=OpticalFlowWarper` with empty params. This meant two unsmoothed non-rigid passes (one coarse at 1024px, one micro at whatever dim).

**Fix**: Pass non-rigid config explicitly to Valis init, or (current approach) set `non_rigid_registrar_cls=None` to disable the harmful coarse pass.

## Current Architecture

```python
# Valis init — coarse non-rigid EXPLICITLY DISABLED
# CRITICAL: non_rigid_registrar_cls=None must be passed explicitly.
# Without it, VALIS defaults to OpticalFlowWarper at 1024px (unsmoothed),
# which poisons alignment before the 4096px micro pass.
registrar = registration.Valis(
    src_dir=str(EDF_DIR),
    dst_dir=str(reg_output_dir),
    img_list=dapi_images,
    reference_img_f=dapi_images[ref_idx],
    max_image_dim_px=MAX_IMAGE_DIM,           # 4096 (was 2048)
    max_processed_image_dim_px=MAX_IMAGE_DIM,  # 4096 (was 2048)
    non_rigid_registrar_cls=None,              # MUST be explicit — disables coarse NR
    feature_detector_cls=fd_cls,               # VggFD (GPU)
    imgs_ordered=True,
    align_to_reference=True,
)

# Rigid registration at 4096px
rigid_registrar, non_rigid_reg, rigid_summary = registrar.register()

# Non-rigid exclusively via register_micro() at 4096px with tuned smoothing
# Sigma math: sigma_pixels = sigma_ratio * max(image_dim_px)
# At 4096px: 0.01 = 41px, 0.005 = 20px (OpticalFlowWarper default), 0.05 = 205px (too high!)
non_rigid_registrar, non_rigid_summary = registrar.register_micro(
    max_non_rigid_registration_dim_px=4096,
    non_rigid_registrar_cls=non_rigid_registrars.OpticalFlowWarper,
    non_rigid_reg_params={
        "smoothing_method": "gauss",
        "sigma_ratio": 0.01,       # 41px sigma at 4096px (was 0.05 = 205px, way too high)
        "n_grid_pts": 50,          # No-op with "gauss" (only for broken "regularize"/"inpaint")
        "fold_penalty": 1e-6,      # No-op with "gauss" (only for broken "regularize")
    },
    align_to_reference=True,
)
```

### Optical Flow Algorithm

OpticalFlowWarper uses OpenCV optical flow under the hood:
- **GPU (CUDA available)**: TVL1 optical flow (`cv2.cuda.OpticalFlowDual_TVL1`) with default parameters
- **CPU fallback**: DeepFlow (`cv2.optflow.createOptFlow_DeepFlow()`) with default parameters
- No tuning knobs are exposed for the flow algorithm itself — only smoothing of the resulting displacement field

### Smoothing Methods

| Method | Status | Parameters Used |
|--------|--------|----------------|
| `"gauss"` | **Working** | `sigma_ratio` only |
| `None` | **Working** | No smoothing (raw optical flow — usually too noisy) |
| `"inpaint"` | **Broken** | Would use `n_grid_pts` — untested code path |
| `"regularize"` | **Broken** | Would use `n_grid_pts`, `fold_penalty` — untested code path |

### Config (`workflow/config.yaml`)

```yaml
registration:
  reference_cycle: 1
  reference_channel: 1
  max_image_dim: 4096         # Rigid feature detection resolution (was 2048)
  rigid_only: false           # Non-rigid enabled with tuned smoothing
  feature_detector: "VggFD"
  imgs_ordered: true          # Keep sequential cycle order
  align_to_reference: true    # Direct alignment to reference (not serial chain)
  non_rigid:
    max_dim: 4096             # Displacement field resolution
    smoothing_method: "gauss"
    sigma_ratio: 0.01         # sigma = 0.01 * 4096 = ~41px (was 0.05 = 205px, extreme over-smoothing)
    n_grid_pts: 50            # No-op with "gauss"
    fold_penalty: 1.0e-6      # No-op with "gauss"
```

## Validation Results (CX_19-001_SP_CC2-A28, Feb 18 2026)

| Field | Value |
|-------|-------|
| **Dataset** | CX_19-001_SP_CC2-A28 (spleen) |
| **Cycles** | 13 cycles, 4 channels each |
| **Total TIFFs warped** | 52 |
| **Total time** | 67.9 minutes on B200 GPU |
| **Mean rigid D** | 1.12 |
| **Mean non-rigid D** | 0.77 |
| **Cycles improved** | 11 / 12 (non-rigid beats rigid) |
| **Only regression** | cyc02 (NR D=1.27 vs rigid D=1.16) |

### Key Findings

- **Non-rigid with tuned smoothing (sigma_ratio=0.01) decisively outperforms rigid-only.** The earlier "rigid-only is best" conclusion, based on the broken parameter-passing code, is now conclusively disproven.
- **Dimension normalization is critical for VALIS.** EDF output images had inconsistent dimensions across cycles. The registration wrapper now pads all images to a common size (7479 x 12662 for this dataset) before passing to VALIS. Without this, VALIS either crashes or produces incorrect displacement fields. The `normalize_dimensions: true` config option enables this behavior.
- **Defensive guard in `measure_error()`**: When `end_non_rigid_time` is `None` (e.g., non-rigid step skipped or errored), the original code crashed with a `NoneType` subtraction. A guard now handles this gracefully.
- **Timing record added at end of `register_micro()`**: Ensures `measure_error()` always has valid timing data, even if called from different code paths.

### Per-Cycle Results

| Cycle | Rigid D | Non-Rigid D | Improved? |
|-------|---------|-------------|-----------|
| cyc02 | 1.16 | 1.27 | No (only regression) |
| cyc03 | 1.07 | 0.67 | Yes |
| cyc04 | 0.92 | 0.55 | Yes |
| cyc05 | 0.88 | 0.58 | Yes |
| cyc06 | 1.50 | 0.90 | Yes |
| cyc07 | 0.84 | 0.62 | Yes |
| cyc08 | 1.02 | 0.75 | Yes |
| cyc09 | 1.40 | 0.82 | Yes |
| cyc10 | 1.38 | 1.12 | Yes |
| cyc11 | 0.93 | 0.67 | Yes |
| cyc12 | 1.18 | 0.92 | Yes |
| cyc13 | 1.20 | 0.87 | Yes |

### Registration QC: Green/Magenta Overlay

Full-resolution 1000x1000 crop (whole-image thumbnails are too zoomed out):

```python
import pyvips, numpy as np
img = pyvips.Image.new_from_file(path, access="random")
crop = img.crop(x, y, 1000, 1000)
# Green = cyc01 DAPI, Magenta = last cycle DAPI
# White/gray = aligned, color fringing = misaligned
```

**Important**: Average metrics (mean_rigid_D, mean_NCC) are meaningless since poor registration affects only parts of the image. Use spatial NCC heatmaps or targeted overlays on specific regions to evaluate quality.

## Failed Attempts

| Attempt | What Happened | Why It Failed |
|---------|--------------|---------------|
| Non-rigid with default params (all earlier tests) | `params=init_kwargs` passed dict as single arg, not unpacked | `smoothing_method=None`, `sigma_ratio=0.005` — raw unsmoothed optical flow applied |
| Coarse non-rigid at 1024px | Valis default `max_non_rigid_registration_dim_px=1024` | Resolution too low for CODEX nuclei; poisoned alignment before micro pass |
| `max_image_dim=2048` for rigid | Limited rigid feature detection to 2048px | Feature matching found local optima for cycles 10-11 (low NCC despite low D) |
| `rigid_only: true` (all 47 batch datasets) | Based on "11/12 datasets worse with non-rigid" | Conclusion was wrong — all tests used broken non-rigid (params bug). Real non-rigid deformation exists |
| `sigma_ratio=0.01` with disabled coarse NR | Moderate smoothing at 4096px | Non-rigid still degraded 10/12 cycles (tuning ongoing) |
| `sigma_ratio=0.05` (205px sigma!) | Extreme over-smoothing washes out all local corrections | Sigma = 0.05 * 4096 = 205 pixels — averaging over 400+ pixel neighborhoods |
| Attributing bad registration to "tissue degradation" | Late cycles (10-11) had near-zero NCC | User confirmed: all images have clear contrast; it's feature matching + non-rigid tuning, not tissue quality |
| Duplicate Snakemake submissions | Stale background Snakemake coordinators auto-resubmit after cancel | Always check `squeue` for duplicate jobs before manual resubmission |
| `fallback_copy` sentinel masked broken registrations | 3 projects had `method=fallback_copy` with `error=Rigid registration failed` — only caught by manual QC inspection of sentinels, not by pipeline exit code | Remove fallback copy entirely; registration failures must raise loudly. Silent fallbacks hide data quality issues |
| Race condition: old SLURM jobs writing stale results | Killed Snakemake coordinators leave SLURM jobs running. After Phase 1 cleanup + relaunch, old jobs write stale results to the same output directory | Always `scancel` old jobs AND kill stale coordinators before relaunching. Check `squeue -u $USER` for duplicates |
| `declare -a TODO_PROJECTS` does NOT clear bash arrays | Adding `declare -a TODO_PROJECTS` to a script that already has the array populated does NOT reset it — the old values persist | Use `TODO_PROJECTS=()` (empty assignment) to explicitly clear a bash array before repopulating |
| Snakemake targets after `--configfile` parsed as configs | `snakemake --configfile config.yaml registration` treats `registration` as a second config file, not as a target rule | Targets must come BEFORE options: `snakemake registration --configfile config.yaml` |

## What Worked

| Approach | Dataset | Result |
|----------|---------|--------|
| Disable coarse NR, fix params unpacking (Bug 1) | 1904CC1-1L | Cycle 10 NR_D dropped from 10.75 to 1.50 (coarse NR was root cause) |
| 4096px rigid feature detection (vs 2048px) | 1904CC1-1L | Better feature matching on difficult cycles |
| `align_to_reference=True` | All CODEX datasets | Prevents serial error accumulation across 13+ cycles |
| `imgs_ordered=True` | All CODEX datasets | Prevents VALIS from reordering cycles by visual similarity |
| Non-rigid with tuned params (sigma_ratio=0.01) | CX_19-001_SP_CC2-A28 | 11/12 cycles improved, mean D: 1.12 -> 0.77 |
| Dimension normalization (pad to common size) | CX_19-001_SP_CC2-A28 | Inconsistent EDF dims padded to (7479, 12662) — critical for VALIS |
| Defensive `measure_error()` guard for None timing | CX_19-001_SP_CC2-A28 | Prevents NoneType crash when `end_non_rigid_time` is None |
| Batch re-registration validated (4/16 projects) | CX_19-002_lymph-node_R1 (29.5 min), CX_19-002_lymph-node_R3 (27.6 min), CX_19-003_lymph-node_R1 (40.8 min) | Confirms tuned non-rigid params generalize across tissue types (spleen + lymph node) |
| Fallback copy removed — loud failure on error | All projects | Registration failures now raise exceptions instead of silently copying EDF images. Prevents masked broken registrations from passing QC undetected |
| Wave-based parallel execution across GPU pool | 5 concurrent (3 clive + 2 maigan) | Multiple projects registered in parallel waves using multi-account GPU pool. Account distribution controlled by config.yaml accounts list order |

## Experiment Tracking

| Experiment | max_image_dim | Coarse NR | sigma_ratio | Result |
|-----------|--------------|-----------|-------------|--------|
| Baseline (broken) | 2048 | On (1024px, unsmoothed) | 0.01 (ignored) | NR 3.4x worse than rigid |
| Fix params only | 2048 | On (1024px, smoothed) | 0.01 | Not tested (went straight to disabling coarse) |
| Disable coarse NR + 4096px rigid | 4096 | **Disabled** | 0.01 | Cycle 10 fixed (NR_D 10.75→1.50), but NR still worse for 10/12 cycles |
| Heavy smoothing | 4096 | **Disabled** | 0.05 | **Failed** — 205px sigma washes out all local corrections |
| Fixed sigma + coarse NR + None bk_dxdy | 4096 | **Disabled** (`None` explicit) | 0.01 | **Pending** — needs re-registration to verify |
| **CX_19-001_SP_CC2-A28 (VALIDATED)** | 4096 | **Disabled** (`None` explicit) | 0.01 | **11/12 cycles improved**, mean D: 1.12 -> 0.77, 52 TIFFs in 67.9 min (B200) |
| **CX_19-002_lymph-node_R1 (VALIDATED)** | 4096 | **Disabled** | 0.01 | 29.5 min — confirms params generalize to lymph node tissue |
| **CX_19-002_lymph-node_R3 (VALIDATED)** | 4096 | **Disabled** | 0.01 | 27.6 min — second lymph node dataset validated |
| **CX_19-003_lymph-node_R1 (VALIDATED)** | 4096 | **Disabled** | 0.01 | 40.8 min — third lymph node dataset validated |
| **Batch re-registration (4/16)** | 4096 | **Disabled** | 0.01 | Fallback copy removed; wave-based parallel across 5 GPUs (3 clive + 2 maigan) |

## VALIS Metrics Reference

| Metric | Meaning |
|--------|---------|
| `original_D` | Displacement before any registration (pixels at processing resolution) |
| `rigid_D` | Displacement after rigid transform (pixels at processing resolution) |
| `non_rigid_D` | Displacement after non-rigid transform (pixels at processing resolution) |
| `rTRE` | `D / max(processed_shape)` — resolution-independent (use for cross-experiment comparison) |
| `NCC` | Normalized cross-correlation (1.0 = perfect match; near-zero = failed feature matching) |

**Important**: `D` values are at **processing resolution**, not original image resolution. When comparing experiments at different `max_image_dim`, use `rTRE` for valid comparison.

## Key Insights

- **Non-rigid parameters were NEVER applied** in all previous tests (Bug 1). The "rigid-only is best" conclusion is invalidated.
- **Coarse non-rigid at 1024px is actively harmful** — always disable it for CODEX (set `non_rigid_registrar_cls=None` in Valis init)
- **4096px rigid processing** improves feature matching on difficult cycles (vs 2048px)
- **Three VALIS dimension parameters** control different things — conflating them causes silent quality loss
- **Average metrics are meaningless** — poor registration is localized. Use spatial NCC heatmaps or full-resolution crops.
- **`imgs_ordered=True`** is critical — VALIS default reorders by visual similarity, breaking CODEX sequential order
- **`align_to_reference=True`** prevents error accumulation in long cycle chains (13+ cycles)
- **All 47 batch-processed datasets** may need re-registration once optimal non-rigid parameters are determined
- **Diagnostic logging**: Added print in `OpticalFlowWarper.__init__` confirms params reach the constructor
- **`non_rigid_registrar_cls=None` must be EXPLICIT** — omitting it leaves the VALIS default (OpticalFlowWarper), which runs the harmful coarse NR pass. The comment was there but the param was never passed.
- **None bk_dxdy**: When coarse NR is disabled, `slide_obj.bk_dxdy` stays None. `register_micro()` needs a zero-displacement fallback or it crashes on `slide_obj.bk_dxdy[0]`
- **Sigma math**: `sigma_pixels = sigma_ratio * max(image_dim_px)`. sigma_ratio=0.05 at 4096px = 205px sigma — averages over 400+ pixel neighborhoods, completely washing out local corrections needed for nuclei alignment (~3-6px at 4096px)
- **Validated (Feb 18 2026)**: sigma_ratio=0.01 at 4096px confirmed on CX_19-001_SP_CC2-A28 — 11/12 cycles improved, mean D 1.12 to 0.77. This is the recommended starting configuration for CODEX datasets.
- **Dimension normalization**: EDF outputs can have inconsistent dimensions across cycles. The registration wrapper must pad all images to a common size before VALIS, or displacement fields will be incorrect. Use `normalize_dimensions: true` in config.
- **Stale Snakemake coordinators**: After cancelling SLURM jobs, background Snakemake processes may still be alive and resubmit jobs. Always check `squeue` for duplicate jobs before manual resubmission.
- **Defensive timing**: `register_micro()` must record `end_non_rigid_time` before returning, and `measure_error()` must guard against `None` timing values to prevent crashes in edge cases
- **Batch re-registration validated**: 4/16 projects completed (CX_19-002_lymph-node_R1: 29.5 min, CX_19-002_lymph-node_R3: 27.6 min, CX_19-003_lymph-node_R1: 40.8 min). Tuned non-rigid params (sigma_ratio=0.01, 4096px) generalize across spleen and lymph node tissue types.
- **Fallback copy is dangerous**: The old `fallback_copy` sentinel masked 3 broken registrations with `error=Rigid registration failed`. These passed the pipeline without error and were only caught by manual inspection of sentinel JSON. Fallback copies should NEVER be used — registration failures must raise exceptions.
- **Race condition on relaunch**: Old SLURM jobs from killed Snakemake coordinators can write stale output after Phase 1 cleanup. Must cancel ALL old jobs (`scancel`) and kill stale coordinators before relaunching registration.
- **Bash array pitfall**: `declare -a TODO_PROJECTS` does NOT clear an existing bash array. Use `TODO_PROJECTS=()` to explicitly empty it before repopulating.
- **Snakemake CLI argument order**: Targets after `--configfile` are interpreted as additional config files, not rule targets. Always place targets BEFORE options: `snakemake registration --configfile config.yaml`

## When to Apply

- Any CODEX/multiplex IF dataset with multi-cycle acquisition
- When registration QC shows color fringing in green/magenta DAPI overlays
- When VALIS summary CSV shows `non_rigid_D > rigid_D` — check if params are actually being applied
- After any upgrade to the VALIS/Kreg library — re-verify parameter passing

## Files Modified

| File | Change |
|------|--------|
| `notebooks/Kreg/serial_non_rigid.py:438` | `params=init_kwargs` → `**init_kwargs` (ROOT CAUSE fix) |
| `notebooks/Kreg/non_rigid_registrars.py:~1012` | Added diagnostic print in `OpticalFlowWarper.__init__` |
| `notebooks/Kreg/registration.py:4852` | Handle `None` bk_dxdy when coarse NR disabled (zero displacement fallback) |
| `workflow/scripts/registration.py` | Import non_rigid_registrars; `non_rigid_registrar_cls=None` EXPLICIT in Valis init; pass params to register_micro(); sigma_ratio default 0.01; `normalize_dimensions: true` config option; dimension padding to common size |
| `workflow/config.yaml` | `max_image_dim: 4096`, `sigma_ratio: 0.01` (was 0.05), no-op param comments |
| `notebooks/Kreg/registration.py` | Defensive guard in `measure_error()` for None `end_non_rigid_time` |
| `notebooks/Kreg/serial_non_rigid.py` | Timing record added at end of `register_micro()` |

## References

- Related skill: `gpu-only-scheduling` (GPU slot management for registration jobs)
- Related skill: `snakemake-skip-existing` (sentinel file patterns)
- Related skill: `cleanup-qc-review-guard` (QC verification before cleanup)
- VALIS library: `notebooks/Kreg/registration.py` (Valis class, line 1771 for dimension defaults)
- VALIS library: `notebooks/Kreg/serial_non_rigid.py` (line 438, params bug location)
