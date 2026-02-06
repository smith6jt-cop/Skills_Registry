---
name: discounted-thompson-sampling
description: "Use when implementing Thompson sampling for non-stationary environments, handling regime changes in bandits, or tuning exploration-exploitation with decay"
author: Claude
date: 2026-02-06
version: v3.8.0
---

# Discounted Thompson Sampling - Non-Stationary Bandit

## Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-06 |
| **Goal** | Handle non-stationary reward distributions in OnlineBandit |
| **Files** | `alpaca_trading/training/online_bandit.py` |
| **Status** | Success |

## Context
Standard Thompson Sampling assumes stationary reward distributions. In financial markets,
reward distributions change with regime shifts (bull -> bear, low -> high volatility).

Old arm statistics become stale after regime changes, causing the bandit to make
decisions based on outdated information.

**Literature Source:**
- "POW-dTS: Policy Weighting via Discounted Thompson Sampling", AI Review (Jul 2025)

## Solution: Exponential Discounting

### The Discounting Mechanism
Instead of treating all observations equally, we exponentially decay past observations:

```python
# Standard Thompson Sampling
n += 1
mean = mean + (reward - mean) / n

# Discounted Thompson Sampling
effective_n = effective_n * discount + 1.0
sum_rewards = sum_rewards * discount + reward
mean = sum_rewards / effective_n
```

With `discount=0.99`:
- Observation from 100 steps ago has weight: 0.99^100 = 0.366
- Observation from 200 steps ago has weight: 0.99^200 = 0.134
- Recent observations dominate the mean estimate

### Configuration Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `discount` | 1.0 | Discount factor in (0, 1]. 1.0 = standard TS |

### Usage Examples
```python
from alpaca_trading.training.online_bandit import OnlineBandit

# Standard Thompson Sampling (original behavior)
bandit = OnlineBandit([0.5, 1.0, 1.5], discount=1.0)

# Discounted Thompson Sampling for non-stationarity
bandit = OnlineBandit([0.5, 1.0, 1.5], discount=0.99)

# More aggressive discounting for fast regime changes
bandit = OnlineBandit([0.5, 1.0, 1.5], discount=0.95)
```

### Implementation Details

#### New State Variables
```python
@dataclass
class ArmState:
    value: float
    n: int = 0                # Raw count (for diagnostics)
    mean: float = 0.0
    effective_n: float = 0.0  # Discounted count
    sum_rewards: float = 0.0  # Discounted sum
```

#### Update Logic
```python
def update(self, arm_index: int, reward: float):
    a = self.state.arms[int(arm_index)]
    reward = float(reward)

    if self.discount < 1.0:
        # Discounted Thompson Sampling
        a.effective_n = a.effective_n * self.discount + 1.0
        a.sum_rewards = a.sum_rewards * self.discount + reward
        a.mean = a.sum_rewards / max(1.0, a.effective_n)
        a.n += 1  # Keep raw count for diagnostics
    else:
        # Standard Thompson Sampling (original behavior)
        a.n += 1
        a.mean += (reward - a.mean) / a.n
        a.effective_n = float(a.n)
        a.sum_rewards = a.mean * a.n

    self._save_state()
```

#### Selection with Effective N
```python
def select_arm(self) -> int:
    samples = []
    for a in self.state.arms:
        # Use effective_n for discounted TS, or regular n for standard TS
        n_effective = a.effective_n if self.discount < 1.0 else float(a.n)
        sd = 1.0 / max(1.0, n_effective)
        samples.append(self.rng.normal(a.mean, sd))
    return int(np.argmax(samples))
```

### New Utility Methods
```python
# Get diagnostic statistics for all arms
stats = bandit.get_arm_stats()
# Returns: [{'value': 0.5, 'n': 10, 'effective_n': 8.2, 'mean': 0.65}, ...]

# Reset a specific arm after regime change
bandit.reset_arm(0)

# Reset all arms
bandit.reset_all()
```

## Why Discounting Works

### Regime Change Handling
After a regime change:
- Old observations are down-weighted automatically
- New observations quickly dominate the mean
- Bandit adapts to new reward distribution

### Exploration Recovery
With discounting:
- `effective_n` decreases over time if arm isn't pulled
- Variance `1/effective_n` increases
- Unpulled arms become exploratory again

### Backward Compatibility
With `discount=1.0` (default):
- Behavior identical to standard Thompson Sampling
- Existing state files load correctly
- New fields initialized from legacy data

## Choosing the Discount Factor

| Discount | Half-Life (steps) | Use Case |
|----------|-------------------|----------|
| 1.00 | ∞ (infinite) | Stationary rewards |
| 0.99 | ~69 | Slow regime changes (days/weeks) |
| 0.95 | ~14 | Medium regime changes (hours/days) |
| 0.90 | ~7 | Fast regime changes (minutes/hours) |

Half-life = ln(0.5) / ln(discount) ≈ 0.693 / (1 - discount) for discount near 1.

## Failed Attempts

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Sliding window (keep last N) | Memory overhead, discontinuous | Use exponential decay instead |
| Hard reset on regime change | Lose all information, cold start | Gradual decay preserves some info |
| discount=0.5 | Too aggressive, always exploring | Use discount >= 0.9 for stability |
| No effective_n tracking | Variance computation wrong | Track discounted count separately |

## Key Insights

### Discount Factor Selection
- **0.99**: Conservative, for markets with slow regime shifts
- **0.95**: Moderate, for markets with monthly regime cycles
- **0.90**: Aggressive, for highly volatile markets

### Persistence
State files now include:
- `effective_n`: Discounted observation count
- `sum_rewards`: Discounted reward sum
- `discount`: Factor used (for validation)

Old state files are automatically upgraded with backward-compatible defaults.

### Variance Scaling
In Thompson Sampling, variance scales as `1/n`.
With discounting, variance scales as `1/effective_n`.
This means:
- Older arms have higher variance (more exploration)
- Recently updated arms have lower variance (more exploitation)

## Related Skills
- `regime-aware-bandit` - Strategy-level bandit for regime-based selection
- `adaptive-predator-prey` - Regime-aware predator-prey dynamics
- `integrated-risk-manager` - Unified risk management with regime awareness
