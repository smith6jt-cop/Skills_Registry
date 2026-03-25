---
name: multi-tf-backtesting
description: "Multi-timeframe backtesting combining 15Min + 1Hour model signals. Trigger when: (1) multi-TF backtest, (2) combining timeframe signals in backtest, (3) validating multi-TF strategy, (4) --multi-tf CLI flag."
author: Claude Code
date: 2026-03-25
---

# Multi-Timeframe Backtesting

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-03-25 |
| **Goal** | Validate multi-TF signal aggregation strategy in backtesting (same as live trading) |
| **Environment** | Python 3.12, v5.3.2, BacktestEngine + WalkForwardValidator |
| **Status** | Success |

## Context

Training (v5.2.0+) produces separate 15Min and 1Hour models per symbol. The live trader uses `MultiTimeframePricePredictor` to aggregate signals via weighted voting. But backtesting ran each model independently — no way to validate the combined multi-TF strategy that actually runs in production.

**Solution**: Add `run_multi_tf()` to `BacktestEngine` that replicates live trading's aggregation logic.

## Verified Workflow

### 1. Signal Aggregation (shared function)

```python
from alpaca_trading.prediction.aggregation import aggregate_timeframe_predictions

preds = [
    {'direction': 1, 'magnitude': 0.02, 'confidence': 0.8, 'weight': 0.15, 'size_mult': 0.5},  # 15Min
    {'direction': 1, 'magnitude': 0.03, 'confidence': 0.9, 'weight': 0.25, 'size_mult': 0.75}, # 1Hour
]
result = aggregate_timeframe_predictions(preds)
# result: {direction: 1, magnitude: ..., confidence: ..., agreement_ratio: 1.0, ...}
```

Weights from `TIMEFRAME_WEIGHTS`: 15Min=0.15, 1Hour=0.25.

### 2. Bar Synchronization (15Min → 1Hour)

```python
import numpy as np
from alpaca_trading.signals.multi_timeframe import resample_to_timeframe

hourly_data = resample_to_timeframe(data_15min, '1Hour')
# Map each 15min bar to its corresponding hourly bar
tf_bar_map = np.searchsorted(hourly_data.index, data_15min.index, side='right') - 1
```

The 1Hour prediction is only recomputed when `tf_bar_map[bar_idx]` changes (i.e., at hour boundaries). Cached otherwise.

### 3. CLI Usage

```bash
# Single symbol
python scripts/run_backtest.py --multi-tf --symbol WST --model-dir models/rl_symbols/

# Walk-forward
python scripts/run_backtest.py --multi-tf --symbol WST --model-dir models/rl_symbols/ --walk-forward 5

# Batch (all symbols with paired models)
python scripts/run_backtest.py --multi-tf --all --model-dir models/rl_symbols_staging/mar18/trained_models/
```

Model pairs auto-discovered by `SYMBOL_TIMEFRAME.pt` naming convention.

### 4. Engine Method

```python
engine = BacktestEngine(config)
result = engine.run_multi_tf(
    models={'15Min': model_15, '1Hour': model_1h},
    data=data_15min,
    symbol='WST',
)
# result.multi_tf_diagnostics has per-TF action counts, agreement ratios
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Dynamic attr on `BacktestResult` | `slots=True` prevents dynamic attributes | Added `multi_tf_diagnostics` field to dataclass |
| Patching `BacktestObservationBuilder` at engine module level | Lazy imports in method don't create module-level references | Patch at source module (`alpaca_trading.gpu.inference_obs_builder`) |
| Importing `aggregation.py` through `prediction/__init__.py` in tests | Circular import chain: prediction → signals → training → trading → signals | Use `importlib.util` to import aggregation.py directly in tests |

## Final Parameters

```yaml
# Timeframe weights (from TIMEFRAME_WEIGHTS)
15Min: 0.15
1Hour: 0.25

# Aggregation
direction_threshold: 0.3       # >0.3 → BUY, <-0.3 → SELL, else HOLD
agreement_boost_threshold: 0.7  # 70%+ agreement triggers boost
agreement_boost_factor: 1.1     # +10% confidence boost

# Observation builders
builder: BacktestObservationBuilder  # Pre-computed, ~100x faster
window: 100
# DO NOT use InferenceObservationBuilder (too slow for backtest)
# DO NOT enable predator-prey validation (requires live Markov state)

# Start index
min_start: max(window, first_15min_idx_where_hourly_bar >= window)
# ~390 15Min bars ≈ 15 trading days of history required
```

## Key Insights

- **DRY aggregation**: Extract pure functions from live trading classes — backtest reuses identical logic without duplicating code
- **Bar synchronization via searchsorted**: `np.searchsorted(coarse_index, fine_index, side='right') - 1` maps each fine bar to its most recent coarse bar
- **Cached coarser predictions**: Only recompute when the coarse bar index changes — significant performance win (4x fewer 1Hour predictions)
- **`slots=True` dataclasses**: Cannot add attributes dynamically — must add fields to the dataclass definition
- **Circular import workaround**: The `prediction/__init__.py` → `multi_tf_predictor.py` → `signals` chain causes circular imports. Import `aggregation.py` directly via `importlib.util` in tests, or use lazy imports inside methods.

## References

- `alpaca_trading/prediction/aggregation.py`: Shared aggregation function
- `alpaca_trading/prediction/multi_tf_predictor.py`: Live trading multi-TF (source of aggregation logic)
- `alpaca_trading/backtest/engine.py`: `BacktestEngine.run_multi_tf()`
- `alpaca_trading/backtest/walk_forward.py`: `WalkForwardValidator.run_single_model_multi_tf()`
- `scripts/run_backtest.py`: `--multi-tf` CLI flag
- `tests/test_multi_tf_backtest.py`: 23 tests
- `alpaca_trading/signals/multi_timeframe.py`: `resample_to_timeframe()`, `TIMEFRAME_WEIGHTS`
