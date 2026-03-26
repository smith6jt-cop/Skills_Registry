---
name: agent-validation-review
description: "End-to-end review of agent validation system for live trader readiness. Audits gating thresholds, model health wiring, live feedback loop, notebook consistency."
author: Claude Code
date: 2026-02-21
---

# Agent Validation Review — Live Trader Readiness Audit

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-21 |
| **Goal** | Verify agent validation system end-to-end before running live trader |
| **Scope** | Training agents → gating → model health → circuit breakers → live feedback |
| **Status** | Completed — 7 fixes applied |

## Context

The agent validation system (v3.0 guardrails + v4.1.0 integration) is the quality pipeline between training and live trading. After v4.1.0 upgrades (reward redesign, model health monitoring, gating recalibration), all changes needed end-to-end verification before running the live trader.

## Audit Checklist

Systematic audit of every component in the training-to-live pipeline:

| Component | File(s) | Status | Notes |
|-----------|---------|--------|-------|
| Phase gates (v3.0) | multi_agent.py | PASS | EARLY 0-30%, MID 30-70%, LATE 70-100% |
| Entropy bounds | multi_agent.py | PASS | [0.5x, 1.5x] cumulative |
| Action types | multi_agent.py | PASS | 6 canonical + 15 aliases |
| Fitness-gated checkpoints | multi_agent.py | PASS | current > best |
| LR disabled | multi_agent.py | PASS | Returns rejection |
| Agent memory | agent_memory.py | PASS | Preserves live_* fields |
| Diagnostic summary | multi_agent.py | PASS | Exports overrides |
| Gating thresholds (gating.py) | gating.py | PASS | v4.1.0 correct |
| **BACKTEST_VALIDATOR prompt** | multi_agent.py | **BUG** | Had v3.0 thresholds (0.70/1.8) |
| **Direction threshold doc** | evaluation/CLAUDE.md | **MISMATCH** | Said 0.45, code uses 0.40 |
| **check_model_health() wiring** | live_trader.py | **BROKEN** | Never called from risk monitor |
| **LivePerformanceBridge sync** | live_trader.py | **BROKEN** | No shutdown hook |
| Notebook cost calculation | analysis.ipynb | **WRONG** | Assumed 1 API call/consultation |
| Post-training skill thresholds | SKILL.md | **STALE** | Had v2.4.5 thresholds |

## Fixes Applied

### Fix 1: BACKTEST_VALIDATOR thresholds (CRITICAL)
- **File**: `alpaca_trading/training/multi_agent.py:358-361`
- **Before**: APPROVED: Fitness ≥0.70, PF ≥1.8 (old v3.0 values — unreachable)
- **After**: APPROVED: Fitness ≥0.35, PF ≥1.4, Consistency ≥70%, MaxDD ≤10%
- **Impact**: Disabled by default but would break if enabled

### Fix 2: Direction collapse threshold doc
- **File**: `alpaca_trading/evaluation/CLAUDE.md:20`
- **Before**: `direction_accuracy < 0.45`
- **After**: `direction_accuracy < 0.40` (matches `model_health.py:62`)

### Fix 3: Wire check_model_health() into risk monitor
- **File**: `scripts/live_trader.py:2827-2833`
- **What**: Added `risk_monitor.check_model_health(health_data)` call after `update_positions()`
- **Effect**: Health alerts now trigger circuit breaker logging via unified risk system

### Fix 4: LivePerformanceBridge shutdown hook
- **File**: `scripts/live_trader.py:2867-2873`
- **What**: Added `LivePerformanceBridge().sync()` in KeyboardInterrupt handler
- **Effect**: Live performance automatically saved to agent memory on graceful shutdown

### Fix 5: Notebook cost calculation
- **File**: `notebooks/agent_validation_analysis.ipynb` cell 22
- **Before**: `consultations * $0.07` (assumes 1 API call)
- **After**: `consultations * (n_agents + 1) * $0.07` (agents + orchestrator)

