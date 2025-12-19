# Regime-Aware Thompson Sampling Pattern

## Problem
Standard Thompson Sampling maintains a single set of priors for all contexts. But in trading, optimal parameters differ by market regime - what works in a bull market may not work in a bear market.

## Solution
Maintain separate Beta distribution priors per macro regime (bull/sideways/bear), allowing the bandit to learn different optimal parameters for different market conditions.

## Implementation

### RegimeAwareOnlineBandit Class
```python
class RegimeAwareOnlineBandit:
    DEFAULT_REGIMES = ['bull', 'sideways', 'bear']

    def __init__(
        self,
        arm_values: List[float],
        regime_names: Optional[List[str]] = None,
        state_path: str = "models/regime_bandit.json",
        use_beta: bool = True,  # Beta distribution for win/loss
    ):
        self.arm_values = arm_values
        self.regime_names = regime_names or self.DEFAULT_REGIMES
        self.state = self._load_state()

    def select_arm(self, regime: Optional[str] = None) -> int:
        """Select arm using Thompson Sampling for the given regime."""
        arms = self._get_arms(regime)
        samples = []
        for arm in arms:
            if self.use_beta:
                sample = self.rng.beta(arm.alpha, arm.beta)
            else:
                sample = self.rng.normal(arm.mean, 1/max(1, arm.n))
            samples.append(sample)
        return int(np.argmax(samples))

    def update(self, arm_index: int, reward: float,
               regime: Optional[str] = None, is_win: Optional[bool] = None):
        """Update arm statistics for the given regime."""
        arm = self._get_arms(regime)[arm_index]
        arm.n += 1
        arm.mean += (reward - arm.mean) / arm.n

        # Update Beta distribution
        if is_win is None:
            is_win = reward > 0
        if is_win:
            arm.alpha += 1
        else:
            arm.beta += 1

        # Also update global (with lower weight) for cross-regime learning
        global_arm = self.state.global_arms[arm_index]
        global_arm.alpha += 0.5 if is_win else 0
        global_arm.beta += 0.5 if not is_win else 0

        self._save_state()
```

### State Structure
```python
@dataclass
class RegimeArmState:
    value: float
    n: int = 0
    mean: float = 0.0
    alpha: float = 1.0  # Wins + prior
    beta: float = 1.0   # Losses + prior

@dataclass
class RegimeBanditState:
    regimes: Dict[str, List[RegimeArmState]]  # Per-regime arms
    global_arms: List[RegimeArmState]          # Fallback
```

## Key Features

### 1. Regime-Specific Priors
- Each regime has its own Beta distribution parameters
- Learning is isolated to the relevant context

### 2. Cross-Regime Learning
- Global arms also updated (with lower weight)
- Provides fallback for unknown regimes
- Prevents cold-start issues

### 3. Win Rate Tracking
```python
def get_arm_stats(self, regime: Optional[str] = None):
    arms = self._get_arms(regime)
    return [{
        'arm_index': i,
        'value': arm.value,
        'n': arm.n,
        'win_rate': arm.alpha / (arm.alpha + arm.beta),
    } for i, arm in enumerate(arms)]
```

### 4. State Persistence
- Saves to JSON for continuity across sessions
- Handles version migration (missing regimes)

## Usage
```python
bandit = RegimeAwareOnlineBandit(
    arm_values=[0.5, 0.7, 0.9],  # e.g., confidence thresholds
    regime_names=['bull', 'sideways', 'bear']
)

# During trading
current_regime = detect_regime(market_data)  # 'bull', 'sideways', 'bear'
arm_idx = bandit.select_arm(regime=current_regime)
param_value = bandit.arm_value(arm_idx)

# After trade completes
bandit.update(arm_idx, reward=pnl, regime=current_regime)
```

## Research Basis
- Multi-context Thompson Sampling shows 5-10% better parameter selection
- Different regimes favor different parameters (e.g., momentum vs mean-reversion)
- Beta distribution is optimal for binary (win/loss) outcomes

## Files Modified
- `alpaca_trading/online_bandit.py`

## Helper Methods
```python
# Get best arm deterministically (for evaluation)
best = bandit.get_best_arm(regime='bull')

# Reset a regime if market dynamics change
bandit.reset_regime(regime='bear')
```
