---
name: vessel3d-frangi-bugfix
description: "Frangi vesselness 3D filter: Ra formula correction, scikit-image deprecations, GPU VRAM guard"
author: KINTSUGI Team
date: 2026-02-21
---

# vessel3d-frangi-bugfix - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-21 |
| **Goal** | Fix critical bugs in 3D vessel segmentation: wrong Frangi Ra formula, scikit-image deprecations, GPU VRAM safety |
| **Environment** | HiPerGator HPC, Python 3.11, scikit-image 0.26.0, CuPy 13.x, NVIDIA B200 (192 GB) + L4 (23 GB) |
| **Status** | Success |

## Context

The vessel3d module was added Feb 16, 2026 and attempted on one project with 5 SLURM runs — all failed due to different issues. Investigation revealed three distinct failure modes and one critical algorithmic bug.

### SLURM Run Failure Analysis

| Run | Node | Root Cause | Resolution |
|-----|------|-----------|------------|
| 1 | B200 | GPU OOM — old `(N,3,3)` eigenvalue path (108 GB) | Fixed by Cardano commit same day |
| 2 | B200 | Frangi completed then `ImportError: skan` | skan 0.13.1 installed |
| 3-4 | B200 | User-cancelled | N/A |
| 5 | L4 (23 GB) | GPU OOM on `gaussian_filter` — L4 too small | VRAM guard added |

**Run 2 proved the Cardano fix works.** The remaining issues were the Ra formula bug and small-GPU safety.

## Verified Fixes

### 1. Frangi Ra Formula (Critical)

The `Ra` ratio discriminates tubes from plates. With eigenvalues sorted `|λ₁| ≤ |λ₂| ≤ |λ₃|`:

**Wrong (vessel3d.py:552):**
```python
Ra = abs_l1 / (abs_l2 + eps)   # |λ₁|/|λ₂| — near 0 for tubes!
```

**Correct (Frangi 1998, eq. 11; scikit-image reference):**
```python
Ra = abs_l2 / (abs_l3 + eps)   # |λ₂|/|λ₃| — near 1 for tubes
```

**Impact**: With the bug, the `(1 - exp(-Ra²/2α²))` term evaluated to ~0 for tubes (since Ra ≈ 0), killing the vesselness response. The pipeline still partially worked because real data has nonzero λ₁ and Otsu threshold adapts, but small/faint vessels were missed.

**Verification**: Synthetic tube test — Ra at tube center = 0.91 (correct) vs ~0.02 (buggy). Plate Ra = 0.05 (correctly low in both versions).

### 2. scikit-image 0.26 Deprecations

| Deprecated | Replacement | Semantics Change |
|-----------|-------------|-----------------|
| `binary_closing(mask, footprint=)` | `closing(mask, footprint=)` | FutureWarning in 0.26, removed in 0.28 |
| `remove_small_objects(mask, min_size=N)` | `remove_small_objects(mask, max_size=N-1)` | New `max_size` removes objects <= threshold (old `min_size` removed < threshold) |

### 3. GPU VRAM Guard

Added to `_hessian_eigenvalues_3d()`:
```python
estimated_vram = volume.nbytes * 15  # Peak: 6 Hessian + input + 8 working arrays
free_vram = cp.cuda.Device(device_id).mem_info[0]
if estimated_vram > free_vram:
    logger.warning(f"GPU VRAM insufficient, falling back to CPU")
    use_gpu = False
```

SLURM job script also queries `nvidia-smi` and forces `device='cpu'` if VRAM < 40 GB.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Compare tube vs plate vesselness by `.max()` | Both normalize to 1.0 — max is always 1.0 | Compare unnormalized Ra terms at known structure centers, not normalized vesselness |
| Compare tube vs plate by `(v > 0.5).sum()` | Plates have more edge voxels on small (32³) volumes — boundary effects dominate | Small synthetic volumes have strong boundary effects; test eigenvalue ratios directly |
| `remove_small_objects(min_size=N)` with new API | `min_size` deprecated in skimage 0.26 | Use `max_size=N-1` (note: `max_size` removes objects with size <= threshold, off-by-one from old `min_size` which removed < threshold) |
| L4 GPU (23 GB) for isotropic volumes | Isotropic volume of 9x7 tile grid = ~9 GB float32; Cardano needs ~15x = 135 GB peak | Always check free VRAM before GPU eigenvalue path; 40 GB minimum for typical volumes |

## Verified: Sensitivity Presets and Multi-Channel (Feb 22, 2026)

### 4. Preset Override Pattern

Preset-overridable params (`sigmas`, `alpha`, `beta`, `min_size`, `denoise_sigma`) default to `None` in `segment_vessels_3d()`. Resolution chain: **explicit value > preset > hardcoded default**.

**Why `None` defaults**: The original design used hardcoded defaults (`alpha=0.5`) and compared against them to detect "caller used default." This failed when SLURM scripts passed values explicitly (e.g., `alpha=VESSEL_ALPHA` where `VESSEL_ALPHA=0.5`). The function couldn't distinguish "caller passed 0.5" from "caller didn't specify."

**SLURM integration**: Build a `seg_kwargs` dict, only including params whose env vars exist (`if 'VESSEL_ALPHA' in os.environ`). Unset vars → param stays `None` → preset fills it.

### 5. Marker Discovery

