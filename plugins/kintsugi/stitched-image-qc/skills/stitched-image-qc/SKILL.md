# Stitched Image Quality Control

## Overview
Quality control for stitched microscopy images to detect common processing failures:
- **Saturation**: Images that appear blank white due to BaSiC correction issues
- **Tile grid patterns**: Visible seams between tiles due to improper blending

## Trigger Conditions
Activate this skill when:
- User reports "blank white" or "saturated" stitched images
- User reports visible tile boundaries or grid patterns
- Processing stitched images for a new dataset
- Running QC on processed outputs

## Problem Detection Criteria

### Saturation Issues
- More than 50% of pixels at near-maximum value (>64000 for uint16)
- Mean intensity significantly higher than expected (>60000 for typical microscopy)
- Usually affects edge z-planes (z1, z13) or specific cycles

### Tile Grid Patterns
- High std/mean ratio (>0.8) indicating intensity discontinuities
- Visible rectangular boundaries in the image
- Often caused by:
  - Flatfield values too low (clamped to BASIC_FLATFIELD_MIN)
  - Stitch model computed from incompatible z-plane
  - Blend sigma too small

## Root Causes

### BaSiC Correction Failures
The BaSiC algorithm estimates flatfield and darkfield corrections. Failures occur when:
1. **Low flatfield values**: If flatfield drops below `BASIC_FLATFIELD_MIN` (default 0.1), correction amplifies signal excessively
2. **Incorrect normalization**: Input must be normalized to [0,1] before correction
3. **Per-z-plane estimation**: BaSiC is run per-z-plane; edge planes may have different characteristics

### Stitching Issues
1. **Stitch model mismatch**: Position model computed from one z-plane may not work for another
2. **Insufficient overlap blending**: Sigmoid taper sigma too small for contrast differences

## Solution Approach

### Diagnostic Steps
```python
from skimage.io import imread
import numpy as np

# Check image statistics
img = imread('path/to/stitched.tif')
mean_val = img.mean()
pct_max = 100.0 * np.sum(img > 64000) / img.size
std_mean_ratio = img.std() / img.mean()

print(f"Mean: {mean_val:.0f}")
print(f"Pct at max: {pct_max:.1f}%")
print(f"Std/Mean ratio: {std_mean_ratio:.2f}")

# Saturation: pct_max > 50%
# Tile grid: std_mean_ratio > 0.8
```

### Reprocessing Fix
Use the reprocessing script at `notebooks/reprocess_problematic_images.py`:
```bash
# Dry run first
python reprocess_problematic_images.py --dry-run

# Then reprocess
python reprocess_problematic_images.py
```

### Manual Reprocessing
```python
from kintsugi.kcorrect_gpu import KCorrectGPU
from kintsugi.stitch_blend import stitch_with_blending_gpu

# Load tiles and normalize
tiles = load_tiles(...)
tiles_norm = tiles.astype(np.float64) / 65535

# BaSiC correction
corrector = KCorrectGPU(use_gpu=True, working_size=128)
flatfield, darkfield = corrector.fit(tiles_norm, if_darkfield=True)

# Apply correction with safe flatfield minimum
flatfield_safe = np.clip(flatfield, 0.1, None)
corrected = np.clip((tiles_norm - darkfield) / flatfield_safe, 0, 1)
corrected_uint16 = (corrected * 65535).astype(np.uint16)

# Stitch with proper blending
stitched = stitch_with_blending_gpu(
    corrected_uint16,
    result_df,
    sigma=10.0,
    overlap_fraction=(0.3, 0.3)
)
```

## Prevention

### Cache Validation
Always validate cached statistics before using:
```python
from Kio import validate_stats_cache

if CACHE_FILE.exists():
    with open(CACHE_FILE, 'rb') as f:
        cached_df = pickle.load(f)
    if validate_stats_cache(cached_df, source_dir, phase='stitched'):
        use_cache = True
    else:
        use_cache = False  # Recompute
```

### Quality Checks Post-Processing
Add automatic QC after stitching:
```python
# After stitching
pct_max = 100.0 * np.sum(stitched > 64000) / stitched.size
if pct_max > 50:
    print(f"WARNING: {pct_max:.1f}% saturated - check BaSiC parameters")
```

## Related Files
- `notebooks/reprocess_problematic_images.py` - Batch reprocessing script
- `kintsugi/kcorrect_gpu.py` - BaSiC GPU implementation
- `kintsugi/stitch_blend.py` - Sigmoid taper blending
- `notebooks/Kio.py` - Cache validation functions
- `notebooks/Kutils.py` - Quantification comparison functions

## See Also
- `gpu-quality-priority` - Always prioritize quality over speed
- `basic-caching-evaluation` - BaSiC caching considerations
