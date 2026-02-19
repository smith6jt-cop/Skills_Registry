---
name: signal-isolation-batch-qc
description: "Batch autofluorescence subtraction workflow with visual QC grid for CODEX multiplex panels"
author: KINTSUGI Team
date: 2026-02-19
---

# Signal Isolation Batch Processing with Visual QC

## Experiment Overview

| Item | Details |
|------|---------|
| **Date** | 2026-02-18 to 2026-02-19 |
| **Goal** | Automated AF subtraction for all signal markers in CX_19-001_SP_CC2-A28 with visual QC |
| **Environment** | HiPerGator login node, KINTSUGI conda env, tifffile + numpy + matplotlib |
| **Status** | Success — 29/29 channels processed, QC grid generated |
| **Dataset** | CX_19-001_SP_CC2-A28: spleen, 13 cycles, 4 CH/cycle, 28 signal + 1 DAPI |
| **Image size** | 7479 x 12662 px (~189 MB per channel) |

## Context

CODEX multiplex imaging produces autofluorescence (AF) in every channel from tissue components (collagen, lipofuscin, RBCs). Cycle 1 captures blank images (no antibody staining) that represent the AF pattern. Subtracting these blanks from signal channels isolates true antibody signal.

For batch processing, each signal channel is matched to its positional blank:
- **CH2** markers → `Blank_1a` (cycle 1, CH2)
- **CH3** markers → `Blank_1b` (cycle 1, CH3)
- **CH4** markers → `Blank_1c` (cycle 1, CH4)
- **CH1** = DAPI (nuclear stain, not subtracted)

## Verified Workflow

### Step 1: Map channels to blanks

Parse `CHANNELNAMES.txt` (1-indexed, 4 channels per cycle):
```python
# Channel position within cycle: (index-1) % 4
# 0=DAPI, 1=CH2, 2=CH3, 3=CH4
# Blank mapping: CH2→Blank_1a, CH3→Blank_1b, CH4→Blank_1c
```

### Step 2: Global autofluorescence subtraction

```python
import numpy as np
import tifffile

def subtract_autofluorescence(signal, blank, scale_factor=1.0):
    """Global AF subtraction — same as MCP subtract_blank(method='global')."""
    scaled_blank = blank.astype(np.float32) * scale_factor
    signal_f = signal.astype(np.float32)
    result = signal_f - np.minimum(signal_f, scaled_blank)
    return np.clip(result, 0, 65535).astype(np.uint16)

# Load once, reuse per blank group
blank = tifffile.imread("registered/cyc01/Blank_1c.tif")
for marker, cyc in markers_using_blank_1c:
    signal = tifffile.imread(f"registered/{cyc}/{marker}.tif")
    result = subtract_autofluorescence(signal, blank)
    tifffile.imwrite(f"signal_isolated/{marker}.tif", result)
```

Key: `min(signal, blank)` ensures subtraction never goes negative — pixels where signal < blank get zeroed.

### Step 3: Visual QC grid

```python
DOWNSAMPLE = 16  # 12662/16 ≈ 792px wide thumbnails

def load_thumbnail(path):
    img = tifffile.imread(str(path))
    h, w = img.shape
    h_trim = (h // DOWNSAMPLE) * DOWNSAMPLE
    w_trim = (w // DOWNSAMPLE) * DOWNSAMPLE
    img = img[:h_trim, :w_trim]
    return img.reshape(h_trim // DOWNSAMPLE, DOWNSAMPLE,
                       w_trim // DOWNSAMPLE, DOWNSAMPLE).mean(axis=(1, 3))

# CRITICAL: normalize BOTH before/after to the REGISTERED image's p1-p99
# This ensures fair visual comparison (same brightness scale)
p1, p99 = np.percentile(reg_thumb, [1, 99])
reg_disp = np.clip((reg_thumb - p1) / (p99 - p1), 0, 1)
sig_disp = np.clip((sig_thumb - p1) / (p99 - p1), 0, 1)
```

### Step 4: Per-channel stats table

Flag channels with:
- `>70% zero pixels` → possible over-subtraction
- `p99 - p1 < 100` → very low dynamic range
- `max >= 65535` → pre-existing saturation (NOT a subtraction issue)

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Normalize before/after independently to own p1-p99 | Both images look equally bright — cannot see subtraction effect | Always normalize BOTH images to the SAME scale (registered p1-p99) |
| Single 29-row grid at 100 DPI | Image too compressed to see detail | Split into pages of 8 rows at 120 DPI for readable thumbnails |
| Flag "SATURATED" as a problem | 10/28 channels flagged, causing alarm | Saturation (max=65535) is pre-existing in registered data, not a subtraction artifact. Normal for bright markers |
| Use pyvips for thumbnail loading | pyvips sequential access mode doesn't easily produce numpy arrays for matplotlib | tifffile + block-average downsampling is simpler and works well |
| Same scale_factor=1.0 for all blanks | Blank_1c (p99=46157) dominates CD45 (p99=29070) and CD1c (p99=26691) | CH4 markers with dim signal may need weighted subtraction or reduced scale_factor for Blank_1c |

