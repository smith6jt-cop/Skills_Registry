---
name: colab-unzip-workflow
description: "Colab notebook setup pattern. Trigger when: (1) Creating new Colab notebooks, (2) API key file not found, (3) file path errors in Colab, (4) repository extraction fails, (5) 'yfinance fallback' despite keys existing."
author: Claude Code
date: 2026-02-01
---

# Colab Notebook Setup Pattern (v3.7.0)

## CRITICAL: Follow training.ipynb Pattern

**When creating ANY new Colab notebook, ALWAYS copy the setup cells from `notebooks/training.ipynb` exactly.**

Do NOT improvise. Do NOT simplify. Do NOT combine cells. Copy the exact pattern.

## Required Cell Structure (In Order)

### Cell 1: GPU Verification
```python
# Verify GPU (from training.ipynb)
!nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv

import torch
assert torch.cuda.is_available(), "CUDA not available!"

gpu_name = torch.cuda.get_device_name(0)
gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9

print(f'\nGPU: {gpu_name}')
print(f'VRAM: {gpu_mem:.0f} GB')
print(f'PyTorch: {torch.__version__}')
print(f'CUDA: {torch.version.cuda}')
```

### Cell 2: Mount Google Drive
```python
# Mount Google Drive
from google.colab import drive  # type: ignore[import-not-found]
drive.mount('/content/drive')
print('Google Drive mounted')
```

### Cell 3: Extract Repository (%%bash)
```bash
%%bash
# Extract project from Drive
cd /content
if [ ! -d "Alpaca_trading" ]; then
    echo "Extracting project..."
    unzip -q /content/drive/MyDrive/Colab_Projects/Alpaca_trading.zip
    echo "Project extracted"
else
    echo "Project already exists"
fi
```

### Cell 4: Setup Python Path
```python
# Change to project directory and setup path
import os
import sys
os.chdir('/content/Alpaca_trading')
sys.path.insert(0, '/content/Alpaca_trading')
print(f'Working directory: {os.getcwd()}')
```

### Cell 5: Install Dependencies
```python
# Install dependencies
%pip install -q torch gymnasium alpaca-py pandas numpy scipy arch
print('Dependencies installed')
```

### Cell 6: API Keys Configuration
```python
# API Keys - Load from config files
import os

API_KEYS_FILE = '/content/Alpaca_trading/config/API_key_500Paper.txt'

# Load Alpaca keys
if os.path.exists(API_KEYS_FILE):
    with open(API_KEYS_FILE, 'r') as f:
        lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
    if len(lines) >= 2:
        os.environ['APCA_API_KEY_ID'] = lines[0]
        os.environ['APCA_API_SECRET_KEY'] = lines[1]
        print(f'[OK] Alpaca API keys loaded')

print(f'API Key Status: {"OK" if os.environ.get("APCA_API_KEY_ID") else "MISSING"}')
```

## Failed Attempts (Session 2026-02-01)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Combined drive mount + extract in one cell | Extract runs before mount completes | Keep as separate cells |
| Python-based extraction without drive mount | Zip file not accessible | Must mount drive FIRST |
| Added instructions instead of error handling | User frustration | Just follow training.ipynb |
| 2-hour tolerance for gap-fill | Caused warnings for 3-day-old cache | Use 7-day threshold |
| Forgot to create output directories | `trainer.save()` failed | Always mkdir before save |

## API Key Files Location

After extraction, keys are at:
```
/content/Alpaca_trading/config/API_key_500Paper.txt   # 500 paper account
/content/Alpaca_trading/config/API_key_Live_mirror.txt # Live mirror paper
/content/Alpaca_trading/config/API_Anthropic_key.txt  # Claude API (if needed)
```

**NOT** `/content/drive/MyDrive/` - files are extracted to `/content/Alpaca_trading/`

## Output Directory Pattern

Always create output directories before saving:
```python
from pathlib import Path

OUTPUT_DIR = '/content/drive/MyDrive/Colab_Projects/experiment_results'
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
Path(f'{OUTPUT_DIR}/models').mkdir(parents=True, exist_ok=True)
Path(f'{OUTPUT_DIR}/logs').mkdir(parents=True, exist_ok=True)
```

## Files Modified

```
notebooks/training.ipynb: Reference implementation
notebooks/agent_validation_analysis.ipynb: Now follows this pattern
```

## References

- Skill: `persistent-cache-gap-filling` - Cache configuration with gap_fill_threshold_days
- Skill: `data-source-priority` - Why Alpaca API matters
- `alpaca_trading/data/caching_fetcher.py` - Gap-fill threshold parameter
