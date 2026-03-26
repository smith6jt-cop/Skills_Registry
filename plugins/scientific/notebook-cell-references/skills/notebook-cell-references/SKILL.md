# Notebook Cell References

## Goal
Communicate clearly about Jupyter notebook cells without confusing the user.

## What Failed
- Referring to cells by number (e.g., "Cell 9", "Cell 12")
- Cell numbers are NOT visible in Jupyter notebooks
- Cell numbers change when cells are added/deleted
- User has no way to know which cell you mean

## What Works
Refer to cells by identifiable characteristics:

1. **Section header**: "the cell under '## Load Data'"
2. **First line of code**: "the cell starting with `sc.read_h5ad(...)`"
3. **Purpose**: "the normalization cell", "the plotting cell"
4. **Variable defined**: "the cell that creates `protein_shared`"
5. **Function defined**: "the cell with `def detection_aware_normalize`"

## Examples

### Bad
- "Update Cell 9"
- "The error is in Cell 12"
- "Cells 10-12 need changes"

### Good
- "Update the normalization cell (starts with `# Normalize shared features`)"
- "The error is in the visualization cell that plots histograms"
- "The cells between 'Load Data' and 'Run Integration' need changes"

## Trigger
When discussing or modifying Jupyter notebook cells.
