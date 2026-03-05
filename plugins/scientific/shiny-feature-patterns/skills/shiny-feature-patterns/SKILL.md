---
name: shiny-feature-patterns
description: "Patterns for adding interactive features to modular Shiny apps with H5AD data, conditional UI, embedded panels, tissue scatter, Leiden clustering"
author: smith6jt
date: 2026-02-20
---

# Shiny Feature Patterns - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-19 (updated 2026-02-20) |
| **Goal** | Interactive Shiny feature patterns: composition explorer, demographics, embedded panels, tissue scatter, Leiden, UI alignment, layer ordering, font standards |
| **Environment** | R 4.x, Shiny 1.12.1, plotly 4.12.0, ggplot2, anndata (R pkg), H5AD with `.obs` containing `prop_*` columns, `age`, `gender` |
| **Status** | Success |

## Context
The Islet Explorer app had rich data in its H5AD `.obs` layer (21 cell-type phenotype proportions, donor demographics) that wasn't exposed in the UI. The Plot tab only offered 3 hormone fraction choices, there were no demographic filters, and the trajectory heatmap was a single donor-status gradient row. Additionally, the Plot tab used a modal popup for segmentation viewing while the Trajectory tab used an embedded panel — inconsistent UX.

## Verified Workflow

### 1. Extract H5AD `.obs` data in the loader, not `prep_data()`
Keep extraction in `load_master_h5ad()` and return new list elements. This preserves the `load_master()` → `prep_data()` contract while adding optional data.

```r
# In load_master_h5ad():
phenotype_df <- tryCatch({
  obs <- as.data.frame(ad$obs)
  prop_cols <- grep("^prop_", colnames(obs), value = TRUE)
  if (length(prop_cols) > 0 && "imageid" %in% colnames(obs)) {
    phen <- obs[, c("imageid", "base_islet_id", prop_cols), drop = FALSE]
    phen$`Case ID` <- as.integer(as.character(phen$imageid))
    phen$islet_key <- gsub("^Islet_Islet_", "Islet_", as.character(phen$base_islet_id))
    phen[, c("Case ID", "islet_key", prop_cols)]
  } else NULL
}, error = function(e) NULL)

# Return extended list:
list(markers=m, targets=t, comp=c, lgals3=l, phenotypes=phenotype_df, donor_demographics=demo_df)
```

### 2. Merge optional data in `prep_data()` with NULL guards
```r
# Phenotypes merge into comp (H5AD only; NULL from Excel)
if (!is.null(master$phenotypes) && nrow(master$phenotypes) > 0) {
  comp <- safe_left_join(comp, master$phenotypes, by = c("Case ID", "islet_key"))
}

# Demographics merge into all dataframes
if (!is.null(master$donor_demographics) && nrow(master$donor_demographics) > 0) {
  targets_all <- safe_left_join(targets_all, master$donor_demographics, by = "Case ID")
  markers_all <- safe_left_join(markers_all, master$donor_demographics, by = "Case ID")
  comp <- safe_left_join(comp, master$donor_demographics, by = "Case ID")
}
```

### 3. Conditional UI with `renderUI` returning NULL
For features that depend on data availability, use `uiOutput` in UI + `renderUI` in server that checks column existence:

```r
# UI: just a slot
uiOutput(ns("age_filter_ui"))

# Server: renders only when data available
output$age_filter_ui <- renderUI({
  pd <- prepared()
  if (is.null(pd$comp) || !("age" %in% colnames(pd$comp))) return(NULL)
  age_vals <- as.numeric(pd$comp$age)
  age_vals <- age_vals[is.finite(age_vals)]
  if (length(age_vals) == 0) return(NULL)
  sliderInput(ns("age_range"), "Donor Age (years)",
              min = floor(min(age_vals)), max = ceiling(max(age_vals)),
              value = c(floor(min(age_vals)), ceiling(max(age_vals))), step = 1)
})
```

### 4. Filter application with column-existence guards
Apply optional filters defensively — check both input existence and column existence:

