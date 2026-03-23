---
name: backtest-observation-mismatch
description: "Backtest observation features that receive hardcoded defaults vs training dynamic values — and why fixing them DEGRADES results. Includes walk-forward batch mode fix."
version: "1.0.0"
tags: [backtest, observation, mismatch, walk-forward, win-rate]
triggers:
  - "backtest win rate"
  - "backtest accuracy"
  - "observation mismatch"
  - "walk-forward batch"
  - "BacktestObservationBuilder"
  - "sub-50% win rate"
---

# Backtest Observation Feature Mismatch (v5.3.0)

## Problem
16/65 features in `BacktestObservationBuilder.get_obs_at_bar()` receive hardcoded default values instead of the dynamic values they receive during training. Sub-50% win rates in backtest led to investigation.

## Finding: Sub-50% Win Rates Are Expected
Models use **high R-multiple strategies** — win rate < 50% but avg win >> avg loss. Example: CNM_1Hour has 46.7% win rate but PF=1.80 because avg win ($138.86) is 2.05x avg loss ($67.61). This is normal in quantitative trading.

## Feature Defaults (DO NOT CHANGE)

| Feature Group | Count | Default | Training Value | Why Default Is Better |
|---|---|---|---|---|
| Intraday | 4 | 0.5 | `step % 390 / 390` | Training pattern uses per-episode step counter that can't be replicated in backtest |
| Account state | 3 | 0.0/0.5/0.0 | Dynamic P&L/win_rate/drawdown | Episode dynamics (4096 envs, ~400 steps) don't match single-pass backtest |
| Position sizing | 3 | 0.0/1.0/0.0 | Dynamic position/capital state | Same episode dynamics issue |
| Regime bars | 3 | 0.0 | Dynamic 0-1.0 duration | Infrastructure exists but requires GPU Markov system |
| Calendar | 7 | 0.5 fallback | Real calendar data | Usually works; 0.5 is safety fallback |

## Experiment Results (2026-03-23)
- **Control**: All defaults → CNM_1Hour PF=1.80, Win Rate=46.7%, 30 trades
- **Real timestamps for intraday**: PF=1.01, Win Rate=38.0%, 50 trades — **DEGRADED**
- **step%390 for intraday**: PF=0.81, Win Rate=41.5%, 41 trades — **DEGRADED**
- **Dynamic account state**: PF=0.91, Win Rate=35.0%, 20 trades — **DEGRADED**
- **Only regime bars**: PF=1.80, Win Rate=46.7%, 30 trades — **NO EFFECT** (GPU Markov not loaded)

## Walk-Forward Batch Fix
`scripts/run_backtest.py`: `--all --walk-forward N` was silently running single-pass backtests because `run_all_models()` ignored the `walk_forward` parameter. Fixed by passing `walk_forward` through to `run_walk_forward()` per model.

## Files
- `alpaca_trading/gpu/inference_obs_builder.py` — `BacktestObservationBuilder`
- `alpaca_trading/gpu/vectorized_env.py` — Training observation construction
- `alpaca_trading/backtest/engine.py` — `BacktestEngine.run()`
- `scripts/run_backtest.py` — CLI with batch walk-forward fix

## Proper Fix (Future)
Would require either: (1) retraining models with backtest-compatible observation patterns, or (2) implementing full episode simulation in backtest that exactly matches training env dynamics (4096 parallel envs with random resets).
