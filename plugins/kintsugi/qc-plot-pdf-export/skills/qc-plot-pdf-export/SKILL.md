---
name: qc-plot-pdf-export
description: "KINTSUGI quantification plots: Always save QC heatmaps and profiles as PDF"
author: Claude Code
date: 2026-01-15
updated: 2026-02-16
triggers:
  - quantification
  - QC plots
  - heatmaps
  - summary plots
  - PDF export
  - plot_summary_heatmaps
  - plot_zplane_profiles
---

# QC Plot PDF Export Pattern

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-01-15 (updated 2026-02-16) |
| **Goal** | Ensure all quantification plots are saved as PDFs for documentation |
| **Environment** | KINTSUGI notebooks/2_Cycle_Processing.ipynb, workflow/scripts/qc_report.py |
| **Status** | Implemented |

## Context
Quantification cells in the cycle processing notebook generate heatmaps and profile plots showing:
- SNR (Signal-to-Noise Ratio) by cycle/channel
- CV (Coefficient of Variation) for uniformity assessment
- Mean intensity distributions
- Z-plane profiles

These plots should be saved as PDFs to `PROJECT_DIR/qc_plots/` for archival and reporting.

## Implementation Pattern

### QC Output Directory Setup
```python
# QC output directory for PDF plots
QC_OUTPUT_DIR = PROJECT_DIR / 'qc_plots'
QC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
```

### Summary Heatmap Function
```python
def plot_summary_heatmaps(stats_df, stage_name="raw", save_pdf=True):
    """Create summary heatmaps: SNR and CV by cycle/channel.

    Args:
        stats_df: DataFrame with statistics
        stage_name: Name for the processing stage (used in PDF filename)
        save_pdf: Whether to save the plot as PDF (default: True)
    """
    # ... create figure with 3 subplots ...

    plt.suptitle(f'{stage_name.upper()} Summary Heatmaps', y=1.02, fontsize=14)
    plt.tight_layout()

    if save_pdf:
        pdf_path = QC_OUTPUT_DIR / f'{stage_name}_summary_heatmaps.pdf'
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', dpi=150)
        print(f"  Saved: {pdf_path}")

    plt.show()
    return fig
```

### Z-Plane Profile Function
```python
def plot_zplane_profiles(stats_df, cycle, channel, stage_name="raw", save_pdf=True):
    """Plot statistics across all z-planes for one cycle/channel.

    Args:
        stats_df: DataFrame with statistics
        cycle: Cycle number
        channel: Channel number
        stage_name: Name for the processing stage (used in PDF filename)
        save_pdf: Whether to save the plot as PDF (default: True)
    """
    # ... create figure with 4 subplots ...

    plt.tight_layout()

    if save_pdf:
        pdf_path = QC_OUTPUT_DIR / f'{stage_name}_zprofile_cyc{cycle:02d}_ch{channel}.pdf'
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', dpi=150)

    plt.show()
    return fig
```

### Usage in Quantification Cells
```python
# Summary heatmaps (always save)
plot_summary_heatmaps(raw_stats_df, stage_name="raw")
plot_summary_heatmaps(stitched_stats_df, stage_name="stitched")
plot_summary_heatmaps(decon_stats_df, stage_name="deconvolved")

# Z-plane profiles — save ALL cycles
for cycle in range(start_cycle, end_cycle + 1):
    for channel in range(start_channel, end_channel + 1):
        plot_zplane_profiles(stats_df, cycle, channel, stage_name="raw", save_pdf=True)
```

## Output Files

| File Pattern | Description |
|--------------|-------------|
| `{stage}_summary_heatmaps.pdf` | 3-panel heatmap (SNR, CV, Intensity) |
| `{stage}_zprofile_cyc{NN}_ch{N}.pdf` | 4-panel z-profile (Intensity, SNR, CV, StdDev) |

Where `{stage}` is one of: `raw`, `stitched`, `deconvolved`, `edf`

## Snakemake-Automated QC Reports (Added 2026-02-13)

The same QC PDFs are now generated automatically by the Snakemake workflow via `workflow/scripts/qc_report.py`. This dispatch script calls the `Kprocess.py` QC functions (`run_stitched_qc`, `run_decon_qc`, `run_edf_qc`) which internally use the same `plot_summary_heatmaps()` and z-profile plotting functions.

### How It Works

1. Three aggregate Snakemake rules (`qc_stitch`, `qc_decon`, `qc_edf`) run after all cycles of a stage complete
2. `qc_report.py` reads `snakemake.params.stage` and dispatches to the correct Kprocess function
3. Output PDFs go to `{project}/qc_plots/` (same location as notebook output)
4. Statistics are cached to `{project}/cache/{stage}_stats.pkl` for cross-stage comparison

### Critical: Headless Matplotlib

`qc_report.py` sets `matplotlib.use("Agg")` **before** importing Kprocess. Without this, Kprocess's internal matplotlib imports will try to open a display and crash on SLURM compute nodes.

```python
# Must be FIRST — before any Kprocess import
import matplotlib
matplotlib.use("Agg")
# Now safe to import
from Kprocess import run_stitched_qc, run_decon_qc, run_edf_qc
```

### Running QC Standalone

```bash
snakemake qc --profile profiles/slurm -j 1  # Generate QC only (no reprocessing)
snakemake -n qc                               # Dry run — verify DAG
```

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `save_pdf = (cycle == start_cycle)` — only save first cycle | Headless Snakemake runs use `matplotlib.use("Agg")`, making `plt.show()` a no-op. Only saved PDFs are produced, so non-first cycles had NO output. | Always `save_pdf=True` for ALL cycles. Filenames already include cycle number (`_cyc{NN}_`) so no conflicts. In notebooks `plt.show()` renders inline regardless; in headless mode only PDFs persist. |
| Not setting `matplotlib.use("Agg")` before Kprocess imports | Kprocess imports matplotlib at module level; display backend crashes on headless nodes | Set Agg backend BEFORE any import chain that touches matplotlib |

## Key Insights
- Always include `stage_name` parameter to differentiate processing stages
- Use `bbox_inches='tight'` to prevent label clipping
- DPI of 150 provides good balance of quality and file size
- Return the figure object for programmatic use if needed
- **Save z-profile PDFs for ALL cycles** — headless runs produce no output from `plt.show()`
- Set `matplotlib.use("Agg")` before ANY import that touches matplotlib on headless nodes

## Related Skills
- `gpu-parallel-scheduling` - Statistics collection uses GPU parallelism
- `notebook-module-refactoring` - Function extraction pattern
- `repo-project-sync-workflow` - Edit main repo first
- `snakemake-workflow-architecture` - QC aggregate rules section

## References
- KINTSUGI `notebooks/Kprocess.py` - `run_stitched_qc()` (line ~1185), `run_decon_qc()` (line ~1282)
- KINTSUGI `notebooks/2_Cycle_Processing.ipynb` - Quantification cells
- KINTSUGI `workflow/scripts/qc_report.py` - Snakemake QC dispatch script
- KINTSUGI `workflow/CLAUDE.md` - QC Report Rules section
