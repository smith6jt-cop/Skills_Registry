# VaR Unit Mismatch Fix

**Version:** v5.4.4 (2026-04-03)
**Status:** Fixed and deployed
**Project:** Alpaca_Trading

## Problem

`RealTimeRiskMonitor.update_positions()` in `risk_monitor.py:100-119` compared `calculate_portfolio_var()` output directly against `max_portfolio_var` (0.02 = 2%). But `calculate_portfolio_var()` returns **dollars** (~$14.85 for a $9.5K position), not a percentage. Result: `14.85 > 0.02` → 742x "breach" → 30-minute circuit breaker → repeat forever → all trading frozen.

Over 7 days of paper trading, this single bug caused **209 circuit breaker activations** and prevented the equity models (32-37% accuracy, well above random) from trading at all.

## Root Cause

```python
# risk_monitor.py:100-101 (BEFORE — BUG)
portfolio_var = self.risk_manager.calculate_portfolio_var(current_positions)
if portfolio_var > self.risk_manager.limits.max_portfolio_var:  # $14.85 > 0.02 → always true
```

The correct pattern already existed 100 lines away in `portfolio_risk.py:200-205`:
```python
# portfolio_risk.py:200-205 (CORRECT)
portfolio_var_dollars = self.calculate_portfolio_var(test_portfolio)
portfolio_var_pct = portfolio_var_dollars / account_value  # $14.85 / $99,000 = 0.00015
if portfolio_var_pct > self.limits.max_portfolio_var:  # 0.015% < 2% → OK
```

## Fix

```python
# risk_monitor.py:100-101 (AFTER — FIXED)
portfolio_var_dollars = self.risk_manager.calculate_portfolio_var(current_positions)
portfolio_var = portfolio_var_dollars / current_account_value if current_account_value > 0 else 0.0
if portfolio_var > self.risk_manager.limits.max_portfolio_var:
```

`current_account_value` was already available as a parameter to `update_positions()`.

## General Pattern

**When adding risk threshold checks, always verify units match:**
- `calculate_portfolio_var()` → returns dollars
- `max_portfolio_var` → configured as percentage (0.02 = 2%)
- Must normalize: `dollars / account_value` → percentage

## Files Modified
- `alpaca_trading/risk/risk_monitor.py`: Lines 100-119

## Detection Heuristics
If you see circuit breakers firing with extreme multipliers (>100x), check for unit mismatches between calculated values and configured limits. The ratio itself (`742.8x limit`) is the clue — real VaR breaches are typically 1-5x.
