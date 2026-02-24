---
name: mcp-absolute-path-config
description: "Fix MCP server 'Executable not found' by resolving absolute paths in .mcp.json"
author: KINTSUGI Team
date: 2026-02-24
---

# MCP Absolute Path Configuration

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-24 |
| **Goal** | Fix "Executable not found in $PATH: kintsugi" when Claude Code starts MCP server |
| **Environment** | HPC login node (no conda env activated), Claude Code CLI, KINTSUGI conda env |
| **Status** | Success |

## Context
Claude Code failed to start the KINTSUGI MCP server because the config used a bare command name (`"command": "kintsugi"`) which isn't on PATH when the conda env isn't activated (typical for HPC login nodes, VS Code terminals, etc.).

Additionally, the old code incorrectly put `mcpServers` in `.claude/settings.local.json` — that field is not recognized there. MCP server definitions belong in `.mcp.json` at the project root.

## Verified Workflow

### 1. Helper function resolves absolute path

```python
# src/kintsugi/project.py
def _resolve_kintsugi_executable() -> str:
    """Resolve absolute path to the kintsugi CLI executable."""
    import shutil
    import sys
    from pathlib import Path

    path = shutil.which("kintsugi")
    if path:
        return str(Path(path).resolve())

    candidate = Path(sys.executable).parent / "kintsugi"
    if candidate.exists():
        return str(candidate.resolve())

    return "kintsugi"
```

### 2. MCP config goes in `.mcp.json` (NOT `settings.local.json`)

```json
// .mcp.json (project root)
{
  "mcpServers": {
    "kintsugi": {
      "command": "/blue/maigan/smith6jt/miniforge3/envs/KINTSUGI/bin/kintsugi",
      "args": ["mcp", "start"],
      "cwd": "/blue/maigan/smith6jt/KINTSUGI"
    }
  }
}
```

### 3. Settings file enables the server

```json
// .claude/settings.local.json
{
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["kintsugi"]
}
```

### 4. CLI commands create both files

```bash
kintsugi mcp config /path/to/project   # Creates .mcp.json + settings.local.json
kintsugi init /path/to/project          # Also creates both files
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `"command": "kintsugi"` (bare name) | Not on PATH when conda env isn't activated | Always use absolute path via `_resolve_kintsugi_executable()` |
| Put `mcpServers` in `settings.local.json` | Schema validation error: "Unrecognized field: mcpServers" | MCP servers go in `.mcp.json` at project root |
| `enabledMcpjsonServers` without `.mcp.json` | References nonexistent file, server never loads | Must create `.mcp.json` that the setting references |

## Final Parameters

```python
# Resolution order for executable path:
# 1. shutil.which("kintsugi") — works if env is activated
# 2. Path(sys.executable).parent / "kintsugi" — same conda env, no PATH needed
# 3. "kintsugi" — bare name fallback (may fail)
```

## Key Insights
- `.claude/settings.local.json` does NOT support `mcpServers` — it only supports `enabledMcpjsonServers` (list of server names from `.mcp.json`)
- `sys.executable` sibling trick works because pip-installed entry points live next to the Python interpreter in the same conda env's `bin/` directory
- The `.mcp.json` file is checked into version control for team sharing; `settings.local.json` is typically local
- Claude Code prompts for approval before using project-scoped MCP servers from `.mcp.json`

## References
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- Claude Code settings schema: `mcpServers` only valid in `.mcp.json`, `~/.claude.json`, or `managed-mcp.json`
