# Inverse ETF Proxy for Crypto Shorts

**Version:** v5.4.4 (2026-04-03)
**Status:** Implemented, untested in live trading
**Project:** Alpaca_Trading

## Problem

Crypto short selling is not supported on most retail exchanges (Alpaca, CCXT). When RL models trained on BTC/USD or ETH/USD predict a price decline (SELL signal), the signal was silently dropped — wasting half the model's predictive capability.

## Solution

Route crypto SELL signals to inverse ETFs: buying an inverse ETF is economically equivalent to shorting the underlying asset.

### Proxy Mapping
```python
INVERSE_ETF_PROXIES = {
    "BTC/USD": "BITI",   # ProShares Short Bitcoin ETF (-1x daily)
    "ETH/USD": "SETH",   # ProShares Short Ether ETF (-1x daily)
}
```

Other available options (not used):
- SBIT: ProShares UltraShort Bitcoin (-2x, higher volume ~2.8M/day)
- ETHD: ProShares UltraShort Ether (-2x)
- BTCZ: T-Rex 2X Inverse Bitcoin (-2x)

### Architecture

1. **Signal detection** (`decide_and_trade_optimized()`, line ~1625): When crypto SELL detected, return `skip_reason="inverse_etf_signal"` with proxy info instead of `"crypto_no_short"`
2. **Proxy execution** (main loop, after `decide_and_trade_optimized`): Check stock market hours → fetch proxy price → calculate position size → submit BUY order via Alpaca (equity routing)
3. **Signal reversal** (main loop): When crypto signal becomes BUY/HOLD, close inverse ETF position with market sell
4. **EOD flatten**: Proxy positions in `states` dict are automatically flattened by existing shutdown loop
5. **Gate status**: Reports `"PROXY"` with `action_taken="inverse_etf:BITI"`

### Key Design Decisions

- **-1x not -2x**: Using unlevered inverse ETFs to match model's prediction magnitude without amplification
- **Half allocation**: Conservative sizing (50% of remaining capital × drawdown scale) since inverse ETFs have tracking error
- **Equity routing**: Inverse ETFs route through Alpaca (not CCXT) automatically since `detect_asset_type("BITI")` returns STOCK
- **Market hours constraint**: Inverse ETFs only trade 9:30-4:00 ET. Off-hours crypto SELL signals are logged and skipped
- **No stop/TP on proxy**: Model-learned stop/TP distances are calibrated for spot crypto, not ETF prices. Exit on signal reversal only.

### Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Market hours gap | Can't act on crypto SELL during nights/weekends | Accept missed signals; crypto recovers fast |
| Tracking error | -1x daily ≠ -1x cumulative over multi-day holds | Use as day-trade instrument; EOD flatten |
| Liquidity | BITI ~2.15M shares/day, SETH lower | Position sizes well within liquidity |
| Expense ratios | BITI 1.03%, SETH 0.95% | Negligible for short holding periods |

### Files Modified
- `scripts/live_trader.py`: INVERSE_ETF_PROXIES config, get_latest_price(), proxy execution in main loop, gate status reporting
- `scripts/CLAUDE.md`: Documentation added

### Testing Needed
- Paper trading with crypto SELL signals during market hours
- Verify BITI/SETH available on Alpaca paper account
- Verify position reconciliation covers proxy symbols
- Verify EOD flatten includes proxy positions

## Failed Attempts

| Attempt | Outcome | Lesson |
|---------|---------|--------|
| Modifying `decide_and_trade_optimized()` directly to execute proxy trades | Blocked — function doesn't have access to `states` dict | Return signal from function, handle in main loop where `states` is accessible |
| Using `broker.data_client.get_stock_snapshot()` for price lookup | `Broker` class doesn't have `data_client` | Use `fetcher.get_latest_bars(symbol, count=1)` instead |
