---
name: genotype-hypothesis-analysis
description: "Multi-hypothesis genotype analysis framework for spatial biology data with small sample sizes. Trigger: (1) comparing measurements across genotype groups with small n (3-4/group), (2) multi-notebook analysis of spatial/multiplex imaging annotations, (3) vessel/region density normalized across tissue compartments."
author: smith6jt
date: 2026-02-26
---

# Genotype Hypothesis Analysis - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-26 |
| **Goal** | Build a reusable multi-hypothesis analysis framework for comparing spatial biology measurements across genotype groups (rs3184504 C/C, C/T, T/T) |
| **Environment** | Python 3.12, pandas 2.x, scipy, seaborn, matplotlib, Jupyter notebooks |
| **Status** | Success |

## Context
QuPath-segmented multiplex imaging data (Phenocycler spleen tissue) with ~500K annotations across 13 images from 10 samples. Need to compare vessel density, morphology, tissue architecture, and follicle vascularization across 3 genotype groups with very small n (3-4 per group). Standard parametric tests are inappropriate; need non-parametric framework with effect size reporting.

## Verified Workflow

### 1. Shared data_utils.py module pattern
Centralize all data loading, genotype mapping, filtering, and statistics in one module imported by all notebooks:

```python
# analysis/data_utils.py — key functions:
# load_data() → reads CSV, adds Sample/Genotype columns, drops exclusions
# get_regions(df) / get_vessels(df) → filter by Classification
# compute_density(df) → vessel count / region area (mm²), with RedPulp normalization
# assign_vessels_to_follicles(df, image) → cKDTree nearest-centroid assignment
# full_stats_table(data, value_col) → Kruskal-Wallis + pairwise Mann-Whitney + Spearman dosage
```

### 2. Sample ID extraction from heterogeneous image names
```python
def extract_sample_id(image_name):
    """Handles HDL011_PC33.ome.tiff, HDL052SPLN_2025Aug6_Scan1.er.qptiff, 1901HBMP004_PC29.ome.tiff"""
    m = re.match(r"(HDL\d+)", image_name)
    if m: return m.group(1)
    m = re.match(r"(\d{4}HBMP\d+)", image_name)
    if m: return m.group(1)
    return image_name.split("_")[0]
```

### 3. Statistical framework for small n
```python
# Omnibus: Kruskal-Wallis (non-parametric ANOVA)
# Pairwise: Mann-Whitney U with rank-biserial effect size r = 1 - 2U/(n1*n2)
# Gene dosage: Spearman correlation with ordinal encoding (C/C=0, C/T=1, T/T=2)
# Unit of analysis: per-image aggregates, NOT individual annotations
```

### 4. Density normalization
```python
# RedPulp normalization: density_normalized = density / redpulp_density_same_image
# This controls for image-level variation in overall vessel detection sensitivity
```

### 5. Spatial vessel-to-follicle assignment (cKDTree)
```python
from scipy.spatial import cKDTree
fol_coords = follicles[["Centroid X µm", "Centroid Y µm"]].values
tree = cKDTree(fol_coords)
_, indices = tree.query(vessel_coords)
# Assign each vessel to nearest follicle centroid
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| pandas Categorical genotype with default `groupby()` | Creates cross-product of all categories × groups, producing NaN rows and memory bloat | Always use `observed=True` with Categorical columns in groupby |
| Using individual annotations as units of analysis | Pseudoreplication — thousands of vessels per image are not independent | Aggregate to per-image statistics (median, count) first, then compare groups |
| `AllAnnotations.csv` as data source | Missing newer images (HDL053, HDL070, HDL073, 1901HBMP004) | Use `AnnotationsFinal.csv` which includes all 13 images |
| Violin plots as primary statistical evidence | Misleading with small n — shows vessel-level distributions, not sample-level | Use boxplot+strip of per-image aggregates; violins are "visual only" with caveat |
| Parametric tests (t-test, ANOVA) | n=3-4 per group violates normality assumptions | Kruskal-Wallis + Mann-Whitney; report effect sizes over p-values |

## Final Parameters

```yaml
# Statistical framework
omnibus_test: kruskal-wallis
pairwise_test: mann-whitney-u (two-sided)
effect_size: rank-biserial (r = 1 - 2U/n1n2)
dosage_trend: spearman correlation
unit_of_analysis: per-image aggregate

# Density computation
area_unit: mm² (divide µm² by 1e6)
normalization: RedPulp density per image
main_regions: [Follicle, PALS, RedPulp, Trabeculae]

# Vessel morphology
metrics: [Area, Circularity, Solidity, Elongation, Max_diameter, Min_diameter]
elongation: Max_diameter / Min_diameter
size_bins_um2: [0, 50, 200, inf]  # Small, Medium, Large

# Spatial assignment
method: scipy.spatial.cKDTree nearest-centroid
follicle_size_stratification: tertiles (qcut q=3)

# Plotting
style: seaborn whitegrid, font_scale=1.1
palette: Set2 (3 colors for 3 genotypes)
figure_dpi: 150
format: PNG
```

## Key Insights
- **Effect sizes > p-values** with n=3-4 per group — include this caveat prominently
- **RedPulp normalization** controls for batch/image-level detection sensitivity differences
- **cKDTree spatial assignment** works well when follicles are well-separated (r=0.76 area-count correlation validates approach)
- **Shared module pattern** (`data_utils.py`) eliminates code duplication and ensures consistency across 5+ notebooks
- **Per-image medians** are more robust than means for morphology metrics with heavy-tailed distributions
- **Include zero-vessel follicles** in per-follicle analyses — left-join with all follicles to avoid survivorship bias
- **Gene dosage trend** (Spearman with ordinal encoding) is particularly informative for allele-dosage hypotheses

## References
- SH2B3/LNK: negative regulator of JAK-STAT signaling
- rs3184504 T allele: R262W loss-of-function variant
- QuPath v0.6.0 for image segmentation
- SpleenFollicleCounterQP project