## Final Parameters

```yaml
# Global subtraction (default, used for all 29 channels)
method: global
scale_factor: 1.0

# QC grid generation
downsample_factor: 16        # ~800px wide thumbnails from 12662px originals
normalization: registered_p1_p99  # Both columns normalized to before-image range
page_size: 8                 # Channels per page for readability
dpi: 120

# QC thresholds
zero_pct_warning: 70         # Flag over-subtraction
min_dynamic_range: 100       # Flag collapsed signal
```

### CX_19-001 Results Summary

| Marker | Blank | Zero% | p99 (after) | Flag |
|--------|-------|-------|-------------|------|
| CD31 | Blank_1a | 15.5 | 13214 | |
| CD8 | Blank_1b | 27.7 | 23397 | |
| CD20 | Blank_1a | 60.5 | 25497 | |
| Ki67 | Blank_1b | 58.4 | 10980 | |
| CD3e | Blank_1c | 53.2 | 9500 | |
| SMActin | Blank_1a | 64.5 | 17016 | |
| Podoplanin | Blank_1b | 61.6 | 9580 | |
| CD68 | Blank_1c | 0.2 | 42447 | |
| PanCK | Blank_1a | 30.6 | 5205 | |
| CD21 | Blank_1b | 34.7 | 35793 | |
| CD4 | Blank_1c | 0.2 | 41710 | |
| Lyve1 | Blank_1a | 5.6 | 16284 | |
| CD45RO | Blank_1b | 57.6 | 10491 | |
| CD11c | Blank_1c | 0.2 | 41139 | |
| CD35 | Blank_1a | 57.7 | 8129 | |
| ECAD | Blank_1b | 49.2 | 9706 | |
| CD107a | Blank_1c | 0.2 | 40027 | |
| CD34 | Blank_1a | 10.5 | 11772 | |
| CD44 | Blank_1b | 56.5 | 9263 | |
| HLA-DR | Blank_1c | 0.2 | 37897 | |
| FoxP3 | Blank_1b | 35.2 | 12838 | |
| CD163 | Blank_1c | 0.2 | 31899 | |
| CollagenIV | Blank_1b | 54.0 | 9330 | |
| Vimentin | Blank_1c | 65.0 | 41423 | |
| CD15 | Blank_1b | 4.9 | 41963 | |
| CD45 | Blank_1c | 35.7 | 7582 | dim vs blank |
| CD5 | Blank_1b | 54.0 | 8346 | |
| CD1c | Blank_1c | 41.0 | 5749 | dim vs blank |

## Key Insights

- **CH4/Blank_1c markers split into two groups**: CD68, CD4, CD11c, CD107a, HLA-DR, CD163, Vimentin have strong signal (p99 >> blank, <1% zeros). CD3e, CD45, CD1c are dim relative to Blank_1c — these may benefit from `method="weighted"` or reduced `scale_factor`
- **Processing rate**: ~2 min/channel for 189 MB images on login node (tifffile load + numpy subtract + tifffile save)
- **Zero percentage is normal up to ~65%**: Tissue background gets zeroed by subtraction. Only flag >70%
- **DAPI is copied, not subtracted**: Include DAPI-01 in signal_isolated/ for completeness but don't apply AF removal
- **Output is flat directory**: `signal_isolated/{marker}.tif` — no cycle subdirectories. This simplifies downstream tools (segmentation, spatial analysis)
- **Block-average downsampling** (reshape + mean) is faster than scipy.zoom or skimage.resize for QC thumbnails

## References

- `src/kintsugi/signal/autofluorescence.py` — Core AF subtraction algorithms (global + weighted)
- `src/kintsugi/mcp/tools/signal_isolation.py` — MCP tool wrappers (subtract_blank, analyze_weighted_subtraction)
- `src/kintsugi/signal/subtractor.py` — AutofluorescenceSubtractor class
- `notebooks/3_Signal_Isolation_QC.ipynb` — Interactive signal isolation notebook
- QC outputs: `CX_19-001_SP_CC2-A28/qc_plots/signal_isolation_qc_p{1-4}.png`
