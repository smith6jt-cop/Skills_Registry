---
name: shiny-statistics-redesign
description: "Statistics tab redesign patterns: 5-section narrative layout, BH correction for stratified tests, plotly legend positioning, synthetic union row density fix, test type UX guidance"
author: smith6jt
date: 2026-03-06
---

# Shiny Statistics Tab Redesign - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-03-06 |
| **Goal** | Redesign Statistics tab from flat 7-card grid to 5-section narrative layout with proper multiple testing correction, improved plotly legend placement, synthetic union row density fix, and test type UX guidance |
| **Environment** | R 4.x, Shiny 1.12.1, plotly 4.12.0, ggplot2, dplyr, scales |
| **Status** | Success |

## Context
The Statistics tab originally used a flat 7-card grid layout that was overwhelming and lacked narrative flow. Several statistical issues needed fixing: raw p-values from per-bin tests were not corrected for multiple comparisons across bins, plotly legends overlapped x-axis titles, synthetic union rows in `prep_data()` had `NA` density values causing data loss, and users had no guidance on when to use parametric vs non-parametric tests.

## Verified Workflows

### 1. Five-Section Narrative Layout
Replaced the flat 7-card grid with numbered sections that guide the user through a statistical analysis workflow:

1. **Configure** -- Feature/region/test type selection with inline guidance
2. **Primary Results** -- Global test + pairwise table + forest plot
3. **Size-Dependent Patterns** -- Per-bin heatmap + trend analysis
4. **Confounders** -- Demographics (age, gender) stratification
5. **Methods & Interpretation** -- Dynamic text describing all tests, corrections, assumptions

Each section uses a `section_heading()` helper for consistent styling:

```r
section_heading <- function(number, title, subtitle = NULL) {
  tagList(
    div(style = "display: flex; align-items: center; gap: 12px; margin-top: 20px; margin-bottom: 12px; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px;",
      span(style = paste0(
        "background: linear-gradient(135deg, #4477AA, #5599CC); color: white; ",
        "font-weight: bold; border-radius: 50%; width: 30px; height: 30px; ",
        "display: flex; align-items: center; justify-content: center; font-size: 15px;"
      ), number),
      div(
        h4(style = "margin: 0; font-size: 17px; font-weight: 600;", title),
        if (!is.null(subtitle)) tags$small(style = "color: #666; font-size: 13px;", subtitle)
      )
    )
  )
}
```

