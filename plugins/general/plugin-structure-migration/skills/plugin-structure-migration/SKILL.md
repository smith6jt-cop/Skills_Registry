---
name: plugin-structure-migration
description: "Migrate improperly structured plugins to correct .claude-plugin/ layout"
author: KINTSUGI Team
date: 2026-03-26
---

# plugin-structure-migration - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-03-26 |
| **Goal** | Fix 38 improperly structured Skills Registry plugins that fail CI validation |
| **Environment** | Skills_Registry submodule, Python 3.10+, GitHub Actions CI |
| **Status** | Success |

## Context
Over time, 38 plugins were created with `plugin.json` at the root level instead of inside `.claude-plugin/`. Some also had `SKILL.md` at root instead of `skills/{name}/SKILL.md`. The `"skills"` field in many `plugin.json` files was an array (e.g., `["skill-name"]`) instead of a string path (`"./skills"`). The CI validation script (`validate_plugins.py`) also had a bug where it called `.lstrip("./")` on the `"skills"` field without checking if it was an array, causing `AttributeError`.

## Verified Workflow

### Step 1: Fix the validation script
Handle `"skills"` as either string or array in `validate_plugins.py`:

```python
skills_field = plugin_data.get("skills", "./skills")
if isinstance(skills_field, str):
    skills_path = skills_field
else:
    skills_path = "./skills"
skills_dir = plugin_dir / skills_path.lstrip("./")
```

### Step 2: Run the migration script
```bash
# Preview changes
python3 scripts/fix_plugin_structure.py --dry-run

# Apply changes
python3 scripts/fix_plugin_structure.py
```

The script handles 4 structural issues:
1. **Root-level plugin.json** → moves to `.claude-plugin/plugin.json`
2. **Root-level SKILL.md** → moves to `skills/{name}/SKILL.md`
3. **Array "skills" field** → converts to string `"./skills"`
4. **Missing plugin.json** → generates minimal one from directory name

### Step 3: Fix remaining validation errors
Some moved `plugin.json` files were missing the `"skills"` field entirely:

```python
import json
from pathlib import Path

failing = ['trading/symbol-database-selection', ...]
for p in failing:
    path = Path('plugins') / p / '.claude-plugin' / 'plugin.json'
    with open(path) as f:
        data = json.load(f)
    if 'skills' not in data:
        data['skills'] = './skills'
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
```

### Step 4: Validate
```bash
python3 scripts/validate_plugins.py
# Expected: "Validated 157 plugins — All plugins valid!"
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Manual fix per plugin | 38 plugins × 3 fixes each = too many manual edits | Write a migration script for bulk structural changes |
| Migration script without dry-run | Couldn't verify actions before applying | Always add `--dry-run` mode to migration scripts |
| Fixing validation script only | Plugins still had wrong structure, just weren't detected | Fix both the validator AND the data it validates |
| Moving files without fixing "skills" field | Array format still caused issues in generate_marketplace.py | Fix data format (array→string) at the same time as file moves |
| Not checking for missing fields after move | 7 plugins had no "skills" field at all in their JSON | Run validation after migration to catch edge cases |

## Final Parameters

Correct plugin structure:
```
plugins/{category}/{skill-name}/
├── .claude-plugin/
│   └── plugin.json       # Must have: name, description, skills, version, author
└── skills/
    └── {skill-name}/
        └── SKILL.md       # Frontmatter + experiment sections
```

Required `plugin.json` fields:
```json
{
  "name": "skill-name",
  "version": "1.0.0",
  "description": "Trigger conditions: (1) ..., (2) ...",
  "author": {"name": "Team Name"},
  "skills": "./skills"
}
```

## Key Insights
- The `"skills"` field must be a string path, not an array — the validator and marketplace generator both call `.lstrip()` on it
- Generated `plugin.json` from directory name is a reasonable fallback for skills with only `SKILL.md`
- Git correctly detects file moves (root → `.claude-plugin/`) as renames when staged together
- Branch divergence in submodules is common — rebase before committing fixes to avoid merge conflicts
- Always run `validate_plugins.py` after any structural changes to catch edge cases

## References
- `scripts/fix_plugin_structure.py` — bulk migration script
- `scripts/validate_plugins.py` — CI validation script
- `.github/workflows/validate.yml` — CI workflow that runs validation on push/PR
