---
name: dynamic-universe-management
description: "Integrate dynamic universe management for automatic model discovery and performance-based symbol rotation (v3.0). Trigger when: (1) setting up automatic model detection, (2) implementing performance-based eviction, (3) adding universe expansion from new models, (4) configuring advisory vs execution mode."
author: Claude Code
date: 2025-01-03
version: v3.0
---

# Dynamic Universe Management (v3.0)

## Experiment Overview

| Item | Details |
|------|---------|
| **Date** | 2025-01-03 |
| **Goal** | Automatic model discovery and performance-based symbol rotation in live trading |
| **Branch** | `feature/v3.0-multi-agent` |
| **New Code** | ~1,200 lines across 4 files |
| **Status** | Success - Merged with multi-agent integration |

## Context

The live trader had several gaps in long-running trading sessions:

1. **No Model Hot-Loading**: Models loaded once at startup; new `.pt` files required restart
2. **Static Universe**: Universe refresh only re-ranked existing symbols; couldn't expand
3. **No Performance-Based Eviction**: Underperforming symbols stayed in universe indefinitely
4. **Manual Model Deployment**: Models trained but required manual copy to trigger trading

This skill addresses all four gaps with a unified `DynamicUniverseManager` class.

## Verified Workflow

### 1. Enable Dynamic Universe in Live Trader

```bash
# Enable with default 30-minute scan interval
python scripts/live_trader.py --paper 1 --dynamic-universe 1

# Custom scan interval (60 minutes)
python scripts/live_trader.py --paper 1 --dynamic-universe 1 --universe-scan-interval 60
```

### 2. Configuration

```python
from alpaca_trading.selection.dynamic_universe import (
    DynamicUniverseManager,
    UniverseManagerConfig,
)

config = UniverseManagerConfig(
    model_dir="models/rl_symbols",     # Where to scan for models
    scan_interval_minutes=30,           # How often to scan
    min_symbols=3,                       # Minimum universe size
    max_symbols=10,                      # Maximum universe size
    eviction_win_rate_threshold=0.40,   # Below 40% -> consider removal
    eviction_drawdown_threshold=0.12,   # Above 12% -> consider removal
    min_trades_for_eviction=10,          # Minimum trades before evaluating
    enable_selection_agents=True,        # Use AI agents for recommendations
    advisory_mode=True,                  # Log but don't auto-apply
)

manager = DynamicUniverseManager(config=config)
```

### 3. Core Operations

```python
# Scan for available models
models = manager.scan_model_directory()  # Dict[symbol, path]

# Detect newly added models
new_symbols = manager.detect_new_models()  # List[str]

# Get expansion candidates (models not in active universe)
expansion = manager.get_expansion_candidates(max_candidates=10)

# Get eviction candidates (poor performers)
eviction = manager.get_eviction_candidates()

# Update performance metrics from profit_tracker
manager.update_symbol_performance(
    symbol="AAPL",
    win_rate=0.55,
    total_pnl=1500.0,
    max_drawdown=0.08,
    total_trades=25,
)
```

### 4. Advisory Mode Output

```
INFO: New models detected: ['NVDA', 'AMD']
INFO: Eviction candidates based on performance:
   XYZ: win_rate=35.0%, max_dd=14.2%, trades=25
INFO: Expansion candidates available:
   NVDA: score=0.82
INFO: (Advisory mode: review recommendations above)
```

### 5. Background Scanning

