---
name: shiny-feature-patterns
description: "Patterns for adding interactive features to modular Shiny apps with H5AD data, conditional UI, embedded panels"
author: smith6jt
date: 2026-02-19
---

# Shiny Feature Patterns - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-19 |
| **Goal** | Add three new interactive features (phenotype composition explorer, demographic filters, multi-feature heatmap) to a modular Shiny app backed by H5AD data with Excel fallback |
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

## References
- [Shiny Modules](https://shiny.posit.co/r/articles/improve/modules/)
- [selectInput with optgroups](https://shiny.posit.co/r/reference/shiny/latest/selectinput)
- [ggplot2 scale_fill_gradient2](https://ggplot2.tidyverse.org/reference/scale_gradient.html)
- Islet Explorer: `app/shiny_app/` — `data_loading.R`, `mod_plot_*.R`, `mod_trajectory_*.R`
- Related skill: `shiny-modularization` (extraction order, plotly namespacing)
- Related skill: `h5ad-shiny-data-pipeline` (H5AD loading, .uns storage, Excel fallback)
