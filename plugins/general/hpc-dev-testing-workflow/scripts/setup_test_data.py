#!/usr/bin/env python3
"""
Setup test data for KINTSUGI development.

Copies center 4 tiles from a full project to create a minimal 2x2 test dataset.
Tiles are renumbered to form a proper 2x2 snake-pattern grid.

For a 13x9 grid, center tiles are:
- Row 4, Col 5: tile 58 → new tile 1
- Row 4, Col 6: tile 59 → new tile 2
- Row 5, Col 6: tile 72 → new tile 4 (snake pattern)
- Row 5, Col 5: tile 73 → new tile 3 (snake pattern)
"""

import shutil
import re
from pathlib import Path
from tqdm import tqdm

# Configuration
SOURCE_PROJECT = Path("/blue/maigan/smith6jt/KINTSUGI_Projects/CODEX_SP_LN/1904CC1-1L")
DEST_PROJECT = Path("/blue/maigan/smith6jt/KINTSUGI/test_data/mini_project")

# Cycles to copy (first 3)
CYCLES = ["cyc001", "cyc002", "cyc003"]

# Tile mapping: old_tile_number -> new_tile_number
# For 13x9 grid, center 2x2 tiles with snake pattern
TILE_MAPPING = {
    58: 1,  # Row 4, Col 5 → position (0,0)
    59: 2,  # Row 4, Col 6 → position (0,1)
    73: 3,  # Row 5, Col 5 → position (1,0) - snake reverses
    72: 4,  # Row 5, Col 6 → position (1,1) - snake reverses
}

def rename_tile(filename: str, old_tile: int, new_tile: int) -> str:
    """Rename tile number in filename."""
    # Pattern: 1_XXXXX_Z0ZZ_CHC.tif where XXXXX is 5-digit tile number
    old_str = f"1_{old_tile:05d}_"
    new_str = f"1_{new_tile:05d}_"
    return filename.replace(old_str, new_str)


def copy_cycle(cycle_name: str):
    """Copy tiles for a single cycle."""
    source_dir = SOURCE_PROJECT / "data" / "raw" / cycle_name
    dest_dir = DEST_PROJECT / "data" / "raw" / cycle_name

    if not source_dir.exists():
        print(f"Warning: Source cycle not found: {source_dir}")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for old_tile, new_tile in TILE_MAPPING.items():
        # Find all files for this tile (all z-planes and channels)
        pattern = f"1_{old_tile:05d}_*.tif"
        tile_files = list(source_dir.glob(pattern))

        for src_file in tile_files:
            new_name = rename_tile(src_file.name, old_tile, new_tile)
            dest_file = dest_dir / new_name

            if not dest_file.exists():
                shutil.copy2(src_file, dest_file)
                copied += 1

    return copied


def copy_metadata():
    """Copy metadata files if they exist."""
    source_meta = SOURCE_PROJECT / "meta"
    dest_meta = DEST_PROJECT / "meta"

    dest_meta.mkdir(parents=True, exist_ok=True)

    # Copy channel names file if exists
    for fname in ["CHANNELNAMES.txt", "channelnames.txt", "channel_names.txt"]:
        src = source_meta / fname
        if src.exists():
            shutil.copy2(src, dest_meta / fname)
            print(f"Copied: {fname}")
            break


def main():
    print("=" * 60)
    print("KINTSUGI Test Data Setup")
    print("=" * 60)
    print(f"Source: {SOURCE_PROJECT}")
    print(f"Destination: {DEST_PROJECT}")
    print(f"Cycles: {CYCLES}")
    print(f"Tiles: {list(TILE_MAPPING.keys())} → {list(TILE_MAPPING.values())}")
    print("=" * 60)

    # Create destination structure
    DEST_PROJECT.mkdir(parents=True, exist_ok=True)

    # Copy cycles
    total_copied = 0
    for cycle in tqdm(CYCLES, desc="Copying cycles"):
        copied = copy_cycle(cycle)
        total_copied += copied
        print(f"  {cycle}: {copied} files")

    # Copy metadata
    print("\nCopying metadata...")
    copy_metadata()

    print(f"\nTotal files copied: {total_copied}")
    print(f"\nTest dataset ready at: {DEST_PROJECT}")
    print("\nTest grid configuration:")
    print("  Rows: 2")
    print("  Columns: 2")
    print("  Overlap: 30%")
    print("  Pattern: Snake by rows")

    # Create a README
    readme = DEST_PROJECT / "README.md"
    readme.write_text(f"""# KINTSUGI Mini Test Project

Minimal test dataset for development and testing.

## Configuration

| Parameter | Value |
|-----------|-------|
| Grid size | 2×2 (4 tiles) |
| Cycles | {len(CYCLES)} |
| Channels | 4 per cycle |
| Z-planes | 13 per tile |
| Overlap | ~30% |
| Pattern | Snake by rows |

## Source

Extracted from: `{SOURCE_PROJECT.name}`

Original tiles (center of 13×9 grid):
- Tile 58 → 1 (row 4, col 5)
- Tile 59 → 2 (row 4, col 6)
- Tile 73 → 3 (row 5, col 5)
- Tile 72 → 4 (row 5, col 6)

## Usage

```python
# In notebook, set project path:
PROJECT_DIR = Path("{DEST_PROJECT}")

# Grid parameters for this test set:
n = 2  # rows
m = 2  # columns
overlap_percentage = 30
```

## Regenerate

```bash
python test_data/setup_test_data.py
```
""")

    print(f"Created: {readme}")


if __name__ == "__main__":
    main()