```r
if (!is.null(input$age_range) && length(input$age_range) == 2 && "age" %in% colnames(out)) {
  out <- out[is.finite(as.numeric(out$age)) &
             as.numeric(out$age) >= input$age_range[1] &
             as.numeric(out$age) <= input$age_range[2], , drop = FALSE]
}
```

### 5. Grouped selectInput for mixed data sources
Use named lists for grouped choices:

```r
base_choices <- c("Ins_frac" = "Ins_any", "Glu_frac" = "Glu_any", "Stt_frac" = "Stt_any")
prop_cols <- grep("^prop_", colnames(prepared()$comp), value = TRUE)
if (length(prop_cols) > 0) {
  choices <- list(
    "Hormone Fractions" = base_choices,
    "Cell Type Proportions" = setNames(prop_cols, gsub("^prop_", "", prop_cols))
  )
} else {
  choices <- base_choices
}
```

### 6. Embedded segmentation panel (replacing modal)
Both Plot and Trajectory tabs use the same pattern:

```r
# Click handler — just set the shared reactiveVal
selected_islet(list(case_id=id, islet_key=key, centroid_x=cx, centroid_y=cy))

# Embedded panel renderUI
output$segmentation_viewer_panel <- renderUI({
  info <- selected_islet()
  if (is.null(info)) return(NULL)
  div(class = "card", style = "border: 2px solid #0066CC;",
    # Header + close button
    # plotOutput("islet_segmentation_view") — non-namespaced, root-level
    # Legend + islet info
  )
})

# Close button
observeEvent(input$clear_segmentation, { selected_islet(NULL) })
```

### 7. Multi-row z-scored heatmap along pseudotime
Extract expression for selected markers from cached `tr$adata`, bin pseudotime, compute per-bin means, z-score across bins per marker:

