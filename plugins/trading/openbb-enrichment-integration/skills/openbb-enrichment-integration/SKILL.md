---
name: openbb-enrichment-integration
description: "OpenBB Platform as parallel enrichment layer — fundamentals, FRED, earnings, news, options IV"
author: Claude Code
date: 2026-02-24
version: 4.4.0
---

# OpenBB Enrichment Integration

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-24 |
| **Goal** | Add non-OHLCV enrichment data via OpenBB Platform without touching core Alpaca pipeline |
| **Environment** | Python 3.11+, openbb-core>=4.3.0 |
| **Status** | Success (Phase 1 complete: Foundation + T1.1 + T1.3 + T2.2) |

## Context
The Alpaca_trading system had significant blind spots: no fundamental data, no macro/economic context, no real earnings calendar, no sentiment/news, no options analytics. OpenBB fills these gaps as a parallel enrichment layer.

**CRITICAL**: OpenBB NEVER touches OHLCV data. Alpaca API remains mandatory for all price/volume data.

## Architecture
```
CURRENT:
  Alpaca API (OHLCV) --> DataFetcher --> Cache --> GPU Env (59 features)
                                            |
  OpenBB Platform --> OpenBBDataProvider ---+--> Selection (sector lookups via FMP)
    |                                      +--> Risk Manager (VIX scaling)
    |                                      +--> Calendar Features (macro modulation)
    +-- FMP, FRED, Benzinga providers
```

## Verified Workflow

### 1. OpenBBDataProvider (Singleton)
```python
from alpaca_trading.data.openbb_provider import OpenBBDataProvider, get_openbb_provider

provider = get_openbb_provider()

# Check availability (True if SDK installed + any API key configured)
if provider.is_available:
    profile = provider.get_equity_profile("AAPL")    # FMP fundamentals
    vix = provider.get_latest_vix()                   # FRED VIX level
    spread = provider.get_yield_curve_spread()         # T10Y2Y
```

### 2. Key Design Choices
- **Lazy SDK init**: `_ensure_sdk()` loads OpenBB only on first method call
- **Thread-safe singleton**: `__new__` with `threading.Lock()`
- **SQLite cache**: `{cache_dir}/openbb_cache.db` with per-type TTL
- **FMP rate limiting**: 250/day free tier tracked with sliding window
- **API key priority**: `config/openbb_keys.json` > env vars > Colab Secrets
- **Graceful degradation**: All methods return `None` when unavailable

### 3. Mock Pattern for Tests (CRITICAL)
```python
# CORRECT — patch at source module (lazy import inside methods)
@patch("alpaca_trading.data.openbb_provider.get_openbb_provider")
def test_something(self, mock_get):
    mock_provider = MagicMock()
    mock_provider.is_available = True
    mock_get.return_value = mock_provider
    ...

# WRONG — fails because get_openbb_provider is not a module-level attribute
@patch("alpaca_trading.risk.integrated_risk.get_openbb_provider")
```

### 4. Colab Installation
```python
# In notebook setup cell — do NOT install openbb[all] (~100+ packages)
!pip install openbb-core openbb-equity openbb-economy openbb-news openbb-derivatives
```

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Patching at consuming module | `AttributeError: module does not have attribute` | Lazy imports aren't module-level attrs — patch at source |
| `pd.read_json(cached_string)` | FutureWarning: literal strings deprecated | Use `pd.read_json(io.StringIO(cached_string))` |
| Module-level OpenBB import | Import error when OpenBB not installed | Lazy import inside methods + `_ensure_sdk()` |
| Installing `openbb[all]` | ~100+ packages, ~500MB, dependency conflicts | Only install 4 needed extensions (~50MB) |

## Final Parameters
```python
# Cache TTL (seconds)
CACHE_TTL = {
    'equity_profile': 2592000,   # 30 days (quarterly data)
    'fred_series': 14400,        # 4 hours
    'earnings_calendar': 86400,  # 1 day
    'company_news': 300,         # 5 minutes
    'options_chain': 3600,       # 1 hour
}

# FMP rate limit
FMP_MAX_REQUESTS_PER_DAY = 250  # Free tier

# Dependencies (requirements.txt)
openbb-core>=4.3.0
openbb-equity>=4.3.0
openbb-economy>=4.3.0
openbb-news>=4.3.0
openbb-derivatives>=4.3.0
```

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `alpaca_trading/data/openbb_provider.py` | Created | Singleton provider (~500 LOC) |
| `alpaca_trading/data/__init__.py` | Modified | Added exports |
| `alpaca_trading/selection/symbol_database.py` | Modified | OpenBB sector lookups (T1.1) |
| `alpaca_trading/features/calendar_features.py` | Modified | Macro modulation (T1.3) |
| `alpaca_trading/risk/integrated_risk.py` | Modified | VIX scaling (T2.2) |
| `alpaca_trading/risk/risk_monitor.py` | Modified | VIX circuit breaker (T2.2) |
| `alpaca_trading/risk/capital_shift.py` | Modified | VIX suppression (T2.2) |
| `config/requirements.txt` | Modified | Added OpenBB deps |
| `tests/test_openbb_integration.py` | Created | 41 tests |

## Testing
41 tests across 6 test classes, all passing:
```bash
python -m pytest tests/test_openbb_integration.py -v
# Full suite: 1002 passed, 96 skipped
```

## References
- OpenBB Platform: https://docs.openbb.co/platform
- FMP API: https://site.financialmodelingprep.com/developer/docs
- FRED API: https://fred.stlouisfed.org/docs/api/fred/