```python
# Start background thread (scans every scan_interval_minutes)
manager.start_background_scanning()

# Stop on shutdown
manager.stop_background_scanning()
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Modifying trade_step function | Too deep in call stack, too many params | Hook at trading loop level instead |
| Immediate universe changes | Could disrupt active positions | Use advisory mode first |
| Evicting without min trades | Flagged new symbols with 2-3 trades | Require min_trades_for_eviction=10 |
| Direct model loading | Requires full predictor initialization | Just track paths, let main loop load |
| Synchronous agent calls | Blocks trading loop | Use async for recommendations |
| No baseline for detect_new | All models appeared "new" on restart | Use set_loaded_models() at startup |

## Final Parameters

```yaml
# Recommended production configuration
UniverseManagerConfig:
  model_dir: "models/rl_symbols"
  scan_interval_minutes: 30        # Every 30 minutes
  min_symbols: 3                    # Never go below 3
  max_symbols: 10                   # Match --max-assets
  eviction_win_rate_threshold: 0.40 # 40% minimum
  eviction_drawdown_threshold: 0.12 # 12% max drawdown
  min_trades_for_eviction: 10       # Need data before judging
  enable_selection_agents: true     # AI-assisted recommendations
  advisory_mode: true               # Start safe!
```

## Key Insights

- **Advisory Mode First**: Always start with `advisory_mode=True`. Review recommendations for 1-2 weeks before enabling execution mode.

- **Performance Data Required**: The eviction system only works if `update_symbol_performance()` is called regularly. Hook into `profit_tracker.close_trade()` events.

- **Baseline at Startup**: Call `manager.set_loaded_models(current_models)` at trader startup to establish baseline for `detect_new_models()`.

- **Thread Safety**: All state access uses `threading.RLock()`. Safe to call from trading loop while background scanner runs.

- **Integration with Multi-Agent**: Selection agents can validate expansion/eviction recommendations when `enable_selection_agents=True`.

- **Min/Max Bounds**: `apply_change()` respects min_symbols/max_symbols. Won't over-expand or over-contract.

## Architecture

```
DynamicUniverseManager
├── scan_model_directory()     # Find all .pt files
├── detect_new_models()        # Compare to baseline
├── get_expansion_candidates() # New models + DB scoring
├── get_eviction_candidates()  # Performance < thresholds
├── update_symbol_performance() # Track win_rate, PnL, DD
├── apply_change()             # Advisory or execute
├── start_background_scanning() # Background thread
└── stop_background_scanning()  # Cleanup

Integration Points:
├── scripts/live_trader.py
│   ├── --dynamic-universe CLI arg
│   ├── Initialization after risk monitor
│   ├── Periodic checks in trading loop
│   └── Cleanup on shutdown
└── alpaca_trading/selection/__init__.py
    └── Exports DynamicUniverseManager
```

## Files Location

| File | Lines | Purpose |
|------|-------|---------|
| `alpaca_trading/selection/dynamic_universe.py` | ~550 | Core manager class |
| `alpaca_trading/selection/__init__.py` | +10 | Module exports |
| `scripts/live_trader.py` | +80 | Integration code |
| `tests/test_dynamic_universe.py` | ~465 | 24 unit tests |

## Testing

```bash
# Run dynamic universe tests
python -m pytest tests/test_dynamic_universe.py -v

# Output: 24 passed
```

Test Coverage:
- Configuration dataclasses
- Model directory scanning (empty, with models, crypto)
- New model detection (first scan, after addition)
- Eviction candidates (low win rate, high drawdown, not enough trades)
- Expansion candidates (new models, excludes active)
- Advisory vs execution mode
- Background scanning start/stop
- Performance tracking updates

## Rollout Strategy

| Phase | Description | Duration |
|-------|-------------|----------|
| 1 | Merge to stable, run tests | Day 1 |
| 2 | Advisory mode, review logs | 1-2 weeks |
| 3 | Validate recommendations manually | Week 2-3 |
| 4 | Enable execution mode (supervised) | Week 4+ |

**Critical**: Do NOT enable `advisory_mode=False` until you've validated the recommendations match your judgment for at least 2 weeks.

## References

- `README.md` - Full system documentation
- `alpaca_trading/selection/dynamic_universe.py` - Implementation
- `tests/test_dynamic_universe.py` - Test cases
- Branch: `feature/v3.0-multi-agent`
- Related skill: `multi-agent-integration` (for agent-validated recommendations)
