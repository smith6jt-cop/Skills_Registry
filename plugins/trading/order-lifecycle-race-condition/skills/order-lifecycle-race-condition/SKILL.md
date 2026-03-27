# Order Lifecycle Race Condition

## Problem
After v5.3.3 deployment, the live trader exhibited two critical order execution bugs:

1. **Flatten loop (182 retries)**: After successfully flattening CNM (221.5 shares), the system retried the flatten 182 times over ~45 minutes, each failing with "fractional orders cannot be sold short".

2. **Double-buy**: WST received two buy orders (14.8 shares each = 29.6 total) instead of one, because the system submitted a second buy on the next 15-second loop.

## Root Cause

**Two independent sub-bugs combined:**

### Sub-bug A: Missing `return` in exception handlers
`decide_and_trade_optimized()` had two exception handlers (stop-loss exit at line ~1450, flatten exit at line ~1474) that caught Alpaca API errors but did NOT return. After the except block, execution fell through to entry logic below.

### Sub-bug B: Immediate post-trade reconciliation race condition
At line 2720, immediately after detecting a trade was executed, `reconcile_positions()` queried the broker. Market orders take 100ms-2s to fill at Alpaca. If the broker hadn't processed the fill yet, the broker still showed the OLD position state. Reconciliation then overwrote the optimistic internal state with stale broker data.

**Flatten loop sequence:**
1. Flatten order submitted → internal state reset to side=0
2. `reconcile_positions()` queries broker → order pending → broker shows old position (side=1)
3. Reconciliation overwrites internal state back to side=1
4. Next loop (15s): flatten condition still met → tries to flatten zero shares → "fractional orders cannot be sold short"
5. Exception caught without return → falls through → state unchanged from reconciliation (side=1)
6. Repeats 182 times until periodic 30-min reconciliation finally sees broker has no position

**Double-buy sequence:**
1. Buy order submitted → internal state set to side=1
2. `reconcile_positions()` queries broker → order pending → broker shows no position
3. Reconciliation clears internal state to side=0
4. Next loop: model generates buy again → second order submitted

## What Worked

1. **`return` after exception handlers**: Simple one-line fix prevents fall-through
2. **60-second per-symbol cooldown**: `TRADE_RECONCILIATION_COOLDOWN_SECONDS = 60` — after a trade, reconciliation skips that symbol for 60 seconds
3. **`skip_symbols` parameter on `reconcile_positions()`**: Clean interface for excluding recently-traded symbols
4. **`last_trade_time` field on `PositionState`**: Per-symbol tracking without global state
5. **Periodic reconciliation preserved**: The 30-min reconciliation still runs (respecting cooldowns)

## What Failed / Would Have Failed

- **Removing reconciliation entirely**: Violates "broker is source of truth" guardrail
- **Global trade cooldown**: A trade in WST shouldn't prevent reconciliation of CNM
- **Tracking pending orders**: Over-engineering — the 60s cooldown is sufficient for market orders
- **Reducing loop frequency**: Would hurt responsiveness for all operations, not just reconciliation

## Recommended Parameters

```python
TRADE_RECONCILIATION_COOLDOWN_SECONDS = 60  # 4 loop iterations for order fill
# Per-symbol: state.last_trade_time = datetime.now() after each trade
# Periodic reconciliation: every 120 loops (~30 min), skip symbols within cooldown
```

## Key Files
- `scripts/live_trader.py` — lines ~1450, ~1474, ~2720, ~2840
- `PositionState` dataclass — `last_trade_time` field

## Verification
- `tests/test_v534_fixes.py::TestExitExceptionReturns` — verify return after exceptions
- `tests/test_v534_fixes.py::TestReconciliationCooldown` — verify skip_symbols works
- CNM no longer produces "Flatten failed" error spam
- WST trades show single buy per signal (not doubled)
