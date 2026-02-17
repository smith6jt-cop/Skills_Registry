---
name: shiny-modularization
description: "Patterns and pitfalls for modularizing large Shiny apps with plotly, sf, and cross-module reactives"
author: smith6jt
date: 2026-02-16
---

# Shiny App Modularization - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-16 |
| **Goal** | Break a 5,397-line monolithic Shiny app.R into modules without losing functionality |
| **Environment** | R 4.x, Shiny 1.12.1, plotly 4.12.0, htmlwidgets 1.6.4, sf, ggplot2 |
| **Status** | Success |

## Context
The Islet Explorer app grew to 5,400 lines in a single app.R. Modularization was needed for maintainability, but interactive features (plotly click-to-segmentation, cross-tab communication) broke during extraction.

## Verified Workflow

### 1. Extraction Order (least to most coupled)
1. `00_globals.R` - library loads, constants, feature flags
2. Pure utility functions (no Shiny deps): `utils_safe_join.R`, `utils_stats.R`, `data_loading.R`
3. Domain helpers: `segmentation_helpers.R`, `viewer_helpers.R`, `ai_helpers.R`
4. Self-contained modules: AI Assistant
5. Data-consuming modules: Statistics, Viewer
6. Interactive modules: Plot (click handler), Trajectory (click handler + H5AD)

### 2. Plotly Click Events in Modules
```r
# In module server - namespace the source string
ns <- session$ns
gg <- ggplotly(p, source = ns("my_source"))
gg <- gg %>% event_register("plotly_click")

# Click handler - use matching ns() source
observeEvent(event_data("plotly_click", source = ns("my_source")), {
  d <- event_data("plotly_click", source = ns("my_source"))
  # ...
})
```

### 3. Root-Level Shared Outputs for Cross-Module Rendering
When multiple modules need to render to the same output (e.g., segmentation plot used by both a modal and an embedded panel), define the `renderPlot` at the ROOT level in app.R, not inside any module.

```r
# app.R server - root level
output$shared_plot <- renderPlot({
  req(shared_reactive())
  render_function(shared_reactive())
})

# Module A - modal references root-level output (NO ns() prefix)
showModal(modalDialog(plotOutput("shared_plot")))

# Module B - embedded panel references root-level output (NO ns() prefix)
output$my_panel <- renderUI({
  plotOutput("shared_plot")
})
```

### 4. ggplot2 vs sf Namespace
```r
# WRONG - coord_sf and geom_sf are NOT sf exports
sf::coord_sf(...)   # Error: 'coord_sf' is not an exported object from 'namespace:sf'
sf::geom_sf(...)    # Works but wrong namespace

# CORRECT - these are ggplot2 functions
ggplot2::coord_sf(xlim = ..., ylim = ..., expand = FALSE)
ggplot2::geom_sf(data = polygons, fill = NA, color = "blue")
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Module-scoped `plotOutput(ns("seg_view"))` for modal | `showModal` inserts at DOM body level; module-scoped `renderPlot` didn't reliably bind to the output element | Use root-level shared outputs for cross-module rendering |
| Non-namespaced plotly source `source = "plot_scatter"` in module | `event_data()` couldn't find the event because plotly's JS uses the source string to namespace `Shiny.setInputValue()` calls | Always use `ns("source_name")` for plotly sources inside modules |
| `sf::coord_sf()` in extracted helper file | `coord_sf` is a ggplot2 function, not sf. Original app used bare `coord_sf()` (ggplot2 was loaded) which worked, but explicit namespacing exposed the wrong package | When adding explicit namespaces during extraction, verify which package actually exports each function |
| Adding `event_register("plotly_click")` to fix click detection | `plotly_click` is already in default `shinyEvents` so `event_register` wasn't the fix | The real issue was the source string namespacing, not event registration |
| Debugging with JS `shiny:inputchanged` listener and R `showNotification` | Helpful for confirming click handlers fire, but didn't reveal the downstream rendering issue | Start by comparing with the working original code rather than adding incremental diagnostics |

## Key Insights

- Shiny's `R/` directory is auto-sourced alphabetically before `global.R`. Prefix globals file with `00_` to ensure it loads first.
- `showModal` from inside a module works fine for sending the modal, but the `plotOutput` inside the modal must match a `renderPlot` that Shiny can bind. Root-level outputs are safest for shared rendering.
- `reactiveVal` objects can be passed as module parameters for cross-module communication (e.g., `selected_islet`, `forced_image`).
- When extracting monolithic code, grep for bare function calls (like `coord_sf`, `geom_sf`) and verify which package exports them before adding `pkg::` prefixes.
- For diverging data (zero-centered z-scores), use `scale_color_gradient2()` with `limits` and `scales::squish`, not sequential colormaps.

## References
- [Shiny Modules](https://shiny.posit.co/r/articles/improve/modules/)
- [Plotly event_data in modules](https://plotly-r.com/linking-views-with-shiny.html)
- Islet Explorer: `app/shiny_app/` in this repository
