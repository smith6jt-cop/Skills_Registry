---
name: notebook-module-extraction
description: "Extract long code cells from Jupyter notebooks into reusable Python modules while preserving transparency and autoreload compatibility"
author: smith6jt
date: 2026-01-20
---

# Notebook Module Extraction - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-01-20 |
| **Goal** | Refactor long notebook cells (100+ lines) into reusable modules while maintaining code transparency and not disrupting active processing jobs |
| **Environment** | Python 3.10+, Jupyter notebooks with `%autoreload 2` enabled |
| **Status** | Success - 99% line reduction in QC cells |

## Context
Large Jupyter notebooks become difficult to maintain when cells contain hundreds of lines of function definitions. This creates several problems:
- Code duplication across notebooks
- Difficulty testing functions in isolation
- Long cells obscure the actual workflow logic
- Git diffs become unreadable

However, simply extracting code to modules can break:
- Global variable dependencies (notebook variables not accessible in modules)
- Processing transparency (users can't see what functions do)
- Active processing jobs if files are synced mid-execution

## Verified Workflow

### Phase 1: Identify Extraction Candidates
```python
# Analyze notebook cell lengths
import json
with open('notebook.ipynb') as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        lines = len(cell['source'])
        if lines > 100:
            preview = ''.join(cell['source'])[:100].replace('\n', ' ')
            print(f'Cell {i}: {lines} lines - {preview}...')
```

### Phase 2: Design Module Interface
Key principle: **Make all functions accept explicit parameters instead of relying on notebook globals.**

```python
# BAD - relies on notebook globals
def compute_stats():
    # Uses GPU_DEVICE_IDS, IO_WORKERS from notebook
    for device_id in GPU_DEVICE_IDS:  # Global!
        ...

# GOOD - explicit parameters with defaults
def compute_stats(
    gpu_device_ids: List[int] = None,
    io_workers: int = 4,
) -> pd.DataFrame:
    gpu_ids = gpu_device_ids or [0]
    ...
```

### Phase 3: Create Module with Convenience Wrappers
Structure the module with three layers:
1. **Core functions** - Single-image/item operations
2. **Parallel collection** - Batch operations with progress tracking
3. **Convenience wrappers** - Full workflow with caching, printing, plotting

```python
# Module structure (Kprocess.py example)

# Layer 1: Core functions
def compute_zplane_stats_gpu(image_dir, cycle, channel, zplane, device_id=0):
    """Single z-plane statistics computation."""
    ...

# Layer 2: Parallel collection
def collect_raw_stats_parallel(image_dir, start_cycle, end_cycle, ...):
    """Parallel stat collection with progress tracking."""
    ...

# Layer 3: Convenience wrappers
def run_raw_qc(image_dir, cache_file, start_cycle, end_cycle, ...):
    """Complete QC workflow: load/compute, cache, plot, print summary."""
    ...
```

### Phase 4: Refactor Notebook Cells
Replace long function definitions with imports + usage:

```python
# =============================================================================
# COMPREHENSIVE QUANTITATIVE ANALYSIS - All cycles, channels, z-planes
# =============================================================================
# Implementation extracted to: notebooks/Kprocess.py
# Functions: compute_zplane_stats_gpu, collect_raw_stats_parallel,
#            plot_summary_heatmaps, plot_zplane_profiles
# =============================================================================

from Kprocess import run_raw_qc

# Cache and output directories
RAW_STATS_CACHE = PROJECT_DIR / 'cache' / 'raw_stats.pkl'
QC_OUTPUT_DIR = PROJECT_DIR / 'qc_plots'

# Run comprehensive raw data QC
raw_stats_df = run_raw_qc(
    image_dir=image_dir,
    cache_file=RAW_STATS_CACHE,
    start_cycle=start_cycle,
    end_cycle=end_cycle,
    # ... explicit parameters from notebook
)
```

### Phase 5: Programmatic Notebook Modification
Use Python to modify notebook JSON directly:

```python
import json

with open('notebook.ipynb', 'r') as f:
    nb = json.load(f)

# Replace cell source
new_source = '''from Kprocess import run_raw_qc
...'''

lines = new_source.split('\n')
nb['cells'][15]['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]]

with open('notebook.ipynb', 'w') as f:
    json.dump(nb, f, indent=1)
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Directly editing notebook in VS Code | JSON formatting issues, easy to corrupt cell structure | Use Python script to modify notebook JSON programmatically |
| Using notebook globals in module | Functions fail when imported because globals don't exist | Pass all dependencies as explicit parameters with defaults |
| Syncing changes mid-processing | Could disrupt active jobs using notebook code | Only sync on commit; changes don't affect project folders until git commit triggers post-commit hook |
| One giant convenience function | Too inflexible for different use cases | Use three-layer approach: core → parallel → convenience |
| Extracting orchestration code | Made notebook too opaque; lost "what happens" visibility | Keep orchestration/workflow logic in notebook; extract only reusable functions |

## Final Parameters

### Module Template Structure
```python
"""
Module Docstring - Explain what was extracted and from where.

Functions:
---------
Core Operations:
    - compute_X_stats(): Single-item computation
    - compute_Y_stats(): Single-item computation

Parallel Collection:
    - collect_X_parallel(): Batch with progress tracking
    - collect_Y_parallel(): Batch with progress tracking

Visualization:
    - plot_summary(): Summary plots
    - plot_details(): Detailed plots

Convenience:
    - run_X_qc(): Complete workflow with caching
"""

from typing import Dict, List, Optional, Union
from pathlib import Path
import pandas as pd

# Core function signature pattern
def compute_stats(
    data_dir: Union[str, Path],
    item_id: int,
    device_id: int = 0,
    workers: int = 4,
) -> Optional[Dict[str, float]]:
    """Explicit parameters, optional return for missing data."""
    ...
```

### Notebook Cell Template
```python
# =============================================================================
# SECTION NAME - Brief description
# =============================================================================
# Implementation extracted to: notebooks/ModuleName.py
# Functions: func1, func2, func3
# =============================================================================

from ModuleName import convenience_function

# All configuration comes from notebook variables defined earlier
result = convenience_function(
    data_dir=data_dir,           # From notebook
    param1=PARAM1,               # From notebook config cell
    param2=param2,               # From notebook config cell
)
```

## Key Insights

- **Autoreload compatibility**: With `%autoreload 2`, users don't need to restart kernels after module changes
- **Transparency via comments**: Add header comments explaining where code was moved; users can easily find the implementation
- **Three-layer design**: Core functions for testing, parallel for batch ops, convenience for notebooks
- **Explicit parameters eliminate globals**: Makes functions testable and reusable outside notebooks
- **JSON modification is safe**: Python's json module handles notebook format correctly; just preserve cell structure
- **Post-commit sync pattern**: Changes only affect project folders after commit, preventing disruption of active jobs

## References
- KINTSUGI CLAUDE.md: Automatic Project Sync section
- KINTSUGI commit a7a17de: Reference implementation of this pattern
- Python json module: For notebook manipulation