```r
# Per marker: compute bin means, z-score, clamp
z <- (bin_means - mean(valid_means)) / sd(valid_means)
z <- pmax(-2.5, pmin(2.5, z))

# Render with diverging colormap
scale_fill_gradient2(low = "#2166ac", mid = "#f7f7f7", high = "#b2182b",
                     midpoint = 0, limits = c(-2.5, 2.5))

# Dynamic height based on selection count
height = function() { max(150, 40 + n_markers * 30) }
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Modal popup for segmentation in Plot tab | Modal inserts DOM at body level; when both Plot + Trajectory use the same `plotOutput("islet_segmentation_view")`, the root-level renderPlot doesn't reliably bind across modal+embedded contexts | Use embedded panels consistently across all tabs; modal is not needed when there's space below the distribution chart |
| Validating `prop_*` against hardcoded list `c("Ins_any", "Glu_any", "Stt_any")` | Phenotype proportion columns are dynamic (`prop_Beta cell`, `prop_CD8a Tcell`, etc.) and not in the hardcoded list → value defaulted to `Ins_any` even when a `prop_*` was selected | Build `valid_comp` dynamically: `c("Ins_any", "Glu_any", "Stt_any", grep("^prop_", colnames(pd$comp), value = TRUE))` |
| Computing `prop_*` values as `count / cells_total * 100` | `prop_*` columns are already proportions (0-1), dividing by cells_total produces nonsensical values | Check `startsWith(w, "prop_")` and multiply by 100 directly; only use count/total for hormone fractions |
| Scaling phenotype proportions with diverging colormap | Proportions are 0-1, not zero-centered — diverging colormap misleads | Use percentage (0-100%) and keep same "% composition" y-axis label |
| Filtering `out[as.numeric(out$age) >= ...]` without `is.finite()` | `NA` ages produce `NA` comparisons, which pass through `[` as `NA` rows → crash downstream | Always wrap numeric filter comparisons with `is.finite()` guard |
| Adding demographic merge after AAb filter in `prep_data()` | AAb merge uses `select(-any_of(aab_cols))` which would strip demographics if they happened to collide | Place demographic merge after all AAb-related merges to avoid column name conflicts |
| Fixed-height `plotOutput` for multi-feature heatmap | With 2 markers selected = wasted space; with 20 markers = cramped | Use `height = "auto"` in UI + `height = function()` in `renderPlot` for dynamic sizing |

## Key Insights

- **NULL propagation pattern**: Design the entire feature chain so `NULL` from Excel path → no merge → no columns → `renderUI` returns `NULL` → filter checks column existence → no filtering. Zero special-case code needed.
- **Grouped selectInput**: Shiny's `selectInput` natively supports `list("Group A" = c(...), "Group B" = c(...))` — optgroups render automatically.
- **`startsWith()` branching**: When mixing original columns (Ins_any) with new dynamic columns (prop_*), use `startsWith(w, "prop_")` to branch computation logic rather than trying to unify them.
- **Embedded > Modal for repeated use**: Modals require dismiss/reopen cycle for each click. Embedded panels update in-place — much better for exploratory click-through of many points.
- **Z-score clamping**: `-2.5` to `2.5` prevents a single extreme bin from washing out the colorscale. Combined with `min 3 observations per bin`, this produces clean heatmaps.
- **Marker ordering**: Consistent ordering (hormones → immune → other) across heatmaps aids visual comparison. Use `intersect()` to preserve only markers actually selected.
- **Dynamic height formula**: `max(150, 40 + n * 30)` gives 30px per marker row with a 40px overhead for axes/title and a 150px minimum so the plot doesn't collapse to nothing.
- **CSS overflow for dropdowns in cards**: `selectInput` dropdown menus extend below their container. If the container has `overflow: hidden` (common with gradient backgrounds or `border-radius`), the menu gets clipped. Fix: add `overflow: visible;` to the card's style.
- **Return structure verification**: Always verify the exact field names returned by utility functions (`cohens_d` → `ci_lo`/`ci_hi`, `pairwise_wilcox` → `group1`/`group2`/`p_value`). Generic Shiny "An error has occurred" often means NULL field access in `sprintf()`.

## Phase 6 Additions (Statistics Tab, Feb 2026)

### 8. Shared sidebar across tabs
Rather than duplicating sidebar controls, make the existing Plot sidebar visible on the Statistics tab by editing two places in `app.R`:
- `conditionalPanel` condition: `"input.tabs == 'Plot' || input.tabs == 'Statistics'"`
- JS `adjustLayout()`: same condition to show sidebar column

The Statistics module consumes `plot_returns$raw_df` and `plot_returns$summary_df` directly — zero data duplication.

### 9. Pseudo-log transform for zero-safe log-scale
`scale_y_log10()` silently drops zero values (log10(0) = -Infinity). Replace with:

```r
# Helper for clean axis labels (0, 1, 10, 100, ...)
pseudo_log_breaks <- function(base = 10) {
  function(limits) {
    max_val <- max(limits)
    if (max_val <= 0) return(0)
    max_pow <- ceiling(log(max_val, base))
    min_pow <- if (max_val < 1) floor(log(max_val, base)) else 0
    brks <- c(0, base^seq(min_pow, max_pow))
    sort(unique(brks[brks <= max_val * 1.1]))
  }
}

# Usage
p + scale_y_continuous(trans = scales::pseudo_log_trans(base = 10),
                       breaks = pseudo_log_breaks(10))
```

Pseudo-log is linear near zero (zeros visible at y=0) and asymptotically log10 for larger values.

### 10. Case ID zero-padding fallback for GeoJSON
GeoJSON files may use zero-padded IDs (`0112.geojson`) while data uses unpadded (`112`). Fix in all three places:
- `load_case_geojson()`: try `sprintf("%04d", as.integer(case_id))` as fallback
- Plot click handler: spatial lookup fallback with padded ID
- Trajectory click handler: same fallback

### 11. AUC trapezoidal integration with guards
```r
auc = if (n() < 2) 0 else sum(diff(diam_mid) * (head(y,-1) + tail(y,-1))) / 2

# Division-by-zero guard for percentage change
if (length(nd_auc) > 0 && is.finite(nd_auc) && nd_auc != 0) {
  pct_change <- (t1d_auc - nd_auc) / nd_auc * 100
}
```

### Phase 6 Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `scale_y_log10()` with zero values | `log10(0) = -Inf`, ggplot2 silently drops these points. Users see missing data with no warning. | Use `scales::pseudo_log_trans(base=10)` which is linear near zero and log for larger values. |
| `scales::log_breaks(base=10)` with pseudo_log_trans | `log_breaks()` calls `log()` on the data limits; with pseudo_log domain starting at 0, produces `NaN` → crash: "missing value where TRUE/FALSE needed" | Write custom `pseudo_log_breaks()` that explicitly includes 0 and generates powers of 10 from min_pow to max_pow |
| `git add -A` after sed edit | A malformed sed pattern created a junk file named `pt_size[^"]*"` (906-line HTML dump) which got committed | Always use dedicated Edit tool instead of `sed` for file modifications; inspect `git status` before committing |
| Testing changes on dev port 7777 while user views production at :8080 | shiny-server on port 3838 (proxied by nginx :8080) serves from symlink; dev server on :7777 is completely separate | Always verify via production URL; kill stale R workers if code updates aren't reflected |

## Phase 7-8: Spatial Neighborhoods + Single-Cell Drill-Down (2026-02-19)

### 12. Neighborhood metrics in existing Plot+Stats workflow
Add new option groups to composition `selectInput` — the highest-ROI pattern for surfacing new data:
```r
# Detect columns dynamically from comp
peri_prop_cols <- grep("^peri_prop_", comp_cols, value = TRUE)
immune_metric_cols <- intersect(c("immune_frac_peri", ...), comp_cols)
choices <- list(
  "Hormone Fractions" = base_choices,
  "Cell Type Proportions" = setNames(prop_cols, ...),
  "Peri-Islet Proportions" = setNames(peri_prop_cols, ...),
  "Immune Metrics" = setNames(immune_metric_cols, ...)
)
```
This automatically makes all neighborhood metrics available in scatter, distribution, AND Statistics tab with zero changes to mod_statistics_server.R.

### 13. Extracting reusable base plot from segmentation renderer
```r
build_segmentation_base_plot(info)  # Returns ggplot with GeoJSON polygons + coord_sf
  # NO crosshairs, NO title — callers add their own layers
render_islet_segmentation_plot(info)  # = base_plot + crosshairs + title
render_islet_drilldown_plot(info, cells, color_by)  # = base_plot + cell scatter
```
Key: base plot handles GeoJSON loading, bbox query, polygon layers, clicked islet highlight. Callers compose on top.

### 14. Non-namespaced inputs from inside modules
Both Plot and Trajectory modules generate the same non-namespaced inputs (`drilldown_view_mode`, `drilldown_color_by`, `drilldown_show_peri`) inside their `renderUI`. These are read by root-level `renderPlot` outputs in app.R. Safe because only one tab is visible at a time — no duplicate ID conflicts.

### 15. Cell coordinate alignment
Cell centroids in single-cell H5AD are in micrometers (X_centroid, Y_centroid). GeoJSON polygons are in pixels. Convert: `x_px = X_centroid / PIXEL_SIZE_UM`. This matches the existing segmentation coordinate system.

### 16. Phenotype name sanitization for column names
Single-cell phenotype names have spaces and `+` which are invalid in H5AD obs columns:
- `Alpha cell` → `Alpha_cell`
- `ECAD+` → `ECADplus`
- `SMA+` → `SMAplus`
Applied consistently in compute_neighborhood_metrics.py via `name.replace(" ", "_").replace("+", "plus")`.

### 17. Dedicated tab with inline controls (no sidebar sharing)
The Spatial tab uses `spatial_server("spatial", prepared)` with its own inline controls (metric category, feature selector, donor status, diameter range). No `conditionalPanel` sidebar sharing needed — cleaner for independent analysis workflows.

### Phase 7-8 Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Using `backed='r'` for the aggregated H5AD (1,015 islets) | Unnecessary — only 47 MB. `backed='r'` matters for the 3.7 GB single-cell file. | Use backed mode only for large files (>500 MB). Small H5ADs load faster without backing. |
| Column naming with raw phenotype names in CSV (spaces, `+`) | R `read.csv` converts spaces to `.` and `+` to `.`. Inconsistent between Python output and R loading. | Sanitize column names in Python: `_` for space, `plus` for `+`. Match in R grep patterns. |
| Storing neighborhood metrics directly in `.uns` like groovy data | Too many sparse arrays (62 cols × 1,015 rows). `.obs` columns are the natural fit — already indexed by islet_id. | Use `.obs` for per-observation data (metrics per islet). Use `.uns` for multi-row tabular data (groovy exports). |
| Total_cells_peri == 0 treated as NaN in CSV | `pd.to_csv` preserves `0` and `NaN` separately. The 66 islets without peri data have `total_cells_peri=0` but `immune_frac_peri=NaN`. | Guard with `total_cells_peri > 0` not `!is.na(total_cells_peri)` since zero is valid but meaningless. |
| `cd$ci_lower` / `cd$ci_upper` in spatial stats | `cohens_d()` returns `list(d, ci_lo, ci_hi)` — NOT `ci_lower`/`ci_upper`. Accessing NULL fields caused `sprintf()` crash, showing generic Shiny error | Always check the actual return structure of utility functions; `cohens_d()` uses `ci_lo`/`ci_hi` |
| `pairs$p.adj` / `pairs$statistic` for pairwise results | `pairwise_wilcox()` returns columns `group1`, `group2`, `p_value` — NOT `p.adj` or `statistic` | Match column names to what `pairwise_wilcox()` actually returns |
| selectInput dropdowns hidden behind cards | Bootstrap card `overflow: hidden` (default from gradient background) clips dropdown menus that extend below the card boundary | Add `overflow: visible;` to card container `style` attribute in UI |

## Phase 9: Spatial Tab Overhaul (2026-02-20)

### 18. Large scatter plots with ggplot2 (not plotly)
For tissue-wide scatter plots with >100K points, plotly's WebGL renderer freezes the browser. Use `ggplot2::renderPlot()` with explicit `height`:

```r
output$tissue_scatter <- renderPlot({
  # ~177K cells per donor
  cells <- donor_cells()
  ggplot(cells, aes(X_centroid, Y_centroid, color = phenotype)) +
    geom_point(size = 0.4, alpha = 0.6) +
    coord_fixed() + scale_y_reverse() +
    theme_minimal(base_size = 18)
}, height = 800)
```

Key decisions:
- `coord_fixed()` preserves spatial proportions
- `scale_y_reverse()` matches microscopy convention (y increases downward)
- `size = 0.15-0.4` and `alpha = 0.3-0.6` for readable density at 177K points
- Explicit `height = 800` in `renderPlot()` for spatial detail

### 19. Foreground/background layering for tissue scatter
Show ALL cells for spatial context but highlight the selected region:

```r
# Background: tissue cells in light grey, very small
ggplot() +
  geom_point(data = bg, aes(x, y), color = "#d9d9d9", size = 0.15, alpha = 0.3) +
  # Foreground: core/peri cells colored by phenotype or leiden
  geom_point(data = fg, aes(x, y, color = phenotype), size = 0.4, alpha = 0.6)
```

### 20. Islet-level Leiden → cell-level mapping
Leiden clustering is at the islet level (1,015 islets). To color individual cells by cluster:

```r
# Build islet_key → cluster lookup from comp
comp <- prepared()$comp
sub <- comp[comp$`Case ID` == donor_id, c("islet_key", leiden_col)]
lmap <- setNames(as.character(sub[[leiden_col]]), as.character(sub$islet_key))

# Map cells via islet_name column
cells$cluster <- lmap[cells$islet_name]
cells$cluster[is.na(cells$cluster)] <- "tissue"  # non-islet cells
```

### 21. Per-donor tissue CSV extraction
For tissue scatter, extract ALL cells per donor (not just islet cells):

```python
# scripts/extract_per_donor_tissue.py
# 15 files × ~177K cells each = 2.65M total, ~78 MB
# Columns: X_centroid, Y_centroid, phenotype, cell_region, islet_name
# cell_region: "core" (Islet_N), "peri" (Islet_N_exp20um), "tissue" (everything else)
```

Pattern mirrors `extract_per_islet_cells.py` but groups by `imageid` instead of `combined_islet_id`. No expression data needed — just spatial coords + metadata.

### 22. Documentation banners for context-dependent charts
When charts show metrics that overlap with other tabs, add prominent documentation:

```r
doc_style <- "background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 5px;
              padding: 8px 12px; font-size: 13px; color: #856404; margin-bottom: 10px;"
div(style = doc_style,
    "These z-scores compare peri-islet proportions against tissue-wide background...")
```

### Phase 9 Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Using plotly for tissue scatter (~177K cells) | Browser tab freezes/crashes with >50K WebGL points in plotly. Even with `toWebGL()`, hover/zoom events process all points. | Use `ggplot2::renderPlot()` for >50K points. Plotly is fine for <5K (like 1,015 islets on Leiden UMAP). |
| Donor 6533 assumed to have islet annotations | 6533 has 205K cells but 0 core/0 peri — all cells are tissue background. No islet annotations exist for this donor. | Always handle donors with zero islet cells gracefully. Don't assume all donors have core/peri regions. |
| Storing expression data in per-donor tissue CSVs | 31 marker columns × 177K cells = 30+ MB per file, 450+ MB total. App doesn't need expression for spatial overview. | Only extract the columns actually needed: X/Y coords, phenotype, cell_region, islet_name. Reduces 450+ MB → 78 MB. |

## Session 2026-02-20: UI Alignment, Layer Ordering, Font Standards

### 23. Injecting extra UI between module cards via `extra_panel` parameter
When a module's `tagList` output needs external content (e.g., AI chat) inserted at a specific position in the Bootstrap column flow, add an optional parameter rather than restructuring the caller:

```r
# Module UI: accept optional panel injection
plot_main_ui <- function(id, extra_panel = NULL) {
  ns <- NS(id)
  tagList(
    column(10, tip_banner),       # 10 cols, wraps
    column(5, left_card),         # 5 cols
    column(5, right_card),        # 10 cols total
    extra_panel,                  # e.g., column(2, ai_chat) → 12 cols, same row as cards
    column(12, seg_panel)         # wraps to next row, full width
  )
}

# Caller in app.R:
plot_main_ui("plot", extra_panel = column(2, ai_assistant_ui("ai")))
```

Bootstrap column flow: col-10 wraps because >12; then col-5 + col-5 + col-2 = 12 → same visual row. The AI chat card top aligns with the plot cards automatically.

### 24. ggplot2 layer ordering: lines on top of individual points
In ggplot2, layers render in the order they're added. To show summary lines ON TOP of individual scatter points, add individual points FIRST:

```r
p <- ggplot(sm, aes(x, y, color = group))

# Individual points FIRST (drawn underneath)
if (show_points) {
  p <- p + geom_point(data = raw, aes(x, y, color = group, key = click_key),
                      position = position_jitter(...), size = pt_size, alpha = pt_alpha,
                      inherit.aes = FALSE)
}

# Summary lines + error bars ON TOP
p <- p + geom_line() + geom_point() + geom_errorbar(aes(ymin, ymax))

# Color scale AFTER all layers (last scale_color_manual wins)
if (has_donor_colors) {
  p <- p + scale_color_manual(values = c(status_colors, donor_colors), breaks = donor_breaks)
} else {
  p <- p + scale_color_manual(values = status_colors, breaks = status_levels)
}
```

Key: Extract `donor_colors` and `donor_id_breaks` inside the if-block, store in outer-scope variables, apply scale after all layers.

### 25. Font size standards for scientific visualization plots
Established minimums for readability across the app's visualization contexts:

| Context | base_size | legend.text | legend.title | legend.key.size | plot.title |
|---------|-----------|-------------|--------------|-----------------|------------|
| Drilldown (islet viewer) | 12 | 14px | 16px bold | 0.9cm | 14px |
| Cell Composition bar | 16 | — | — | — | — |
| Tissue Scatter (800px) | 18 | 15px | 18px bold | 0.7cm | 22px |
| Scatter plot (plotly) | 14 | — | — | — | — |

Phenotype dots in the islet viewer: `size = 3.0` (was 1.8). Fallback gray dots: `size = 2.5`.

HTML-based legends (Boundaries mode): minimum 16px font-size on container, individual items 16px.

### Session 2026-02-20 Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Placing `column(2, ai_chat)` as sibling after `plot_main_ui()` tagList in fluidRow | Bootstrap column wrapping puts col-2 next to col-10 (seg panel) at the bottom, not next to col-5+col-5 (cards) | DOM order determines Bootstrap column flow. Insert col-2 BETWEEN the cards and seg panel so 5+5+2=12 fills a row. |
| Adding individual points after summary geom_line/geom_point | Individual scatter points render ON TOP of summary lines, obscuring the trend | ggplot2 layers render in addition order. Add individual points FIRST so summary lines draw on top. |

## Phase 12: Cell-Count-Weighted Trajectory Visualization (2026-03-05)

### 26. Cell-count-aware point sizing and weighted LOESS
When aggregated data has variable sample sizes per observation (e.g., islet-level means from 1-1,902 cells), give visual weight proportional to measurement quality:

```r
# Point sizing: sqrt for area-proportional display
df$size_cells <- sqrt(df$total_cells)
aes_mapping$size <- as.name("size_cells")
scale_size_continuous(range = c(0.3 * base, 3.0 * base), guide = "none")

# LOESS weighting: log1p to prevent extreme values from dominating
df$loess_weight <- log1p(df$total_cells)
geom_smooth(aes(weight = loess_weight), method = "loess", span = 0.75)
```

**Critical**: Raw counts as LOESS weights cause catastrophic overfitting. With median=9 and max=1,902, a few large islets get 200× the weight of typical ones, producing wild trend curves (e.g., diving to -150 on the y-axis). `log1p()` compresses the 1,902:1 ratio to ~11:1 — still meaningful upweighting but safe.

### 27. Hover tooltip with data quality indicator
Add a text aesthetic to ggplot that passes through to plotly tooltip:

```r
df$hover_cells <- paste0("Cells: ", df$total_cells)
aes_mapping <- aes(x = pt, y = value, text = hover_cells)
p <- ggplotly(g, tooltip = c("x", "y", "colour", "text"), source = ns("scatter"))
```

### Phase 12 Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `weight = total_cells` (raw) in LOESS | A few islets with 1,000+ cells dominated the fit, causing the trend line to swing wildly (e.g., -150 on y-axis) despite all data being near 0 | Raw counts too skewed (median=9, max=1,902). Use `log1p(total_cells)` to compress the ratio from 1,902:1 to ~11:1. |
| Point size by raw `total_cells` | A few extreme islets were massive dots obscuring all neighbors | Use `sqrt(total_cells)` so area (not radius) is proportional to count. Moderate visual range [0.3×, 3.0×] of base size. |

## References
- [Shiny Modules](https://shiny.posit.co/r/articles/improve/modules/)
- [selectInput with optgroups](https://shiny.posit.co/r/reference/shiny/latest/selectinput)
- [ggplot2 scale_fill_gradient2](https://ggplot2.tidyverse.org/reference/scale_gradient.html)
- Islet Explorer: `app/shiny_app/` — `data_loading.R`, `mod_plot_*.R`, `mod_trajectory_*.R`, `mod_spatial_*.R`, `spatial_helpers.R`, `drilldown_helpers.R`
- Related skill: `shiny-modularization` (extraction order, plotly namespacing)
- Related skill: `h5ad-shiny-data-pipeline` (H5AD loading, .uns storage, Excel fallback)
