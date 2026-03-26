---
name: unified-install-resolution
description: "Fix cascading dependency conflicts from sequential pip install per group. Trigger: (1) `kintsugi install all` causes numpy/torch/CUDA version conflicts, (2) pip install per-group overwrites cross-group constraints, (3) dependency conflict cascade from sequential pip invocations"
author: smith6jt
date: 2026-03-14
---

# Unified Install Resolution — pyproject.toml Extras

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-03-14 |
| **Goal** | Fix `kintsugi install all` cascading dependency conflicts |
| **Environment** | HiPerGator, Python 3.11, conda KINTSUGI env, 12 optional groups |
| **Status** | Success |

## Context

`kintsugi install all` ran `pip install` sequentially for each of 12 optional groups. Each pip invocation made locally-optimal but globally-incompatible choices:
- `bio` pulled numpy 2.4.3 (violating `numpy<2.0`)
- `rapids` overwrote torch's CUDA bindings
- Later groups undid constraints satisfied by earlier groups

The proper constraints were already declared in `pyproject.toml` extras — they just needed to be resolved together in a single pip pass.

## What Worked

### Single pip extras pass
```python
# In _install_all():
extras_str = ",".join(extras)  # "gpu,viz,dl,analysis,bio,claude,dev,docs,kronos,denoise"
cmd = f'pip install -e "{project_root}[{extras_str}]"'
```

Key elements:
1. `_find_project_root()` in `deps.py` — walks up from `kintsugi.__file__` to find `pyproject.toml`
2. `_install_all()` extracted as helper in `cli.py` with three paths:
   - **pip extras** (default): single `pip install -e ".[gpu,viz,dl,...]"` — unified resolution
   - **conda hybrid** (`--conda`): conda groups first, then remaining via pip extras
   - **fallback** (no pyproject.toml): sequential install + `pip install -e .` repair
3. `full` and `rapids` excluded from `all` — rapids needs NVIDIA channel, full is composite
4. Single-group installs (`kintsugi install gpu`) unchanged

### Test pattern for mocking
```python
@patch("subprocess.run")
@patch("kintsugi.cli._find_project_root")
def test_install_all_uses_extras(self, mock_root, mock_run, runner, tmp_path):
    mock_root.return_value = tmp_path
    mock_run.return_value = MagicMock(returncode=0)
    result = runner.invoke(main, ["install", "all"])
    assert mock_run.call_count == 1  # Single pip call
    cmd_arg = mock_run.call_args[0][0]
    assert "pip install -e" in cmd_arg
    assert "rapids" not in cmd_arg
```

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Sequential pip per group | Each pip invocation makes locally-optimal choices that break cross-group constraints | Always resolve all extras together in one pip pass |
| `pip install -e .` repair after sequential | Can't reliably undo numpy 2.x → 1.x downgrades if packages have already been compiled against numpy 2.x | Prevention > repair — single pass from the start |
| Including `rapids` in `all` | NVIDIA channel packages conflict with PyPI resolution | Exclude channel-specific groups from unified pip pass |
| Including `full` in `all` | Composite group duplicates individual groups' packages | Skip composites, install only leaf groups |

## Final Parameters

```python
# deps.py
def _find_project_root() -> Path | None:
    import kintsugi
    pkg_dir = Path(kintsugi.__file__).parent
    for parent in [pkg_dir.parent.parent, pkg_dir.parent]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None

# cli.py
_SKIP_FROM_ALL = {"full", "rapids"}
extras = [k for k in OPTIONAL_GROUPS if k not in _SKIP_FROM_ALL]
```

## Key Insights

- pyproject.toml extras are the correct mechanism for multi-group dependency resolution — pip's resolver handles cross-group constraints
- `_find_project_root()` enables editable installs to find their own pyproject.toml
- The fallback path (sequential + repair) is important for wheel installs without source checkout
- Conda hybrid mode handles groups that need non-PyPI channels (nvidia, conda-forge)

## References
- `src/kintsugi/deps.py` — `_find_project_root()`, `OPTIONAL_GROUPS`
- `src/kintsugi/cli.py` — `_install_all()`, `install` command
- `tests/test_workflow.py` — `TestInstallCommand` (8 tests)
