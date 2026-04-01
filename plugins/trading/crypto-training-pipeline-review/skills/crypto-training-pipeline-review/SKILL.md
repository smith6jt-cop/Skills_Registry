# Crypto Training Pipeline Review (v5.4.1)

## Context
Full audit of the crypto training pipeline for efficiency, correctness, and alignment with data source policy.

## What Worked
- `_infer_asset()` in `alpaca_trading/utils.py` — canonical format-based crypto detection (checks `/USD` suffix or `USD` ending with `len > 3`). No hardcoded coin lists, no false positives.
- `prefetch_all_data()` with `use_ccxt_for_crypto=True` — routes crypto data through Coinbase/Kraken/Binance.US automatically.
- `GPUVectorizedTradingEnv` handles crypto correctly when `symbol=` is passed: PDT exemption, 24/7 calendar, 0.25% slippage.
- Skipping notebook cells 15+17 for crypto-only training — avoids ~12K equity database update.

## What Failed / Bugs Found
1. **Hardcoded crypto indicator lists** in `vectorized_env.py` — `['BTC', 'ETH', 'SOL', ...]` with substring matching. `any(c in symbol_upper for c in indicators)` false-positived on equity symbols containing those substrings. Fixed: use `_infer_asset()`.
2. **Missing CCXT routing in prefetch** — `prefetch_all_data()` in notebook cell 30 was called without `use_ccxt_for_crypto=True`. Crypto data silently came from Alpaca API. Fixed: added params.
3. **Inconsistent crypto detection** in notebook cell 19 — used `s.endswith('USD')` only, missing `BTC/USD` format. Fixed: use `_infer_asset()`.
4. **Fragmented crypto detection** — 4 separate locations with different logic (2 in vectorized_env.py, 2 in notebook). Consolidated to `_infer_asset()`.

## Recommended Approach
- **Always use `_infer_asset(symbol)` for crypto detection** — never hardcode coin indicator lists
- **Crypto-only training**: Skip cells 15+17, set `SYMBOLS_TO_TRAIN` manually in cell 19
- **First crypto run**: Set `FORCE_REFRESH = True` in cell 30 to fetch fresh CCXT data
- **Crypto slippage**: 0.25% (Alpaca Tier 1 taker fee) — auto-applied via `get_slippage_for_symbol()`

## Key Code Locations
| Component | File | Function |
|-----------|------|----------|
| Canonical detection | `alpaca_trading/utils.py:19` | `_infer_asset()` |
| Slippage routing | `alpaca_trading/gpu/vectorized_env.py` | `get_slippage_for_symbol()` |
| PDT exemption | `alpaca_trading/gpu/vectorized_env.py` | `_is_crypto()` |
| CCXT data routing | `alpaca_trading/data/caching_fetcher.py:219` | `_fetch_bars()` |
| Prefetch entry | `alpaca_trading/data/caching_fetcher.py:554` | `prefetch_all_data()` |
| Notebook prefetch | `notebooks/training.ipynb` cell 30 | `use_ccxt_for_crypto=True` |

## Test Coverage
- 52 crypto/slippage-related tests pass (0 failures)
- `tests/test_ccxt_data_routing.py` — 21 tests for CCXT routing
- `tests/test_selection_crypto_hardfilter.py` — crypto selection filters
