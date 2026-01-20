# Stitching Stripe Artifacts

## Overview
Vertical stripe artifacts can appear in stitched microscopy images. This skill documents the diagnosis and fix process, specifically clarifying that **stripes are NOT caused by raw data**.

## Trigger Conditions
Activate this skill when:
- User reports vertical stripe patterns in stitched images
- Stripes have ~30-pixel periodic spacing
- Stripes are stronger in edge z-planes (Z1, Z2, Z13) than middle z-planes
- User suspects raw data quality issues

## Key Finding: Stripes Are NOT From Raw Data

**Critical insight from January 2026 investigation:**

Stripe artifacts in stitched CODEX images were diagnosed through systematic analysis:

1. **Raw tiles**: No significant stripe pattern (HP std ~1000-1200)
2. **After BaSiC correction**: No significant change (~1.0x)
3. **After stitching**: 2.8-5.5x amplification in stripe metric

**Root cause**: The stitched files were created with buggy pipeline code. Reprocessing with current code reduced stripes by 2.8x.

## Diagnostic Process

### Step 1: Quantify Stripe Severity
```python
from scipy import ndimage
import numpy as np

def compute_stripe_metric(img):
    """Compute high-pass column profile std (stripe metric)."""
    img_f = img.astype(np.float32)
    col_profile = img_f.mean(axis=0)
    col_hp = col_profile - ndimage.gaussian_filter1d(col_profile, sigma=50)
    return float(col_hp.std())

# Typical values:
# Clean image: 800-1300
# Stripe artifact: 3000+ (>2x typical)
```

### Step 2: Compare Raw vs Stitched
```bash
python scripts/check_raw_stripe_pattern.py
```

Expected result: Raw tiles should have LOWER stripe metric than stitched. If stitched/raw ratio > 2, stripes were introduced during processing.

### Step 3: Isolate the Source
```bash
python scripts/check_correction_vs_stitching.py
```

This script measures:
- Raw tiles → After BaSiC → After stitching

Typical findings:
- BaSiC: ~1.0x (no significant change)
- Stitching: Where stripes appear

## Solution: Reprocess with Current Code

Use the reprocessing script:
```bash
python scripts/reprocess_striped_zplanes.py
```

This script:
1. Creates backups of existing files (`.tif.bak`)
2. Reprocesses with current pipeline code
3. Reports improvement metrics

### Manual Reprocessing
```python
from kintsugi.kcorrect_gpu import KCorrectGPU
from kintsugi.stitch_blend import stitch_with_blending

# Load tiles, apply BaSiC
corrector = KCorrectGPU(use_gpu=True, verbose=False)
flatfield, darkfield = corrector.fit(tiles_norm, if_darkfield=True)

# Apply correction with flatfield minimum
flatfield_safe = np.clip(flatfield, 0.1, None)
corrected = (tiles_norm - darkfield) / flatfield_safe

# Stitch with sigmoid blending
stitched = stitch_with_blending(
    corrected_uint16,
    result_df,
    blend=True,
    sigma=10.0,
    overlap_fraction=(0.3, 0.3),
    output_dtype=np.uint16
)
```

## Failed Attempts Table

| Attempt | What Was Tried | Outcome | Learning |
|---------|---------------|---------|----------|
| Check raw tiles | Analyzed raw tile stripe patterns | Raw tiles were clean | Stripes NOT from raw data |
| Check BaSiC | Compared pre/post BaSiC metrics | ~1.0x ratio | BaSiC not causing stripes |
| Check flatfield | Analyzed flatfield frequency content | No 30px pattern | Flatfield upsampling not the cause |
| Fresh stitching | Reprocessed with current code | 2.8-5.5x improvement | Existing files from buggy code |

## Verified Configuration

**Reprocessing parameters (Jan 2026):**
- `OVERLAP_PERCENTAGE = 30.0`
- `BLEND_SIGMA = 10.0`
- `BASIC_FLATFIELD_MIN = 0.1`
- `max_iterations = 500`

**Results on test dataset:**
- cyc01_CH3_Z13: 3402 → 1212 (2.81x improvement)
- cyc02_CH3_Z02: 3136 → 1175 (2.67x improvement)

## Related Files
- `scripts/reprocess_striped_zplanes.py` - Batch reprocessing script
- `scripts/check_raw_stripe_pattern.py` - Raw vs stitched comparison
- `scripts/check_correction_vs_stitching.py` - Pipeline stage isolation
- `kintsugi/stitch_blend.py` - Sigmoid taper blending implementation

## See Also
- `stitched-image-qc` - General stitched image QC
- `gpu-quality-priority` - Quality over speed principle
- `basic-caching-evaluation` - BaSiC caching considerations
