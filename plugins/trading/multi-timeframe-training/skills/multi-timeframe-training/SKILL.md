---
name: multi-timeframe-training
description: "DEPRECATED in v5.6.0 — see joint-multi-tf-v560 skill. Documents the v5.2.0 dual-model approach (train separate 15Min/1Hour models, combine via weighted voting). Still relevant for: (1) loading legacy v5.5.0 dual models, (2) understanding the historical aggregation layer, (3) resampling pattern via origin='start'."
author: Claude Code
date: 2024-12-29
---

# Multi-Timeframe Training Pattern (v5.2.0)

> **DEPRECATED in v5.6.0**: Replaced by single joint model per symbol with broadcast 1Hour context features. See [`joint-multi-tf-v560`](../../joint-multi-tf-v560/skills/joint-multi-tf-v560/SKILL.md) for the current architecture.
>
> **Why deprecated**: The Mar-25 evaluation (see "Multi-TF Strategy" section below) showed dual-model + weighted voting was NOT universally better — only CLSK improved, while CNM/MOH/PSTG degraded. The aggregation layer added combinatorial uncertainty (direction threshold, agreement boost, weight ratios) without letting the models learn to complement each other.
>
> **What this skill is still useful for**:
> - Loading and inferring with legacy v5.5.0 and earlier dual models (still supported via `MultiTimeframePricePredictor`)
> - Understanding the `resample_to_timeframe()` `origin='start'` pattern for bar alignment (still used for any data resampling)
> - Historical context on the PDT window scaling pattern

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2024-12-29 |
| **Goal** | Train separate models for each timeframe using resampled data from base timeframe |
| **Environment** | training notebook, multi_timeframe.py, GPUVectorizedTradingEnv |
| **Status** | Success |

## Context

Single-timeframe training limits strategy adaptability. Different timeframes capture different market dynamics:
- 1Hour: Short-term momentum, intraday patterns
- 4Hour: Medium-term trends, reduced noise
- 1Day: Long-term trends, swing trading

**Solution**: Train separate models for each timeframe, resampling from cached 1Hour data.

## Verified Workflow

### 1. Configure Training Timeframes (notebook)

```python
# Data configuration
TIMEFRAME = '1Hour'               # Base timeframe for data fetching
TRAINING_TIMEFRAMES = ['1Hour']   # Single timeframe (default)
# TRAINING_TIMEFRAMES = ['1Hour', '4Hour']  # Multi-TF training
```

### 2. Build Training Combinations

```python
# Build training combinations (symbol x timeframe)
training_combinations = [(s, tf) for tf in TRAINING_TIMEFRAMES for s in SYMBOLS_TO_TRAIN_FINAL]
total_combinations = len(training_combinations)

print(f'TRAINING {len(SYMBOLS_TO_TRAIN_FINAL)} SYMBOLS × {len(TRAINING_TIMEFRAMES)} TIMEFRAMES = {total_combinations} models')
```

### 3. Resample Data with Proper Alignment

```python
from alpaca_trading.signals.multi_timeframe import resample_to_timeframe

# Load base data (1Hour)
df_base = PREFETCHED_DATA[symbol]

# Resample if training on different timeframe
if training_tf != TIMEFRAME:
    df = resample_to_timeframe(df_base, training_tf)
    print(f'  Resampled {len(df_base)} bars -> {len(df)} bars for {training_tf}')
else:
    df = df_base
```

### 4. Resampling Function (multi_timeframe.py)

