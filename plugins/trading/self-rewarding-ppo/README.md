# Self-Rewarding PPO Training Pattern

## Problem
Standard PPO uses only extrinsic rewards from the environment. This can lead to suboptimal exploration and doesn't incentivize the agent to improve its prediction accuracy over time.

## Solution
Add intrinsic rewards based on prediction improvement and differential Sharpe ratio. This "self-rewarding" mechanism encourages the agent to learn better trading strategies.

## Research Basis
- Paper: "Self-Rewarding Mechanism for DRL Trading" (MDPI Mathematics, 2024)
- Results: Sharpe 3.93 → 4.43 (+12.7%), Returns 816% → 1124% (+37.7%)
- URL: https://www.mdpi.com/2227-7390/12/24/4020

## Implementation

### Config Parameters
```python
@dataclass
class NativePPOConfig:
    use_self_reward: bool = True
    self_reward_alpha: float = 0.1   # Accuracy improvement weight
    self_reward_beta: float = 0.2    # Differential Sharpe weight
    self_reward_baseline_window: int = 1000
    self_reward_warmup_steps: int = 10000
```

### SelfRewardComputer Class
```python
class SelfRewardComputer:
    def __init__(self, alpha=0.1, beta=0.2, baseline_window=1000):
        self.alpha = alpha
        self.beta = beta
        self.baseline_window = baseline_window
        self.outcome_history = []
        self.baseline_accuracy = 0.5
        self.current_accuracy = 0.5
        # EMA for differential Sharpe
        self.ema_return = 0.0
        self.ema_return_sq = 0.0
        self.ema_decay = 0.99

    def update_outcomes(self, actions, rewards):
        """Track prediction accuracy over time."""
        for action, reward in zip(actions, rewards):
            correct = (action == 1 and reward > 0) or \
                      (action == 2 and reward > 0) or \
                      (action == 0 and abs(reward) < 0.001)
            self.outcome_history.append((action, reward, correct))

        # Update baseline (first half) and current (recent) accuracies
        if len(self.outcome_history) >= self.baseline_window:
            self.baseline_accuracy = ...
            self.current_accuracy = ...

    def compute_intrinsic_reward(self, base_rewards):
        """Add intrinsic reward to base rewards."""
        if len(self.outcome_history) < self.baseline_window:
            return base_rewards

        # Component 1: Accuracy improvement
        accuracy_improvement = (current - baseline) / baseline

        # Component 2: Differential Sharpe ratio
        variance = self.ema_return_sq - self.ema_return ** 2
        sharpe_component = self.ema_return / sqrt(variance)

        # Combine
        intrinsic = alpha * accuracy_improvement + beta * sharpe_component

        # Scale relative to base reward magnitude
        return base_rewards + intrinsic * base_rewards.abs().mean()
```

### Integration in Training Loop
```python
# After rollout collection, before GAE computation
if (
    self.self_reward_computer is not None and
    self.global_step >= self.config.self_reward_warmup_steps
):
    # Update outcome tracking
    self.self_reward_computer.update_outcomes(
        self.buffer.actions, self.buffer.rewards
    )

    # Apply intrinsic rewards
    self.buffer.rewards = self.self_reward_computer.compute_intrinsic_reward(
        self.buffer.rewards
    )
```

## Key Components

### 1. Accuracy Improvement Reward
- Tracks if predictions are getting better over time
- Compares current accuracy to baseline accuracy
- Encourages learning, not just exploitation

### 2. Differential Sharpe Ratio
- Smooth measure of risk-adjusted performance
- Uses EMA for stability
- Optimizes Sharpe ratio directly

### 3. Warmup Period
- Wait for baseline_window outcomes before activating
- Prevents noise in early training

## Logging
```python
if self.self_reward_computer is not None:
    sr_stats = self.self_reward_computer.get_stats()
    print(f"Self-Reward | Baseline: {baseline:.1%} | "
          f"Current: {current:.1%} | Improve: {improve:+.1%}")
```

## Files Modified
- `alpaca_trading/gpu/ppo_trainer_native.py`

## Expected Impact
- Sharpe improvement: 10-20%
- Better exploration during training
- More stable convergence
