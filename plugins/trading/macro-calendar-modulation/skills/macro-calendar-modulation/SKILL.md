---
name: macro-calendar-modulation
description: "CPI/GDP/retail sales date awareness and VIX regime scaling for calendar features"
author: Claude Code
date: 2026-02-24
version: 4.4.0
---

# Macro Calendar Modulation

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-24 |
| **Goal** | Add CPI/GDP/retail sales awareness and VIX regime scaling to calendar features without changing obs_dim |
| **Environment** | Python 3.11+, OpenBB FRED provider |
| **Status** | Success |

## Context
Calendar features only knew FOMC + employment first Friday. No VIX level, no CPI/GDP dates. Earnings cause 5-10% average moves; CPI/GDP releases move markets significantly.

**Design constraint**: NUM_FEATURES must stay at 7 (no obs_dim change). Solution: modulate existing `hour_weight` value.

## Implementation

### Macro Event Dates
```python
CPI_RELEASE_DATES = [datetime(2024,1,11), datetime(2024,2,13), ...]  # 2024-2026
GDP_RELEASE_DATES = [datetime(2024,1,25), datetime(2024,2,28), ...]  # 2024-2026
RETAIL_SALES_DATES = [datetime(2024,1,17), datetime(2024,2,15), ...]  # 2024-2026
ALL_MACRO_EVENT_DATES = sorted(set(CPI + GDP + RETAIL))
```

### hour_weight Modulation
```python
CalendarFeatureCalculator(enable_macro_modulation=True)

# In _hour_weight():
base_weight = ... # existing market hours logic (0.1 - 1.0)

if enable_macro_modulation:
    # +20% on CPI/GDP/retail sales days
    if ts_date in self._macro_event_dates:
        base_weight *= 1.20

    # VIX regime scale (cached 4h via OpenBB FRED)
    vix_scale = _get_vix_regime_scale()  # 0.9x to 1.3x
    base_weight *= vix_scale
```

### VIX Regime Scaling
| VIX Level | Scale | Rationale |
|-----------|-------|-----------|
| < 15 | 1.0x | Normal volatility |
| 15-25 | 0.95x | Slightly reduce weight (elevated but manageable) |
| 25-35 | 1.1x | Higher volatility = more signal in price moves |
| > 35 | 1.3x | Panic = high weight (big moves, high importance) |

### Caching
- Module-level `_macro_data_cache` dict (not instance-level)
- VIX cached for 4 hours via `_fetch_vix_level()` using OpenBB FRED
- `_macro_event_dates` pre-built as set in `__init__` for O(1) lookup

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Adding new feature (earnings_proximity) | Changes obs_dim from 5900 to 6000, breaks all existing models | Modulate existing features instead |
| Instance-level VIX cache | Multiple CalendarFeatureCalculator instances waste API calls | Module-level cache shared across instances |

## Final Parameters
```python
MACRO_EVENT_BOOST = 1.20       # +20% on macro release days
VIX_REGIME_SCALES = {
    'normal': 1.0,     # VIX < 15
    'elevated': 0.95,  # VIX 15-25
    'high': 1.1,       # VIX 25-35
    'panic': 1.3,      # VIX > 35
}
VIX_CACHE_TTL = 14400  # 4 hours
```

## Files Modified

| File | Change |
|------|--------|
| `alpaca_trading/features/calendar_features.py` | Added date lists, `_fetch_vix_level()`, `_is_macro_event_day()`, `_get_vix_regime_scale()`, modulated `_hour_weight()` |
| `tests/test_openbb_integration.py` | 6 tests for macro modulation |
