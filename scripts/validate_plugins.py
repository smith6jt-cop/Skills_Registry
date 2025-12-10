#!/usr/bin/env python3
"""
Validate plugin structure and required fields in the Skills Registry.
"""

import json
import sys
from pathlib import Path


def validate_plugin(plugin_dir: Path) -> list[str]:
    """Validate a single plugin directory. Returns list of errors."""
    errors = []

    # Check for .claude-plugin directory
    claude_plugin_dir = plugin_dir / ".claude-plugin"
    if not claude_plugin_dir.is_dir():
        errors.append(f"Missing .claude-plugin directory in {plugin_dir}")
        return errors

    # Check for plugin.json
    plugin_json_path = claude_plugin_dir / "plugin.json"
    if not plugin_json_path.is_file():
        errors.append(f"Missing plugin.json in {claude_plugin_dir}")
        return errors

    # Validate plugin.json content
    try:
        with open(plugin_json_path, "r", encoding="utf-8") as f:
            plugin_data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in {plugin_json_path}: {e}")
        return errors

    # Check required fields
    required_fields = ["name", "description", "skills"]
    for field in required_fields:
        if field not in plugin_data:
            errors.append(f"Missing required field '{field}' in {plugin_json_path}")

    # Check that skills directory exists
    skills_path = plugin_data.get("skills", "./skills")
    skills_dir = plugin_dir / skills_path.lstrip("./")
    if not skills_dir.is_dir():
        errors.append(f"Skills directory not found: {skills_dir}")
    else:
        # Check for at least one SKILL.md file
        skill_files = list(skills_dir.rglob("SKILL.md"))
        if not skill_files:
            errors.append(f"No SKILL.md files found in {skills_dir}")

    return errors


def main():
    """Main validation function."""
    plugins_dir = Path(__file__).parent.parent / "plugins"

    if not plugins_dir.is_dir():
        print("No plugins directory found")
        sys.exit(0)

    all_errors = []
    plugins_found = 0

    # Find all plugin directories (any directory containing .claude-plugin)
    for category_dir in plugins_dir.iterdir():
        if not category_dir.is_dir():
            continue

        for plugin_dir in category_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            if (plugin_dir / ".claude-plugin").is_dir():
                plugins_found += 1
                errors = validate_plugin(plugin_dir)

                if errors:
                    all_errors.extend(errors)
                    print(f"FAIL {plugin_dir.name}")
                    for error in errors:
                        print(f"  - {error}")
                else:
                    print(f"OK {plugin_dir.name}")

    print(f"\nValidated {plugins_found} plugins")

    if all_errors:
        print(f"\n{len(all_errors)} error(s) found")
        sys.exit(1)
    else:
        print("All plugins valid!")
        sys.exit(0)


if __name__ == "__main__":
    main()
