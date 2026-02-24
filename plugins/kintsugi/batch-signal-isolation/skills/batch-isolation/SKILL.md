# Batch Signal Isolation with Recipe-Driven Processing

## Goal

Replace naive batch signal isolation with a recipe-driven pipeline that matches the legacy Notebook 3 interactive workflow: multi-step subtraction, per-marker tuned parameters, background cleaning, and parameter learning for cross-dataset transfer.

## Context

CX_19-001_SP_CC2-A28 (13 cycles, 28 signal markers, spleen) was first processed with auto-analyzed parameters at ~8 min/channel. The results were poor compared to the manually tuned Notebook 3 outputs — the batch code only did a single subtraction step with expensive blank smoothing (sigma=500), while the legacy pipeline uses primary + secondary subtraction + background cleaning with per-marker tuned parameters.

**Root cause**: Our batch code implemented a single subtraction with automated parameters. The legacy pipeline uses a multi-step process:
1. Primary subtraction with tuned clip/scale factors
2. Optional second subtraction with a different blank
3. Background cleaning (threshold + median smooth + small object removal)

## What Worked

### Recipe-Driven Pipeline (v2.0)

**`load_legacy_recipes(recipe_dir)`** parses `*_param.txt` files (key-value format from Notebook 3) into `MarkerRecipe` dataclasses:
- Uses `ast.literal_eval()` with fallback for unparseable values
- Skips `dask.array<...>` and `datetime.datetime(...)` artifact lines
- Handles missing fields with dataclass defaults

**Three new dataclasses**: `SubtractionParams`, `CleanParams`, `MarkerRecipe`

**Blank name resolution chain**:
1. `_normalize_blank_name()`: `Blank1b` → `Blank_1b`, `Blank13c` → `Blank_13c`
2. Exact match in location map (all channel names → paths)
3. Fuzzy match: strip hyphens/underscores, case-insensitive (e.g., `HLADR` → `HLA-DR`)

**`clean_background(image, params)`** — pure numpy reimplementation of `Kutils.clean()`:
1. Zero pixels below `background_threshold`
2. Median filter in transition zone (between 0 and `smooth_threshold`)
3. `remove_small_objects` + morphological closing

### Performance: sigma=0 + recipes = ~30 sec/channel
- Old: ~8 min/channel (sigma=500 blank smoothing dominated)
- New with recipes + sigma=0: ~30 sec/channel
- Full batch (28 markers): completed successfully, all 28 channels processed

### Auto Method Selection (unchanged from v1)
- **Rule 1**: `blank_p99 / signal_p99 > 1.2` → weighted
- **Rule 2**: `af_contribution > 0.3 AND correlation > 0.4` → weighted
- **Rule 3**: `correlation > 0.5 AND dynamic_range > 5000` → weighted
- **Default**: global

### Parameter Learning DB Integration
- Records recipe outcomes to `ParameterLearningEngine` after successful processing
- Two operations per channel: `blank_subtraction` and `clean_background`
- `algorithm_version="recipe_v1"` distinguishes from auto-analyzed params
- `--learn/--no-learn` CLI flag controls recording (default: `--learn`)
- Enables cross-dataset transfer: manually tuned params from CX_19-001 spleen propagate to other spleen datasets

### Self-Normalized QC (unchanged from v1)
- Before/After/Difference 3-column layout
- Self-normalized to own p1-p99 — dim signal visible instead of all-black

### CLI Updates
- `--recipe-dir` option on `plan` and `run` subcommands
- `--learn/--no-learn` flag on `run` subcommand
- `--tile-smooth-sigma` default changed from 500 to 0
- Summary output includes recipe count

## Failed Attempts

