---
name: agent-validation-v430
description: Agent validation v4.3.0 — Make agents act effectively by disabling harmful actions, lowering gates, and injecting cross-run learning
author: Claude Code
date: 2025-02-22
---

# Agent Validation v4.3.0: Effective Agent Training

## Experiment Overview

| Field | Value |
|-------|-------|
| **Date** | Feb 22, 2025 |
| **Goal** | Make agents act on the RIGHT things (reward weights, checkpoints) while preventing harmful actions (entropy) |
| **Environment** | Google Colab A100 GPU, Python 3.10, PPO reinforcement learning |
| **Status** | Implemented, tests passing (91/91), awaiting experiment validation |
| **Supersedes** | `agent-validation-v420` (v4.2.0) |

## Context

Four agent validation experiments (Jan 31 - Feb 19) revealed a fundamental problem:

| Run | Agents Acted? | PF Change | Fitness Change | Root Cause |
|-----|---------------|-----------|----------------|------------|
| Run 1-2 | NO (all "continue") | ~0% | ~0% | Fitness gate (3 consecutive) unreachable with PPO oscillation |
| Run 3 | YES (entropy 1.3x) | **-6.3%** | **-38.2%** | Entropy increase harmful (confirmed across 2 experiments) |
| Run 4 | NO (all "continue") | +7.0% | +144% | Fitness gate still blocking; natural PPO improvement |

**Core insight**: Agents are excellent diagnosticians (identify overtrading, direction collapse, reward imbalance) but the system either blocks them from acting or gives them harmful actions. The solution: remove harmful actions, lower gates for safe actions, and inject institutional memory.

## Verified Fixes (6 changes)

### 1. Auto-save best checkpoint at every validation
**File**: `multi_agent.py` — `validation_callback()` start

Before ANY agent consultation, save checkpoint if `current_fitness > self._best_fitness`. Prevents losing peak model state between agent consultation windows.

```python
# At start of validation_callback, before agent logic:
if current_fitness > self._best_fitness:
    checkpoint_path = f"checkpoints/auto_best_{trainer.global_step}.pt"
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    # Clean up previous auto_best (only auto_best, not agent checkpoints)
    if self._best_checkpoint_path and self._best_checkpoint_path.startswith("checkpoints/auto_best_"):
        os.remove(self._best_checkpoint_path)
    trainer.save(checkpoint_path)
    self._best_fitness = current_fitness
    self._best_fitness_step = trainer.global_step
    self._best_checkpoint_path = checkpoint_path
```

### 2. Disable `adjust_entropy` action
**File**: `multi_agent.py` — `_apply_action()`, agent prompts

Two independent experiments confirm entropy adjustments hurt: v2.4 (-38.2%) and Run 3 (-38.2%). PPO's cosine schedule manages entropy optimally.

- `_apply_action()` returns early with "Disabled" message
- Kept in `VALID_ACTION_TYPES` for alias resolution (backward compat)
- All agent prompts updated: "Entropy is managed by cosine schedule. Do NOT recommend entropy changes."
- Hyperparameter Tuner prompt rewritten as diagnostic-only

### 3. Tiered fitness decline gate
**File**: `multi_agent.py` — `_is_fitness_declining(strict=True)`

```python
def _is_fitness_declining(self, strict: bool = True) -> bool:
    if not strict:  # Moderate gate for low-risk actions (reward weights)
        # 2 consecutive declines OR >30% drop from peak
        two_declining = recent[-1] < recent[-2]
        peak_drop = self._best_fitness > 0.01 and recent[-1] < self._best_fitness * 0.7
        return two_declining or peak_drop
    # Strict gate (3 consecutive) for high-risk actions (rollback, halt)
    return recent[-1] < recent[-2] and recent[-2] < recent[-3]
```

- `strict=True` (default): 3 consecutive declines — for rollback/halt
- `strict=False`: 2 consecutive OR >30% from peak — for reward weights

### 4. Lower phase gate: 30% → 15%
**File**: `multi_agent.py` — `_apply_action()` reward weights section

With phase gate at 30% and first consultation at ~31%, agents got barely 1 chance. At 15%, Reward Engineer gets 2-3 more consultation windows. Safe because reward weights are bounded (+-0.05/call, +-0.15 cumulative).

