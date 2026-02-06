---
name: differential-sharpe-ratio
description: "Use when implementing risk-adjusted rewards, discussing Sharpe ratio in RL training, or tuning reward components for risk awareness"
author: Claude
date: 2026-02-06
version: v3.8.0
---

# Differential Sharpe Ratio (DSR) - Risk-Adjusted Reward Component

## Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-06 |
| **Goal** | Add risk-adjusted reward component using online Sharpe ratio estimation |
| **Files** | `alpaca_trading/gpu/vectorized_env.py` |
| **Status** | Success |

## Context
The reward function in v3.3.0 had 7 components but lacked explicit risk-adjusted metrics.
Literature review (2024-2025) identified Differential Sharpe Ratio (DSR) as a key technique
for online risk-adjusted learning in financial RL.

**Literature Sources:**
- Moody & Saffell (1998): "Learning to trade via direct reinforcement"
- arXiv 2506.04358: "A Risk-Aware RL Reward for Financial Trading"
- SAGE Journals 2025 (CPPO): Risk-adjusted PPO achieving Sharpe ~2.15

## Solution: Differential Sharpe Ratio

### The DSR Formula
DSR provides an incremental, online measure of risk-adjusted returns:

```
A_t = A_{t-1} + eta * (R_t - A_{t-1})       # EMA of returns
B_t = B_{t-1} + eta * (R_t^2 - B_{t-1})     # EMA of squared returns
DSR_t = (B_t * delta_A - 0.5 * A_t * delta_B) / (B_t - A_t^2)^1.5
```

Where:
- `R_t` = return at time t
- `eta` = EMA decay rate (default 0.01)
- `A` = exponential moving average of returns (tracks mean)
- `B` = exponential moving average of squared returns (tracks variance)
- `delta_A` = R_t - A_{t-1} (innovation in mean)
- `delta_B` = R_t^2 - B_{t-1} (innovation in variance)

### Configuration Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `dsr_weight` | 0.10 | Weight in combined reward (10%) |
| `dsr_eta` | 0.01 | EMA decay rate for A and B statistics |

### Implementation

#### State Variables
```python
# In GPUEnvConfig dataclass (~line 496)
dsr_weight: float = 0.10             # Risk-adjusted return component
dsr_eta: float = 0.01                # EMA decay for DSR statistics

# In GPUVectorizedTradingEnv.__init__ (~line 1006)
self.dsr_A = torch.zeros(self.n_envs, dtype=self.dtype, device=self.device)
self.dsr_B = torch.zeros(self.n_envs, dtype=self.dtype, device=self.device)
```

#### Reset Logic
```python
# In reset() method (~line 1098)
self.dsr_A[env_ids] = 0.0
self.dsr_B[env_ids] = 0.0
```

#### DSR Calculation Method
```python
def _calculate_dsr_reward(self, returns: Tensor) -> Tensor:
    eta = self.config.dsr_eta

    # Compute deltas before update
    delta_A = returns - self.dsr_A
    delta_B = returns ** 2 - self.dsr_B

    # Update EMA statistics
    A_new = self.dsr_A + eta * delta_A
    B_new = self.dsr_B + eta * delta_B

    # Variance with stability floor
    variance = torch.clamp(B_new - A_new ** 2, min=1e-8)

    # DSR formula
    numerator = B_new * delta_A - 0.5 * A_new * delta_B
    denominator = variance ** 1.5
    dsr = numerator / (denominator + 1e-8)

    # Update state
    self.dsr_A = A_new
    self.dsr_B = B_new

    # Scale and clamp
    return torch.clamp(dsr * 10, -2.0, 2.0)
```

#### Integration in Reward Function
```python
# In _calculate_rewards() (~line 2252)
dsr_reward = self._calculate_dsr_reward(raw_pnl)

# Combined reward (8 components as of v3.8.0)
reward = (
    self.config.direction_weight * direction_reward +
    self.config.magnitude_weight * magnitude_reward +
    self.config.pnl_weight * pnl_reward +
    self.config.stop_tp_weight * stop_tp_reward +
    self.config.exploration_weight * exploration_bonus +
    self.config.slippage_weight * slippage_penalty +
    self.config.drawdown_penalty_weight * drawdown_penalty +
    self.config.dsr_weight * dsr_reward  # NEW in v3.8.0
) * risk_adjustment
```

## Why DSR Works

### Online Estimation
Unlike batch Sharpe ratio (requires full episode), DSR:
- Updates incrementally at each step
- Provides immediate feedback during training
- No need to wait for episode completion

### Risk Adjustment
DSR penalizes volatile returns:
- High mean, low variance = high DSR (good)
- High mean, high variance = moderate DSR (risky)
- Low mean = low or negative DSR (bad)

### Gradient Signal
DSR provides gradient signal for:
- Reducing position size in volatile periods
- Maintaining consistent returns over erratic wins
- Avoiding large drawdowns even with occasional big wins

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Batch Sharpe in reward | Required full episode, delayed feedback | Use incremental DSR instead |
| High eta (0.1) | Too reactive, noisy signal | Use lower eta (0.01) for stability |
| No variance floor | Division by zero in low-vol periods | Add min=1e-8 clamp |
| Unscaled DSR | Values too small relative to other components | Scale by 10x before clamp |

## Key Insights

### Weight Balance
At 10% weight, DSR provides meaningful signal without dominating:
- P&L (40%) remains primary objective
- DSR (10%) adds risk awareness
- Other components maintain their roles

### EMA Decay Rate
The `eta=0.01` default means:
- ~63% weight on last 100 observations
- Smooth signal that adapts to regime changes
- Not too reactive to individual outliers

### Scaling
Raw DSR values are typically small (-0.1 to 0.1), so we:
1. Multiply by 10 to amplify signal
2. Clamp to [-2, 2] to prevent extreme values
3. Handle NaN/Inf from numerical edge cases

## Related Skills
- `reward-function-v330` - Base reward function design
- `integrated-risk-manager` - Unified risk sizing
- `adaptive-predator-prey` - Regime-aware dynamics
