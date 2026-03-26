#!/usr/bin/env python3
"""
Migrate improperly structured skills to the correct layout.

Correct structure:
    skill-name/
    ├── .claude-plugin/
    │   └── plugin.json
    └── skills/
        └── skill-name/
            └── SKILL.md

This script handles:
1. plugin.json at root → move to .claude-plugin/plugin.json
2. SKILL.md at root → move to skills/skill-name/SKILL.md
3. Missing plugin.json → generate from SKILL.md metadata
"""

import json
import shutil
from pathlib import Path


def fix_plugin(plugin_dir: Path, dry_run: bool = False) -> list[str]:
    """Fix a single plugin directory structure. Returns list of actions taken."""
    actions = []
    name = plugin_dir.name
    claude_dir = plugin_dir / ".claude-plugin"
    correct_json = claude_dir / "plugin.json"
    root_json = plugin_dir / "plugin.json"

    # Step 1: Ensure .claude-plugin/ exists
    if not claude_dir.is_dir():
        actions.append(f"  CREATE .claude-plugin/")
        if not dry_run:
            claude_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Move or create plugin.json
    if root_json.is_file() and not correct_json.is_file():
        actions.append(f"  MOVE plugin.json → .claude-plugin/plugin.json")
        if not dry_run:
            claude_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root_json), str(correct_json))
    elif not correct_json.is_file() and not root_json.is_file():
        # Generate minimal plugin.json from directory name
        plugin_data = {
            "name": name,
            "version": "1.0.0",
            "description": f"{name.replace('-', ' ').title()} skill",
            "author": {"name": "KINTSUGI Team"},
            "skills": "./skills",
        }
        actions.append(f"  GENERATE .claude-plugin/plugin.json (from name)")
        if not dry_run:
            claude_dir.mkdir(parents=True, exist_ok=True)
            with open(correct_json, "w", encoding="utf-8") as f:
                json.dump(plugin_data, f, indent=2)
                f.write("\n")

    # Step 3: Fix "skills" field format in plugin.json (array → string)
    # Check whichever file exists (correct location after move, or root for dry-run)
    target = correct_json if correct_json.is_file() else root_json
    if target.is_file():
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("skills"), list):
            actions.append(f"  FIX skills field: array → \"./skills\"")
            if not dry_run:
                data["skills"] = "./skills"
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")

    # Step 4: Ensure skills/ directory exists with SKILL.md in correct location
    skills_dir = plugin_dir / "skills" / name
    root_skill_md = plugin_dir / "SKILL.md"

    if root_skill_md.is_file() and not skills_dir.is_dir():
        actions.append(f"  MOVE SKILL.md → skills/{name}/SKILL.md")
        if not dry_run:
            skills_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root_skill_md), str(skills_dir / "SKILL.md"))
    elif not skills_dir.is_dir():
        # Check if skills/ exists with SKILL.md in a subdirectory already
        existing_skills = list((plugin_dir / "skills").rglob("SKILL.md")) if (plugin_dir / "skills").is_dir() else []
        if not existing_skills:
            actions.append(f"  WARNING: No SKILL.md found anywhere in {name}")

    return actions


def main():
    import sys

    dry_run = "--dry-run" in sys.argv
    plugins_dir = Path(__file__).parent.parent / "plugins"

    if not plugins_dir.is_dir():
        print("No plugins directory found")
        return

    total_fixed = 0
    total_actions = 0

    for category_dir in sorted(plugins_dir.iterdir()):
        if not category_dir.is_dir():
            continue

        for plugin_dir in sorted(category_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue

            # Check if this plugin needs fixing
            has_correct = (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
            has_root_json = (plugin_dir / "plugin.json").is_file()
            has_root_skill = (plugin_dir / "SKILL.md").is_file()
            has_skills_subdir = (plugin_dir / "skills").is_dir()

            needs_fix = (
                (has_root_json and not has_correct)
                or has_root_skill
                or (not has_correct and not has_root_json and has_skills_subdir)
            )

            if needs_fix:
                actions = fix_plugin(plugin_dir, dry_run=dry_run)
                if actions:
                    total_fixed += 1
                    total_actions += len(actions)
                    print(f"{'[DRY RUN] ' if dry_run else ''}FIX {category_dir.name}/{plugin_dir.name}")
                    for action in actions:
                        print(action)

    mode = "would fix" if dry_run else "fixed"
    print(f"\n{mode.capitalize()} {total_fixed} plugins ({total_actions} actions)")
    if dry_run:
        print("Run without --dry-run to apply changes")


if __name__ == "__main__":
    main()