### 5. Cross-run learning in agent prompts
**File**: `multi_agent.py` — `_get_current_metrics()`, `_consult_agent_simple()`

Agent memory was accumulated but never injected into prompts. Now adds `previous_runs` to metrics:

```python
metrics['previous_runs'] = {
    'total_runs': patterns.get('total_runs', 0),
    'avg_fitness_with_agents': patterns.get('avg_fitness_with_agents', 0),
    'best_fitness_ever': patterns.get('best_fitness_ever', 0),
    'weight_adjustment_success_rate': patterns.get('weight_adjustment_success_rate', None),
    'weight_adjustments_total': patterns.get('weight_adjustments_total', 0),
    'recent_actions': [...]  # Last 3 runs' actions and fitness
}
```

Rendered as `**CROSS-RUN LEARNING**` section in consultation prompt.

### 6. Notebook: N_SEEDS=5, 200M production, updated config
**File**: `notebooks/agent_validation_runpod.ipynb`

- `N_SEEDS=5` (from 3) — needed for p<0.05 with Cohen's d ~1.0
- `TIMESTEPS=200_000_000` — production length, ~20+ validation windows
- `MultiAgentConfig(seed=seed, no_intervention_before_pct=15.0, reward_interval=8)`

## Failed Attempts

| Attempt | Why Failed | Lesson Learned |
|---------|-----------|----------------|
| Run 1-2: Standard fitness gate (3 consecutive) | PPO fitness oscillates — 3 consecutive declines almost never occurs | Need tiered gates: strict for risky actions, moderate for bounded actions |
| Run 3: Agent increases entropy 1.3x | Entropy increase destroys PPO learning (-38.2% fitness) | NEVER adjust entropy during training — cosine schedule is optimal |
| v2.4: Entropy increase experiment | Independent confirmation: also -38.2% fitness decline | Two independent failures = permanent disable, not parameter tuning |
| Agent memory without prompt injection | Data accumulated but agents never saw it — repeated same mistakes | Memory is useless unless injected into the prompt context |
| Phase gate at 30% for reward weights | First consultation at ~31% = barely 1 chance before midpoint | Bounded actions (+-0.05) deserve lower gates than unbounded ones |
| n=3 seeds for A/B experiments | p>0.12 even with Cohen's d ~1.0 | Need n=5 minimum for statistical power with training variance |

## Final Parameters

```python
# MultiAgentConfig
MultiAgentConfig(
    symbol=symbol,
    seed=seed,                          # Cross-run tracking
    no_intervention_before_pct=15.0,    # Lowered from 50% (entropy gone)
    reward_interval=8,                  # Reward Engineer primary lever
    risk_interval=5,                    # Risk Analyst frequent checks
    log_agent_responses=True,
)

# Experiment config
N_SEEDS = 5                    # Statistical power
TIMESTEPS = 200_000_000       # Production length
TRAINING_MODE = 'production'   # 2048,1024,512,256 network

# Fitness decline gate
_is_fitness_declining(strict=True)   # 3 consecutive — rollback/halt
_is_fitness_declining(strict=False)  # 2 consecutive OR >30% from peak — reward weights

# Phase gates
# entropy: DISABLED (no phase gate needed)
# reward weights: 15% progress
# rollback/halt: no phase gate (always available when fitness declining)
```

## Key Insights

- **Entropy is the most dangerous lever**: Two independent experiments confirm -38.2% fitness. Disable permanently, don't tune bounds
- **Bounded actions need lower gates**: Reward weights (+-0.05/call, +-0.15 cumulative, normalized) can't cause catastrophic damage. Gate proportionally to risk
- **Auto-best checkpoints are free insurance**: Every validation is cheap; losing peak state between agent windows is not
- **Memory without injection is dead data**: Cross-run learning only works if agents see it in their prompt
- **Statistical power matters**: n=3 wastes compute if you can't achieve significance. n=5 at 200M is the minimum viable experiment

## References

- Plan: `.claude/plans/piped-cooking-kahan.md`
- Notebook: `notebooks/agent_validation_runpod.ipynb`
- Tests: `tests/test_multi_agent.py` (91 tests, 5 GPU-only skips)
- Core file: `alpaca_trading/training/multi_agent.py`
- Agent memory: `alpaca_trading/training/agent_memory.py`
- Previous skill: `.skills/plugins/trading/agent-validation-v420/`
