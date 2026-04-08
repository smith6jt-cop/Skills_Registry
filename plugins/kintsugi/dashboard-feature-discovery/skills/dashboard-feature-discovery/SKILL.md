---
name: dashboard-feature-discovery
description: "Surface a shipped-but-undocumented CLI feature in user-facing docs. Trigger: user reports a known feature missing from README/readthedocs even though the CLI command exists."
author: KINTSUGI Team
date: 2026-04-08
---

# Surfacing Shipped-But-Undocumented CLI Features

## Experiment Overview

| Item | Details |
|------|---------|
| **Date** | 2026-04-08 |
| **Goal** | Document the `kintsugi workflow status` / `workflow run --dashboard` progress dashboard in README + readthedocs after the user reported it missing |
| **Environment** | KINTSUGI repo, `src/kintsugi/dashboard.py`, `src/kintsugi/cli.py`, `docs/cli.md`, `README.md` |
| **Status** | Success |

## Context

The user said "There was a feature to display a dashboard of project processing progress. I don't see it in the repo README or the readthedocs.io."

`/advise` against `Skills_Registry/plugins/kintsugi/` returned 0 hits for "dashboard". A direct `Grep dashboard` against the repo returned **5** matches:

- `src/kintsugi/dashboard.py` — 1200+ line module with `scan_project_progress`, `render_dashboard`, `watch_dashboard`, `estimate_completion`
- `src/kintsugi/cli.py` — `@workflow.command("status")` plus `--dashboard` flag on `workflow run`
- `tests/test_dashboard.py` — full test coverage
- `CLAUDE.md` — agent-facing docs mention both entry points

`README.md` and `docs/` returned **0** matches. The feature shipped, was tested, and was documented for Claude — but never advertised to humans. This is a recurring failure mode: a developer adds a CLI command, updates `CLAUDE.md` so the AI assistant knows about it, and forgets the user-facing surfaces.

## Verified Workflow

### 1. Confirm the feature actually exists

Before assuming it was deleted or renamed, grep for the feature name across the *whole* repo (not just docs):

```bash
# Search code, tests, AND docs
Grep "dashboard|workflow_status" --output_mode files_with_matches
```

If matches appear only in `src/`, `tests/`, and `CLAUDE.md` but not `README.md` / `docs/`, you have a documentation gap, not a missing feature.

### 2. Read the implementation to extract the public surface

Open the CLI command definition and the underlying module to enumerate:

- All flags and their defaults
- All entry points (e.g., standalone `workflow status` AND embedded `workflow run --dashboard`)
- What each section of the rendered output actually shows
- Which functions are the public API (so docs can name them for code spelunkers)

For the KINTSUGI dashboard:

| Surface | Where |
|---------|-------|
| Standalone CLI | `kintsugi workflow status` (`cli.py` `workflow_status`) |
| Embedded CLI | `kintsugi workflow run --dashboard` (`cli.py` `_run_with_dashboard`) |
| Public API | `scan_project_progress`, `render_dashboard`, `watch_dashboard`, `estimate_completion` in `dashboard.py` |
| Flags | `--watch/-w`, `--interval/-i`, `--all-projects`, `--json`, `--no-hardware`, `--no-estimates`, `--no-jobs` |

### 3. Match the existing docs style — do not invent a new format

Read a peer doc (e.g., `docs/cli.md` for a sibling command, `README.md` for the section conventions) and mirror:

- Heading depth
- Code-block flags
- Whether examples use `/path/to/project` or `.`
- Whether tables describe flags or prose does
- Where the section sits in the table of contents

For KINTSUGI: `docs/cli.md` already had `### kintsugi workflow run` with a code block — the new `### kintsugi workflow status` slots in immediately after, mirroring the same shape. README's `## HPC/SLURM Job Submission` has a flat list of subsections — add `### Progress Dashboard` between "Snakemake Workflow" and "Monitoring and Logs".

### 4. Update the README in TWO places