```python
def resample_to_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample OHLCV data to a different timeframe."""
    if df.empty:
        return df

    # Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # Map timeframe to pandas frequency (pandas 2.2+ uses lowercase 'h')
    freq_map = {
        "1Min": "1min",
        "5Min": "5min",
        "15Min": "15min",
        "30Min": "30min",
        "1Hour": "1h",
        "2Hour": "2h",
        "4Hour": "4h",
        "1Day": "1D",
        "1Week": "1W",
    }

    freq = freq_map.get(timeframe, "1min")

    # Resample OHLCV with origin='start' to preserve alignment
    # CRITICAL: origin='start' ensures bars align with market open (9:30)
    # not clock-hour boundaries (10:00, 11:00)
    resampled = pd.DataFrame()
    resampled["open"] = df["open"].resample(freq, origin='start').first()
    resampled["high"] = df["high"].resample(freq, origin='start').max()
    resampled["low"] = df["low"].resample(freq, origin='start').min()
    resampled["close"] = df["close"].resample(freq, origin='start').last()

    if "volume" in df.columns:
        resampled["volume"] = df["volume"].resample(freq, origin='start').sum()

    return resampled.dropna()
```

### 5. Model Naming Convention

```python
# Models named with timeframe suffix
model_filename = f'{symbol}_{training_tf}.pt'
# Examples: GOOGL_1Hour.pt, GOOGL_4Hour.pt

# Save paths
local_model_path = f'models/rl_symbols/{model_filename}'
drive_model_path = f'{DRIVE_MODEL_DIR}/{model_filename}'
```

### 6. Live Trader Model Loading

```python
# Load models organized by symbol and timeframe
for model_file in model_dir.glob('*.pt'):
    filename = model_file.stem
    parts = filename.split('_')
    symbol = parts[0]
    timeframe = parts[1] if len(parts) > 1 else '1Hour'

    model = load_native_model(str(model_file))

    if symbol not in models_by_symbol:
        models_by_symbol[symbol] = {}
    models_by_symbol[symbol][timeframe] = model
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Resampling without origin='start' | Bars aligned to clock hours, not market open | Use origin='start' for equity market alignment |
| Using 'H' instead of 'h' | Deprecated in pandas 2.2+ | Use lowercase 'h' for hours |
| Training all timeframes in parallel | OOM errors | Train sequentially, clean up between |
| Mixing 1Hour and 4Hour data sources | Data inconsistency | Always resample from same base data |
| Not cleaning GPU memory between TFs | Memory accumulation, crash | Call cleanup_gpu_memory() between each |

## Final Parameters

```yaml
# Timeframe configuration
base_timeframe: '1Hour'       # Data fetched at this resolution
training_timeframes:          # Train models at these resolutions
  - '1Hour'                   # Default (single TF)
  # - '4Hour'                 # Add for multi-TF
  # - '1Day'                  # Add for swing trading

# Resampling rules
origin: 'start'               # Align to first bar (market open)
open: 'first'                 # First open in period
high: 'max'                   # Max high in period
low: 'min'                    # Min low in period
close: 'last'                 # Last close in period
volume: 'sum'                 # Total volume in period

# pandas frequency map
1Hour: '1h'
2Hour: '2h'
4Hour: '4h'
1Day: '1D'
1Week: '1W'
```

## Key Insights

- **origin='start' is CRITICAL**: Without it, 4Hour bars start at 00:00, not market open
- **Lowercase frequency strings**: pandas 2.2+ deprecated uppercase 'H'
- **Sequential training**: GPU memory doesn't allow parallel multi-TF training
- **Same base data**: All timeframes should resample from same cached data
- **Consistent naming**: `SYMBOL_TIMEFRAME.pt` enables auto-discovery

## Data Requirements

| Timeframe | Min Bars (training) | From 1Hour (4 years) |
|-----------|---------------------|----------------------|
| 1Hour     | 2000                | ~10,000 bars         |
| 4Hour     | 500                 | ~2,500 bars          |
| 1Day      | 125                 | ~1,000 bars          |

## v5.2.0 Update: 15Min + 1Hour Dual-Timeframe (2026-03-14)

### Sub-Hourly Training (15Min)
When adding sub-hourly timeframes (e.g., 15Min), additional adjustments are needed:

#### PDT Window Scaling
```python
_bars_per_hour = {'15Min': 4, '30Min': 2, '1Hour': 1}
pdt_window_scaled = int(1200 * _bars_per_hour.get(training_tf, 1))

