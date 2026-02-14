---
name: tissuumaps-export-pipeline
description: "TissUUmaps export pipeline: DZI tile conversion via pyvips, .tmap project file generation, rsync deploy, skip-existing manifest. Trigger: TissUUmaps, DZI, dzsave, tile pyramid, export, deploy, web visualization, OpenSeadragon, .tmap, marker color mapping."
author: KINTSUGI Team
date: 2026-02-14
---

# TissUUmaps Export Pipeline

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-14 |
| **Goal** | Export KINTSUGI processed images to web-optimized DZI tiles for TissUUmaps collaborative visualization |
| **Environment** | HiPerGator HPC, pyvips, Apache server with TissUUmaps |
| **Status** | Implemented |

## Context

After processing (correction → stitching → deconvolution → EDF → registration → segmentation), results need web-based collaborative review. TissUUmaps uses OpenSeadragon which loads DZI tiles natively. DZI tiles are static PNG files that Apache serves directly — no TissUUmaps backend needed for image rendering.

## Verified Approach

### DZI Conversion via pyvips

```python
import pyvips

# Registered images (16-bit grayscale, ~327 MB, ~12666×13519 px)
img = pyvips.Image.new_from_file(str(tif_path), access="sequential")
img.dzsave(str(output_dir / marker_name), tile_size=256, overlap=1, suffix=".png")

# Segmentation masks (int32 label images) — CRITICAL: nearest-neighbor resampling
img.dzsave(str(output_dir / name), tile_size=256, overlap=1, suffix=".png",
           region_shrink="nearest")  # Preserves label IDs
```

**Key insight**: `access="sequential"` is critical for performance with large TIFFs — enables streaming rather than loading entire image into memory.

### .tmap Project File Format

```json
{
    "filename": "project.tmap",
    "layers": [
        {"tileSource": "images/registered/cyc01/DAPI-01.dzi", "name": "DAPI-01 (cyc01)", "visible": true}
    ],
    "layerFilters": [
        [{"name": "Color", "value": "#0000ff"}]
    ],
    "compositeMode": "lighter",
    "markerFiles": [
        {"path": "data/cell_stats.csv", "title": "Cell Features",
         "expectedHeader": {"X": "centroid_1", "Y": "centroid_0"}}
    ],
    "plugins": ["Feature_Space"],
    "regions": {}
}
```

- `layerFilters` is array-of-arrays — outer index matches layer index
- `compositeMode: "lighter"` for fluorescence channel blending
- KINTSUGI uses `centroid_0`=Y (row), `centroid_1`=X (col) convention

### Skip-Existing Logic

`export_manifest.json` stores source file mtime + size (not MD5 — too slow for 327 MB files). On re-run: source newer/different size → reconvert. `--force` bypasses all checks.

### Marker Color Mapping

22 predefined marker→color mappings with a 15-color fallback cycle. DAPI variants (DAPI-01, DAPI_cyc02) are normalized before lookup: `re.sub(r"[-_]\d+$", "", name.lower())` then `re.sub(r"_cyc\d+$", "", key)`.

### CLI Structure

`@workflow.group("export")` with three subcommands: `prepare`, `deploy`, `status`. Follows the existing Click pattern where groups don't have default behavior.

## Failed Attempts

| Attempt | Why It Failed | Fix |
|---------|---------------|-----|
| `invoke_without_command=True` on group with positional args | Click can't disambiguate `export prepare .` from `export . prepare` when group takes positional `project_dir` | Use subcommands only — no group-level arguments |
| MD5 checksums for skip-existing | 327 MB files × 36 channels = reading all data twice (once for DZI, once for MD5) | Use mtime + size instead — fast and sufficient |
| Pyramidal TIFF instead of DZI | TissUUmaps uses OpenSeadragon which loads DZI natively; pyramidal TIFF needs server-side rendering | DZI tiles are static files Apache serves directly |

## Key Files

| File | Purpose |
|------|---------|
| `src/kintsugi/export.py` | Core logic: discovery, DZI conversion, .tmap generation, deploy, status |
| `src/kintsugi/cli.py` | CLI commands under `@workflow.group("export")` |

## Storage Estimates

Per dataset (~36 markers at ~327 MB each):
- Source registered: ~11.5 GB
- DZI tiles (PNG pyramid): ~15–20 GB
- 47 datasets total: ~700–940 GB on Apache server

## Final Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| tile_size | 256 | OpenSeadragon default |
| overlap | 1 | Standard DZI overlap |
| suffix | .png | Lossless, supports 16-bit |
| region_shrink | nearest | Labels only — preserves integer IDs |
| exclude_blanks | True | Default: skip Blank/Empty channels |
