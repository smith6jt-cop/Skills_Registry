# CVaR Risk Gates Pattern

## Problem
VaR (Value at Risk) only captures the threshold loss at a given confidence level, but doesn't tell you how bad losses could be beyond that threshold. This leads to underestimation of tail risk.

## Solution
Add CVaR (Conditional Value at Risk / Expected Shortfall) as an additional risk gate alongside VaR. CVaR measures the expected loss given that the loss exceeds VaR.

## Implementation

### 1. Extend RiskLimits dataclass
```python
@dataclass(frozen=True)
class RiskLimits:
    max_portfolio_var: float = 0.02   # 2% daily VaR limit
    max_portfolio_cvar: float = 0.03  # 3% daily CVaR limit (must be >= VaR)
    # ... other fields

    def __post_init__(self):
        if self.max_portfolio_cvar < self.max_portfolio_var:
            raise ValueError(
                f"max_portfolio_cvar ({self.max_portfolio_cvar}) should be >= "
                f"max_portfolio_var ({self.max_portfolio_var})"
            )
```

### 2. Calculate CVaR
```python
def calculate_portfolio_cvar(self, positions: Dict[str, float],
                            confidence: float = 0.05) -> float:
    """Calculate portfolio Conditional Value at Risk (Expected Shortfall)."""
    from scipy.stats import norm

    # Calculate portfolio volatility (same as VaR)
    portfolio_vol = self._calculate_portfolio_volatility(positions)

    # CVaR for normal distribution: CVaR = sigma * phi(Phi^-1(alpha)) / alpha
    z_alpha = norm.ppf(confidence)
    phi_z = norm.pdf(z_alpha)
    cvar = portfolio_vol * phi_z / confidence

    return float(abs(cvar))
```

### 3. Add CVaR gate to position checks
```python
def check_position_limits(...) -> Tuple[bool, str]:
    # ... existing VaR check ...

    # CVaR check
    projected_cvar = self.calculate_portfolio_cvar(projected_positions)
    cvar_pct = projected_cvar / account_value
    if cvar_pct > self.limits.max_portfolio_cvar:
        return False, f"Portfolio CVaR {cvar_pct:.1%} exceeds {self.limits.max_portfolio_cvar:.1%}"
```

## Key Properties
- CVaR >= VaR (always, by definition)
- For normal distribution: CVaR ≈ 1.25 * VaR at 5% confidence
- CVaR is coherent (VaR is not) - better for portfolio optimization
- More conservative than VaR for tail events

## Research Basis
- CVaR-based Risk Parity outperforms volatility-based risk parity
- Better tail risk protection (~5% improvement)
- CPPO (CVaR-constrained PPO) shows 20-30% tail risk reduction

## Files Modified
- `alpaca_trading/risk/portfolio_risk.py`
- `tests/test_portfolio_risk.py`

## Testing
```python
def test_cvar_greater_than_var(self):
    """CVaR should always be >= VaR for the same confidence level."""
    var_value = mgr.calculate_portfolio_var(positions)
    cvar_value = mgr.calculate_portfolio_cvar(positions)
    assert cvar_value >= var_value
```
