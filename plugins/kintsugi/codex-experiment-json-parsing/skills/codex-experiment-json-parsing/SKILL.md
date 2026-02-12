---
name: codex-experiment-json-parsing
description: "CODEX/Akoya experiment.json uses different field names and flat wavelength lists that must be translated to KINTSUGI format"
author: Claude Code
date: 2026-02-11
---

# CODEX experiment.json Parsing

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-11 |
| **Goal** | Correctly parse CODEX/Akoya experiment.json into KINTSUGI ExperimentConfig |
| **Environment** | KINTSUGI src/kintsugi/project.py, HiPerGator |
| **Status** | Success |

## Context
CODEX/Akoya PhenoCycler experiment.json files use different field names and data formats than KINTSUGI's internal ExperimentConfig. When `kintsugi init` loads an existing CODEX experiment.json, fields were silently dropped and wavelengths were incorrectly duplicated. This affected batch project setup for 34 datasets.

## Two Distinct Problems

### Problem 1: Field Name Mismatch
CODEX experiment.json uses Akoya field names. `ExperimentConfig.from_dict()` filtered to "valid fields only" which silently dropped all CODEX-named fields.

| CODEX Field | KINTSUGI Field | Type |
|-------------|---------------|------|
| `numCycles` | `n_cycles` | int |
| `numZPlanes` | `n_zplanes` | int |
| `regionHeight` | `tile_rows` | int |
| `regionWidth` | `tile_cols` | int |
| `numChannels` | `channels_per_cycle` | int |
| `xyResolution` | `xy_pixel_size` | float (nm) |
| `zPitch` | `z_step_size` | float (nm) |
| `aperture` | `numerical_aperture` | float |

**Fix**: Added `_CODEX_FIELD_MAP` class variable and translation step in `from_dict()`:
```python
_CODEX_FIELD_MAP: ClassVar[dict[str, str]] = {
    "numCycles": "n_cycles",
    "regionHeight": "tile_rows",
    "regionWidth": "tile_cols",
    # ... etc
}

# In from_dict():
for codex_key, kintsugi_key in cls._CODEX_FIELD_MAP.items():
    if codex_key in data and kintsugi_key not in data:
        data[kintsugi_key] = data[codex_key]
```

### Problem 2: Flat Wavelength List
CODEX stores wavelengths as a flat list of excitation wavelengths only:
```json
"wavelengths": [358, 488, 550, 650]
```

KINTSUGI expects `{channel: (excitation, emission)}` pairs. The old code duplicated the value: `(358, 358)` — wrong.

**Fix**: Added `_CODEX_FILTER_SETS` lookup table mapping excitation wavelengths to known filter set (excitation, emission) pairs:

```python
_CODEX_FILTER_SETS = {
    358: (358.0, 461.0),   # DAPI
    488: (488.0, 525.0),   # FITC / Alexa 488
    550: (560.0, 575.0),   # TRITC / Cy3
    650: (648.0, 668.0),   # Cy5
    750: (753.0, 775.0),   # Cy7
}
```

The `_excitation_to_filter_pair()` function includes ±10 nm fuzzy matching and warns for unknown wavelengths.

## Two CODEX Wavelength Variants Found

Across 34 HuBMAP CODEX datasets, only two distinct wavelength arrays exist:
- `[358, 488, 550, 650]` — 23 datasets (FITC on CH2)
- `[358, 750, 550, 650]` — 15 datasets (Cy7 on CH2)

CH1 (DAPI), CH3 (TRITC), and CH4 (Cy5) are always the same.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Duplicating excitation as emission `(w, w)` | Physically wrong — excitation ≠ emission for any fluorophore | Must use filter set lookup table |
| Passing CODEX fields directly to ExperimentConfig | `from_dict()` filtered to valid field names, silently dropping CODEX names | Need explicit field name translation before filtering |
| Relying on CLI params to override experiment.json | `create_experiment_config(overwrite=False)` loads existing file, ignoring CLI tile/cycle params | Must translate fields within the loaded file itself |

## Additional Context

### Tissue Refractive Index
CODEX experiment.json does NOT include refractive index. For uncleared tissue (all HuBMAP CODEX datasets), RI is always **1.44**. The batch setup script defaults `RI=?` to `1.44`.

### Data Flow During Batch Setup
1. `setup_all_projects.sh` copies CODEX experiment.json to `meta/`
2. `kintsugi init --force` calls `create_experiment_config(overwrite=False)`
3. Existing file found → `load_experiment_config()` → `ExperimentConfig.from_dict()`
4. `from_dict()` translates CODEX field names and maps wavelengths
5. Config saved in KINTSUGI format via `save_experiment_config()`

## Key Files Modified
- `src/kintsugi/project.py`: `_CODEX_FILTER_SETS`, `_excitation_to_filter_pair()`, `_CODEX_FIELD_MAP`, `ExperimentConfig.from_dict()`

## Trigger Conditions
This skill applies when:
- Parsing CODEX/Akoya experiment.json files
- Wavelengths show duplicated excitation==emission values
- ExperimentConfig fields are None despite experiment.json existing
- Setting up batch projects from CODEX raw data on orange storage