Key design choices:
- Gradient pill badge (#4477AA to #5599CC) for section numbers
- 17px title, 13px subtitle
- Bottom border separates sections visually
- Numbered flow creates a narrative: configure -> test -> explore patterns -> check confounders -> understand methods

### 2. Plotly Legend Overlap Fix
When converting ggplot2 to plotly, legend positioning requires coordination between both systems:

```r
# Step 1: Suppress ggplot legend (plotly will override it anyway)
g <- g + theme(legend.position = "none")

# Step 2: In plotly layout, create space and position legend below
p <- ggplotly(g) %>%
  layout(
    margin = list(b = 60),  # 60px bottom margin for legend room
    legend = list(
      orientation = "h",
      x = 0.5,
      xanchor = "center",
      y = -0.25
    )
  )
```

**Critical**: The `margin(b = 60)` is essential. Without it, plotly does not auto-expand to accommodate the legend, and it overlaps the x-axis title. The `y = -0.25` positions the legend below the plot area, and `xanchor = "center"` centers it horizontally.

### 3. BH Correction Across Bins
Per-bin hypothesis tests (ANOVA, Kruskal-Wallis, Kendall) produce one p-value per bin. With 7 bins, uncorrected testing at alpha=0.05 inflates the family-wise error rate to ~30%. Apply Benjamini-Hochberg correction across all bins:

```r
# In per_bin_anova() or per_bin_kendall():
results$p_raw <- results$p_value
results$p_adjusted <- p.adjust(results$p_value, method = "BH")

# Heatmap shows -log10(q) not -log10(p)
z_matrix <- -log10(results$p_adjusted)

# Star annotations use corrected values
stars <- ifelse(results$p_adjusted < 0.001, "***",
         ifelse(results$p_adjusted < 0.01, "**",
         ifelse(results$p_adjusted < 0.05, "*", "")))
```

The heatmap x-axis shows bin midpoints, y-axis shows test type, and z-values are `-log10(q)` where q is the BH-adjusted p-value. This ensures that significance claims account for the number of bins tested.

### 4. Synthetic Union Row Density Fix
`prep_data()` synthesizes union (Core+Peri) rows for the Microenvironment analysis mode. The original code set `area_um2`, `region_um2`, and `area_density` to `NA` for these rows:

```r
# BROKEN: density is NA for synthetic union rows
union_row$area_um2 <- NA_real_
union_row$region_um2 <- NA_real_
union_row$area_density <- NA_real_
```

When the default metric is "Density" (which uses `area_density`), the `!is.na(value)` filter removes all synthetic rows. Only donors with pre-existing union rows in the source data survive -- typically 3 out of 15 donors.

**Fix**: Sum core + band areas and compute density:

```r
# FIXED: compute actual values for synthetic union rows
union_row$area_um2 <- core_row$area_um2 + band_row$area_um2
union_row$region_um2 <- core_row$region_um2 + band_row$region_um2
union_row$area_density <- union_row$area_um2 / union_row$region_um2
```

### 5. Equal-Height Cards in a Row
When placing multiple cards side-by-side (e.g., pairwise table and forest plot), use flexbox to equalize heights:

```r
fluidRow(
  style = "display: flex; flex-wrap: wrap;",
  column(5, div(style = "height: 100%;", pairwise_table_card)),
  column(7, div(style = "height: 100%;", forest_plot_card))
)
```

The `display: flex; flex-wrap: wrap;` on the row makes child columns stretch to equal height. Inner cards with `height: 100%` fill their column.

### 6. Test Type Explanation UX
Inline `tags$small()` below radio buttons explains parametric vs non-parametric assumptions so users can make informed choices:

```r
radioButtons(ns("test_type"), "Test Type",
  choices = c("Non-parametric" = "nonparametric", "Parametric" = "parametric"),
  selected = "nonparametric", inline = TRUE
),
tags$small(style = "color: #666; font-size: 12px; display: block; margin-top: -5px;",
  "Non-parametric (Kruskal-Wallis + Wilcoxon): no normality assumption.",
  tags$br(),
  "Parametric (ANOVA + t-test): assumes normal distribution within groups."
)
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Plotly legend at `y = -0.15` with no extra margin | Overlaps x-axis title -- plotly does not auto-expand to accommodate legend | Must set `margin = list(b = 60)` in `layout()` to create space, then position legend at `y = -0.25` |
| Running per-bin tests with raw p-values and star annotations at 0.05/0.01/0.001 | Multiple testing across 7 bins inflates false positive rate to ~30%. A feature with no real effect will show spurious significance in 1-2 bins by chance | Must BH-correct p-values across all bins. Heatmap shows `-log10(q)` not `-log10(p)`. Stars use corrected values. |
| Setting `area_density = NA_real_` for synthetic union rows | Default metric is "Density" which uses `area_density`. NA values filtered by `!is.na(value)`. Only donors with pre-existing union data survive (3/15). | Synthetic union rows must compute real values: sum core+band areas, divide for density. Never use NA for a metric that will be the default display. |
| Using `legend.position = "bottom"` in ggplot alone | `ggplotly()` overrides ggplot legend position. The ggplot `"bottom"` setting has no effect after conversion. | Set `legend.position = "none"` in ggplot theme, then control legend entirely via `layout(legend = ...)` in plotly. |
| Forest plot crammed into same card as pairwise table | Forest plot needs vertical space (350px minimum) to show confidence intervals clearly. Combining with table compresses both. | Give forest plot its own card. Use `col-5` for table, `col-7` for forest plot (wider for CI whiskers). |
| Flat 7-card layout for statistics | Users couldn't find a logical reading order. Cards competed for attention. No clear workflow from "configure" to "interpret". | Numbered sections with visual hierarchy (gradient badge, subtitle, border) create a narrative flow. Users progress from configuration through results to methods naturally. |

## Key Parameters

| Parameter | Value | Context |
|-----------|-------|---------|
| Plotly legend bottom margin | `b = 60` pixels | `layout(margin = list(b = 60))` |
| Plotly legend y position | `-0.25` | `layout(legend = list(y = -0.25))` |
| Section heading gradient | `#4477AA` to `#5599CC` | `linear-gradient(135deg, ...)` |
| Section title font size | 17px | `h4` with `font-size: 17px` |
| Section subtitle font size | 13px | `tags$small` with `font-size: 13px` |
| Forest plot height | 350px | Minimum for readable CI whiskers |
| Table:forest column split | 5:7 | `column(5, table)` + `column(7, forest_plot)` |
| BH correction method | `p.adjust(method = "BH")` | Applied across all bins per test type |
| Per-bin minimum observations | 3 | Bins with <3 points skipped in per-bin tests |

## Key Insights

- **Narrative > Grid**: A numbered sequence (Configure -> Test -> Explore -> Check -> Understand) is more usable than a flat grid of cards. Users have a clear path through the analysis.
- **Multiple testing is mandatory for binned analysis**: 7 bins at alpha=0.05 gives ~30% family-wise error rate. BH correction is the minimum -- Bonferroni is too conservative for correlated bins.
- **Default metric must never be NA**: If the default display metric is computed from other fields, synthetic/derived rows must compute it too. NA defaults silently filter out data with no user-visible error.
- **Plotly legend needs explicit space**: Unlike ggplot2, plotly does not auto-allocate margin for legends placed outside the plot area. Always pair `margin(b=N)` with `legend(y=-M)`.
- **Separate ggplot and plotly legend control**: When using `ggplotly()`, set `legend.position = "none"` in ggplot to suppress it, then control legend entirely through plotly's `layout()`. Trying to use ggplot's legend positioning with plotly conversion produces unpredictable results.
- **Inline test guidance reduces support burden**: A two-line explanation of parametric vs non-parametric assumptions below the radio buttons prevents the most common user confusion without requiring external documentation.
- **Forest plots need dedicated space**: Confidence interval whiskers are the primary visual element. Cramming the forest plot into a shared card with the pairwise table compresses both below usefulness. Minimum 350px height in its own card.

## References
- Benjamini & Hochberg (1995): Controlling the false discovery rate
- Shiny `p.adjust()`: https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html
- Plotly R layout: https://plotly.com/r/reference/layout/
- Related skill: `shiny-feature-patterns` (pseudo-log, AUC, effect sizes, shared sidebar)
- Related skill: `shiny-modularization` (module extraction, namespacing)
- Islet Explorer: `app/shiny_app/R/mod_statistics_server.R`, `app/shiny_app/R/mod_statistics_ui.R`, `app/shiny_app/R/utils_stats.R`

### Demographics Card Redesign (2026-03-16)

**Verified Patterns:**
- Islet-level age scatter (`alpha=0.4, size=1.5`) with Pearson r subtitle noting "correlated within donors" — more informative than 15 donor-mean points
- Sex box plot (`facet_wrap(~ gender)`) replaces p-value table — shows distribution shape, not just significance
- AAb analysis (Aab+ only): `n_aab = rowSums(sapply(aab_avail, ...))` counts positive autoantibodies per islet; box plot by AAb count with Kruskal-Wallis test
- Full-width demographics card with side-by-side age + sex plots via `fluidRow(column(6), column(6))` inside renderUI
- AUC card belongs in Primary Results (Section 2), not Confounders — it's a primary outcome metric

**Layout Lessons:**
- 3-column equal-height: `fluidRow(style = "display: flex; flex-wrap: wrap;")` with `column(4)` + `height: 100%` cards
- Trend plot must match heatmap card height — use `height: 100%` on both card divs + same plotlyOutput height
- Trend plot legend: remove ggplot `legend.position = "none"` suppression, add plotly `showlegend = TRUE` with `legend(orientation = "h", y = -0.15)`

**Failed Approaches:**
| What failed | Why | Fix |
|------------|-----|-----|
| Global Kendall τ arrow in per-bin trend title | Misleading — single global τ doesn't represent per-bin variation | Remove title entirely; explain disease coding (ND=0, Aab+=1, T1D=2) in card description |
| "Wider bins recommended" in UI text | Implementation jargon, not interpretive guidance | Replace with explanation of what τ values mean |
| Gender terminology | "Gender" is a social construct; donor metadata records biological sex | Use "Sex" in all user-facing labels; keep `gender` as internal variable name |
