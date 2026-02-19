---
name: h5ad-shiny-data-pipeline
description: "Patterns for H5AD-backed Shiny apps with Excel fallback, groovy data in .uns, scVI QC validation"
author: smith6jt
date: 2026-02-17
---

# H5AD → Shiny Data Pipeline - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-17 |
| **Goal** | Replace scattered Excel data loading with a single validated H5AD pipeline, while maintaining backward compatibility with existing Excel-based loading |
| **Environment** | R 4.x, Shiny 1.12.1, anndata (R pkg), Python: scanpy 1.11.5, anndata 0.12.4, scvi-tools 1.4.0, scib-metrics, conda env `scvi-env` |
| **Status** | Success |

## Context
The Islet Explorer app loaded data from `master_results.xlsx` (4 sheets: targets, markers, composition, LGALS3), built from per-donor TSV exports. The trajectory tab loaded a separate `adata_ins_root.h5ad` that was produced by a problematic pipeline (mixed morphology+protein features, weak n_neighbors=5, missing batch correction). Phase 2 rebuilt the pipeline and unified data loading.

Key problems with the old pipeline:
- `.X` contained 47 variables (proteins + morphology mixed) — morphology dominated trajectory
- n_neighbors=5 (non-standard, too sparse)
- No `X_scVI_mean` (no batch correction in embeddings)
- Missing phenotype_proportions in `.obsm`
- 5,158 islets (combined core+peri regions)
- Donor 6533 potentially missing

## Verified Workflow

### 1. Store groovy/TSV tabular data in H5AD `.uns`
H5AD's `.uns` dict can store arbitrary arrays. For tabular data (like QuPath TSV exports), store each column as a separate array with a naming convention:

```python
# Python: scripts/build_h5ad_for_app.py
for col in targets_df.columns:
    vals = targets_df[col].values
    key = f'groovy_targets_{col}'
    if pd.api.types.is_bool_dtype(vals):
        adata.uns[key] = vals.astype(bool)
    elif pd.api.types.is_numeric_dtype(vals):
        adata.uns[key] = np.array(vals, dtype=float)
    else:
        adata.uns[key] = np.array(vals, dtype=str)

# Also store column names and row count for reconstruction
adata.uns['groovy_targets_columns'] = list(targets_df.columns)
adata.uns['groovy_targets_n_rows'] = len(targets_df)
```

```r
# R: Reconstruct DataFrame from .uns arrays
reconstruct_groovy_df <- function(ad, sheet) {
  prefix <- paste0("groovy_", sheet, "_")
  cols_key <- paste0("groovy_", sheet, "_columns")
  col_names <- ad$uns[[cols_key]]
  n_rows <- as.integer(ad$uns[[paste0("groovy_", sheet, "_n_rows")]])
  df <- data.frame(row.names = seq_len(n_rows))
  for (col in col_names) {
    df[[col]] <- ad$uns[[paste0(prefix, col)]]
  }
  df
}
```

### 2. H5AD → Excel fallback in Shiny data loading
Design the H5AD loader to return the **same list structure** as the existing Excel loader. This means `prep_data()` needs zero changes.

```r
# In data_loading.R
load_master_auto <- function(h5ad_path = NULL, excel_path = master_path) {
  if (!is.null(h5ad_path) && file.exists(h5ad_path)) {
    result <- load_master_h5ad(h5ad_path)
    if (!is.null(result)) return(result)
  }
  if (file.exists(excel_path)) return(load_master(excel_path))
  stop("No data source found")
}

# In app.R server
master <- reactive({
  load_master_auto(h5ad_path = h5ad_path, excel_path = master_path)
})
# prepared() calls prep_data(master()) — unchanged
```

### 3. scVI batch correction validation
Validate with three complementary metrics on a subsample (50K cells for efficiency):

```python
# Silhouette batch score (lower = better mixing)
sil_pca = silhouette_score(X_pca, batch_labels, sample_size=10000)
sil_scvi = silhouette_score(X_scVI, batch_labels, sample_size=10000)
# Pass: sil_scvi < sil_pca

# Cell-type silhouette (higher = better separation, preserved biology)
sil_ct_scvi = silhouette_score(X_scVI, celltype_labels, sample_size=10000)
# Pass: sil_ct_scvi >= 0.8 * sil_ct_pca

# LISI (custom implementation using k-NN + inverse Simpson's index)
# Batch LISI: higher = better mixing (ideal = n_batches)
# Cell-type LISI: lower = better separation (ideal = 1)
```