### Fix 6: Post-training workflow skill
- **File**: `.skills/.../post-training-workflow/SKILL.md:43-49`
- **Before**: v2.4.5 thresholds (APPROVED: 0.70/1.8)
- **After**: v4.1.0 thresholds (APPROVED: 0.35/1.4)

### Fix 7: Documentation updates
- New CLAUDE.md files: `alpaca_trading/risk/`, `scripts/`
- Updated: root CLAUDE.md, docs/LIVE_TRADING.md, docs/TRAINING.md, docs/ARCHITECTURE.md
- All reward function references updated from v3.8.0 to v4.1.0 curriculum

## Failed Attempts (Critical)

| Attempt | Why It Failed | Lesson Learned |
|---------|---------------|----------------|
| RunPod notebook "missing import" (Fix 6 in plan) | Import was already present in cell 15 — analysis was wrong | Always read actual notebook source before assuming a fix is needed |
| Trusting gating thresholds across all files | BACKTEST_VALIDATOR prompt had separate copy | Grep ALL occurrences of thresholds — string literals in prompts can diverge from code |
| Assuming health monitoring works end-to-end | check_model_health() existed but was never called | Trace the full data flow: record → check → alert → act |
| Manual LivePerformanceBridge sync | Planned but never implemented in live_trader | "Planned" items in docs need explicit implementation tracking |

## Key Insights

1. **String literals in agent prompts can drift** — BACKTEST_VALIDATOR had hardcoded thresholds that weren't updated when gating.py was recalibrated. Always grep for threshold values across the entire codebase.

2. **Method existence ≠ method invocation** — `check_model_health()` was fully implemented with proper circuit breaker logic, but never called from the live trader. The health alerts were only logged, not fed into the risk system.

3. **"Planned" is not "done"** — The evaluation CLAUDE.md said "Live trader shutdown hook (planned)" for months. Adding explicit "TODO" tracking or verifying planned items during reviews prevents this.

4. **Notebook cost estimates compound errors** — Underestimating API calls per consultation (1 vs n_agents+1) cascades through cost-benefit analysis. The RunPod notebook already had the fix; the Colab notebook didn't.

5. **Audit checklist pattern is effective** — Systematically walking every component in the pipeline caught 6 issues that would have been missed by point fixes.

## Quality Pipeline (Production Ready)

```
Training (Colab) → Model Gating → Paper Trading → Live Trading
     │                  │                │               │
  Agent            APPROVED/         Health Monitor   LivePerformanceBridge
  Diagnostics      REVIEW/DROP      Circuit Breakers  → Agent Memory
                                    Dashboard Alerts   → Next Training
```

## Verification

```bash
# All 77 multi-agent + model health tests pass
python -m pytest tests/test_multi_agent.py tests/test_model_health.py -v

# Verify BACKTEST_VALIDATOR has v4.1.0 thresholds
grep "0.35" alpaca_trading/training/multi_agent.py | grep APPROVED

# Verify check_model_health is called in live_trader
grep "check_model_health" scripts/live_trader.py

# Verify LivePerformanceBridge in shutdown handler
grep "LivePerformanceBridge" scripts/live_trader.py
```

## References

- `alpaca_trading/training/multi_agent.py` — Agent definitions, guardrails
- `alpaca_trading/training/gating.py` — Model quality classification
- `alpaca_trading/evaluation/model_health.py` — ModelHealthMonitor
- `alpaca_trading/evaluation/live_bridge.py` — LivePerformanceBridge
- `alpaca_trading/risk/risk_monitor.py` — RealTimeRiskMonitor + circuit breakers
- `scripts/live_trader.py` — Live trading loop, shutdown handler
- Related skill: `agent-validation-integration` (v4.1.0 original implementation)
- Related skill: `agent-validation-experiment` (v3.0 guardrails A/B test)