A README update isn't done until both:

- The **Table of Contents** has the new anchor
- The new section exists at the right heading level

Forgetting the TOC entry leaves the section unreachable from the top of the README.

### 5. Write a retrospective skill

The whole reason this happened is that nobody documented the rule "user-facing CLI commands must land in README + docs/, not just CLAUDE.md." Save it as a skill so `/advise` finds it next time.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Searching only `docs/` for "dashboard" | Returned 0 hits; could have falsely concluded the feature was deleted | Always grep the whole repo before declaring a feature missing — `src/`, `tests/`, and `CLAUDE.md` are the source of truth for "does it exist" |
| Documenting only the standalone `workflow status` command | Missed the embedded `workflow run --dashboard` entry point — users would discover only half the feature | Read `cli.py` end-to-end for all references to the feature, not just the obvious command |
| Adding a new section to README without updating the Table of Contents | Section was unreachable from the TOC anchor list at the top | A README edit isn't done until the TOC entry exists too |
| Treating CLAUDE.md as user documentation | CLAUDE.md is agent-facing context, not user-facing docs — users don't read it | User-facing CLI commands live in **README.md + docs/cli.md**; CLAUDE.md is a separate, agent-only surface |
| Inventing a new doc format for the new section | Inconsistency makes the docs feel unmaintained | Mirror the heading depth, table style, and example format of the closest peer command in the same file |

## Final Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Discovery grep scope | Whole repo (`src/`, `tests/`, `CLAUDE.md`, `README.md`, `docs/`) | Lets you distinguish "missing" from "undocumented" |
| README placement | New `### Progress Dashboard` subsection inside `## HPC/SLURM Job Submission` | Adjacent to the workflow commands users already know about |
| TOC update | Mandatory in the same edit as the section | Otherwise the section is unreachable |
| docs/ placement | New `### kintsugi workflow status` block in `docs/cli.md`, plus a `--dashboard` example added to `### kintsugi workflow run` | Both entry points need a home |
| Cross-reference | Each new section names the source files (`src/kintsugi/dashboard.py`, public function names) | Lets future maintainers find the implementation |

## Key Insights

- **A feature can ship, be tested, and be documented for the AI assistant without ever reaching users.** CLAUDE.md is agent-facing context — it does *not* count as user documentation.
- **Two entry points are easy to miss.** A `workflow run --dashboard` flag is structurally separate from a `workflow status` subcommand. Always read the CLI module end-to-end for references to the feature name.
- **Grepping `docs/` is not enough to confirm absence.** Grep the whole repo — if matches appear in `src/` and `tests/` but not `README.md`/`docs/`, you have a documentation gap, not a deleted feature.
- **README and docs are separate surfaces with different jobs.** README is the entry point for new users (short, high-signal); `docs/cli.md` is the reference (exhaustive flag list). Both need updates — neither is sufficient alone.
- **The TOC is part of the section.** A new heading without a matching TOC anchor is half-done.
- **Always retrospective the gap, not just the fix.** The next missing feature will be found the same way; saving a skill makes the discovery process repeatable.

## Results

| Surface | Before | After |
|---------|--------|-------|
| `README.md` mentions of "dashboard" | 0 | 9 (new section + TOC entry) |
| `docs/cli.md` mentions of "dashboard" | 0 | 7 (`workflow status` block + `workflow run --dashboard` example) |
| `CLAUDE.md` mentions | 5 (already documented for agent) | unchanged |
| Source/tests | `src/kintsugi/dashboard.py`, `tests/test_dashboard.py` | unchanged (already shipped) |

## References

- `src/kintsugi/dashboard.py` — `scan_project_progress`, `render_dashboard`, `watch_dashboard`, `estimate_completion`
- `src/kintsugi/cli.py:1898` — `_run_with_dashboard()` (embedded variant)
- `src/kintsugi/cli.py:2188` — `@workflow.command("status")` (standalone variant)
- `tests/test_dashboard.py` — coverage