### 4. Trajectory rebuild from fixed pipeline
The fixed aggregation keeps only proteins in `.X` and uses `X_scVI_mean` for neighbors:

```python
# Aggregate with fixed_islet_aggregation.py
adata = create_islet_dataset_fixed(adata_sc, region='islet_only', min_cells=20)
# .X = protein expression only (31 vars)
# .obsm['X_scVI_mean'] = batch-corrected latent means
# .obsm['phenotype_proportions'] = cell type fractions

# Compute trajectory
sc.pp.neighbors(adata, n_neighbors=15, use_rep='X_scVI_mean', metric='cosine')
sc.tl.paga(adata, groups='donor_status')
sc.tl.umap(adata, init_pos='paga')
# Root: ND islet with highest INS expression
sc.tl.diffmap(adata, n_comps=10)
sc.tl.dpt(adata)
```

Validation checks:
- INS vs pseudotime: Spearman r < -0.3
- GCG vs pseudotime: Spearman r > 0.2
- Donor status ordering: mean(ND) < mean(Aab+) < mean(T1D)
- No single donor > 80% of any pseudotime quintile

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Old pipeline: mixing morphology + protein in `.X` (47 vars) | Morphology features (cell area, nucleus size) dominated the neighbor graph and trajectory, masking biological signal from protein markers | Always keep `.X` as protein-only; store morphology in `.obsm['morphology']` |
| Old pipeline: n_neighbors=5 | Too few neighbors created disconnected/noisy graphs, especially with <1000 islets | Use n_neighbors=15 (standard) for islet-level data; 5 is only appropriate for very dense single-cell data |
| Old pipeline: PCA-based neighbors (no batch correction) | Donor-specific technical effects drove the UMAP clustering, obscuring disease biology | Use `X_scVI_mean` with cosine metric for batch-corrected neighbor computation |
| Storing DataFrames directly in `.uns` | H5AD serialization doesn't handle pandas DataFrames well in `.uns` (type conversion issues) | Store each column as a separate numpy array with a naming convention prefix; reconstruct on the R side |
| Defining slash commands in CLAUDE.md | Claude Code only discovers skills from `.claude/skills/<name>/SKILL.md` files — CLAUDE.md is loaded as documentation context only, NOT for skill registration | Always create skill files in `.claude/skills/`; git submodule CLAUDE.md files are not searched for skills |
| `adata.obs.reset_index()` when index name matches column | `islets_core_fixed.h5ad` has `islet_id` as both the index name AND a column → pandas raises `ValueError: cannot insert islet_id, already exists` | Check `if idx_name in adata.obs.columns: reset_index(drop=True)` before any merge that uses reset_index |
| `fillna('')` on categorical columns | h5py can't write NaN in string columns, but `.fillna('')` on a Categorical raises `TypeError: Cannot setitem on a Categorical with a new category` | Always `.astype(str)` BEFORE `.fillna('')` for categorical obs columns |
| Using `CODEX_Pancreas_Donors.xlsx` for donor metadata | The Excel file has a **different donor cohort** (nPOD pilot: 6090, 6171...) than the CODEX data (6505, 6533...) — ALL merges produce NaN | Derive donor metadata (status, age, gender, AAb flags) from the h5ad obs itself, not from external donor key files. Build `donor_key_df` from `adata.obs.groupby('imageid')` |
| Missing `combined_islet_id` in rebuilt h5ad | `islets_core_fixed.h5ad` has `islet_id` (e.g., `6505_Islet_284`) but trajectory module references `combined_islet_id` | Add `adata.obs['combined_islet_id'] = adata.obs['islet_id'].copy()` before saving trajectory h5ad |
| Heatmap `mids` vs `hm` row count mismatch | `mids` computed for all 25 bins but `hm` only has rows for bins with >=3 points → `replacement has 25 rows, data has 24` | Use `match(as.character(hm$pt_bin), bin_levels)` to index `all_mids` so skipped bins are excluded |
| Diverging colormap for raw expression on UMAP | `scale_color_gradient2(limits=c(-3,3))` assumed z-scored data but `.X` values are raw mean expression — colorbar misleading | Use `scale_color_viridis_c(option="inferno", limits=range(value))` for continuous min/max scaling |

