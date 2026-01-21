# Notebook Data Consistency

## Goal
Avoid shape mismatches when changing data sources in Jupyter notebooks.

## What Failed
- Changing `protein_shared` to use gated data (1.2M cells) but leaving `protein_active` using raw data (1.9M cells)
- Updating one cell without checking downstream cells that depend on the same variable
- Guessing at detection thresholds instead of tracing the actual data processing pipeline

## What Works
1. **Before changing any data source**, grep for ALL references:
   ```bash
   grep -n "protein_adata" notebook.ipynb
   ```

2. **Trace the dependency chain**:
   - `protein_adata` → `protein_adata_active` → `protein_active`
   - `protein_gated` → `protein_shared_adata` → `protein_shared`
   - ALL must use the SAME source

3. **Check shapes immediately after changes**:
   ```python
   assert protein_shared.shape[0] == protein_active.shape[0], "Cell count mismatch"
   ```

4. **For thresholds/gates**: Find the notebook/script that created the data and use those exact values

## Common Shape Mismatch Causes
| Symptom | Cause | Fix |
|---------|-------|-----|
| `protein_shared` vs `protein_active` different rows | Mixed data sources | Use same h5ad for both |
| Feature count mismatch after filtering | Didn't update correspondence array | Filter all arrays together |
| AnnData shape error on assignment | Didn't subset AnnData before updating .X | `adata = adata[:, valid_features].copy()` first |

## Trigger
When modifying data loading or normalization cells in multi-cell notebooks.
