---
name: agent-validation-experiment
description: "A/B testing infrastructure for validating Claude agent integration in RL training. Trigger when: (1) planning agent validation, (2) analyzing agent effectiveness, (3) deciding whether to enable agents, (4) understanding agent cost-benefit, (5) reviewing agent prompt design, (6) debugging agent response parsing, (7) notebook API key loading issues, (8) agent guardrails and phase gates."
author: Claude Code
date: 2026-02-18
version: v3.0
---

# Agent Validation Experiment

## Overview

| Item | Details |
|------|---------|
| **Date** | 2026-02-18 |
| **Goal** | Determine if Claude agent integration improves model predictive power |
| **Status** | v2.4 showed agents HURT performance (fitness -38.2%, PF -6.3%). **v3.0 implements guardrails**: phase gates, cumulative entropy bounds, fitness-gated checkpoints, rollback, institutional knowledge, agent memory persistence. Awaiting re-run. |
| **Files** | `scripts/agent_validation_experiment.py`, `notebooks/agent_validation_analysis.ipynb`, `alpaca_trading/training/multi_agent.py`, `alpaca_trading/training/agent_memory.py`, `alpaca_trading/gpu/vectorized_env.py`, `tests/test_multi_agent.py` |

## The Question

**Does integrating Claude agents during RL training provide measurable improvement to model quality?**

The codebase has ~4,744 lines of agent integration code. Before relying on it:
1. We need empirical evidence that agents help
2. We need to quantify the cost-benefit tradeoff

## v2.4 Experiment Results (Agents HURT Performance)

| Metric | Baseline | Treatment | Change |
|--------|----------|-----------|--------|
| Profit Factor | 1.191 | 1.115 | **-6.3%** |
| Fitness Score | 0.110 | 0.068 | **-38.2%** |
| Reward-to-Risk | 0.075 | 0.047 | **-37.1%** |
| Final Equity | 1.014 | 1.009 | -0.5% |

AAPL hit hardest (-12.9% PF, -51.6% fitness); GOOGL roughly neutral (+1.3% PF). Cohen's d > 0.9 (large effect) but p-values > 0.12 (underpowered with n=6).

### Top 5 Root Causes

1. **COMPOUNDING ENTROPY INCREASES DESTROY LEARNED POLICIES**: Every treatment model received 1-2 entropy increases at ~63% progress. GOOGL got cumulative 1.56x. No mechanism to decrease or revert.
2. **AGENTS MISDIAGNOSE NORMAL TRAINING DYNAMICS**: Agents flagged normal PPO behavior (PF < 1.0 early, oscillation) as problems and intervened.
3. **ENTROPY APPLIED AT WRONG TIMES**: At 63% progress, agents prescribed entropy INCREASE when the correct action was nothing or DECREASE.
4. **CHECKPOINT SPAM**: 4-5 per model, never used. Each save causes GPU stall.
5. **LR ADJUSTMENTS ARE SILENT NO-OPS**: `lr_scheduler.step()` (line 986) overwrites agent LR changes on the very next PPO update. `current_entropy_coef` has NO scheduler, so entropy changes persist and compound.

## v3.0 Guardrails (Current Implementation)

### Phase Gates
- **EARLY (0-30%)**: No intervention allowed. PF < 1.0 is NORMAL. All consultations skipped.
- **MID (30-70%)**: Entropy DECREASES only. Prefer continue unless 3+ validation decline trend.
- **LATE (70-100%)**: NEVER increase entropy. Continue only. Halt only if fitness collapsed >50%.

### Cumulative Entropy Bounds
- Track `_cumulative_entropy_multiplier` across all adjustments
- Bounds: `[0.5x, 1.5x]` of initial value (configurable)
- Initial entropy captured on first `_apply_action()` call

### Fitness-Gated Checkpoints
- Only save when `current_fitness > self._best_fitness`
- Track `_best_checkpoint_path` for rollback
- Skip with message when fitness hasn't improved

### Rollback Action
- New action type: `rollback` (aliases: `restore_best`, `revert`, `load_checkpoint`)
- Loads best checkpoint via `trainer.load(path)`
- Resets entropy to initial value
- Resets cumulative multiplier to 1.0

### LR Adjustments Disabled
- `adjust_lr` always returns rejection message: "LR managed by cosine schedule"
- Prevents agents from wasting reasoning on no-op actions

### Institutional Knowledge
- 5 hardcoded lessons from v2.4 injected into every consultation
- Includes: entropy increases harmful, PPO oscillation normal, LR managed by scheduler, checkpoints need fitness improvement, HOLD 30-70% is normal

### Agent Memory Persistence
- `AgentMemory` class in `agent_memory.py` stores `RunSummary` per symbol
- Tracks: action outcomes, entropy_increase_success_rate, avg fitness with/without agents
- Loaded as context into agent prompts so agents don't repeat mistakes
- JSON files in configurable `memory_dir`

