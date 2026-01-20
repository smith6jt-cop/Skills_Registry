---
name: repo-project-sync-workflow
description: "When editing KINTSUGI notebook modules (Kdecon, Kstitch, Kreg, etc.), always edit the main repo first then sync to project folders. Uses checksum comparison to detect changes."
author: Claude Code
date: 2026-01-20
version: 2.0
---

# KINTSUGI Repository-to-Project Sync Workflow

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-01-20 (updated from 2025-12-17) |
| **Goal** | Establish correct workflow for editing shared notebook modules |
| **Environment** | KINTSUGI multi-project setup with shared codebase |
| **Status** | Success |

## Context
KINTSUGI uses a shared codebase model where:
- **Main repo**: `/blue/maigan/smith6jt/KINTSUGI/` contains the source code
- **Project folders**: `/blue/maigan/smith6jt/KINTSUGI_Projects/.../notebooks/` contain working copies

Project folders sync FROM the main repo. If you edit a project folder directly, those changes will be **overwritten** when the user syncs from the main repo.

## Automated Sync System

The sync happens automatically via:
- `scripts/sync_to_projects.py` - Sync script (uses **MD5 checksum comparison**)
- `.git/hooks/post-commit` - Git hook that runs sync after each commit

### Checksum-Based Comparison (v2.0)
The sync script now uses **MD5 checksums** instead of timestamps to detect changes:

```python
# Old (problematic): timestamp comparison
if src_mtime <= dst_mtime:
    skip()  # WRONG: skips if dest is newer even with different content

# New (correct): checksum comparison
if compute_checksum(src) == compute_checksum(dst):
    skip()  # Only skips if content is identical
```

This ensures:
- Notebooks saved with output in project folders don't block updates
- Content changes are always detected regardless of file timestamps
- Network file system timestamp issues don't cause sync failures

### Manual Sync Commands
```bash
python scripts/sync_to_projects.py           # Sync all projects (checksum comparison)
python scripts/sync_to_projects.py --dry-run # Preview changes
python scripts/sync_to_projects.py --verbose # Show detailed output
python scripts/sync_to_projects.py --force   # Force sync all files (ignore checksum)
```

## Verified Workflow

### CORRECT: Edit Main Repo First
```bash
# 1. Make edits to the main repo
/blue/maigan/smith6jt/KINTSUGI/notebooks/Kdecon/deconvolution.py

# 2. Commit changes (auto-syncs via post-commit hook)
git add . && git commit -m "fix: update deconvolution"

# 3. Or manually sync if needed
python scripts/sync_to_projects.py --verbose
```

### Key Paths
| Component | Main Repo Path | Project Folder Path |
|-----------|---------------|---------------------|
| KDecon | `KINTSUGI/notebooks/Kdecon/` | `KINTSUGI_Projects/.../notebooks/Kdecon/` |
| Kstitch | `KINTSUGI/notebooks/Kstitch/` | `KINTSUGI_Projects/.../notebooks/Kstitch/` |
| Kreg | `KINTSUGI/notebooks/Kreg/` | `KINTSUGI_Projects/.../notebooks/Kreg/` |
| Kview2 | `KINTSUGI/notebooks/Kview2/` | `KINTSUGI_Projects/.../notebooks/Kview2/` |
| Kview_qc | `KINTSUGI/notebooks/Kview_qc.py` | `KINTSUGI_Projects/.../notebooks/Kview_qc.py` |
| Kprocess | `KINTSUGI/notebooks/Kprocess.py` | `KINTSUGI_Projects/.../notebooks/Kprocess.py` |
| src/kintsugi | `KINTSUGI/src/kintsugi/` | N/A (installed package) |

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Editing project folder first | User synced from main repo, overwriting all changes | Always edit main repo first |
| Copying project→main after edit | Creates confusion about source of truth | Main repo is ALWAYS the source |
| **Timestamp-based sync comparison** | **Notebooks saved with output got newer timestamps, blocking sync even when source was updated** | **Use checksum comparison instead of timestamp** |
| Assuming sync worked after commit | Sync reported "up to date" because destination had newer timestamp | Verify with `--verbose` or check file sizes |

## Key Insights
- The main repo (`/blue/maigan/smith6jt/KINTSUGI/`) is the **single source of truth**
- Project folders are working copies that get synced FROM main repo
- After editing main repo, remind user to sync OR sync for them
- **When sync reports "up to date" but changes aren't applied**: destination file was modified (e.g., notebook saved with output), creating a newer timestamp - now fixed with checksum comparison
- When user reports a fix "didn't work", check if they synced (overwriting your changes)
- Jupyter kernels cache imports - remind user to restart kernel after sync (autoreload helps but doesn't catch everything)

## Verification Steps
After making changes to main repo:
```bash
# 1. Check file sizes differ (quick sanity check)
ls -la notebooks/2_Cycle_Processing.ipynb
ls -la /path/to/project/notebooks/2_Cycle_Processing.ipynb

# 2. Verify checksums match after sync
md5sum notebooks/2_Cycle_Processing.ipynb
md5sum /path/to/project/notebooks/2_Cycle_Processing.ipynb

# 3. Spot-check specific cell content
python -c "
import json
with open('path/to/notebook.ipynb') as f:
    nb = json.load(f)
cell = nb['cells'][15]  # Check specific cell
print(f'Lines: {len(\"\".join(cell[\"source\"]).splitlines())}')
"
```

## Trigger Conditions
This skill applies when:
- Editing any file in `KINTSUGI/notebooks/` subdirectories (Kdecon, Kstitch, Kreg, Kview2, etc.)
- User mentions syncing or copying files between repos
- A fix "doesn't work" after being applied
- Working with KINTSUGI_Projects folders
- Sync reports "up to date" but expected changes aren't present
- File sizes differ between main repo and project folder

## References
- KINTSUGI CLAUDE.md development workspace section
- VS Code multi-root workspace: `kintsugi-dev.code-workspace`
- `scripts/sync_to_projects.py` - Main sync script with checksum logic
