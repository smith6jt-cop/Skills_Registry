---
name: data-source-priority
description: "Ensure Alpaca API is used for quality data, not yfinance fallback. Trigger when: (1) crypto volume filter fails unexpectedly, (2) zero-volume bars in data, (3) API key configuration issues."
author: Claude Code
date: 2024-12-26
---

# Data Source Priority - Alpaca vs yfinance

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2024-12-26 |
| **Goal** | Fix crypto selection failing due to poor data quality |
| **Environment** | alpaca_trading/data/fetcher.py, training notebook |
| **Status** | Success |

## Context

User reported crypto selection failing:
```
No symbols passed filters.
Stats: 0/30 passed hard filter
BTCUSD: volume (consistency too low)
```

BTCUSD should have billions in daily volume - this was a data quality issue.

**Root Cause**: Alpaca API keys weren't configured, so DataFetcher fell back to yfinance. yfinance crypto data has:
- Many zero-volume bars (data gaps)
- ~50% of bars missing volume data
- Lower reliability than Alpaca

## The Bug

```python
# DataFetcher checks API keys
key = os.environ.get("APCA_API_KEY_ID")
secret = os.environ.get("APCA_API_SECRET_KEY")

# If no keys, Alpaca is disabled
if not (key and secret):
    self._use_alpaca_data = False  # Falls back to yfinance!
```

When tested:
```
Alpaca data enabled: False
Stock client: False
Crypto client: False
Zero-volume bars: 85 / 168  (50%!)
```

## Verified Solution

### 1. Always Use Alpaca API for Quality Data

The DataFetcher priority order:
1. **Environment variables** (RECOMMENDED): `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`
2. **Keys file** (fallback): `DataFetcher(keys_file='path/to/keys.txt')`
3. **yfinance** (last resort): Only if Alpaca unavailable

### 2. Configure API Keys in Training Notebook

```python
# Option 1: Environment variables (RECOMMENDED for Colab)
# Set in Colab Secrets:
#   APCA_API_KEY_ID = your_key
#   APCA_API_SECRET_KEY = your_secret

# Option 2: Keys file path
API_KEYS_FILE = '/content/drive/MyDrive/API_key.txt'

# Verify configuration
alpaca_key = os.environ.get('APCA_API_KEY_ID')
if alpaca_key:
    print(f'Alpaca API: ENABLED (quality data)')
else:
    print(f'WARNING: yfinance fallback (lower quality)')
```

### 3. Check Data Source in Logs

Look for these log messages:
```
# GOOD - Alpaca is being used
[INFO] alpaca_trading.data.fetcher: Alpaca fetched 720 bars for BTCUSD

# BAD - yfinance fallback
[INFO] alpaca_trading.data.fetcher: yfinance fetched 169 bars for BTC-USD
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Lower volume consistency to 30% | Masks the real problem | Fix data source, not thresholds |
| Hardcode API key file path | Path changes between environments | Use environment variables |
| Assume API keys exist | Keys not always configured | Always verify key status |
| Use yfinance for crypto | Zero-volume bars, data gaps | Alpaca is required for quality |

## Data Quality Comparison

| Data Source | Volume Data | Reliability | Crypto Support |
|-------------|-------------|-------------|----------------|
| **Alpaca API** | Complete | High | Excellent |
| yfinance | 50% missing | Low | Poor |

## API Key Configuration Checklist

### For Google Colab
1. Go to Colab Secrets (key icon in left sidebar)
2. Add `APCA_API_KEY_ID` = your API key
3. Add `APCA_API_SECRET_KEY` = your secret key
4. Enable access to notebook

### For Local Development
```bash
# Add to ~/.bashrc or ~/.zshrc
export APCA_API_KEY_ID="your_key"
export APCA_API_SECRET_KEY="your_secret"
```

### For Training Notebook
```python
# Cell 14 in VSCode_Colab_Training_NATIVE.ipynb
API_KEYS_FILE = None  # Use env vars (recommended)
# OR
API_KEYS_FILE = '/content/drive/MyDrive/API_key.txt'  # Fallback
```

## Diagnostic Commands

### Check if Alpaca is enabled:
```python
from alpaca_trading.data.fetcher import DataFetcher
fetcher = DataFetcher(keys_file=API_KEYS_FILE)
print(f'Alpaca enabled: {fetcher._use_alpaca_data}')
print(f'Stock client: {fetcher._stock_client is not None}')
print(f'Crypto client: {fetcher._crypto_client is not None}')
```

### Check data quality:
```python
df = fetcher.get_bars('BTCUSD', timeframe='1Hour', lookback_days=7)
zero_vol = (df['volume'] == 0).sum()
print(f'Zero-volume bars: {zero_vol} / {len(df)} ({zero_vol/len(df):.0%})')
# If > 10%, you're using yfinance - fix API keys!
```

## Key Insights

- **Alpaca data is required for crypto** - yfinance crypto data has too many gaps
- **Environment variables are best** - Works across all environments, no path issues
- **Don't lower quality thresholds** - Fix the data source instead
- **Volume consistency 70%** - Alpaca data easily passes; yfinance fails
- **Check logs for data source** - "yfinance fetched" = problem

## Files Modified

```
alpaca_trading/data/fetcher.py:
  - Lines 119-131: _load_alpaca_keys() checks env vars first

notebooks/VSCode_Colab_Training_NATIVE.ipynb:
  - Cell 14: API key configuration with verification
  - Shows clear warning when falling back to yfinance
```

## References
- `alpaca_trading/data/fetcher.py`: DataFetcher implementation
- Alpaca API docs: https://docs.alpaca.markets/docs/
- `.skills/plugins/trading/symbol-selection-asset-filters/`: Asset-type filter patterns
