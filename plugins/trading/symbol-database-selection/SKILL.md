# Symbol Database Selection Pattern

## Problem
Universe selection was impractically slow because it tried to download 4 years of hourly historical data for all ~12,000 tradable symbols on Alpaca. This took hours and often hit rate limits.

Additionally, the API key lookup was broken - it only searched for key files in the project root, not in the `config/` directory where they actually lived. This caused the system to fall back to a hardcoded list of only ~98 symbols.

## Solution - Multi-Stage Selection Pipeline

### Stage 1: Database Update (~2 minutes)
Use Alpaca's **snapshot API** to get current price, volume, and volatility for ALL 12k+ symbols. This is fast because:
- Snapshot API returns bulk data (up to 1000 symbols per request)
- No historical data needed
- Results stored in SQLite for instant queries

```python
from alpaca_trading.selection import SymbolDatabase

db = SymbolDatabase(db_path='data/symbol_database.db', keys_file='API_key.txt')
db.update_equities(verbose=True)  # ~12k symbols in ~2 min
db.update_crypto(verbose=True)    # ~60 symbols in seconds
db.print_summary()
```

### Stage 2: Pre-filter (instant)
Use SQL queries to filter candidates by volume, price, and other criteria. No API calls needed.

```python
# Get equities with >$1M daily volume, price $5-$10000
candidates = db.get_candidates(
    asset_types=['equity'],
    min_volume_usd=1_000_000,
    min_price=5.0,
    max_price=10000,
)
# Returns ~3,600 candidates (from 12k total)
```

### Stage 3: Download Historical Data
Only download 4 years of hourly data for the ~3,600 pre-filtered candidates, not all 12k.

### Stage 4: Deep Analysis
Run Hurst exponent, GARCH, half-life, and trainability scoring only on candidates with data.

## Typical Performance

| Stage | Time | Symbols |
|-------|------|---------|
| 1. Database update | ~2 min | 12,325 |
| 2. Pre-filter | instant | ~3,600 |
| 3. Data download | varies | ~3,600 |
| 4. Deep analysis | ~30 min | ~3,600 |

**Before**: Hours to scan ~100 symbols (broken key lookup)
**After**: ~35 min to scan 12k symbols and select best 10

## Key Files

- `alpaca_trading/selection/symbol_database.py` - SQLite database + snapshot API
- `alpaca_trading/selection/empirical_config.py` - Market-stats-based config generation
- `alpaca_trading/data/pipeline.py` - Fixed API key lookup (check config/ directory)
- `notebooks/training.ipynb` - Integrated database-driven selection (v2.9.0)

## Empirical Thresholds

The database enables empirical threshold selection based on actual market data:

```python
# Get median values from database
thresholds = db.get_thresholds(volume_percentile=50)
# Returns: {'min_volume_equity': 180432, 'price_p25': 0.64, 'price_p75': 370.02, ...}
```

Typical candidate counts at various volume thresholds:
| Volume | Candidates |
|--------|------------|
| $100k/day | ~7,000 |
| $500k/day | ~4,500 |
| $1M/day | ~3,600 |
| $5M/day | ~1,800 |
| $10M/day | ~1,300 |

## Root Cause Fix

The original bug was in `alpaca_trading/data/pipeline.py`:

```python
# BEFORE (broken): Only checked project root
for keys_file in ["API_key.txt", "API_key_Paper.txt"]:
    ...

# AFTER (fixed): Also checks config/ directory
for keys_file in [
    "API_key.txt", "API_key_Paper.txt",
    "config/API_key.txt", "config/API_key_100kPaper.txt", ...
]:
    ...
```

This fix allowed the TradingClient to be created, which enabled fetching all 12,325 tradable equities instead of falling back to the 98-symbol hardcoded list.
