---
name: claude-md-context-management
description: "Split oversized CLAUDE.md into subdirectory files. Trigger: CLAUDE.md too large, context window, documentation splitting."
author: KINTSUGI Team
date: 2026-02-21
---

# CLAUDE.md Context Management

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-21 |
| **Goal** | Keep root CLAUDE.md under 40k chars while preserving all documentation |
| **Environment** | Claude Code with auto-loaded CLAUDE.md files per subdirectory |
| **Status** | Success |

## Context

Root `CLAUDE.md` grew to 40,952 chars — just over the 40k limit. Claude Code auto-loads `CLAUDE.md` files when working on files in a directory, so feature-specific docs can live near the code they describe. The challenge is splitting without losing discoverability or creating broken cross-references.

## Verified Workflow

### 1. Identify what to move

Categorize each section as either "always needed" (keep in root) or "feature-specific" (move to subdirectory):

**Keep in root** (essential context for any task):
- Project overview, architecture, build commands
- CLI patterns, testing, code style, dependencies
- Critical fixes table (short, high-impact)
- Key patterns, release/versioning

**Move to subdirectory** (only needed when working on that feature):
- Registration details → `workflow/CLAUDE.md`
- Signal isolation → `src/kintsugi/signal/CLAUDE.md`
- KRONOS/vessel3d/cleanup → `src/kintsugi/CLAUDE.md`

### 2. Check for existing subdirectory docs

Before creating new files, check if content already exists in subdirectory CLAUDE.md files. Avoid duplication — replace the root section with a pointer instead of creating a new file.

### 3. Create subdirectory CLAUDE.md files

Each file should include:
- A "See also" header with back-references to related docs
- Content moved verbatim (adjust relative paths)
- No duplication with root or peer files

### 4. Replace root sections with pointers

Replace verbose sections with 2-line pointers:
```markdown
## Registration

See `workflow/CLAUDE.md` for comprehensive registration documentation: ...
```

### 5. Add a "Subdirectory Documentation" section to root

```markdown
## Subdirectory Documentation

Feature-specific documentation lives in CLAUDE.md files near the code:
- `src/kintsugi/CLAUDE.md` — KRONOS, vessel3d, cleanup
- `src/kintsugi/signal/CLAUDE.md` — Weighted AF, batch signal isolation
- `workflow/CLAUDE.md` — Snakemake, registration, batch processing
- `notebooks/CLAUDE.md` — Jupyter autoreload, Notebook 4
```

### 6. Verify

```bash
wc -c CLAUDE.md                          # Should be well under 40k
wc -c src/kintsugi/CLAUDE.md             # Each under 40k
wc -c src/kintsugi/signal/CLAUDE.md
```

Check cross-references with grep for any section names that were removed.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Moving ALL feature docs out of root | Root became too sparse — no context for common tasks | Keep architecture overview, critical fixes, and build commands in root |
| Creating one giant `docs/CLAUDE.md` | Claude Code only auto-loads CLAUDE.md in the directory you're working in | Files must be in the subdirectory where the code lives |
| Duplicating content in root + subdirectory | Stale content diverges over time | Root should have pointers only, never duplicated details |
| Moving content without back-references | Subdirectory files become orphaned — hard to discover | Every subdirectory CLAUDE.md needs a "See also" header |

## Final Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Root CLAUDE.md target | < 25k chars | Well under 40k limit with room to grow |
| Pointer format | 2-line section (heading + "See X for Y") | Minimal but discoverable |
| Back-reference format | "See also:" header in each subdirectory file | Consistent navigation pattern |
| File placement | Same directory as the code it documents | Claude Code auto-loads based on working directory |

## Key Insights

- Claude Code auto-loads `CLAUDE.md` files from the directory tree you're working in — this is the key mechanism that makes splitting work
- The "Subdirectory Documentation" pointer section in root acts as an index — always keep this updated
- Relative paths in subdirectory files (e.g., `../../workflow/CLAUDE.md`) are for human readers; Claude Code finds CLAUDE.md files by directory traversal
- Content that's referenced across many features (architecture, dependencies, testing) should stay in root — it's always loaded
- Registration was already documented in both root and `workflow/CLAUDE.md` — removing the root copy eliminated 65 lines of duplication with zero information loss

## Results

| File | Before | After |
|------|--------|-------|
| Root `CLAUDE.md` | 40,952 chars | 21,042 chars (49% reduction) |
| `src/kintsugi/CLAUDE.md` | (new) | 8,265 chars |
| `src/kintsugi/signal/CLAUDE.md` | (new) | 4,908 chars |
| `workflow/CLAUDE.md` | 24,158 chars | unchanged |
| `notebooks/CLAUDE.md` | 3,983 chars | unchanged |

## References

- Claude Code documentation on CLAUDE.md auto-loading behavior
- KINTSUGI commit `9bc9e0f`: "docs: split CLAUDE.md into subdirectory files to stay under 40k char limit"
