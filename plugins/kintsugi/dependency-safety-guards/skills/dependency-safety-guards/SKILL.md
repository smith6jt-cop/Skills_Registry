# Dependency Safety Guards

| Field | Value |
|-------|-------|
| **Date** | 2026-03-24 |
| **Status** | Verified Success |
| **Environment** | Python 3.11, conda, HiPerGator HPC |
| **Scope** | 14 optional install groups, numpy<2.0 constraint |

## Context

KINTSUGI has 14 optional dependency groups (`gpu`, `dl`, `analysis`, `bio`, `workflow`, etc.) installed via `kintsugi install <group>`. Three critical conflict classes emerged:

1. **numpy 2.x breakage**: `analysis`/`bio` packages pull numpy 2.x transitively, breaking scipy/scikit-image/cupy compiled against numpy 1.x
2. **CPU-only PyTorch**: `dl`/`denoise`/`kronos` groups ran `pip install torch` without CUDA index, silently installing CPU-only builds
3. **CuPy missing CUDA runtime**: `pip install cupy-cuda12x` only provides Python bindings; actual CUDA libs (`libcufft`, `libcublas`) must come from conda

## Verified Workflow

### 1. Constraints file (`constraints.txt`)
Central `numpy>=1.24.0,<2.0.0` constraint at repo root. Auto-injected into all `kintsugi install` pip commands via `_inject_constraints()`.

### 2. CUDA index URL in all torch groups
Every group that installs torch uses `--index-url https://download.pytorch.org/whl/cu124`. This prevents pip from downloading CPU-only builds from PyPI.

### 3. numpy<2.0 in pyproject.toml per-group extras
Individual group installs (`pip install kintsugi[analysis]`) only see that group's constraints. Adding `numpy>=1.24.0,<2.0.0` to `analysis`, `bio`, `kronos` groups prevents transitive numpy 2.x.

### 4. Pre-install guard (`_pre_install_guard()`)
Checks before running install commands: CPU-only torch present, numpy 2.x present. Warns but does not block.

### 5. Post-install validation (`_post_install_validate()`)
Runs `DependencyChecker` after every install. Reports errors (numpy version, torch build type).

### 6. Deep validation in `kintsugi check --strict`
Four checks: numpy version constraint, torch CUDA build, CuPy CUDA libraries, SLURM TRES patch status.

## Failed Attempts

| Attempt | Why It Failed |
|---------|--------------|
| Multi-environment split (2 envs: processing + analysis) | 47 projects use single env; Snakemake precommand activates one env; notebooks expect all packages in one kernel; migration disruptive |
| Lock files (conda-lock / pip-compile) | 6+ platform-specific lock files to maintain; scientist maintainer can't sustain the overhead; goes stale with every dependency release |
| Upper-bound pins on all transitive dependencies | Fragile: pins go stale quickly; blocks legitimate upgrades; creates false security |
| Relying solely on `pip install -e ".[group1,group2]"` unified resolution | Only works for `install all`; individual `kintsugi install analysis` bypasses pyproject.toml core constraints |
| Adding numpy<2.0 only to pyproject.toml core (not per-group) | Core constraint not enforced when installing a single extra (`pip install kintsugi[bio]` only sees the bio group deps) |

## Final Implementation

### Key Files
- `src/kintsugi/deps.py` — `OPTIONAL_GROUPS`, `_inject_constraints()`, `_pre_install_guard()`, `DependencyChecker` deep validation
- `pyproject.toml` — numpy<2.0 in analysis/bio/kronos groups, workflow group
- `constraints.txt` — Central constraint file
- `src/kintsugi/cli.py` — `check --strict --for`, `patch slurm`, `_post_install_validate()`

### Key Insights
- **Constraints must be enforced at every install path**: pyproject.toml extras (for `install all`), per-group constraints (for individual installs), and constraints.txt (for manual pip)
- **PyTorch CUDA index is the most dangerous omission**: CPU-only torch is silently functional until GPU code runs — hard to detect without explicit build check
- **Post-install validation catches cascading breakage**: Individual installs can break previously-working packages
- **Pre-install warnings prevent foot-guns**: Alerting users before they install `dl` on top of CPU-only torch
- **Single env with guard rails beats multi-env for scientific users**: The complexity of activating different environments per pipeline stage outweighs the theoretical cleanliness

## References
- `docs/DEPENDENCY_GUIDE.md` — User-facing troubleshooting guide
- `CLAUDE.md` "Dependency Safety" section — Developer reference
- Skills: `pypi-collision-fix`, `dependency-deprecation`, `conda-multi-account-hipergator`
