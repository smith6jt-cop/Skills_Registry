---
name: hdl73-signal-isolation
description: "Batch signal isolation for Phenocycler spleen channels using matched blank pairs and kintsugi.signal"
author: smith6jt
date: 2026-02-25
---

# HDL73 Signal Isolation - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-25 |
| **Goal** | Process all 28 signal channels from HDL73 spleen sample with autofluorescence subtraction using matched blank pairs |
| **Environment** | KINTSUGI conda env, kintsugi.signal module, Python 3.x, tifffile, numpy |
| **Status** | Success |

## Context
HDL73 spleen sample from HiperGator had 28 signal markers but only 5 had been manually signal-isolated (CD11c, CD20, CD3e, CD4, CD8). The remaining 23 markers needed autofluorescence subtraction before the OME-TIFF could be rebuilt with all channels. Existing param files covered 9 channels (including the 5 already done), so 19 channels needed auto-analysis.

## Verified Workflow

### 1. Channel-to-blank mapping from channelnames.txt
The Phenocycler cycle layout in `channelnames.txt` encodes 3 positions per cycle (a/b/c). Blanks at cycles 1 and 13 provide matched autofluorescence references:

```python
POSITION_A = ["CD20", "CD31", "CD34", "CD35", "Lyve1", "PanCK", "SMActin"]
POSITION_B = ["CD8", "CD15", "CD21", "CD44", "CD45RO", "CD5", "CollagenIV", "ECAD", "FoxP3", "Ki67", "Podoplanin"]
POSITION_C = ["CD3e", "CD4", "CD11c", "CD107a", "CD163", "CD1c", "CD45", "CD68", "HLADR", "Vimentin"]
```

### 2. Blank averaging
```python
blank_avg = ((blank1.astype(np.float32) + blank13.astype(np.float32)) / 2.0).astype(np.uint16)
```

### 3. Parameter resolution (file or auto)
```python
from kintsugi.signal import analyze_for_subtraction, subtract_autofluorescence, compute_subtraction_quality

# If param file exists, parse blank_clip_factor and background_scale_factor
# If not, auto-analyze:
params = analyze_for_subtraction(signal, blank_avg, tissue_type="spleen", marker_name=name)
```

### 4. Subtraction and quality check
```python
result = subtract_autofluorescence(signal, blank_avg,
    blank_clip_factor=params["blank_clip_factor"],
    blank_scale_factor=params["blank_scale_factor"])
quality = compute_subtraction_quality(signal, result, blank_avg)
```

### 5. OME-TIFF rebuild
```bash
python scripts/convert_to_ome_tiff.py FromHipergator/HDL73_SPL_Processed/ImageJ Images/HDL073_PC29.ome.tiff
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `conda run -n KINTSUGI python script.py` | stdout completely buffered — appeared to hang with no output for 10+ minutes | Use direct python path: `$HOME/miniconda3/envs/KINTSUGI/bin/python -u` |
| `conda run --no-banner` flag | Not supported in this conda version | Stick with direct python invocation |
| Importing `kintsugi.signal_isolation` | Module doesn't exist | Correct path is `kintsugi.signal` (check `kintsugi._SUBMODULE_MAPPING`) |
| f-strings with nested braces in inline python | SyntaxError on older Python | Use `.format()` for complex formatting in `-c` one-liners |

## Final Parameters

### Channels with existing param files
```yaml
CD11c:  clip=7000,  scale=1.4
CD15:   clip=9000,  scale=0.7
CD1c:   clip=5000,  scale=1.8  # failed marker
CD20:   clip=7000,  scale=0.2
CD21:   clip=3000,  scale=1.6
CD3e:   clip=12000, scale=1.9  # param file also contains ImageJ macros
CD4:    clip=7000,  scale=2.0
CD5:    clip=10000, scale=1.4  # failed marker
CD8:    clip=8000,  scale=1.5
```

### Blank medians by position
```yaml
position_a: 14526  # highest autofluorescence
position_b: 6708
position_c: 4341   # lowest autofluorescence
```

### Output
- 29 files in ImageJ/ (28 signal + DAPI copy)
- OME-TIFF: 2.69 GB, pyramidal 5-level, 512x512 tiles, DEFLATE

## Key Insights
- CD3e param file contained ImageJ macro commands mixed with subtraction params — must parse carefully, only extract `blank_clip_factor` and `background_scale_factor`
- DAPI requires no subtraction — just copy directly
- `analyze_for_subtraction()` with `tissue_type="spleen"` works well for most channels but PanCK, Podoplanin, SMActin got low signal preservation (<0.3) — may need manual parameter tuning
- CD1c and CD5 were listed in `Failed_markers.txt` — processed anyway but results should be visually validated
- Position a blanks have ~3x higher median than position c — blank intensity varies significantly across positions

## References
- `scripts/process_hdl73_channels.py` — the processing script
- `scripts/convert_to_ome_tiff.py` — OME-TIFF builder
- `FromHipergator/HDL73_SPL_meta/channelnames.txt` — cycle layout source
- `FromHipergator/HDL73_SPL_Processed/Processing_parameters/` — existing param files
