# Trading System Enhancements (v3.0.1)

## Summary
Enhanced trading system with complete Alpaca Trading API coverage, candlestick visualization for backtests, and WebSocket streaming for live trading.

## Components

### 1. Extended Broker API (`alpaca_trading/trading/broker.py`)

Added 12+ new methods for complete Alpaca Trading API coverage:

**Order Management:**
```python
# Modify existing order without cancel+resubmit race condition
broker.replace_order(order_id, qty=20, limit_price=155.50)
```

**Account Activities:**
```python
# Get activity history (fills, dividends, etc.)
activities = broker.get_account_activities(activity_types=['FILL', 'DIV'])
```

**Account Configuration:**
```python
# Get/set account settings
config = broker.get_account_configurations()
broker.set_account_configurations(fractional_trading=True)
```

**Watchlist Management:**
```python
# Full CRUD for watchlists
watchlists = broker.get_watchlists()
wl = broker.create_watchlist("My Watchlist", ["AAPL", "GOOGL"])
broker.add_to_watchlist(wl['id'], "MSFT")
broker.remove_from_watchlist(wl['id'], "AAPL")
broker.delete_watchlist(wl['id'])
```

**Corporate Actions:**
```python
from datetime import date, timedelta
# Get dividends, splits, etc.
actions = broker.get_corporate_actions(
    ca_types=['dividend', 'split'],
    since=date.today() - timedelta(days=90),
    until=date.today()
)
```

**Asset Discovery:**
```python
# List all tradable assets
assets = broker.list_assets(status='active', asset_class='us_equity')
crypto = broker.list_assets(asset_class='crypto')
```

### 2. Candlestick Visualization (`alpaca_trading/visualization/backtest_charts.py`)

Generate candlestick charts with entry/exit markers from backtest results:

**Static Charts (mplfinance):**
```python
from alpaca_trading.visualization.backtest_charts import plot_candlestick_with_trades

# After running backtest
result = engine.run(data)
plot_candlestick_with_trades(result, save_path="backtest_chart.png")
```

**Interactive Charts (plotly):**
```python
from alpaca_trading.visualization.backtest_charts import plot_interactive_backtest

fig = plot_interactive_backtest(result)
fig.write_html("backtest_interactive.html")
# Or display in Jupyter: fig.show()
```

**Using BacktestResult method:**
```python
# Static chart
result.plot_with_candlesticks(save_path="chart.png", interactive=False)

# Interactive chart
fig = result.plot_with_candlesticks(interactive=True)
```

**Features:**
- Entry markers (green triangles up)
- Exit markers (red triangles down)
- Equity curve subplot
- Drawdown subplot
- Volume bars
- P&L distribution analysis

### 3. WebSocket Streaming (`alpaca_trading/data/stream.py`)

Real-time market data streaming for live trading:

**Basic Usage:**
```python
from alpaca_trading.data.stream import MarketDataStream, StreamConfig

# Initialize
config = StreamConfig(feed='iex', reconnect_delay=5.0)
stream = MarketDataStream(api_key, secret_key, config)

# Subscribe with callback
def on_bar(symbol, bar):
    print(f"{symbol}: {bar.close}")

stream.subscribe_bars(['AAPL', 'GOOGL', 'BTCUSD'], callback=on_bar)
stream.start()

# Later...
stream.stop()
```

**Live Trader Integration:**
```bash
# Enable WebSocket streaming (instead of polling)
python scripts/live_trader.py --paper 1 --use-websocket 1

# Default (polling mode)
python scripts/live_trader.py --paper 1 --use-websocket 0
```

**Features:**
- Automatic reconnection with exponential backoff
- Separate equity and crypto streams
- Symbol-specific callbacks
- Connection status monitoring
- Thread-safe operation

## Dependencies

Added to `config/requirements.txt`:
```
mplfinance>=0.12.10b0
plotly>=5.18.0
```

## Tests

- `tests/test_broker_extended.py` - 29 tests for new broker methods
- `tests/test_backtest_visualization.py` - 18 tests for candlestick charts
- `tests/test_stream.py` - 41 tests for WebSocket streaming

Run tests:
```bash
pytest tests/test_broker_extended.py tests/test_backtest_visualization.py tests/test_stream.py -v
```

## API Compatibility Notes

Some broker methods require specific versions of alpaca-py:
- `get_account_activities()` requires `GetAccountActivitiesRequest`
- `set_account_configurations()` requires `PatchAccountConfigurationsRequest`
- `get_corporate_actions()` requires non-None `ca_types`, `since`, `until` parameters

If these classes aren't available in your alpaca-py version, the methods will return empty results and log a warning.

## Related Files

- `alpaca_trading/trading/broker.py` - Extended broker API
- `alpaca_trading/data/stream.py` - WebSocket streaming client
- `alpaca_trading/visualization/backtest_charts.py` - Candlestick visualization
- `alpaca_trading/backtest/engine.py` - BacktestResult with ohlc_data
- `scripts/live_trader.py` - --use-websocket flag
