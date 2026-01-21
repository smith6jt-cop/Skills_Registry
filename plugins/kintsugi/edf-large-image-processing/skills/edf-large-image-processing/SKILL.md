---
name: edf-large-image-processing
description: "EDF processing fixes: visualization path matching, smooth transitions, OOM prevention, worker thread imports"
author: Claude Code
date: 2026-01-21
---

# EDF Large Image Processing - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-01-21 |
| **Goal** | Fix EDF visualization (images not found), enable smooth transitions, prevent GPU OOM on large images |
| **Environment** | KINTSUGI on HiPerGator, 2x GPUs, images 13515x12666 px, 13 z-planes |
| **Status** | Success |

## Context

Three distinct issues with EDF (Extended Depth of Focus) processing in KINTSUGI:

1. **Visualization path mismatch**: `view_pipeline_comparison()` and `QCPanel` expected EDF files at `edf/cyc##/CH#/edf.tif` but actual output structure was `edf/cyc##/MARKER_NAME.tif`

2. **Smoothing not applied**: Smooth transition parameters (`blend_depth`, `z_smooth_sigma`) existed in `src/kintsugi/edf.py` but notebook's `EDF_PARAMS` didn't include them, so they defaulted to 0

3. **GPU OOM on large images**: With 13515x12666 images and blend_depth > 0, the variance arrays exceeded GPU memory (tried to allocate 53GB while already using 167GB)

4. **Worker thread import error**: `load_stack_parallel` was imported at module level but unavailable in ThreadPoolExecutor workers during multi-GPU processing

## Verified Workflow

### Fix 1: EDF Visualization Path Matching

Add flexible path matching helper in `notebooks/Kview_qc.py`:

```python
def _find_edf_file(
    edf_base_dir: Path,
    cycle: int,
    channel: int | None = None,
    channel_name: str | None = None,
) -> Path | None:
    """
    Find EDF file with flexible path matching.

    Supports multiple EDF output structures:
    - edf/cyc##/MARKER_NAME.tif (marker-named files directly in cycle dir)
    - edf/cyc##/CH#/edf.tif (channel subdirectories with edf.tif)
    - edf/cyc##/CH#.tif (channel-numbered files)
    """
    cycle_dir = edf_base_dir / f"cyc{cycle:02d}"

    if not cycle_dir.exists():
        return None

    # Strategy 1: Direct channel name match
    if channel_name:
        for pattern in [f"{channel_name}.tif", f"{channel_name}*.tif"]:
            matches = list(cycle_dir.glob(pattern))
            if matches:
                return matches[0]

    # Strategy 2: CH# subdirectory structure (legacy)
    if channel is not None:
        ch_dir = cycle_dir / f"CH{channel}"
        if ch_dir.exists():
            edf_file = ch_dir / "edf.tif"
            if edf_file.exists():
                return edf_file

    # Strategy 3: Return first available file
    all_tifs = sorted(cycle_dir.glob("*.tif"))
    if all_tifs:
        return all_tifs[0]

    return None
```

Update `view_pipeline_comparison()` to use the helper:

```python
def view_pipeline_comparison(
    project_dir, cycle, channel, channel_name=None, ...
):
    edf_base_dir = proc_dir / "edf"
    edf_path = _find_edf_file(edf_base_dir, cycle, channel, channel_name)
```

### Fix 2: Enable Smooth Transitions

Add parameters to `EDF_PARAMS` in `2_Cycle_Processing.ipynb`:

```python
EDF_PARAMS = {
    'radius_x': 5,
    'radius_y': 5,
    'sigma': 10.0,
    'z_start': 1,
    'z_end': n_zplanes,
    'tiles': (3, 3),      # Process in 9 tiles for large images
    'backend': 'auto',
    'device': 'auto',
    'blend_depth': 0,     # Set to 2 for smooth transitions (requires more memory)
    'z_smooth_sigma': 1.0 # Smooth z-index map spatially
}
```

Pass through `edf_processor.process()`:

```python
result = edf_processor.process(
    stack,
    radius_x=EDF_PARAMS['radius_x'],
    ...
    blend_depth=EDF_PARAMS.get('blend_depth', 0),
    z_smooth_sigma=EDF_PARAMS.get('z_smooth_sigma', 0.0)
)
```

