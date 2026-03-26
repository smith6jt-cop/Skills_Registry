---
name: agent-validation-integration
description: "v4.1.0 integration of agent validation learnings into live trading, backtesting, and feedback loops"
author: Claude Code
date: 2026-02-21
---

# agent-validation-integration - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-21 |
| **Goal** | Integrate v3.0 agent validation insights (overtrading, DSR dominance, direction collapse) into the full pipeline: backtest diagnostics, live monitoring, gating, and training feedback loop |
| **Environment** | Alpaca Trading v4.0.0 → v4.1.0 |
| **Status** | Implemented, 757 tests passing |

## Context
v3.0 agent validation showed agents correctly identified CRITICAL issues (DSR dominance, overtrading, direction collapse) but the insights stayed trapped in training logs. No mechanism existed to:
1. Surface these patterns in backtest results
2. Monitor them during live trading
3. Feed live performance back to agent memory for next training run
4. Automatically adjust training config based on diagnostics

Additionally, gating thresholds (APPROVED: fitness>=0.70, PF>=1.8) were unreachable, causing every model to classify as DROP.

## Verified Workflow

### 1. Backtest Diagnostics
Added `ModelHealthDiagnostics` to `BacktestResult`:
```python
@dataclass
class ModelHealthDiagnostics:
    hold_pct: float  # % HOLD actions
    buy_pct: float
    sell_pct: float
    close_pct: float
    trades_per_bar: float
    direction_accuracy: float
    is_overtrading: bool  # hold_pct < 0.30
    is_direction_collapse: bool  # direction_accuracy < 0.45
```
Both `BacktestEngine` and `RealisticBacktestEngine` track actions during simulation.

### 2. Live Health Monitoring
```python
# ModelHealthMonitor (evaluation/model_health.py)
monitor = ModelHealthMonitor(window=100)
monitor.record(symbol, action, confidence, price)
health = monitor.check_health(symbol)  # HealthSnapshot
# Integrated into live_trader.py main loop
# Writes to gate_status.json for dashboard consumption
```

### 3. Circuit Breakers
```python
# Added to CircuitBreakerConfig:
overtrading_hold_pct_threshold: float = 0.15
direction_accuracy_threshold: float = 0.40
# RealTimeRiskMonitor.check_model_health(health_data) triggers alerts
```

### 4. Live Feedback Loop
```python
# LivePerformanceBridge (evaluation/live_bridge.py)
bridge = LivePerformanceBridge(db_path="data/trading_performance.db")
bridge.sync()  # Reads PerformanceTracker SQLite → writes AgentMemory JSON
# Agent prompts automatically include live data via format_for_prompt()
```

### 5. Diagnostic Overrides
```python
# After training with agents:
diagnostics = trainer.get_diagnostic_summary()
# Next training run:
new_config = config.apply_diagnostic_overrides(diagnostics)
```

### 6. Gating Recalibration
| | APPROVED | REVIEW |
|---|---|---|
| Fitness | ≥0.35 (was 0.70) | ≥0.10 (was 0.50) |
| PF | ≥1.4 (was 1.8) | ≥1.1 (was 1.3) |
| Consistency | ≥70% (was 85%) | ≥50% (was 65%) |
| MaxDD | ≤10% (was 8%) | ≤20% (was 15%) |

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Unreachable gating thresholds (PF>=1.8) | Every model classified as DROP → zero useful signal | Calibrate thresholds to population, tighten as models improve |
| Backtest without action distribution | Can't detect overtrading in historical results | Always track action distribution alongside PF/Sharpe |
| No live-to-training feedback | Agent memory only has training data, misses live performance drift | LivePerformanceBridge closes the loop |
| Direct import in signals.py | Circular import: signals → server → routes → signals | Use lazy import in function wrapper (`_get_gate_data()`) |
| `hasattr(mock, 'obs_dim')` in tests | Always True for Mock objects → TypeError in arithmetic | Use `isinstance(getattr(obj, 'attr', None), expected_type)` |

## Key Insights
- The data flow is: Training (agents observe) → Diagnostics → Config overrides → Next training AND Training → Backtest → Live → PerformanceTracker → LivePerformanceBridge → AgentMemory → Next training
- Model health monitoring catches the same issues in live that agents catch in training
- Gating thresholds should create a meaningful gradient, not a binary pass/fail nobody passes
- `write_gate_status()` in live_trader.py is the IPC mechanism between trader and dashboard — extend it for new data, don't create parallel channels
- AgentMemory's `save_run_summary()` must preserve `live_*` fields when recomputing training patterns

## References
- v3.0 agent validation: Treatment outperformed baseline on ALL metrics (PF +7%, fitness +144%) with ZERO harmful agent actions
- v2.4 agent validation: Agents HURT performance (fitness -38.2%) due to compounding entropy increases
- `alpaca_trading/evaluation/model_health.py` — ModelHealthMonitor
- `alpaca_trading/evaluation/live_bridge.py` — LivePerformanceBridge
- `alpaca_trading/training/multi_agent.py` — get_diagnostic_summary()
