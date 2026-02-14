---
name: snakemake-skip-existing
description: "Per-channel skip-existing checks in Snakemake wrapper scripts for resuming interrupted SLURM jobs. Trigger: Snakemake interrupted job, skip existing channels, resume incomplete cycle, sentinel missing but outputs exist, per-channel completeness check, wrapper script resume logic."
author: KINTSUGI Team
date: 2026-02-13
---

# Per-Channel Skip-Existing in Snakemake Wrapper Scripts

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-13 |
| **Goal** | Avoid re-processing completed channels when a SLURM job is interrupted mid-cycle |
| **Environment** | HiPerGator HPC, Snakemake >= 8.0, KINTSUGI workflow scripts |
| **Status** | Implemented |

## Context

Snakemake controls the DAG at the **cycle** level using sentinel files (`.snakemake_complete/`). If a sentinel is missing, Snakemake reruns the entire cycle — all channels, all z-planes. On a 4-channel cycle where each channel takes ~1 hour, an interruption after 3 channels wastes 3 hours on re-processing.

The fix adds per-channel skip-existing checks **inside** the 3 wrapper scripts (`stitch.py`, `deconvolve.py`, `edf.py`). Snakemake still manages cross-rule dependencies; this prevents re-doing completed work within a single job.

## Verified Workflow

### Completeness Checks Per Script

Each script has a helper function that determines if a channel's output is complete:

**stitch.py** — `channel_complete(channel)`:
```python
def channel_complete(channel):
    """Check if all z-planes are already stitched for this channel."""
    ch_dir = STITCH_DIR / f"cyc{CYCLE:02d}" / f"CH{channel}"
    if not ch_dir.exists():
        return False
    for z in range(1, n_zplanes + 1):
        if not (ch_dir / f"{z:02d}.tif").exists():
            return False
    # CH1 also needs the stitch model pickle
    if channel == 1 and not (ch_dir / "result_df.pkl").exists():
        return False
    return True
```

**deconvolve.py** — `channel_decon_complete(ch)`:
```python
def channel_decon_complete(ch):
    """Check if deconvolution output is complete for this channel."""
    decon_ch_dir = DECON_DIR / f"cyc{CYCLE:02d}" / f"CH{ch}"
    if not decon_ch_dir.exists():
        return False
    stitch_ch_dir = STITCH_DIR / f"cyc{CYCLE:02d}" / f"CH{ch}"
    expected = len(list(stitch_ch_dir.glob("*.tif")))
    if expected == 0:
        return False
    actual = len(list(decon_ch_dir.glob("*.tif")))
    return actual >= expected
```

**edf.py** — `channel_edf_complete(ch)`:
```python
def channel_edf_complete(ch):
    """Check if EDF output file exists for this channel."""
    output_path = EDF_DIR / f"cyc{CYCLE:02d}"
    output_file = output_path / get_channel_output_name(CYCLE, ch)
    return output_file.exists()
```

### Main Loop Pattern (All 3 Scripts)

```python
channels_to_process = []
skipped_channels = []
for ch in CHANNELS:
    if channel_X_complete(ch):
        print(f"  Channel {ch} SKIPPED (...)")
        skipped_channels.append(ch)
    else:
        channels_to_process.append(ch)

if channels_to_process:
    results = [process_channel(ch) for ch in channels_to_process]
else:
    print(f"All channels already complete — nothing to do")
    results = []

# Include skipped channels in success count
successful = sum(1 for _, ok in results if ok) + len(skipped_channels)
```

### Sentinel Files Include Skip Count

```
stage=decon
cycle=3
completed=2026-02-13T14:30:00
channels=1-4
successful=4
skipped=3
duration_minutes=12.5
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Skip individual z-planes within a channel | Partial channel output can be corrupted (e.g. stitching model computed from wrong reference) | Per-channel granularity: if a channel is partially done, redo the whole channel |
| Use file modification times to detect partial completion | Network filesystem (NFS) timestamps are unreliable on HPC | Count expected vs actual files instead |
| Sentinel-level only (Snakemake default) | Too coarse — reruns entire cycle even if 3/4 channels are done | Add per-channel checks inside wrapper scripts |

## Key Insights

- **Two-level skip logic**: Snakemake sentinel = cycle-level skip (coarse); wrapper script = channel-level skip (fine-grained). Both complement each other.
- **All-or-nothing per channel**: A channel is only skipped when ALL expected output files exist. Partially-complete channels are fully reprocessed to avoid subtle data integrity issues.
- **Stitch model is special**: CH1's `result_df.pkl` is used by all other channels. The completeness check for CH1 includes this pickle file.
- **Decon checks against stitched input**: The deconvolution script counts expected z-planes from the stitched input directory, not a hardcoded number. This handles datasets with different z-plane counts.
- **EDF checks marker-named files**: EDF output uses marker names from `CHANNELNAMES.txt` (e.g., `CD3.tif`), so the check uses `get_channel_output_name()` to construct the expected filename.
- **All-skipped = success**: If every channel was already complete, the script still writes the sentinel and exits 0. The cycle is done.
- **No changes to Snakefile or DAG**: This is purely internal to the wrapper scripts. Snakemake's DAG, sentinel logic, and cross-rule dependencies are completely unchanged.

## References

- `workflow/scripts/stitch.py` — `channel_complete()` helper
- `workflow/scripts/deconvolve.py` — `channel_decon_complete()` helper
- `workflow/scripts/edf.py` — `channel_edf_complete()` helper
- `snakemake-workflow-architecture` skill — Overall Snakemake workflow design
- KINTSUGI CLAUDE.md — "Per-channel skip-existing checks" section
