---
name: notebook-function-not-found
description: "Troubleshooting NameError for functions defined in notebook cells, not external modules"
author: Claude Code
date: 2026-01-20
version: 1.0
---

# Notebook Function Not Found - Troubleshooting Guide

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-01-20 |
| **Goal** | Diagnose and fix "NameError: name 'function_name' is not defined" in Jupyter notebooks |
| **Environment** | KINTSUGI Jupyter notebooks, especially 2_Cycle_Processing.ipynb |
| **Status** | Resolved |

## Context

When users report that a function like `run_deconvolution` is "not found", the issue is usually **cell execution order**, not missing imports or sync problems. Many KINTSUGI notebooks define wrapper functions directly in notebook cells rather than importing them from modules.

## Root Cause

Functions defined in notebook cells (not external modules) require the definition cell to be executed before the calling cell. This is different from module imports which persist across notebook restarts.

### Key Distinction
```python
# MODULE IMPORT (persists after import cell runs):
from Kdecon import decon  # decon is available immediately

# NOTEBOOK-DEFINED FUNCTION (requires cell execution):
def run_deconvolution(...):  # Only available AFTER this cell runs
    ...
```

## Diagnostic Steps

### 1. Identify if function is notebook-defined or imported

```python
import json
with open('notebook.ipynb') as f:
    nb = json.load(f)

func_name = 'run_deconvolution'  # Change as needed
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] != 'code':
        continue
    source = ''.join(cell.get('source', []))
    if func_name in source:
        is_def = f'def {func_name}' in source
        is_import = f'from' in source and func_name in source
        print(f"Cell {i}: {'DEFINES' if is_def else 'IMPORTS' if is_import else 'CALLS'} {func_name}")
```

### 2. Check cell execution order

If the function is **defined in the notebook** (not imported), the definition cell MUST run before the calling cell.

### 3. Common patterns in 2_Cycle_Processing.ipynb

| Function | Type | Defined/Imported In | Called In |
|----------|------|---------------------|-----------|
| `decon` | Import | Cell 3 | Cell 24 (inside run_deconvolution) |
| `run_deconvolution` | **Notebook-defined** | Cell 24 | Cell 25 |
| `process_edf_tiff` | **Notebook-defined** | Cell 31 | Cell 32 |
| `decon_channel_wrapper` | **Notebook-defined** | Cell 25 | Cell 25 (same cell) |
| `visualize_deconvolution` | **Notebook-defined** | Cell 27 | Manual use |

## Verified Solution

1. **Run cells in order**: Start from the top of the notebook, or at minimum:
   - Run Cell 3 (imports)
   - Run Cell 24 (defines `run_deconvolution`)
   - Then run Cell 25 (calls `run_deconvolution`)

2. **Use "Run All Above"**: In Jupyter, use "Run All Above" on the cell that's failing.

3. **Check for execution numbers**: Look at `In [N]:` - if the definition cell has no number or a higher number than the calling cell, that's the problem.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Searching modules for the function | `run_deconvolution` is defined in the notebook, not a module | Check notebook cells first, not just .py files |
| Re-syncing project folders | Sync was already up-to-date; issue was cell execution order | Sync issues show different errors (ImportError, ModuleNotFoundError) |
| Telling user to restart kernel | Unnecessary - autoreload handles module changes, but won't help with notebook-defined functions | Kernel restart doesn't define notebook functions |
| Looking for import statements | Function is defined with `def`, not imported | Search for `def function_name` not just `function_name` |

## Key Insights

- **Notebook-defined functions** require running the definition cell every time the kernel starts
- **Module imports** with autoreload persist and update automatically
- **Cell execution numbers** (`In [N]:`) reveal execution order - missing numbers mean the cell hasn't run
- **"Run All"** or **"Run All Above"** are the safest way to ensure correct execution order
- Most wrapper functions in KINTSUGI notebooks (like `run_deconvolution`, `process_edf_tiff`) are notebook-defined, not module imports

## Trigger Conditions

This skill applies when:
- User reports `NameError: name 'X' is not defined`
- The function exists in the notebook but "isn't working"
- `run_deconvolution`, `process_edf_tiff`, or similar wrapper functions aren't found
- User jumped directly to a cell without running earlier cells
- Notebook was just opened and cells weren't run

## Related Skills
- `jupyter-autoreload-awareness` - When NOT to restart kernels
- `repo-project-sync-workflow` - When sync issues cause import errors
- `notebook-module-refactoring` - When functions move between notebooks and modules

## References
- KINTSUGI `notebooks/2_Cycle_Processing.ipynb` - Cell 24 (run_deconvolution definition)
- KINTSUGI CLAUDE.md - "Troubleshooting Function Not Found Errors" section
