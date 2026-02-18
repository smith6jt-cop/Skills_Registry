---
name: repo-project-sync-workflow
description: "When editing KINTSUGI notebook modules (Kdecon, Kstitch, Kreg, etc.), always edit the main repo first then sync to project folders"
author: Claude Code
date: 2025-12-17
updated: 2026-02-18
---

# KINTSUGI Repository-to-Project Sync Workflow

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2025-12-17 (updated 2026-02-18) |
| **Goal** | Establish correct workflow for editing shared notebook modules |
| **Environment** | KINTSUGI multi-project setup with shared codebase |
| **Status** | Success |

## Context
KINTSUGI uses a shared codebase model where:
- **Main repo**: `/blue/maigan/smith6jt/KINTSUGI/` contains the source code
- **Project folders**: `/blue/maigan/smith6jt/KINTSUGI_Projects/.../notebooks/` contain working copies

Project folders sync FROM the main repo. If you edit a project folder directly, those changes will be **overwritten** when the user syncs from the main repo.

## Verified Workflow

### CORRECT: Edit Main Repo First
```bash
# 1. Make edits to the main repo
/blue/maigan/smith6jt/KINTSUGI/notebooks/Kdecon/deconvolution.py

# 2. Commit triggers auto-sync via post-commit hook
git commit -m "fix: update deconvolution"
# -> scripts/sync_to_projects.py auto-discovers and syncs ALL 33 projects

# 3. Manual sync (if needed outside of git commit)
python scripts/sync_to_projects.py          # sync changed files
python scripts/sync_to_projects.py --force  # force sync all files
python scripts/sync_to_projects.py --dry-run  # preview changes
```

### Key Paths
| Component | Main Repo Path | Project Folder Path |
|-----------|---------------|---------------------|
| KDecon | `KINTSUGI/notebooks/Kdecon/` | `KINTSUGI_Projects/.../notebooks/Kdecon/` |
| Kstitch | `KINTSUGI/notebooks/Kstitch/` | `KINTSUGI_Projects/.../notebooks/Kstitch/` |
| Kreg | `KINTSUGI/notebooks/Kreg/` | `KINTSUGI_Projects/.../notebooks/Kreg/` |
| Kview2 | `KINTSUGI/notebooks/Kview2/` | `KINTSUGI_Projects/.../notebooks/Kview2/` |
| src/kintsugi | `KINTSUGI/src/kintsugi/` | N/A (installed package) |

## Auto-Discovery Mechanism (Feb 2026)

Prior to Feb 18, 2026, `sync_to_projects.py` used a hardcoded `DEFAULT_PROJECT_FOLDERS` list containing only 2 projects. As batch processing scaled to 31+ datasets under `KINTSUGI_Projects/`, new projects were never synced. This caused CX_19-001_SP_CC2-A28 to run with 2-month-old Kreg code, crashing registration.

### How It Works Now
- `_BATCH_PROJECT_GLOB = "/blue/maigan/smith6jt/KINTSUGI_Projects/*/notebooks"` discovers all batch project notebooks directories at import time
- `_discover_default_project_folders()` builds the full project list: 2 static entries + all glob matches
- Discovered **33 total projects** (2 static + 31 batch) as of Feb 2026
- Post-commit hook calls `sync_to_projects.py` automatically on every commit
- First run after the change (commit `1f0bc2b`) auto-synced **338 files** to all 33 projects

### Key Implementation Details
- Discovery happens at **import time** (module-level), not per-invocation
- Uses MD5 checksum comparison to skip unchanged files (efficient for 33 projects)
- New batch projects added to `KINTSUGI_Projects/` are automatically included on next sync
- No manual `DEFAULT_PROJECT_FOLDERS` updates are ever needed again

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Editing project folder first | User synced from main repo, overwriting all changes | Always edit main repo first |
| Copying project->main after edit | Creates confusion about source of truth | Main repo is ALWAYS the source |
| Hardcoded DEFAULT_PROJECT_FOLDERS (2 projects) | New batch projects never synced | CX_19-001 had 2-month-old Kreg code, registration crashed. Auto-discovery via glob is the fix |

## What Worked
- **Auto-discovery via glob** ensures new batch projects are automatically included without code changes
- **Post-commit hook** makes sync automatic -- no manual step to forget
- **MD5 checksum comparison** makes syncing 33 projects efficient (only copies changed files)
- **Single source of truth** pattern: main repo is always canonical, project folders are copies

## Key Insights
- The main repo (`/blue/maigan/smith6jt/KINTSUGI/`) is the **single source of truth**
- Project folders are working copies that get synced FROM main repo
- After editing main repo, the post-commit hook auto-syncs to all discovered projects
- When user reports a fix "didn't work", check if they synced (overwriting your changes)
- Jupyter kernels cache imports but **autoreload is enabled** -- just re-run the cell, no kernel restart needed
- If a project has stale code, run `python scripts/sync_to_projects.py --force` to force-refresh all files

## Trigger Conditions
This skill applies when:
- Editing any file in `KINTSUGI/notebooks/` subdirectories (Kdecon, Kstitch, Kreg, Kview2, etc.)
- User mentions syncing or copying files between repos
- A fix "doesn't work" after being applied
- Working with KINTSUGI_Projects folders

## References
- KINTSUGI CLAUDE.md development workspace section
- VS Code multi-root workspace: `kintsugi-dev.code-workspace`