`discover_vessel_markers(channel_names)` finds vessel markers ranked by priority:

| Pattern | Role | Priority |
|---------|------|----------|
| CD34 | endothelial | 1 (best) |
| CD31 | endothelial | 2 |
| aSMA, a-SMA, alpha-SMA, αSMA, Smooth Muscle Actin | smooth_muscle | 3 |

Excludes: DAPI, Blank, Empty, Autofluorescence, generic "Actin" (too ambiguous).

### 6. Multi-Channel Combination

`segment_vessels_multichannel({"CD31": vol1, "SMA": vol2}, ...)`: Runs Frangi independently per channel (avoids inter-cycle misalignment), then combines binary masks via `combine_vessel_masks()` (union or intersection). Skeletonizes and analyzes the combined result. Stores individual masks in `result.per_channel_masks`.

### CC3-C Rerun Results (high_sensitivity)

| Metric | Default | high_sensitivity |
|--------|---------|-----------------|
| Segments | 207 | **537** (+159%) |
| Duration | ~25 min | ~27.5 min |

## Final Parameters

**Presets (`VESSEL_PRESETS`):**

| Preset | sigmas | alpha | beta | min_size | denoise_sigma |
|--------|--------|-------|------|----------|---------------|
| `default` | [1,2,4,8] | 0.5 | 0.5 | 500 | 0.5 |
| `high_sensitivity` | [0.5,1,2,4,8] | 0.3 | 0.3 | 250 | 0.3 |
| `CD34` | [0.5,1,2,4,8] | 0.3 | 0.3 | 250 | 0.3 |

**VRAM guard**: 15x volume bytes minimum for GPU path.

**Thin-slab note**: Datasets are ~10 z-planes (~15 um depth). Topology features (tortuosity, branching angle) are unreliable. Cross-section radii and cleaner masks are the main 3D value.

**Test assertions that verify the fix:**
- Tube center Ra > 0.5 (typically ~0.9)
- Plate center Ra < 0.5 (typically ~0.05)
- Ra term for tube > Ra term for plate at same center voxel
- Eigenvalues sorted: |l1| <= |l2| <= |l3| everywhere
- alpha=0.1 mask >= alpha=0.9 mask (sensitivity forwarding works)
- Preset fills None params, explicit values override preset

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Compare tube vs plate vesselness by `.max()` | Both normalize to 1.0 — max is always 1.0 | Compare unnormalized Ra terms at known structure centers, not normalized vesselness |
| Compare tube vs plate by `(v > 0.5).sum()` | Plates have more edge voxels on small (32³) volumes — boundary effects dominate | Small synthetic volumes have strong boundary effects; test eigenvalue ratios directly |
| `remove_small_objects(min_size=N)` with new API | `min_size` deprecated in skimage 0.26 | Use `max_size=N-1` (note: `max_size` removes objects with size <= threshold, off-by-one from old `min_size` which removed < threshold) |
| L4 GPU (23 GB) for isotropic volumes | Isotropic volume of 9x7 tile grid = ~9 GB float32; Cardano needs ~15x = 135 GB peak | Always check free VRAM before GPU eigenvalue path; 40 GB minimum for typical volumes |
| Preset with hardcoded defaults (`alpha=0.5`) | SLURM script always passes explicit values; `alpha == 0.5` check can't distinguish "caller passed 0.5" from "default" | Use `None` defaults for preset-overridable params; resolution: explicit > preset > hardcoded |
| SLURM `export VESSEL_SIGMAS="1,2,4,8"` with preset | Env var exists → script passes it as explicit kwarg → overrides preset | Only export env vars you want to override; leave unset to let preset control |

## Key Insights

- **Always verify Frangi formula against the original paper** (Frangi et al., 1998, MICCAI). The Ra/Rb ratios are easy to mix up because different implementations use different eigenvalue orderings
- **scikit-image 0.26 is aggressive about deprecations** — `binary_closing`, `binary_opening`, `binary_dilation`, `binary_erosion` all deprecated in favor of generic `closing`, `opening`, `dilation`, `erosion`
- **GPU VRAM estimation**: 15x volume size is a good heuristic for the Cardano eigenvalue path (6 Hessian arrays + input copy + 8 working arrays during computation and sorting)
- **Small synthetic volume tests**: Boundary effects dominate on 32³ volumes. Test eigenvalue ratios at known structure centers rather than aggregate statistics
- **Preset override pattern**: Use `None` defaults for any param a preset should control. The `if 'ENV_VAR' in os.environ` pattern in SLURM scripts cleanly separates "explicitly set" from "use default"
- **Multi-channel vessel segmentation**: Run Frangi independently per channel, combine binary masks. Don't combine raw volumes — inter-cycle misalignment corrupts Hessian analysis
- **Thin-slab data**: ~10 z-planes gives value for cross-section radii and cleaner 3D masks, but topology metrics (tortuosity, branching angle) are not meaningful

## References
- Frangi, A.F. et al. (1998). "Multiscale vessel enhancement filtering." MICCAI, LNCS 1496, pp. 130-137.
- scikit-image 0.26 changelog: https://scikit-image.org/docs/stable/release_notes/release_0.26.html
- `src/kintsugi/vessel3d.py` — Presets, marker discovery, multichannel, preset override pattern
- `tests/test_vessel3d.py` — 34 tests validating all fixes and new features
