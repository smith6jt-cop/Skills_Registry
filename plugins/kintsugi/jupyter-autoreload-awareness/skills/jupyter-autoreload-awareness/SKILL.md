# Jupyter Autoreload Awareness

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2025-01-14 |
| **Goal** | Stop telling users to restart kernels or reload notebooks unnecessarily |
| **Environment** | Jupyter notebooks with autoreload extension |
| **Status** | Critical workflow improvement |

## Context

KINTSUGI notebooks use IPython's autoreload extension:

```python
%load_ext autoreload
%autoreload 2
```

With `%autoreload 2`, **all imported modules are automatically reloaded before executing any code**. This means:

- Edits to `.py` files (Kio.py, modules in Kdecon/, Kstitch/, etc.) take effect immediately
- No kernel restart needed
- No notebook reload needed
- Just re-run the cell that imports/uses the module

## NEVER Say These Things

| Bad Advice | Why It's Wrong |
|------------|----------------|
| "Restart your Jupyter kernel" | Autoreload handles module updates automatically |
| "Reload the notebook" | Wastes time, loses output/state, unnecessary |
| "Close and reopen the notebook" | Even worse - complete productivity killer |
| "You may need to restart..." | Creates doubt; autoreload makes this unnecessary |

## Correct Guidance

After editing a Python module that a notebook imports:

**CORRECT**: "Re-run the cell" or just confirm the edit was made
**WRONG**: "Restart kernel and reload notebook"

## When Kernel Restart IS Needed

Only tell user to restart kernel when:
1. Installing new packages (`pip install`)
2. Changing environment variables that were read at import time
3. C extension modules were recompiled
4. Autoreload is NOT enabled in the notebook
5. User explicitly asks to restart

## Trigger Conditions

This skill applies when:
- About to tell user to restart Jupyter kernel
- About to tell user to reload/reopen notebook
- After editing .py files imported by notebook (Kio.py, kintsugi/*.py, etc.)
- User is working in a Jupyter notebook environment

## Key Insight

Telling users to restart kernels or reload notebooks **lowers productivity significantly**. With autoreload enabled, the only action needed after editing imported modules is to re-run the relevant cell.
