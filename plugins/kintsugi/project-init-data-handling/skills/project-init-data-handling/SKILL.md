---
name: project-init-data-handling
description: "KINTSUGI project initialization differentiates raw vs processed data and handles --slurm on existing projects"
author: Claude Code
date: 2026-02-02
---

# KINTSUGI Project Initialization Data Handling

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-02 |
| **Goal** | Improve init command to intelligently handle existing data and add SLURM to existing projects |
| **Environment** | KINTSUGI CLI (src/kintsugi/cli.py, src/kintsugi/project.py) |
| **Status** | Success |

## Context
The `kintsugi init` command needs to handle multiple scenarios:
- New empty directories
- Directories with raw data in `data/raw/`
- Directories with processed data in `data/processed/`
- Existing projects that need SLURM added

Previously, the command treated all data the same and the "Adopt" option didn't make sense for the workflow.

## Verified Behavior

### Data Detection
The `scan_existing_data()` function now tracks raw vs processed data separately:

```python
# ExistingDataReport fields
has_raw_data: bool
raw_image_count: int
raw_size_mb: float
raw_cycle_folders: list[str]

has_processed_data: bool
processed_stages: dict[str, int]  # stage_name -> file_count
processed_size_mb: float
```

### Init Options by Scenario

| Scenario | Options | Default |
|----------|---------|---------|
| Raw data only | Continue, Cancel | Continue |
| Processed data exists | Delete processed, Keep processed, Cancel | Keep |
| Existing project + --slurm | Auto-adds SLURM if not configured | - |
| Existing project (no --slurm) | Shows status, suggests --force | - |

### Adding SLURM to Existing Project
Both methods work:
```bash
kintsugi init /path/to/project --slurm    # Detects existing, adds SLURM only
kintsugi slurm init /path/to/project      # Explicit command
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| "Adopt" option for moving data to raw/ | Raw data stays in raw folder; processed never moves to raw | Remove option - didn't match workflow |
| --slurm on existing project (before fix) | `KintsugiProject.create()` just loaded existing project, skipped SLURM | Added early detection of existing project + SLURM request |
| Single data category for all files | Couldn't distinguish raw cycles from processed stages | Track raw and processed separately |

## Key Insights
- Raw data in `data/raw/` should stay there; no "adoption" needed
- Processed data may need to be deleted when reprocessing from scratch
- When a project exists with `kintsugi_project.json`, the CLI should handle `--slurm` specially
- The `kintsugi scan` command provides preview of what init will detect

## Key Files Modified
- `src/kintsugi/project.py`: `ExistingDataReport`, `scan_existing_data()`
- `src/kintsugi/cli.py`: `init()` command, `scan()` command

## Trigger Conditions
This skill applies when:
- User runs `kintsugi init` on directory with existing data
- User runs `kintsugi init --slurm` on existing project without SLURM
- User asks about raw vs processed data handling in KINTSUGI
- Debugging why SLURM wasn't created on init

## References
- KINTSUGI CLAUDE.md "Project Initialization Behavior" section
- `kintsugi init --help`
- `kintsugi scan --help`
