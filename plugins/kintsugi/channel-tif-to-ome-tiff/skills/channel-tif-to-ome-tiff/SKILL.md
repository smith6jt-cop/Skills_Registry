---
name: channel-tif-to-ome-tiff
description: "Convert single-channel TIF directories to pyramidal OME-TIFF with SubIFDs"
author: SpleenFollicleCounterQP
date: 2026-02-24
---

# Channel TIF to OME-TIFF Conversion - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-24 |
| **Goal** | Convert HiperGator signal-isolated channel TIFs into pyramidal OME-TIFF for QuPath |
| **Environment** | Python 3.12, tifffile, numpy; Linux |
| **Status** | Success |

## Context
HiperGator CODEX/Phenocycler processing outputs individual TIF files per channel (after signal isolation). These need to be consolidated into a single pyramidal OME-TIFF with proper metadata to be opened in QuPath v0.6.0 for downstream analysis.

## Verified Workflow

### Script Usage
```bash
python scripts/convert_to_ome_tiff.py <input_dir> <output_path> [--pixel-size 0.508]
```

### Key Implementation: Block-Mean Downsampling
```python
def downsample_2x(img):
    """Block-mean 2x downsample, trimming odd dimensions."""
    h, w = img.shape
    img = img[:h - h % 2, :w - w % 2]
    return img.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3)).astype(np.uint16)
```

### Key Implementation: tifffile Pyramid Writing
```python
with tifffile.TiffWriter(output, bigtiff=True) as tw:
    for i, (path, name) in enumerate(zip(channel_paths, names)):
        img = tifffile.imread(str(path)).astype(np.uint16)

        options = dict(tile=(512, 512), compression="deflate", subifds=4)
        if i == 0:
            options["description"] = ome_xml  # OME-XML only on first page
            options["metadata"] = None        # CRITICAL: prevent auto-metadata

        tw.write(img, **options)

        # Write SubIFD pyramid levels
        sub = downsample_2x(downsample_2x(img))  # 4x
        del img
        for level in range(4):
            tw.write(sub, tile=(512, 512), compression="deflate", subfiletype=1)
            if level < 3:
                sub = downsample_2x(sub)
```

### Key Implementation: OME-XML with ASCII-Safe Units
```python
# MUST use XML entity &#181; for µ — tifffile requires 7-bit ASCII
xml = f'''...PhysicalSizeXUnit="&#181;m"...'''
```

### Target OME-TIFF Format
- 5 pyramid levels: 1x, 4x, 8x, 16x, 32x (SubIFDs)
- 512x512 tiles, DEFLATE compression, uint16
- CYX axes (one page per channel)
- Pixel size: 0.5077663810243286 µm

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Using Unicode `µm` in OME-XML | `ValueError: TIFF strings must be 7-bit ASCII` — tifffile encodes description tag as ASCII | Use XML numeric entity `&#181;m` instead of Unicode µ |
| Not setting `metadata=None` on first page | tifffile adds its own metadata conflicting with OME-XML | Always pass `metadata=None` when providing custom `description` |

## Final Parameters

### Channel Discovery
- Glob `*.tif` in input directory
- Exclude files starting with `BLANK`
- Rename `DAPI-01` to `DAPI`
- Sort: DAPI first, then alphabetical

### Memory Profile
- ~180 MB per channel in RAM (one at a time)
- Full-res image deleted before writing sub-levels
- Safe for 29+ channel images on standard workstations

## Key Insights
- `subifds=N` on the full-res write tells tifffile to expect N sub-resolution levels
- `subfiletype=1` marks each subsequent write as a reduced-resolution image
- First sub-level should be 4x (not 2x) to match QuPath/Bio-Formats convention
- Block-mean is preferred over interpolation for uint16 fluorescence data (preserves intensity semantics)
- `bigtiff=True` is required even though individual files may be < 4 GB (total IFD count can overflow)

## References
- tifffile documentation: https://github.com/cgohlke/tifffile
- OME-TIFF specification: https://docs.openmicroscopy.org/ome-model/latest/ome-tiff/
- QuPath v0.6.0 image format requirements
- Related skill: `channel-name-parsing` (CHANNELNAMES.txt parsing)
