---
name: cycle-dir-normalization
description: "Normalize long-form CODEX cycle folders to short form before notebooks run. Trigger: cyc001_reg001_*, hard-coded cyc paths breaking, staged CODEX raw data failing in Notebooks 1/2."
author: KINTSUGI Team
date: 2026-04-16
---

# Cycle Directory Normalization

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-04-16 |
| **Goal** | Make `cyc004_reg001_211206_201615` → `cyc004` rename available in both Notebook 1 and Notebook 2 |
| **Environment** | KINTSUGI notebooks, CODEX raw data staged from `src_*` source folders |
| **Status** | Success |

## Context

CODEX raw data often lands in long-form folders:
```
data/raw/cyc004_reg001_211206_201615/
data/raw/cyc005_reg001_211206_212937/
```

Both notebooks assume short form everywhere:
- Notebook 1 cell 14: `cycle_folder = project.paths.raw / "cyc001"` (hard-coded literal!)
- Notebook 2 cell 13 (raw preview): `Path(image_dir) / f"cyc{cycle:03d}"`
- Notebook 2 cell 16 (QC): `glob(..., f'cyc{str(cycle).zfill(3)}', ...)`
- Notebook 2 cell 42 (reprocess): `f'cyc{REPROCESS_CYCLE:03d}'`

Without normalization, these paths silently find zero files and the notebooks run "successfully" with empty results. An early version of Notebook 2 had a rename cell, but it was dropped (git history shows no explicit rename operations in any committed notebook version — likely existed only in a staging script that was never checked in).

**The SLURM/Snakemake path works differently**: `workflow/scripts/stitch.py:find_cycle_dir()` and `Snakefile:_resolve_raw_cycle_dir()` use glob patterns (`cyc{N:03d}_*`) to resolve long-form names at query time. That is why the pipeline batches ran fine on long-form data while the notebooks broke.

## Verified Workflow

### 1. Shared helper in `notebooks/Kio.py`

```python
_CYCLE_DIR_LONG_RE = re.compile(
    r"^(?:cyc|cycle)[_\-]?(\d+)(?:_reg\d+)?(?:[_\-].*)?$",
    re.IGNORECASE,
)

def normalize_cycle_dirs(raw_dir, width=3, dry_run=False, verbose=True):
    """Rename cyc<N>_reg<M>_... -> cyc<N zero-padded to width> in place."""
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        return {}

    renames, collisions = {}, []
    for item in sorted(raw_dir.iterdir()):
        if not item.is_dir():
            continue
        m = _CYCLE_DIR_LONG_RE.match(item.name)
        if not m:
            continue
        short = f"cyc{int(m.group(1)):0{width}d}"
        if item.name == short:
            continue
        target = raw_dir / short
        if target.exists() and target.resolve() != item.resolve():
            collisions.append((item.name, short))
            continue
        renames[item.name] = short

    if collisions:
        raise RuntimeError(...)  # Never overwrite
    for old, new in renames.items():
        if not dry_run:
            (raw_dir / old).rename(raw_dir / new)
    return renames
```

### 2. Call before `find_raw_cycles` in both notebooks

**Notebook 1 cell 5**:
```python
from Kio import normalize_cycle_dirs
normalize_cycle_dirs(project.raw_dir)
cycles = find_raw_cycles(project.raw_dir)
```

**Notebook 2 cell 6**: same pattern right before `cycles = find_raw_cycles(image_dir)`.

### 3. Leave Snakemake/SLURM alone

`workflow/scripts/stitch.py:find_cycle_dir()` and `Snakefile:_resolve_raw_cycle_dir()` already handle long-form at glob time. Don't touch them — they're the fallback when the user runs the pipeline without ever opening the notebooks.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Assumed staging scripts renamed folders | `stage_datasets.sh` / `stage_datasets_globus.py` use rsync with a trailing slash — they preserve source names verbatim | Must normalize at notebook entry, not rely on upstream staging |
| Searched git history for the missing rename cell | No explicit `os.rename` for cycle folders in any committed version — only a decon output rename | The lost cell was in a working copy or project-specific notebook, not the repo. Just rebuild it in `Kio.py` |
| Considered rewriting all hard-coded `f"cyc{cycle:03d}"` to use `find_cycle_dir()` | 8+ cells across both notebooks, each would need a 2-line lookup + fallback; plus `project.paths.raw / "cyc001"` literals that can't be easily parameterized | Renaming at the filesystem is one call; path rewrites are N call sites |
| Made the helper prompt before renaming | Notebooks already run many cells automatically; an interactive prompt would block unattended use | Loud print + collision guard is sufficient — errors raise, successes log |
| Skipped the collision guard (`target.exists()` check) | Would silently merge/overwrite if both `cyc001` and `cyc001_reg001_*` existed side by side | Raise `RuntimeError` with collision list; user must resolve manually |

## Final Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Zero-pad width | 3 (`cyc001`) | Matches existing raw data naming (`project.paths.raw / "cyc001"` literal in Notebook 1) |
| Regex | `^(cyc|cycle)[_-]?(\d+)(?:_reg\d+)?(?:[_-].*)?$` | Handles `cyc1`, `cyc01`, `cyc001`, `cyc001_reg001_200210_170925`, `Cycle_1`, `Cycle-2`, case-insensitive |
| Collision policy | Raise | Never overwrite — user must resolve ambiguous state |
| Idempotency | Short-form folders skipped | Safe to re-run on already-normalized datasets |
| Dry-run | `dry_run=True` prints plan, returns map, renames nothing | For inspection before modifying disk |
| Location | `notebooks/Kio.py` | Canonical shared helper module; both notebooks already import from Kio |
| Call site | Notebook 1 cell 5, Notebook 2 cell 6 | Immediately before `find_raw_cycles()`, before any hard-coded `cyc{N:03d}` lookups |

## Key Insights

- Hard-coded path literals in notebook cells are a time bomb: they work on the datasets that were in the author's `data/raw/` at development time, then silently fail when someone stages data with different naming.
- The SLURM/Snakemake path solving this via glob-at-query-time is elegant but doesn't help the notebooks, because notebooks don't call `find_cycle_dir()` from Kio — they build paths directly with f-strings.
- Post-commit sync hook (`scripts/sync_to_projects.py`) propagates `Kio.py` changes automatically to all 33+ project folders, so the fix lands everywhere on commit.
- When a user says "a cell was there in an early version" and git history doesn't show it, it was probably in a project-specific working copy that never got committed. Rebuild from first principles instead of hunting through branches.

## References

- `notebooks/Kio.py:334-436` — `normalize_cycle_dirs()` implementation
- `notebooks/1_Single_Channel_Eval.ipynb` cell 5 — call site
- `notebooks/2_Cycle_Processing.ipynb` cell 6 — call site
- `workflow/scripts/stitch.py:154-175` — `find_cycle_dir()` (SLURM-side, glob-based, unchanged)
- `workflow/Snakefile:86-112` — `_resolve_raw_cycle_dir()` (Snakemake-side, unchanged)

## Related Skills

- `notebook-module-refactoring` — Same pattern (extract shared helpers to `Kio.py`); this skill is the "what to write" when the refactoring skill covers "how to extract safely"
- `repo-project-sync-workflow` — Edit in `KINTSUGI/notebooks/` only; post-commit hook propagates