### Reward Engineer → READ-ONLY
- Diagnostic analyst only, always recommends "continue"
- No weight change recommendations (impossible at runtime anyway)

### Reduced Consultation Intervals
- hyperparam: 8 (was 5), risk: 5 (was 3), reward: 15 (was 10)
- Total ~6 consultations/model (was ~9)

## Experimental Design

### A/B Test Protocol

| Group | Description | Agent Integration |
|-------|-------------|-------------------|
| **Baseline (Control)** | Standard NativePPOTrainer | None |
| **Treatment** | MultiAgentTrainer with agents | Hyperparameter Tuner, Risk Analyst, Reward Engineer |

### Matching Protocol
- Same symbols in both groups
- Same random seeds for reproducibility
- Same training timesteps (50M recommended, sufficient for A/B comparison)
- Same environment configuration (v4.0.0)
- Training mode: 'standard' (6M-param 3-layer network, faster per step than 'production')

### Sample Size
- Minimum: 12 runs total (2 symbols x 3 seeds x 2 groups) — 6 pairs for paired t-test
- Recommended: 20 runs per group (4 symbols x 5 seeds)
- 3 seeds sufficient to detect large effects with paired design

### Statistical Methods (v3.0)
- **Welch's t-test** (`equal_var=False`): More appropriate for small samples with potentially unequal variances
- **Bonferroni correction**: p < 0.05/6 = 0.0083 for 6 metrics (controls family-wise error rate)

## Success Criteria

| Metric | Minimum Improvement | Statistical Significance |
|--------|---------------------|--------------------------|
| Profit Factor | +0.2 (e.g., 1.5 → 1.7) | p < 0.0083 (Bonferroni) |
| Sharpe/Reward-to-Risk | +0.1 | p < 0.0083 |
| Max Drawdown | -2% (e.g., 12% → 10%) | p < 0.10 |
| Consistency | +3% (e.g., 62% → 65%) | p < 0.0083 |

### Decision Matrix

| Result | Action |
|--------|--------|
| 2+ metrics significantly improved | Activate agents in production |
| 1 metric improved, others neutral | Use agents in advisory mode only |
| No significant improvement | Disable agents, save ~$350/year |
| Performance degraded | Do NOT use agents |

## v3.0 Verification Criteria

