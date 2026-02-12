---
name: dashboard-cohesion-fixes
description: "Integration fixes between backtest engine, FastAPI dashboard, Vue.js frontend, and live trader"
author: Claude Code
date: 2025-02-11
---

# Dashboard Cohesion Fixes - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2025-02-11 |
| **Goal** | Fix 13 integration bugs and test gaps between the backtest engine, web dashboard (FastAPI + Vue.js), and live trader so all three components work cohesively |
| **Environment** | Windows 10, Python 3.11, FastAPI, Vue.js 3, pytest |
| **Status** | Success - 818 tests passing (93 new), 0 failures |

## Context
The backtest engine, FastAPI web dashboard, and live trader were architecturally sound individually but had specific wiring issues at the seams where they communicate. The gate_status.json file serves as IPC between `scripts/live_trader.py` (writer) and the dashboard API (reader), but many fields the dashboard expected were never written. The broker API wrapper had parameter name mismatches, and there was zero test coverage for the API layer and live trader decision logic.

## Verified Workflow

### Phase 1: Critical Bugs
1. Fix `broker.submit_order(order_type=...)` to `broker.submit_order(type=...)` in `alpaca_trading/api/routes/orders.py` (3 locations)
2. Extend `GateStatus` dataclass with `price`, `regime`, `magnitude` fields
3. Extend `write_gate_status()` with `market_regime`, `buy_threshold`, `sell_threshold` params
4. Update `compute_gate_status_from_result()` to populate new fields from feats dict
5. Replace duplicate `load_gate_status()` in `signals.py` with lazy import from `server.py`

### Phase 2: Functional Completeness
6. Add "New Trade" button wiring in `App.vue` for the existing but unreachable `TradeControls` modal
7. Add incremental log broadcasting in `DataBroadcaster` via `fetch_logs` callback
8. Improve empty-state handling in `AccountChart.vue`

### Phase 3: Tests (93 new tests)
9. `tests/test_api_server.py` - 41 tests: FastAPI TestClient for all REST routes + WebSocket
10. `tests/test_live_trader.py` - 22 tests: GateStatus, write_gate_status, compute_gate_status_from_result
11. `tests/test_backtest.py` - 30 tests: TestRealisticBacktestEngine (GARCH sizing, drawdown, guardrails)

### Phase 4: Cleanup
12. Replace hardcoded `obs_dim in (4700, 4800, ...)` with dynamic `get_target_features_from_obs_dim()`
13. Centralize PnL cost constants from `DashboardConfig` defaults

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Module-level import `from ..server import get_gate_status_data` in signals.py | Circular import: signals.py -> server.py -> routes/__init__.py -> signals.py | Use lazy import inside a function wrapper: `def _get_gate_data(): from ..server import get_gate_status_data; return get_gate_status_data()` |
| Using `replace_all=True` to rename `get_gate_status_data()` -> `_get_gate_data()` in signals.py | Also replaced the call *inside* the wrapper function, creating infinite recursion | Never use replace_all when the old string appears in the replacement's own definition |
| `hasattr(model, 'obs_dim')` to guard obs_dim arithmetic in backtest engine | Mock objects return True for `hasattr` on ANY attribute; `mock.obs_dim` is a Mock, not int | Use `isinstance(getattr(model, 'obs_dim', None), int)` to guard against both missing attributes and Mock objects |
| Patching `alpaca_trading.api.routes.market.get_market_session` in tests | Import wasn't resolved at module level due to lazy loading | Patch at the source: `alpaca_trading.market_hours.get_market_session` |
| Using `@pytest.mark.asyncio` for ConnectionManager tests | Methods being tested were synchronous; pytest-asyncio not properly configured | Check if methods under test are truly async before marking tests |
| Loss streak cooldown test: checking cooldown expired at bar 200 | Loss streak of 3 was still active, re-triggering cooldown at bar 200 | Insert a win (`_update_win_rate_tracking(True)`) to reset streak before testing past-cooldown behavior |

## Final Parameters

### Gate Status JSON Structure (write_gate_status output)
```json
{
  "updated_at": "2025-02-11T12:00:00Z",
  "market_regime": {"regime": "trending", "volatility": "medium", "garch_forecast": 0.18},
  "buy_threshold": 0.55,
  "sell_threshold": -0.45,
  "symbols": {
    "AAPL": {
      "signal": 1,
      "confidence": 0.72,
      "final_status": "READY",
      "block_reason": "",
      "price": 155.50,
      "regime": "normal",
      "magnitude": 0.025,
      "updated_at": "2025-02-11T12:00:00Z",
      "gates": {
        "confidence": {"pass": true, "reason": null},
        "win_rate": {"pass": true, "reason": null}
      }
    }
  }
}
```

### Dynamic obs_dim Detection Pattern
```python
from ..gpu.inference_obs_builder import get_target_features_from_obs_dim as _get_features

is_native_model = False
if hasattr(model, 'obs_dim') and isinstance(getattr(model, 'obs_dim', None), int):
    try:
        _get_features(model.obs_dim, window)
        is_native_model = True
    except (ValueError, KeyError):
        pass
```

### Lazy Import Pattern for Circular Dependencies
```python
def _get_gate_data() -> dict:
    """Lazy import to avoid circular dependency with server module."""
    from ..server import get_gate_status_data
    return get_gate_status_data()
```

## Key Insights
- Gate status JSON is the critical IPC seam - any field mismatch between writer (live_trader) and reader (API routes) silently defaults to zeros/neutrals
- `broker.submit_order()` uses `type=` not `order_type=` - the Alpaca SDK parameter names don't match REST conventions
- FastAPI circular imports are common when routes need server-level functions; lazy imports inside helper functions are the cleanest fix
- Mock objects in Python have all attributes, making `hasattr` checks unreliable - always use `isinstance` for type guards
- WebSocket log broadcasting works best as incremental push (track `_last_log_count`, send only new entries)
- The `RealisticBacktestEngine` closely mirrors live trader behavior but had zero tests - highest-risk coverage gap
- Pre-existing tests numbered ~725; adding 93 new tests brought total to 818 with no regressions

## References
- Plan file: `.claude/plans/playful-soaring-sutherland.md`
- Related skills: `dashboard-pnl-visualization`, `broker-order-limitations`, `trading-gates-pattern-filter`, `drawdown-guardrails-pattern`
- Files modified: `orders.py`, `signals.py`, `server.py`, `websocket.py`, `live_trader.py`, `engine.py`, `App.vue`, `AccountChart.vue`, `websocket.js`
- New test files: `tests/test_api_server.py` (41 tests), `tests/test_live_trader.py` (22 tests), `tests/test_backtest.py` (+30 tests)