# Use dataclass_replace for per-iteration env config override
env_config_tf = dataclass_replace(
    env_config,
    timeframe=training_tf,
    pdt_window_bars=pdt_window_scaled,
)
```

#### Selectivity Boost for Sub-Hourly
```python
# Counter overtrading risk from 4x more bars/day
if _bars_per_hour.get(training_tf, 1) > 1:
    env.set_reward_weight_override('selectivity', 0.05)
```

#### Selection at Finest Timeframe
```python
# Selection runs at finest TF — symbols viable at 15Min have enough data for 1Hour
from alpaca_trading.signals.multi_timeframe import TIMEFRAME_HIERARCHY
_tf_order = {tf: i for i, tf in enumerate(TIMEFRAME_HIERARCHY)}
SELECTION_TIMEFRAME = min(TRAINING_TIMEFRAMES, key=lambda tf: _tf_order.get(tf, 99))
```

#### Timeframe-Aware PDT Detection (vectorized_env.py)
```python
_bars_per_day_map = {'15Min': 26, '30Min': 13, '1Hour': 7, '4Hour': 2, '1Day': 1}
self._bars_per_trading_day = _bars_per_day_map.get(self.config.timeframe, 7)
# Replaces hardcoded `bars_since_entry <= 7` with `<= self._bars_per_trading_day`
```

### Key Differences from Higher-TF Resampling
| Aspect | Higher TF (4Hour from 1Hour) | Lower TF (15Min) |
|--------|------------------------------|-------------------|
| Data source | Resample from 1Hour cache | Fetch directly from API at 15Min |
| PDT window | Standard (1200 bars) | Scaled (4800 bars for 15Min) |
| Selectivity | No boost needed | +0.05 boost to counter overtrading |
| Bars/day | Fewer (2 for 4Hour) | More (26 for 15Min) |

## v5.2.1 Bug Fixes (2026-03-15)

### Bugs Found and Fixed
| Bug | Root Cause | Fix |
|-----|-----------|-----|
| 15Min timeframe silently ignored | `env_config` always used `timeframe='1Hour'` — per-TF `dataclass_replace()` was documented in this skill but missing from notebook | Added `env_config_tf = dataclass_replace(env_config, timeframe=training_tf, pdt_window_bars=scaled)` to cells 32+37 |
| PDT hardcoded in active path | `_execute_actions_with_sizing` (line ~2283) had `bars_since_entry <= 7` — the non-sizing path (line ~2177) was already fixed | Changed to `<= self._bars_per_trading_day` |
| Selection used single `TIMEFRAME` | `SelectionRunnerConfig(timeframe=TIMEFRAME)` ignored `TRAINING_TIMEFRAMES` | Changed to `timeframe=_finest_training_tf` using `TIMEFRAME_HIERARCHY` ordering |

### Key Lesson
**Document != Implement**: This skill documented the per-TF `dataclass_replace()` pattern and selectivity boost in v5.2.0, but the notebook cells were never updated. The skill was correct — the notebook was wrong. Always verify notebook cells match skill documentation after codebase changes.

## Multi-TF Strategy (ACTIVE as of v5.2.0)

Models exist for 15Min + 1Hour:
1. `MultiTimeframePricePredictor` aggregates signals from both timeframes
2. Live trader auto-discovers models by filename pattern (`SYMBOL_TIMEFRAME.pt`)
3. No live trader code changes needed — existing multi-TF infrastructure handles both

## References
- `notebooks/training.ipynb`: TRAINING_TIMEFRAMES configuration
- `alpaca_trading/signals/multi_timeframe.py`: resample_to_timeframe()
- `scripts/live_trader.py`: Multi-TF model loading pattern
- `alpaca_trading/gpu/vectorized_env.py`: `_bars_per_trading_day` for timeframe-aware PDT
- `scripts/run_backtest.py`: Auto-detects timeframe from model filename