1. Treatment fitness >= Baseline fitness (agents don't hurt)
2. Zero entropy increases applied after 30% progress
3. Agent rejection rate > 50% (gates working)
4. Checkpoint count reduced from ~4-5 to ~0-2 per model
5. Cumulative entropy multiplier stays within [0.5, 1.5] bounds
6. Memory files created in `data/agent_memory/` with action outcome tracking

## Running the Experiment

### Prerequisites
1. Google Colab with A100 GPU
2. `ANTHROPIC_API_KEY` environment variable set
3. Alpaca API credentials configured
4. Pre-cached market data in Google Drive

### MultiAgentConfig (v3.0)

```python
agent_config = MultiAgentConfig(
    enable_hyperparameter_tuner=True,
    enable_risk_analyst=True,
    enable_reward_engineer=True,
    enable_data_monitor=False,
    enable_backtest_validator=False,
    max_consultations_per_run=50,
    log_agent_responses=True,
    # v3.0: Reduced intervals
    hyperparam_interval=8,
    risk_interval=5,
    reward_interval=15,
    # v3.0: Phase gates
    no_intervention_before_pct=30.0,
    entropy_decrease_only_after_pct=50.0,
    # v3.0: Cumulative entropy bounds
    max_cumulative_entropy_multiplier=1.5,
    min_cumulative_entropy_multiplier=0.5,
    # v3.0: Agent memory
    memory_dir='data/agent_memory',
    symbol=symbol,
)
```

## Resource Requirements

### Cost-Optimized (v3.0 — recommended)
| Resource | Estimate |
|----------|----------|
| Training runs | 12 (6 baseline + 6 treatment) |
| Compute time | ~3-4 hours on A100 (~53-83 CU) with pre-computed obs |
| API costs | ~$15 (6 treatment runs x ~$2.50/run with reduced consultations) |
| Storage | ~200 MB (models + logs + memory) |

## Failed Attempts

| Attempt | Date | What Happened | Root Cause | Fix |
|---------|------|--------------|------------|-----|
| v1.0 | 2026-02-01 | Zero agent consultations across all 10 treatment runs. | **validation_interval mismatch**: With 50M timesteps, only 4-5 validation cycles happened. Agent intervals rarely aligned. | `train_with_guidance()` auto-adjusts `validation_interval` to ensure ≥15 cycles. |
| v1.1 | 2026-02-04 | "Parent directory checkpoints does not exist" error. | **Missing directory creation** in `_apply_action()`. | Added `os.makedirs(parent, exist_ok=True)` before save. |
| v1.2 | 2026-02-05 | All HP tuner recommendations identical. Risk Analyst fixated on KL. Wrong weights in RE prompt. | **7 systemic problems**: No per-run context, fixed DD threshold, no component breakdown, KL over-emphasized. | v2.0: Rewritten prompts, per-component metrics, adaptive drawdown. |
| v2.0 | 2026-02-07 | +11.6% PF (p=0.009) but 5 bugs: ~50% RA parse failures, invalid grace period type, unknown action types. | **5 code bugs**: max_tokens too low, grace period→invalid type, no validation. | v2.1: 5-strategy parser, VALID_ACTION_TYPES, max_tokens→1500. |
| v2.1 | 2026-02-10 | Notebook 401 errors, quick validation >10 min. | **API key parsing**: Naive line reading sent "Key:" as API key ID. | Use `_read_keys_from_file()`. Quick val: 2M steps, val_interval=5. |
| v2.2 | 2026-02-16 | 200M production mode = ~29 CU/model, 580 CU total. Exceeded budget. | **Compute cost too high**. | 50M standard mode, 3 seeds, incremental save/resume. ~70-95 CU. |
| v2.3 | 2026-02-17 | 50M standard still ~162 CU. 116 min/model (7,200 FPS). | **GPU env bottleneck**: `.item()` calls, Python loops, 50+ tensor ops. | v2.4: Pre-computed obs via `unfold()`. 15K-25K FPS, ~53-83 CU. |
| v2.4 | 2026-02-18 | **Agents HURT performance**: Fitness -38.2%, PF -6.3%. Entropy increases compounded, agents misdiagnosed normal dynamics, LR changes are no-ops. | **5 root causes**: Compounding entropy, misdiagnosis, wrong timing, checkpoint spam, LR no-ops. | v3.0: Phase gates, cumulative bounds [0.5, 1.5], fitness-gated checkpoints, rollback, LR disabled, institutional knowledge, agent memory, RE read-only. |

## Critical Lessons Learned

### NEVER increase entropy after 30% training progress
Entropy increases at 63% progress undo 30M+ steps of learned policy. The model has developed trading strategies by this point; increasing exploration forces it to "forget" them.

### PPO oscillation is NORMAL — agents must not react
Profit factor naturally oscillates during training. A single validation with PF < 1.0 is not a crisis. Only 3+ consecutive declining validations are meaningful.

### LR adjustments via agents are impossible
The cosine LR scheduler calls `lr_scheduler.step()` every PPO update, overwriting any agent modification to `param_group['lr']`. Only `current_entropy_coef` persists because it has no scheduler.

### Checkpoints are useless without rollback
v2.4 saved 4-5 checkpoints per model, none were ever loaded. Checkpoints only have value if paired with a rollback mechanism triggered by fitness decline.

### Default action must be "continue"
The v2.4 experiment proved that intervention is destructive. 80%+ of consultations should result in "continue". Active intervention should be rare (<20%).

## Implementation Details (v2.4 - Pre-computed Observation Windows)

### The Bottleneck

`_get_observations()` achieved only **7,200 FPS** on A100 due to:
1. **`.item()` calls** (3 per step): Forces CUDA sync
2. **Python for-loop** (100 iterations): 100 tiny GPU kernels
3. **50+ individual tensor ops**: Each indicator sliced/padded/normalized separately

### The Fix

`_precompute_observation_windows()` at init pre-computes all features via `unfold()` (~30 MB). Rewritten `_get_observations()`: ~120 lines (was ~350), zero `.item()`, zero Python loops, ~10 gather ops.

### Per-env indexing bug fix
Old code used `env_ids[0].item()` for ALL envs — wrong observations for recently-reset envs. New code uses per-env index tensors.

---

## References

- `scripts/agent_validation_experiment.py` - Experiment runner
- `notebooks/agent_validation_analysis.ipynb` - Statistical analysis (Welch's t-test + Bonferroni)
- `alpaca_trading/training/multi_agent.py` - Agent integration (v3.0: guardrails, phase gates, rollback)
- `alpaca_trading/training/agent_memory.py` - Persistent cross-run learning (v3.0)
- `alpaca_trading/gpu/vectorized_env.py` - Component metrics + adaptive drawdown + pre-computed obs
- `alpaca_trading/gpu/ppo_trainer_native.py` - Metrics pipeline, LR scheduler
- `tests/test_multi_agent.py` - 62 tests: prompt correctness, metrics flow, phase gates, cumulative tracking, fitness-gated checkpoints, rollback, LR disabled, agent memory, institutional knowledge
- `.skills/plugins/trading/multi-agent-integration/` - Integration documentation