### Fix 3: Prevent GPU OOM

For large images (>10000 px), use tiled processing:

```python
EDF_PARAMS = {
    'tiles': (3, 3),      # Process in 9 chunks
    'blend_depth': 0,     # Disable for memory (creates extra large arrays)
    'z_smooth_sigma': 1.0 # Still applies spatial smoothing
}
```

Memory calculation for 13515x12666 px with 13 z-planes:
- Stack: 13 × 171M pixels × 4 bytes = ~8.9 GB
- Variance array: same = ~8.9 GB
- With blend_depth=2: additional arrays for top-N selection and blending

Clear GPU memory before processing:

```python
from Kio import cleanup_gpu_memory
cleanup_gpu_memory(0)
cleanup_gpu_memory(1)
```

### Fix 4: Worker Thread Import

Add local import inside `process_edf_tiff()`:

```python
def process_edf_tiff(decon_dir, edf_dir, cycle, channel, ...):
    """..."""
    # Import here to ensure availability in ThreadPoolExecutor workers
    from Kio import load_stack_parallel

    # Load deconvolved z-stack
    ...
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Expected `edf/cyc##/CH#/edf.tif` path structure | Actual output uses marker names directly in cycle dir | Use flexible path matching with multiple strategies |
| Adding smooth params to `edf.py` only | Notebook didn't pass them through `edf_processor.process()` | Must update both the module AND the calling code |
| `blend_depth=2` on large images | Creates extra arrays for top-N z-slice selection, causing OOM | Use `z_smooth_sigma` instead, or increase tiles |
| `tiles=(1,1)` with full-size images | Single tile exceeds GPU memory on images >10000 px | Use `tiles=(3,3)` or higher for large images |
| Module-level import of `load_stack_parallel` | ThreadPoolExecutor workers don't inherit module-level imports | Import inside the function that runs in workers |
| Timestamp-based sync comparison | Notebooks saved with output get newer timestamps, blocking sync | Use MD5 checksum comparison (already fixed in sync script) |

## Final Parameters

```python
# EDF_PARAMS for large images (>10000 px)
EDF_PARAMS = {
    'radius_x': 5,
    'radius_y': 5,
    'sigma': 10.0,
    'z_start': 1,
    'z_end': n_zplanes,
    'tiles': (3, 3),      # (4,4) or (5,5) if still OOM
    'backend': 'auto',
    'device': 'auto',
    'blend_depth': 0,     # Memory-safe; set to 2 for smooth transitions on smaller images
    'z_smooth_sigma': 1.0 # Spatial smoothing of z-index map
}

# For smaller images (<5000 px), can enable blend_depth:
EDF_PARAMS_SMALL = {
    ...
    'tiles': (1, 1),      # No tiling needed
    'blend_depth': 2,     # Blend 2 adjacent z-slices
    'z_smooth_sigma': 1.0
}
```

## Key Insights

- **Path flexibility is essential**: EDF output naming varies by workflow (marker names vs CH# vs edf.tif)
- **Two types of smooth transitions**: `blend_depth` (weighted z-slice blending, memory-intensive) vs `z_smooth_sigma` (spatial smoothing of z-index map, memory-efficient)
- **Tiled processing is mandatory for large images**: 13515×12666 images need at least (3,3) tiling
- **Worker thread imports**: Functions running in ThreadPoolExecutor need local imports
- **Memory estimation**: `blend_depth > 0` roughly doubles memory requirements due to top-N selection arrays
- **GPU cleanup matters**: Call `cleanup_gpu_memory()` before EDF when processing multiple channels

## References

- `src/kintsugi/edf.py` - EDF implementation with blend_depth and z_smooth_sigma
- `notebooks/Kview_qc.py` - Visualization functions with flexible path matching
- `notebooks/2_Cycle_Processing.ipynb` - EDF_PARAMS configuration
- `notebooks/Kio.py` - `load_stack_parallel()` and `cleanup_gpu_memory()` utilities
- CLAUDE.md - EDF smooth transitions documentation