| Attempt | Problem | Fix |
|---------|---------|-----|
| Hardcoded `blank_scale_factor=1.0` for all channels | Over-subtraction of dim markers | Per-marker recipes from Notebook 3 param files |
| Single subtraction step only | ~70% of markers need second subtraction | `recipe.second` SubtractionParams with different blank |
| No background cleaning | Noisy background in subtracted images | `clean_background()` with threshold + median + small object removal |
| sigma=500 blank smoothing (default) | 6 min per channel, not needed with recipes | Changed default to sigma=0; recipes work without smoothing |
| Global method only for all channels | Blank dominates dim markers → signal lost | Auto-select weighted when blank dominates (still used for markers without recipes) |
| QC normalized both columns to same range | After images appeared uniformly dark | Self-normalize each column to own p1-p99 |
| `compute_weighted_subtraction_quality()` → flat dict | Returns `{"global": {...}, "per_range": [...]}` | Extract `quality["global"]` for flat quality_score access |
| Blank names from param files don't match filenames | `Blank1b` vs `Blank_1b`, `HLADR` vs `HLA-DR` | Normalize + fuzzy match resolution chain |
| `dask.array<...>` lines in param files | `ast.literal_eval` fails on them | Skip lines with dask/datetime prefixes, return None |

## Key Files

| File | Purpose |
|------|---------|
| `src/kintsugi/signal/batch.py` | Core: `SubtractionParams`, `CleanParams`, `MarkerRecipe`, `load_legacy_recipes()`, `clean_background()`, blank resolution helpers, `discover_channels()`, `process_channel()`, `process_batch()` |
| `src/kintsugi/signal/isolation_qc.py` | QC: `generate_qc_pages()`, `generate_summary_table()`, `_self_normalize()` |
| `src/kintsugi/cli.py` | CLI: `@workflow.group("isolate")` → plan, run, qc, status; `--recipe-dir`, `--learn/--no-learn` |
| `src/kintsugi/signal/__init__.py` | Exports for batch + isolation_qc modules |
| `src/kintsugi/claude/parameter_learning.py` | `ParameterLearningEngine` for recording outcomes |
| `tests/test_batch_signal_isolation.py` | 66 tests across 14 test classes |

## Final Parameters

```python
# Recipe-driven processing (default path with --recipe-dir)
# No blank smoothing — recipes provide exact parameters
tile_smooth_sigma = 0.0

# Method selection thresholds (for markers without recipes)
BLANK_DOMINANCE_RATIO = 1.2
AF_CONTRIBUTION_THRESHOLD = 0.3
CORRELATION_THRESHOLD_AF = 0.4
CORRELATION_THRESHOLD_RANGE = 0.5
DYNAMIC_RANGE_THRESHOLD = 5000

# QC visualization
page_size = 6
downsample = 16
dpi = 120
p_low, p_high = 1.0, 99.0

# CLI usage
# kintsugi workflow isolate run . --recipe-dir .../Processing_parameters --tissue-type spleen
# kintsugi workflow isolate run . --recipe-dir .../Processing_parameters --channels CD3e --force
# kintsugi workflow isolate qc .
```

## Snakemake Pipeline Integration (Feb 2026)

Signal isolation is now **Rule 5** in the Snakemake pipeline, running automatically after registration. The `process_batch()` function is called by `workflow/scripts/signal_isolation.py` as a Snakemake wrapper script. This eliminates manual CLI chaining — `kintsugi workflow batch` now runs the full pipeline through signal isolation. See `snakemake-signal-isolation` skill for implementation details.

## Environment

- Python 3.11, NumPy <2.0, SciPy, scikit-image, tifffile, matplotlib, PyYAML
- HiPerGator SLURM cluster (login nodes, no GPU required for signal isolation)
- Images: ~189 MB per channel (7479x12662 px), uint16
- Processing with recipes: ~30 sec/channel (was ~8 min with sigma=500)
- Test suite: 66 tests, <7 seconds

## Verified On

- CX_19-001_SP_CC2-A28: 13 cycles, 28 signal markers, spleen tissue
  - 24 recipe-driven + 4 auto-weighted (CD5, HLA-DR, PanCK, Podoplanin)
  - Mean quality score: 0.803, 0 errors
- Synthetic test data: 256x256 and 64x64 images with various channel configurations
