---
name: pipeline-reaggregation-rebuild
description: "Full islet pipeline rebuild: changing aggregation filters, creating standalone scripts, running 4-step pipeline"
author: smith6jt
date: 2026-02-23
---

# Pipeline Reaggregation Rebuild - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-23 |
| **Goal** | Remove min_cells=20 filter to recover all ~5,023 paired islets (from 949) and rebuild full pipeline |
| **Environment** | scvi-env conda (scanpy, anndata, scvi-tools), Ubuntu 22.04 |
| **Status** | Success |

## Context

The `fixed_islet_aggregation.py` applied a `min_cells=20` filter that dropped ~81% of islets (5,023 paired down to 949). This was excessive for the Islet Explorer app which benefits from showing all islets regardless of size. The filter was the intersection of: core cells > 20 AND peri cells > 20 AND both regions exist (require_paired=True).

With `min_cells=0`, all 5,023 paired islets are kept (any islet with >=1 cell in both core and peri). The Shiny app code was already robust to variable islet counts — no hardcoded limits anywhere.

The existing workflow used separate notebooks (`rebuild_trajectory.ipynb`, `islet_umap_clustering.ipynb`) that had to be run manually in sequence. This was consolidated into a single `scripts/reaggregate_islets.py`.

## Verified Workflow

### Step 1: Modify aggregation default

```python
# islet_analysis/fixed_islet_aggregation.py line 17
# Change: min_cells=20 → min_cells=0
def create_islet_dataset_fixed(adata_subset, region='islet_only', min_cells=0, ...)
```

### Step 2: Create standalone pipeline script

```bash
# scripts/reaggregate_islets.py consolidates:
#   - Aggregation (from Panc_codex_islet_analysis_fixed.ipynb)
#   - Trajectory (from rebuild_trajectory.ipynb)
#   - Leiden clustering (from islet_umap_clustering.ipynb)
```

Key design decisions:
- Uses existing functions from `fixed_islet_aggregation.py` (no logic duplication)
- Follows same path-anchoring pattern as other scripts (`SCRIPT_DIR`, `PROJECT_ROOT`)
- Argparse with defaults matching existing paths
- Validation checks with PASS/FAIL (non-blocking — saves even on FAIL)

### Step 3: Run full pipeline

```bash
conda activate scvi-env

# Step 1: Reaggregate + trajectory + Leiden (~15 min, reads 2.6M-cell H5AD)
python scripts/reaggregate_islets.py

# Step 2: Compute neighborhood metrics (~3 min)
python scripts/compute_neighborhood_metrics.py

# Step 3: Extract per-islet cell CSVs (~5 min)
python scripts/extract_per_islet_cells.py

# Step 4: Build app H5AD
python scripts/build_h5ad_for_app.py
```

Steps 2 and 3 can run in parallel (independent).

`extract_per_donor_tissue.py` is NOT needed (extracts ALL cells per donor, independent of islet filtering).

### Step 4: Update notebooks for consistency

Update `min_cells=20` → `min_cells=0` in:
- `islet_analysis/Panc_codex_islet_analysis_fixed.ipynb` cell 6
- `notebooks/rebuild_trajectory.ipynb` cell 6

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Donor 6533 validation check | FAIL — 6533 has 0 core/peri cells in single-cell H5AD | This is expected behavior, not a bug. 6533 has tissue cells but no islet-annotated cells. The validation correctly reports FAIL and continues. |
| N/A — no real failures | Pipeline ran cleanly on first attempt | The existing `fixed_islet_aggregation.py` functions were well-designed for parameterization; only the default needed changing |

## Final Parameters

```yaml
# Aggregation
min_cells: 0          # was 20, now keeps all islets with >=1 cell
require_paired: true  # must have both core AND peri-islet regions
region: separate      # creates both core and peri datasets

# Trajectory (unchanged)
n_neighbors: 15
metric: cosine
use_rep: X_scVI_mean
umap_init: paga
umap_min_dist: 0.1
umap_spread: 1.5
diffmap_n_comps: 10
root: ND islet with highest INS

# Leiden clustering
resolutions: [0.3, 0.5, 0.8, 1.0]
leiden_umap_min_dist: 0.3
leiden_umap_spread: 1.0
```

### Pipeline Outputs

| Output | Before (min_cells=20) | After (min_cells=0) |
|--------|----------------------|---------------------|
| islets_core_fixed.h5ad | 949 islets | 5,023 islets |
| adata_ins_root.h5ad | 949 islets | 5,023 islets |
| islets_core_clustered.h5ad | 949 islets | 5,023 islets |
| neighborhood_metrics.csv | 949 rows (66 NaN) | 5,023 rows (0 NaN) |
| data/cells/*.csv | 949 files, 111 MB | 5,023 files, 203 MB |
| islet_explorer.h5ad | 48 MB | 70 MB |

### Trajectory Validation

| Metric | Before (949) | After (5,023) | Threshold |
|--------|-------------|---------------|-----------|
| INS r | -0.741 | -0.591 | < -0.3 |
| GCG r | 0.379 | 0.308 | > 0.2 |
| ND mean PT | 0.491 | 0.488 | ND < Aab+ < T1D |
| Aab+ mean PT | 0.516 | 0.506 | |
| T1D mean PT | 0.743 | 0.571 | |

Note: correlations weaken with more islets (small islets are noisier) but remain well above thresholds.

## Key Insights

- **The Shiny app needed zero changes** — all modules use dynamic data loading with no hardcoded islet counts. This validated the modular architecture from Phase 4.
- **require_paired=True gives 100% peri coverage** — with min_cells=0, there are no NaN peri-islet metrics, eliminating the need for `total_cells_peri > 0` guards (though they remain for robustness).
- **Standalone pipeline script > notebooks** — `reaggregate_islets.py` consolidates 3 notebooks into one runnable script with CLI args, validation, and progress output. Much easier to reproduce.
- **Trajectory correlations weaken but remain valid** — INS r goes from -0.741 to -0.591 with 5x more islets. The small islets (1-20 cells) are noisier but the biological signal persists.
- **Pipeline steps 2 and 3 are parallelizable** — `compute_neighborhood_metrics.py` and `extract_per_islet_cells.py` both read from the single-cell H5AD independently.
- **`islet_analysis/` is gitignored** — changes to `fixed_islet_aggregation.py` and notebooks there won't show in `git status` but still take effect on disk.
- **Donor 6533 has 0 islet cells** — this is a known data characteristic, not a pipeline bug. The donor has tissue cells but no QuPath islet annotations in the single-cell H5AD.
- **Update ALL docs after pipeline changes** — CLAUDE.md, MEMORY.md, DATA_PROVENANCE.md, islet_analysis/CLAUDE.md, docs/user_guide.md all reference islet counts and file sizes.

## References

- `islet_analysis/fixed_islet_aggregation.py` — core aggregation functions
- `scripts/reaggregate_islets.py` — new standalone pipeline script
- `data/DATA_PROVENANCE.md` — full data lineage documentation
- CLAUDE.md "Data Pipeline" section — canonical pipeline documentation
