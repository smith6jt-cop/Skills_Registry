---
name: reward-function-v410
description: "v4.1.0 reward function redesign to fix overtrading and DSR dominance"
author: Claude Code
date: 2026-02-21
---

# reward-function-v410 - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-21 |
| **Goal** | Fix overtrading (HOLD 5-12%), DSR dominance, and direction collapse identified by v3.0 agent validation experiment |
| **Environment** | Google Colab A100, v4.0.0 baseline, 50M timesteps standard mode |
| **Status** | Implemented, pending A/B validation |

## Context
v3.0 agent validation (50M timesteps, 2 symbols x 3 seeds) produced best PF=1.205 and fitness=0.153 — far below APPROVED thresholds. The Reward Engineer flagged CRITICAL issues in ALL runs:
1. DSR contributes ~35% of effective reward despite 10% weight (raw signal is systematically larger than position-size-attenuated P&L)
2. HOLD rate of 5-12% (pathological; normal is 30-70%) because frequent trading accumulates DSR reward
3. Negative direction component in late training because direction weight decays to negligible 0.05

Additionally, `_calculate_slippage()` had a Python for-loop with 2 `.item()` calls per env (2048 CUDA syncs/step), halving FPS.

## Verified Workflow

### Curriculum Weight Formula (vectorized_env.py)
```python
def _get_curriculum_weights(self, progress: float) -> dict:
    direction_w = max(0.10, 0.35 * (1.0 - progress))   # 0.35 -> 0.10 (floor raised)
    pnl_w = min(0.60, 0.15 + 0.55 * progress)           # 0.15 -> 0.60
    drawdown_w = min(0.15, 0.03 + 0.12 * progress)       # 0.03 -> 0.15
    exploration_w = max(0.02, 0.12 * (1.0 - progress))   # 0.12 -> 0.02
    dsr_w = max(0.03, 0.10 * (1.0 - progress * 0.7))     # 0.10 -> 0.03
    magnitude_w = 0.05; stop_tp_w = 0.10; slippage_w = 0.06
    # Normalize to sum=1.0
    raw = {all weights}; total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}
```

### DSR Scaling
```python
# OLD: torch.clamp(dsr * 10, -2.0, 2.0)
# NEW:
dsr_scaled = torch.clamp(dsr * 5, -1.0, 1.0)
```

### Slippage Scaling
```python
# OLD: return total_cost * 10.0  (slippage_weight=0.04)
# NEW: return total_cost * 20.0  (slippage_weight=0.06)
# Net effect: 3x stronger penalty
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Fixed DSR weight at 10% | DSR raw magnitude >> P&L raw magnitude → DSR dominates despite lower weight | Weight alone doesn't control contribution; must also control raw signal scaling |
| Direction floor at 0.05 | Direction signal vanishes in late training → negative direction reward | Floor must be ≥0.10 for meaningful gradient signal |
| Slippage weight 0.04 + 10x scale | Net slippage penalty per trade is only 0.0004-0.0012 weighted → negligible vs DSR reward from trading | Must consider end-to-end magnitude: weight * scale * typical_raw_signal |
| Non-normalized curriculum weights | Weights sum to 0.96 at start, 1.06 at end → implicit weight changes confuse analysis | Always normalize to 1.0 |
| Python for-loop in _calculate_slippage | 2 `.item()` calls per env × 1024 envs = 2048 CUDA syncs/step → halves FPS | The same anti-pattern as `_get_observations()`: always vectorize, never `.item()` in hot paths |

## Final Parameters

```yaml
# Curriculum (start -> end, raw before normalization)
direction_w: 0.35 -> 0.10  # floor=0.10, was 0.40->0.05
pnl_w: 0.15 -> 0.60         # cap=0.60, was 0.10->0.55
drawdown_w: 0.03 -> 0.15
exploration_w: 0.12 -> 0.02
dsr_w: 0.10 -> 0.03         # NEW: decays (was fixed 0.10)
magnitude_w: 0.05           # fixed
stop_tp_w: 0.10             # fixed
slippage_w: 0.06            # was 0.04

# DSR scaling
dsr_scale: 5                # was 10
dsr_clamp: [-1.0, 1.0]      # was [-2.0, 2.0]

# Slippage
slippage_scale: 20           # was 10
direction_threshold: 0.002   # was 0.003
```

## Key Insights
- The effective contribution of a reward component is `weight * scale * typical_raw_magnitude` — not just the weight
- DSR responds to every step's return, producing consistently large signals. P&L is attenuated by position_size_pct (2.6-7.9%). This asymmetry meant DSR dominated despite lower weight
- Overtrading is rational when DSR reward from trading > slippage penalty from trading. Must make slippage > DSR for unnecessary trades
- Normalization prevents implicit weight drift as training progresses and component weights change
- Direction floor of 0.10 (not 0.05) ensures the model always gets meaningful gradient about directional accuracy

## References
- Bengio et al. (2009) "Curriculum Learning", ICML
- Corwin & Schultz (2012) "A Simple Way to Estimate Bid-Ask Spreads from Daily High and Low Prices"
- Moody & Saffell (1998) "Reinforcement Learning for Trading Systems and Portfolios"
- v3.0 agent validation experiment results (agent_validation_results.zip)