## Final Parameters

```yaml
# Islet aggregation (fixed_islet_aggregation.py)
region: islet_only
min_cells: 20
require_paired: false  # Don't require peri-islet for trajectory

# Neighbor computation
n_neighbors: 15
use_rep: X_scVI_mean
metric: cosine

# UMAP
init_pos: paga
min_dist: 0.1
spread: 1.5

# DPT
n_comps: 10  # diffusion map components
root: ND islet with max INS expression

# scVI QC thresholds
silhouette_batch: scVI < PCA
silhouette_celltype: scVI >= 0.8 * PCA
batch_lisi: median(scVI) > median(PCA)

# Python environment
conda_env: scvi-env
python_packages: scanpy==1.11.5, anndata==0.12.4, scvi-tools==1.4.0, scib-metrics
```

## Key Insights

- **Interface stability**: Design H5AD loading to return identical structures as existing Excel loading. This means downstream code (prep_data, modules) needs zero changes. The fallback pattern (`load_master_auto`) is clean and testable.
- **`.uns` for tabular data**: H5AD `.uns` is a flexible dict, but column-by-column storage with a naming convention (`groovy_targets_colname`) is more robust than trying to store entire DataFrames.
- **Subsample for QC metrics**: scVI validation doesn't need all 2.6M cells. 50K cells (or 10K for LISI) gives reliable metrics in seconds vs minutes.
- **PAGA-initialized UMAP**: `init_pos='paga'` gives more meaningful UMAP topology than random initialization, especially for trajectory data where group connectivity matters.
- **Validation gates**: Define quantitative pass/fail criteria (r < -0.3 for INS, etc.) before running the pipeline. This prevents post-hoc rationalization of poor trajectories.
- **Claude Code skills**: `.claude/skills/<name>/SKILL.md` is the ONLY mechanism for registering slash commands. CLAUDE.md, git submodules, and plugin.json files are NOT discovered as skills.
- **Donor metadata provenance**: Never assume an external Excel "donor key" matches your data cohort. Build donor metadata from the canonical h5ad obs itself — it already has `donor_status`, `age`, `gender`, and AAb flags from the single-cell phenotyping.
- **Column name compatibility**: When h5ad obs columns get renamed across pipeline steps (e.g., `islet_id` → `combined_islet_id`), add the expected alias before saving. Check what downstream consumers expect by grepping the app code.
- **H5AD write gotchas**: Before `adata.write_h5ad()`, iterate all obs columns and convert categoricals → `str` then `fillna('')`. Also check that obs index name doesn't collide with a column name.

## Execution Results (2026-02-17)

| Metric | Value |
|--------|-------|
| scVI batch LISI | 2.73 (PCA) → 8.07 (scVI) |
| INS vs pseudotime | r = -0.741 |
| GCG vs pseudotime | r = 0.379 |
| Donor ordering | ND=0.491 < Aab+=0.516 < T1D=0.743 |
| Max donor quintile fraction | 0.38 (threshold: <0.80) |
| Islets | 1,015 (31 protein vars) |
| islet_explorer.h5ad | 47 MB |
| H5AD vs Excel prep_data | targets=48,438, markers=64,584, comp=5,382 (identical) |
| Total validation checks | 33/33 passed |

## References

- [AnnData format](https://anndata.readthedocs.io/) — `.uns` storage for arbitrary metadata
- [scVI-tools](https://docs.scvi-tools.org/) — Batch correction with biological covariates
- [scib-metrics](https://scib-metrics.readthedocs.io/) — Batch integration benchmarking
- [Scanpy trajectory analysis](https://scanpy.readthedocs.io/en/stable/api/tl.html) — DPT, PAGA, diffusion maps
- Islet Explorer: `data/DATA_PROVENANCE.md` for full lineage documentation
