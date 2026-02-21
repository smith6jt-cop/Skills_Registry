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

## Final Parameters

**Frangi vesselness (validated):**
- `sigmas = [1, 2, 4, 8]` — multi-scale vessel radii
- `alpha = 0.5, beta = 0.5` — standard Frangi parameters
- `gamma = auto` (half max Frobenius norm per scale)
- VRAM guard: 15x volume bytes minimum

**Test assertions that verify the fix:**
- Tube center Ra > 0.5 (typically ~0.9)
- Plate center Ra < 0.5 (typically ~0.05)
- Ra term for tube > Ra term for plate at same center voxel
- Eigenvalues sorted: |l1| <= |l2| <= |l3| everywhere

## Key Insights

- **Always verify Frangi formula against the original paper** (Frangi et al., 1998, MICCAI). The Ra/Rb ratios are easy to mix up because different implementations use different eigenvalue orderings
- **scikit-image 0.26 is aggressive about deprecations** — `binary_closing`, `binary_opening`, `binary_dilation`, `binary_erosion` all deprecated in favor of generic `closing`, `opening`, `dilation`, `erosion`
- **GPU VRAM estimation**: 15x volume size is a good heuristic for the Cardano eigenvalue path (6 Hessian arrays + input copy + 8 working arrays during computation and sorting)
- **Small synthetic volume tests**: Boundary effects dominate on 32³ volumes. Test eigenvalue ratios at known structure centers rather than aggregate statistics

## References
- Frangi, A.F. et al. (1998). "Multiscale vessel enhancement filtering." MICCAI, LNCS 1496, pp. 130-137.
- scikit-image 0.26 changelog: https://scikit-image.org/docs/stable/release_notes/release_0.26.html
- `src/kintsugi/vessel3d.py` — Lines 544-553 (Ra formula), 345-364 (VRAM guard), 627+652 (deprecation fixes)
- `tests/test_vessel3d.py` — 19 tests validating all fixes
