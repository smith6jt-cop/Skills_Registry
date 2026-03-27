---
name: crypto-websocket-bars
description: Use Alpaca CryptoDataStream websocket for real-time crypto bars in live trading (OHLC only, volume excluded)
version: 5.4.0
status: success
date: 2026-03-27
triggers:
  - crypto websocket
  - real-time crypto bars
  - live crypto data
  - streaming crypto
---

# Crypto WebSocket Bars for Live Trading

## Problem
Live trader polled Alpaca REST API every 15 seconds for crypto bar updates. The `MarketDataStream` websocket was initialized but never queried — the stream data was wasted.

## Solution
Wire `MarketDataStream.get_latest_bar()` into `update_bars()` for crypto symbols. Append real-time websocket bars with `volume=0` (Alpaca crypto volume is platform-only, not global exchange volume).

## Architecture
```
Alpaca CryptoDataStream (websocket, background thread)
    ↓ _handle_bar() stores under both BTC/USD and BTCUSD keys
    ↓
update_bars(fetcher, symbol, current, market_stream=stream)
    ├─ REST fetch (always, for initial load + bulk history)
    └─ Stream bar append (crypto only, if newer than last REST bar)
        └─ volume=0 (exclude Alpaca platform volume)
```

## Key Implementation Details

### Symbol Normalization
- `_crypto_symbol_variants(symbol)`: Returns both `['BTC/USD', 'BTCUSD']` forms
- `subscribe_bars()`: Normalizes `BTC/USD` → `BTCUSD` for Alpaca API
- `_handle_bar()`: Stores bar under both key formats
- `get_latest_bar()`: Tries both formats for lookup

### Volume Exclusion
Alpaca crypto volume is **platform-only** (~$250k-$750k/day BTC) vs global exchange volume (~$30B). Using it would corrupt volume-based features. Setting to 0 ensures no downstream code uses unreliable volume.

### Files Modified
| File | Change |
|------|--------|
| `scripts/live_trader.py` | `update_bars()` accepts `market_stream`, appends crypto stream bars with `volume=0` |
| `alpaca_trading/data/stream.py` | `_crypto_symbol_variants()`, dual-key storage, subscribe normalization |

## Parameters
```yaml
enable_flag: --use-websocket 1
volume_for_stream_bars: 0.0  # Always zero for crypto
crypto_detection: detect_asset_type(symbol) == AssetType.CRYPTO
backwards_compatible: true  # market_stream=None preserves existing behavior
```

## What Worked
- Supplement REST with stream (not replace) — REST still provides bulk history
- Dual-key storage for symbol format mismatch (`BTC/USD` vs `BTCUSD`)
- Volume exclusion prevents data quality issues downstream

## What Failed / Avoided
- Replacing REST entirely with stream (stream only gives latest bar, not history)
- Using Alpaca crypto volume (platform-only, train/live mismatch)
- Complex stream buffer management (unnecessary — single latest bar is sufficient)
