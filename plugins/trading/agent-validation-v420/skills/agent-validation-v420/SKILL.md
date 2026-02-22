---
name: agent-validation-v420
description: "Agent validation overhaul: reward weight overrides, fitness decline gate, pinned data, staged experiments"
author: Claude Code
date: 2026-02-22
version: v4.2.0
---

# Agent Validation v4.2.0

| Item | Details |
|------|---------|
| Date | 2026-02-22 |
| Goal | Stop agents from burning money ($150+ wasted) — give them effective levers, pin data for reproducibility, validate cheaply before scaling |
| Environment | Google Colab A100, Alpaca Trading v4.2.0, Python 3.10 |
| Status | Implementation complete, awaiting Colab validation |

## Context

Three agent validation experiments were run (Jan 31, Feb 18, Feb 19 2026), burning $150+ in GPU time with zero useful results. Root cause: agents had only ONE lever (entropy), LR adjustment was a confirmed no-op (cosine scheduler overwrites), and the Reward Engineer was explicitly read-only. Agents could diagnose overtrading, DSR dominance, and direction collapse but literally could not fix anything. Additionally, training data wasn't pinned between experiments, causing baseline drift of 76% between runs.

## What Was Fixed (5 Fixes)

### Fix 1: Reward Weight Override Mechanism
**Files**: `vectorized_env.py`, `multi_agent.py`

Agents can now adjust reward component weights mid-training via `set_reward_weight_override()`:
- Per-call bound: +/-0.05 per component
- Cumulative bound: +/-0.15 per component
- Floor: 0.01 (no component can be zeroed)
- Always re-normalized to sum=1.0
- Valid components: `{direction, magnitude, pnl, stop_tp, exploration, slippage, drawdown, dsr}`

Reward Engineer prompt rewritten from read-only diagnostic to actionable:
```python
# When to adjust (ONLY when clear evidence exists):
# - Overtrading (HOLD < 20%): increase slippage +0.02 to +0.05
# - DSR dominating P&L: decrease dsr -0.02 to -0.04
# - Direction collapse (< 40% accuracy): increase direction +0.02 to +0.05
# - P&L stagnant while other metrics OK: increase pnl +0.02 to +0.05
```

### Fix 2: Fitness Decline Gate
**File**: `multi_agent.py`

Requires 3 consecutive fitness declines before ANY intervention (entropy or weight changes). Prevents agents from intervening when training is going well.

```python
def _is_fitness_declining(self) -> bool:
    if len(self._validation_history) < 3:
        return False
    recent = [v.get('fitness_score', 0) for v in self._validation_history[-3:]]
    return recent[-1] < recent[-2] and recent[-2] < recent[-3]
```

### Fix 3: Tightened Entropy Bounds + Phase Gates
- Entropy bounds: [0.75x, 1.25x] (was [0.5x, 1.5x])
- Entropy phase gate: 50% (was 30%)
- Reward weight phase gate: 30% (new — earlier access since this is the main lever)
- LR adjustment: logged skip (was logged rejection with `_agent_rejections` increment)

### Fix 4: Pinned Training Data
**File**: `agent_validation_analysis.ipynb`

```python
DATA_START = datetime(2025, 2, 1, tzinfo=tz.UTC)
DATA_END = datetime(2026, 2, 14, tzinfo=tz.UTC)  # Fixed cutoff
```
Historical data is immutable — same dates = same bars = same results for same seed. Data is sliced after `prefetch_all_data()` (function doesn't support start/end params directly).

### Fix 5: Agent Memory Improvements
**File**: `agent_memory.py`, `multi_agent.py`

- `MultiAgentConfig.seed` field — passed through to `save_run_summary()` (was always 0)
- Weight override history tracked per run (overrides + resulting fitness)
- `_compute_patterns()` aggregates weight adjustment success rate across runs
- Baseline runs saved to agent memory for proper comparison

## Staged Experiment Execution

| Stage | Cost | Time | What it proves |
|-------|------|------|----------------|
| 0. Local tests | $0 | 5 min | Code works, bounds enforced, plumbing connected |
| 1. Smoke (1 sym, 1 seed, 2M) | ~$0.50 | ~5 min | Agents can adjust weights, pinned data works |
| 2. Quick A/B (2 sym, 2 seeds, 10M) | ~$5 | ~30 min | Agents help or don't hurt |
| 3. Full (2 sym, 5 seeds, 50M) | ~$40 | ~20 hrs | Statistical significance |

**Stop after any stage that fails.** Fix and re-run that stage, don't escalate.

## Failed Attempts (Previous Experiments)

| Experiment | Date | What Happened | Root Cause |
|-----------|------|---------------|------------|
| Jan 31 2026 | Treatment = baseline metrics | Agents weren't connected to training loop | Plumbing error |
| Feb 18 2026 | Agents took 5-9 actions, fitness **-38.2%** | Only lever was entropy. Agents made aggressive changes that hurt | Single lever (entropy), no bounds, no fitness gate |
| Feb 19 2026 | Agents took 0 actions | Phase gates blocked everything, but baseline degraded 76% from Feb 18 | Training data not pinned, agents too conservative |
| All runs | Reward Engineer diagnosed problems correctly but recommended "continue" | Reward Engineer was explicitly read-only | Design flaw — see problem, can't fix it |
| All runs | LR adjustments attempted but no effect | Cosine scheduler overwrites LR every step | LR adjustment is a no-op |
| All runs | Agent memory records seed=0 for all runs | Seed not passed through MultiAgentConfig | Bug in plumbing |

## Key Parameters

```python
# MultiAgentConfig (v4.2.0)
MultiAgentConfig(
    symbol=symbol,
    seed=seed,                                      # NEW: seed tracking
    enable_hyperparameter_tuner=False,               # Disabled — consolidated into Reward Engineer
    enable_reward_engineer=True,                     # NOW ACTIONABLE (was read-only)
    reward_interval=8,                               # Increased frequency
    max_cumulative_entropy_multiplier=1.25,           # Tightened from 1.5
    min_cumulative_entropy_multiplier=0.75,           # Tightened from 0.5
    no_intervention_before_pct=50.0,                  # Raised from 30.0
)
```

## Tests Added (26 new)
- `TestRewardWeightOverrideBounds` (5): per-call clamp, cumulative clamp, negative clamp, invalid component, valid components
- `TestRewardWeightOverrideNormalization` (4): sum-to-one, floor prevents zero, weights shift
- `TestAdjustRewardWeightsAction` (6): action in valid set, aliases, apply action, phase gate, fitness gate, empty changes
- `TestFitnessDecliningGate` (6): requires 3 snapshots, declining/improving/flat, only last 3, entropy blocked
- `TestLRAdjustmentNoop` (2): skipped not rejected, doesn't count
- `TestAgentMemoryWeightTracking` (2): patterns with weight data, seed in config

## References
- Plan: `~/.claude/plans/fancy-giggling-puffin.md`
- Notebook: `notebooks/agent_validation_analysis.ipynb` (v2.0.0)
- Tests: `tests/test_multi_agent.py` (87 passed, 5 skipped)
- Key files: `vectorized_env.py`, `multi_agent.py`, `agent_memory.py`
