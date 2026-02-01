---
name: colab-notebook-development
description: "Pattern for creating new Colab notebooks. Trigger when: (1) Creating a new notebook for experiments, (2) Adding notebook-based functionality, (3) Agent or validation notebooks, (4) Any notebook that uses GPU training infrastructure."
author: Claude Code
date: 2026-02-01
---

# Colab Notebook Development Pattern (v3.7.0)

## CRITICAL RULE

**ALWAYS copy the structure from `notebooks/training.ipynb` when creating new notebooks.**

DO NOT:
- Improvise cell structure
- Combine setup cells
- Skip drive mount
- Use different extraction methods
- Assume paths work differently

## Canonical Reference

The authoritative template is `notebooks/training.ipynb`. Every new notebook MUST follow its pattern for:

1. **Part 1: Setup** (Cells 1-6)
   - GPU verification
   - Drive mount (separate cell)
   - Repository extraction (%%bash cell)
   - Path setup
   - Dependencies
   - API keys

2. **Part 2+: Your Content**
   - Configuration cells
   - Data loading (use prefetch_all_data)
   - Training/experiment loops
   - Results saving

## Cell-by-Cell Template

### Setup Cells (MANDATORY - Copy Exactly)

```python
# Cell 1: GPU Verification
!nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
import torch
assert torch.cuda.is_available(), "CUDA not available!"
# ... (see training.ipynb)
```

```python
# Cell 2: Mount Drive
from google.colab import drive
drive.mount('/content/drive')
```

```bash
# Cell 3: Extract (%%bash magic)
%%bash
cd /content
if [ ! -d "Alpaca_trading" ]; then
    unzip -q /content/drive/MyDrive/Colab_Projects/Alpaca_trading.zip
fi
```

```python
# Cell 4: Path Setup
import os, sys
os.chdir('/content/Alpaca_trading')
sys.path.insert(0, '/content/Alpaca_trading')
```

```python
# Cell 5: Dependencies
%pip install -q torch gymnasium alpaca-py pandas numpy scipy arch
```

```python
# Cell 6: API Keys
API_KEYS_FILE = '/content/Alpaca_trading/config/API_key_500Paper.txt'
# ... load keys
```

### Data Loading Pattern

```python
# Use the same pattern as training.ipynb
from alpaca_trading.data.caching_fetcher import prefetch_all_data

CACHE_DIR = '/content/drive/MyDrive/Colab_Projects/training_data'
prefetched_data = prefetch_all_data(
    SYMBOLS,
    force_refresh=False,
    cache_dir=CACHE_DIR,
    min_bars=2000,
    keys_file=API_KEYS_FILE,
)
```

### Output Directory Pattern

```python
# ALWAYS create directories before saving
from pathlib import Path

OUTPUT_DIR = '/content/drive/MyDrive/Colab_Projects/my_experiment'
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
Path(f'{OUTPUT_DIR}/models').mkdir(parents=True, exist_ok=True)

# Then save
trainer.save(f'{OUTPUT_DIR}/models/{symbol}.pt')
```

### GPU Cleanup Pattern

```python
# After each training run (from training.ipynb)
import gc
trainer.cleanup()
del trainer, env, prices
gc.collect()
torch.cuda.empty_cache()
```

## Failed Attempts (Session 2026-02-01)

| Attempt | Why it Failed | Correct Approach |
|---------|---------------|------------------|
| Combined drive mount + extract | Extract fails before mount completes | Separate cells |
| Python os.path.exists() for extraction | Didn't have drive mounted | Use %%bash with conditionals |
| Gave user instructions on error | User frustration | Just copy training.ipynb |
| Created notebook from scratch | Many missing pieces | Always start from training.ipynb |
| Forgot output directories | trainer.save() failed | mkdir before any save |
| Different pip install list | Import errors | Match training.ipynb exactly |

## Checklist for New Notebooks

- [ ] Cells 1-6 copied exactly from training.ipynb
- [ ] Drive mount is separate cell (not combined)
- [ ] %%bash used for extraction (not Python)
- [ ] API keys loaded from config/ files
- [ ] Output directories created with mkdir
- [ ] GPU cleanup after each training run
- [ ] prefetch_all_data() used for data loading

## Files

```
notebooks/training.ipynb         # CANONICAL TEMPLATE
notebooks/agent_validation_analysis.ipynb  # Example following pattern
```

## References

- Skill: `colab-unzip-workflow` - File paths and API keys
- Skill: `persistent-cache-gap-filling` - Data caching configuration
- Skill: `gpu-memory-cleanup` - GPU cleanup patterns
