---
name: vix-scaled-risk-management
description: "VIX-based position sizing, circuit breakers, and capital shift suppression"
author: Claude Code
date: 2026-02-24
version: 4.4.0
---

# VIX-Scaled Risk Management

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-24 |
| **Goal** | Add macro-aware risk scaling to position sizing, circuit breakers, and capital shifts |
| **Environment** | Python 3.11+, OpenBB FRED provider |
| **Status** | Success |

## Context
Position sizing had no macro awareness — during VIX=40 panic, positions were sized the same as VIX=12 calm. VIX spikes correlate with 40-60% of max drawdown events.

## Implementation

### 1. VIX-Scaled Position Sizing (`integrated_risk.py`)
Step 8 in `calculate_position_size()`, between correlation adjustment and capital limits:

```python
# VIX regime scaling (linear interpolation within bands)
VIX < 15:  scale = 1.00  (normal)
VIX 15-25: scale = 0.85  (elevated, linear)
VIX 25-35: scale = 0.65  (high, linear)
VIX > 35:  scale = 0.40  (panic, linear)
```

- `IntegratedPositionSize.macro_risk_scale` field tracks the applied scale
- `get_risk_summary()` includes `vix_level` and `macro_risk_scale`
- Gracefully degrades to 1.0x when OpenBB unavailable
- Cached internally (`_last_vix`, `_last_vix_scale`) with refresh on each call

### 2. VIX Circuit Breaker (`risk_monitor.py`)
```python
# CircuitBreakerConfig additions
vix_warning_threshold = 30.0    # Warning alert
vix_critical_threshold = 40.0   # Circuit breaker alert

# RealTimeRiskMonitor.check_vix_level() -> List[RiskAlert]
```

### 3. Capital Shift Suppression (`capital_shift.py`)
```python
# At top of should_shift_capital():
if vix > 30.0:
    return False, "vix_suppressed"
# Prevents shifting equity capital to crypto during correlated panic
```

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Fixed VIX thresholds (step function) | Abrupt position size jumps at boundaries | Linear interpolation within bands is smoother |
| Patching at `integrated_risk.get_openbb_provider` | Module-level lazy import not found | Must patch at `alpaca_trading.data.openbb_provider.get_openbb_provider` |

## Final Parameters
```python
# VIX bands and scales
VIX_BANDS = [(15, 1.0), (25, 0.85), (35, 0.65), (float('inf'), 0.40)]

# Circuit breaker thresholds
VIX_WARNING = 30.0
VIX_CRITICAL = 40.0

# Capital shift suppression
VIX_SHIFT_SUPPRESS = 30.0
```

## Files Modified

| File | Change |
|------|--------|
| `alpaca_trading/risk/integrated_risk.py` | VIX scaling in `calculate_position_size()` Step 8 |
| `alpaca_trading/risk/risk_monitor.py` | `check_vix_level()` method, `CircuitBreakerConfig` fields |
| `alpaca_trading/risk/capital_shift.py` | VIX suppression at top of `should_shift_capital()` |
| `tests/test_openbb_integration.py` | 15 tests for VIX scaling, circuit breaker, suppression |
