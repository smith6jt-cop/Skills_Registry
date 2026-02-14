---
name: weighted-autofluorescence-subtraction
description: "Multi-range weighted autofluorescence subtraction for multiplex IF. Protects dim signal while aggressively removing bright AF. Trigger: autofluorescence removal, blank subtraction, dim marker preservation, weighted subtraction."
author: KINTSUGI Team
date: 2026-02-14
updated: 2026-02-14
---

# Multi-Range Weighted Autofluorescence Subtraction

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-14 |
| **Goal** | Replace single global `blank_scale_factor` with per-intensity-range weights for AF subtraction |
| **Problem** | Global scale factor either over-subtracts (destroys dim positive cells like FOXP3, CD163) or under-subtracts (leaves residual AF in collagen/lipofuscin) |
| **Environment** | KINTSUGI pipeline, HiPerGator, 16-bit TIFF images (uint16), 9x7+ tile grids |
| **Status** | Implemented and tested |

## Algorithm

1. Clip blank channel (same as global method)
2. Segment signal histogram into N intensity ranges (default 5: background, very_dim, dim, medium, bright)
3. For each range, compute signal-to-AF ratio → per-range weight:
   - `blank_mean / signal_mean > 1.5` → weight 0.3-0.5 (AF dominates, protect signal)
   - ratio 0.8-1.5 → weight 0.5-0.8 (mixed)
   - ratio 0.3-0.8 → weight 0.8-1.0 (signal moderate)
   - ratio < 0.3 → weight 1.0-1.15 (signal dominant)
   - Correlation within range boosts weight slightly (+0.05 if corr > 0.3)
4. Build smooth per-pixel weight map with cosine transitions at range boundaries
5. Apply: `result = signal - min(signal, blank * base_scale * weight_map)`
6. Post-processing (smoothing, erosion — same as global method)
7. Compute per-range quality metrics for learning

**Key insight**: In dim signal regions where blank > signal, the per-range weight drops to 0.3-0.5 (gentle subtraction), preserving real positive cells. In bright signal regions, weight rises to 1.0+ (aggressive AF removal).

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_ranges` | 5 | Number of intensity ranges |
| `range_method` | `"percentile"` | Boundary computation: `"percentile"` or `"otsu"` |
| `base_scale_factor` | 1.0 | Global multiplier before per-range weighting |
| `transition_width` | 0.1 | Fraction of range width for cosine blending |
| `blank_clip_factor` | varies | Inherited from global method analysis |

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Test fixture with 100 dim pixels (10x10 region) in 256x256 image | Percentile-based ranges couldn't separate 100 pixels (<0.2% of image) from dominant AF — dim pixels got lumped into same range as AF | **Percentile ranges require substantial pixel populations (~30%+) to form distinct ranges. Use realistic proportions in test fixtures.** |
| Using `gpus=1` or `gpu=1` in Snakemake resources | `SLURM_TRES_PER_TASK` conflict on SLURM >= 24.11 | Always use `gres="gpu:1"` for GPU resource in Snakemake |
| Otsu boundaries on near-uniform images | `threshold_multiotsu` raises ValueError when variance is near-zero | Catch ValueError and fall back to percentile method |

## What Worked

### Core Algorithm
- **Cosine transitions** between ranges prevent visible discontinuities in subtracted image
- **`smooth_membership()`** function using `(1 - cos(π*t))/2` for rising edges, `(1 + cos(π*t))/2` for falling edges
- **Weight map is float32** — pixel-local computation, no neighbor dependencies (trivially parallelizable with Dask `map_blocks`)
- **Near-uniform fallback**: When `dynamic_range < 100`, falls back to global method (avoids creating meaningless ranges)
- **Sparse signal adaptation**: When <1% nonzero pixels, reduces `n_ranges` to `min(n_ranges, 3)`

### Test Design
- Fixture with **realistic proportions**: 30% dim signal (rows 0:77), 20% bright signal (rows 180:230), 50% background
- Dim signal values: 3000-6000 with bright AF: 7000-9000 in same region
- **Behavioral verification**: `dim_global=0` (destroyed) vs `dim_weighted=432` (preserved)
- **Backwards compatibility**: Uniform weights=1.0 produces `max_diff=0.0` vs global method

### Learning Integration
- `algorithm_version` column in parameter_learning.py via `ALTER TABLE` migration
- Bootstrap records with `user_approved=False` (lower weight in recommendations)
- Range aggregation: average per-range weights across matching records with same `n_ranges`

### Architecture
- `IntensityRange` and `WeightedSubtractionParameters` dataclasses with `to_dict()`/`from_dict()` for serialization
- `AutofluorescenceSubtractor.method` parameter dispatches to `_process_global()` or `_process_weighted()`
- MCP `analyze_weighted_subtraction()` tool previews ranges without performing subtraction
- CLI `kintsugi mcp pretrain` scans EDF outputs for batch bootstrapping

## Implementation Files

| File | Key Functions/Classes |
|------|----------------------|
| `src/kintsugi/signal/autofluorescence.py` | `compute_intensity_ranges()`, `_compute_range_weight()`, `build_weight_map()`, `subtract_autofluorescence_weighted()`, `analyze_for_weighted_subtraction()`, `compute_weighted_subtraction_quality()`, `subtract_autofluorescence_weighted_dask()` |
| `src/kintsugi/signal/utils.py` | `adaptive_range_boundaries()`, `smooth_membership()` |
| `src/kintsugi/signal/subtractor.py` | `IntensityRange`, `WeightedSubtractionParameters`, extended `AutofluorescenceSubtractor` |
| `src/kintsugi/signal/bootstrap.py` | `bootstrap_from_project()`, `bootstrap_from_pairs()` |
| `src/kintsugi/claude/parameter_learning.py` | `algorithm_version` column, `_aggregate_ranges()` |
| `src/kintsugi/mcp/tools/signal_isolation.py` | `analyze_weighted_subtraction()`, extended `subtract_blank()` |
| `src/kintsugi/mcp/tools/learning.py` | Extended `_get_heuristic_suggestion()`, `record_successful_parameters()` |
| `src/kintsugi/cli.py` | `kintsugi mcp pretrain` command |
| `tests/test_signal_autofluorescence.py` | `TestWeightedSubtraction`, `TestComputeIntensityRanges`, `TestBuildWeightMap`, etc. |

## Data Structures

```python
@dataclass
class IntensityRange:
    lower_bound: float       # Inclusive lower boundary
    upper_bound: float       # Exclusive upper boundary
    weight: float            # Scale multiplier (0.1-1.5) for blank in this range
    label: str = ""          # "background", "dim", "medium", "bright"

@dataclass
class WeightedSubtractionParameters:
    blank_clip_factor: int = 0
    base_scale_factor: float = 1.0
    n_ranges: int = 5
    range_method: str = "percentile"   # "percentile" | "otsu" | "manual"
    ranges: list[IntensityRange] = field(default_factory=list)
    transition_width: float = 0.1      # Fraction of range width for blending
```

## Learning Database Schema

```sql
ALTER TABLE parameter_records ADD COLUMN algorithm_version TEXT DEFAULT 'v1';
```

Weighted records store `algorithm_version="weighted_v1"` with per-range weights in `parameters_json`. Aggregation averages per-range weights across matching records with same `n_ranges`.

## References

- `signal/autofluorescence.py` — Core weighted subtraction implementation
- `signal/bootstrap.py` — Batch pretraining from existing processed data
- `tests/test_signal_autofluorescence.py` — Test classes for weighted subtraction
