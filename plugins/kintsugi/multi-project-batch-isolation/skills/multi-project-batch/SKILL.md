---
name: multi-project-batch-isolation
description: "Multi-project signal isolation with cascading recipe resolution"
author: smith6jt
date: 2026-02-22
---

# Multi-Project Batch Signal Isolation

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-22 |
| **Goal** | Run AF subtraction across ~20 projects with intelligent per-marker parameter sourcing |
| **Environment** | HiPerGator, Python 3.11, KINTSUGI conda env |
| **Status** | Success — 17 projects discovered, dry-run validated |

## Context

Only 1 of ~20 registered projects (CX_19-001_SP_CC2-A28) had completed signal isolation. That project had 26 hand-tuned legacy recipes and its outcomes were recorded to the parameter learning DB. The remaining projects needed AF subtraction but had no project-specific recipes. A single-project `kintsugi workflow isolate run` command existed but couldn't orchestrate multiple projects or source parameters from across datasets.

**Key challenge**: Not all markers have recipes in every project. Need a cascading fallback system that uses the best available source per marker.

## Verified Workflow

### CLI Commands

```bash
# Preview all eligible projects and recipe sources
kintsugi workflow isolate batch /path/to/KINTSUGI_Projects --dry-run

# Process single project (test before full batch)
kintsugi workflow isolate batch . -d CX_19-003_spleen_CC1-A

# Full batch with learning enabled
kintsugi workflow isolate batch /blue/maigan/smith6jt/KINTSUGI_Projects --learn

# Force reprocess + custom template
kintsugi workflow isolate batch . -f --template-recipe-dir /path/to/recipes
```

### Cascading Recipe Resolution (4 tiers)

| Tier | Source | Condition |
|------|--------|-----------|
| 1 | Own recipes | `{project}/data/processed/Processing_parameters/*_param.txt` exists |
| 2 | Learned DB | `ParameterLearningEngine.recommend_parameters()` confidence >= 0.6 |
| 3 | Template | Default: CX_19-001's 26 recipes, match by marker name |
| 4 | Auto | `select_method()` picks global vs weighted per marker |

### Tissue Type Parsing (regex, case-insensitive)

```python
_TISSUE_PATTERNS = [
    (r"(?:_SP_|spleen|splenic)", "spleen"),
    (r"(?:_LN_|lymph.?node|lymph)", "lymph_node"),
    (r"(?:_TH_|thymus|thymic)", "thymus"),
    (r"(?:pancrea)", "pancreas"),
]
```

Fallback: `experiment.json` `name` field, then `"unknown"`.

### Architecture: Two-Pass Processing

Markers with recipes (tiers 1-3) use `_write_recipes_as_param_files()` to serialize resolved recipes into temp param files, then call `process_batch(recipe_dir=tmpdir)`. Markers without recipes (tier 4) call `process_batch()` without recipe_dir for auto-analysis. Results are merged into a single `signal_isolation_manifest.json`.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Passing resolved recipes directly to `process_channel()` | `process_batch()` handles all the plumbing (location_map, blank resolution, output dir, learning DB) | Reuse existing `process_batch()` — serialize recipes to temp param files instead of bypassing |
| Patching `kintsugi.signal.batch_multi.ParameterLearningEngine` | Import is inside `resolve_recipes_for_project()`, not at module level | Patch `kintsugi.claude.parameter_learning.ParameterLearningEngine` |
| Testing template tier without mocking learned DB | Real learning DB has data from CX_19-001, so learned tier wins | Mock learning DB to return `{"confidence": 0.0}` in template tier tests |
| Single `process_batch()` call with mixed recipe/auto markers | `process_batch` either uses recipes for all or none per call | Split into two calls: recipe markers + auto markers, then merge results |

## Final Parameters

```python
# Discovery
config_path = project / "workflow" / "config.yaml"  # Must exist
registered_dir = project / "data" / "processed" / "registered"  # Must have .tif files
manifest_path = ".../signal_isolated/signal_isolation_manifest.json"  # Skip if exists

# Recipe search dirs (in order)
_RECIPE_SEARCH_DIRS = [
    "data/processed/Processing_parameters",
    "Processing_parameters",
    "notebooks/Processing_parameters",
]

# Default template project
DEFAULT_TEMPLATE_PROJECT = "CX_19-001_SP_CC2-A28"

# Learning DB confidence threshold
min_confidence = 0.6

# Processing defaults
tile_smooth_sigma = 0.0  # No blank smoothing (recipes don't need it)
method = "auto"  # Per-marker: global vs weighted
learn = True  # Record outcomes for cross-dataset transfer
```

## Key Insights

- **17 of ~48 project directories are eligible** (have config.yaml + registered images, no existing manifest)
- **Most markers resolve from learned DB** (CX_19-001 spleen params cover ~18/28 markers per spleen project)
- **Lymph node projects fall through to template** for 2-4 markers not in the spleen learning DB
- **`_write_recipes_as_param_files()` roundtrips cleanly** — `load_legacy_recipes()` can read the generated files
- **`recipe_source` field on `ChannelResult`** tracks provenance ("own_recipe", "learned", "template", "auto")
- **Sequential processing is correct** for shared filesystem — parallel would cause I/O contention
- **Error isolation per project** — one project failure doesn't stop the batch
- **Cross-project report** `batch_isolation_report_{timestamp}.json` saved to projects_dir

## Key Files

- `src/kintsugi/signal/batch_multi.py` — Core: discovery, tissue parsing, recipe resolution, orchestration
- `src/kintsugi/signal/batch.py` — Single-project processing, `ChannelResult.recipe_source` field
- `src/kintsugi/cli.py` — `@isolate_group.command("batch")` CLI
- `tests/test_batch_multi_project.py` — 34 tests (tissue parsing, discovery, resolution, roundtrip)
- `src/kintsugi/signal/CLAUDE.md` — Documentation

## References

- Builds on `batch-signal-isolation` skill (single-project recipe-driven processing)
- Uses `batch-orchestration-script` pattern (sequential, error isolation, per-dataset filtering)
- Follows `claude-md-context-management` for documentation placement
