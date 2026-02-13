---
name: backtest-notebook-v4
description: "Fix 8-action space bug in backtest engines and rewrite backtest notebook for Colab v4.0.0"
author: Claude Code
date: 2026-02-12
---

# Backtest Notebook v4.0.0 - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-12 |
| **Goal** | Fix 8-action mapping bug in BacktestEngine/RealisticBacktestEngine; rewrite backtest.ipynb as Colab tool |
| **Environment** | Python 3.10, v4.0.0 codebase |
| **Status** | Success |

## Context

Both `BacktestEngine` and `RealisticBacktestEngine` used a 3-value action mapping:
```python
# BUG: Only handles 3-action models correctly
signal = {0: 0, 1: 1, 2: -1}.get(action, 0)
```

For v4.0.0 8-action models, this caused:
- **BUY_50% (action 2)** treated as SELL (-1) instead of BUY (+1)
- **BUY_75% (action 3)** treated as HOLD (0) instead of BUY (+1)
- **SELL_25/50/75% (actions 4-6)** treated as HOLD (0) instead of SELL (-1)
- **CLOSE (action 7)** treated as HOLD (0) instead of closing position

## Verified Fix

### 1. Use `interpret_action()` from model_version.py
```python
from ..training.model_version import interpret_action

# In run() method:
self._model_spec = getattr(model, 'model_spec', None)

# In action mapping:
if self._model_spec is not None:
    direction, size_mult, action_name = interpret_action(action, self._model_spec)
    signal = direction
    is_close = (action == 7 and self._model_spec.n_actions == 8)
else:
    # Legacy 3-action fallback
    signal = {0: 0, 1: 1, 2: -1}.get(action, 0)
    size_mult = 1.0
    is_close = False
```

### 2. Explicit CLOSE handling
```python
# Before guardrail checks - CLOSE always allowed
if is_close and symbol in self.positions:
    self._close_position(symbol, current_price, current_time, bar_idx, "model_close")
```

### 3. Thread size_mult into position sizing
- `_process_signal` accepts `size_mult: float = 1.0` parameter
- `_open_position` applies: `position_value *= size_mult` (BacktestEngine) or `shares *= size_mult` (RealisticBacktestEngine)
- BUY_25% uses 25% of max allocation, BUY_50% uses 50%, BUY_75% uses 75%

## Notebook Colab Pattern

The backtest notebook follows `training.ipynb` structure:
1. GPU check (informational only), Drive mount, zip extract, sys.path setup
2. `_read_keys_from_file()` for API key parsing (NEVER naive line reading)
3. `DataFetcher` for data (Alpaca API only, no yfinance)
4. `NativeModelWrapper` for model loading (has `model_spec` attribute)
5. `BacktestEngine` for standard backtesting
6. `WalkForwardValidator.run_single_model()` for walk-forward
7. Results saved to Google Drive

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Using `n_actions` to switch action mapping | Models without `model_spec` attribute would crash | Use `getattr(model, 'model_spec', None)` with fallback |
| Putting CLOSE handler after guardrail check | CLOSE action should always work, even during drawdown halt | Put CLOSE before `can_trade` check |
| Using `size_mult` as position_size_pct replacement | size_mult=0.0 for HOLD would cause division issues | size_mult multiplies the existing allocation, only called when signal != 0 |

## Key Parameters

```python
# BacktestConfig defaults
initial_capital = 100_000.0    # $100K
position_size_pct = 0.10       # 10% per position
stop_loss_pct = 0.02           # 2%
take_profit_pct = 0.04         # 4%
max_drawdown_pct = 0.15        # 15% halt
slippage_pct = 0.0005          # 0.05%
commission_per_trade = 1.0     # $1

# With 8-action size_mult applied:
# BUY_25%: 10% * 0.25 = 2.5% of capital
# BUY_50%: 10% * 0.50 = 5.0% of capital
# BUY_75%: 10% * 0.75 = 7.5% of capital
```

## Key Insights
- `model.model_spec` is set by `NativeModelWrapper` via `assert_compatibility()` at load time
- Legacy SB3 models don't have `model_spec` - fallback to 3-value mapping is correct for them
- `interpret_action()` handles 8/7/3-action models uniformly
- The bug was silent: backtests ran but BUY signals were inverted and most actions ignored

## References
- `alpaca_trading/training/model_version.py:289` - `interpret_action()` function
- `alpaca_trading/backtest/engine.py` - Both BacktestEngine and RealisticBacktestEngine
- CLAUDE.md guardrail #12: Action space compatibility
