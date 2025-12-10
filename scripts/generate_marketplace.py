#!/usr/bin/env python3
"""
Generate marketplace.json from all plugins in the registry.
"""

import json
from datetime import datetime
from pathlib import Path


def collect_plugins(plugins_dir: Path) -> list[dict]:
    """Collect metadata from all plugins."""
    plugins = []

    if not plugins_dir.is_dir():
        return plugins

    for category_dir in plugins_dir.iterdir():
        if not category_dir.is_dir():
            continue

        category_name = category_dir.name

        for plugin_dir in category_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            plugin_json_path = plugin_dir / ".claude-plugin" / "plugin.json"
            if not plugin_json_path.is_file():
                continue

            try:
                with open(plugin_json_path, "r", encoding="utf-8") as f:
                    plugin_data = json.load(f)

                plugins.append({
                    "name": plugin_data.get("name"),
                    "version": plugin_data.get("version", "1.0.0"),
                    "description": plugin_data.get("description", ""),
                    "author": plugin_data.get("author", {}),
                    "category": category_name,
                    "path": str(plugin_dir.relative_to(plugins_dir.parent)),
                })
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not read {plugin_json_path}: {e}")

    return plugins


def main():
    """Generate marketplace.json."""
    root_dir = Path(__file__).parent.parent
    plugins_dir = root_dir / "plugins"
    marketplace_path = root_dir / "marketplace.json"

    plugins = collect_plugins(plugins_dir)

    marketplace = {
        "version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "repository": "https://github.com/smith-cop/Skills_Registry",
        "plugins": plugins,
    }

    with open(marketplace_path, "w", encoding="utf-8") as f:
        json.dump(marketplace, f, indent=2)

    print(f"Generated marketplace.json with {len(plugins)} plugins")


if __name__ == "__main__":
    main()
