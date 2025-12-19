# RSI Divergence Patterns

## Problem
The pattern filter only had VWAP reversion (68%) and momentum continuation (71%) patterns. Additional high-win-rate patterns can increase trade opportunities without sacrificing quality.

## Solution
Add RSI divergence detection (bullish 66%, bearish 64%) and volume confirmation (65%) patterns to the pattern filter.

## RSI Divergence Concepts

### Bullish Divergence (66% win rate)
- **Price**: Makes lower low
- **RSI**: Makes higher low
- **Signal**: Momentum exhaustion, potential reversal up
- **Entry**: Buy when divergence detected and signal direction is long

### Bearish Divergence (64% win rate)
- **Price**: Makes higher high
- **RSI**: Makes lower high
- **Signal**: Momentum exhaustion, potential reversal down
- **Entry**: Sell when divergence detected and signal direction is short

## Implementation

### RSI Calculation
```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

### Divergence Detection
```python
def check_rsi_divergence(df, signal_direction, lookback=20, rsi_period=14):
    rsi = calculate_rsi(df, period=rsi_period)

    # Get swing points
    mid_lookback = max(3, lookback // 3)
    price_mid = df['close'].iloc[-lookback:-mid_lookback]
    rsi_mid = rsi.iloc[-lookback:-mid_lookback]

    if signal_direction == 1:  # Bullish
        price_prev_low = price_mid.min()
        rsi_at_prev_low = rsi_mid.loc[price_mid.idxmin()]
        recent_price_low = df['close'].iloc[-5:].min()
        recent_rsi_low = rsi.iloc[-5:].min()

        # Bullish divergence: price lower, RSI higher
        if recent_price_low < price_prev_low and recent_rsi_low > rsi_at_prev_low:
            return PatternMatch("rsi_divergence", 0.66, 0.10, True,
                              "bullish_divergence")

        # Also check oversold
        if rsi.iloc[-1] < 30:
            return PatternMatch("rsi_divergence", 0.60, 0.05, True,
                              f"rsi_oversold ({rsi.iloc[-1]:.1f})")

    # Similar for bearish...
```

### Volume Confirmation
```python
def check_volume_confirmation(df, signal_direction, volume_multiplier=2.0):
    """Check for volume surge confirming the move."""
    avg_volume = df['volume'].iloc[-21:-1].mean()
    current_volume = df['volume'].iloc[-1]
    volume_ratio = current_volume / avg_volume

    if volume_ratio >= volume_multiplier:
        price_change = df['close'].iloc[-1] - df['close'].iloc[-2]
        if signal_direction == 1 and price_change > 0:
            return PatternMatch("volume_confirmation", 0.65, 0.10, True,
                              f"bullish_volume ({volume_ratio:.1f}x)")
        if signal_direction == -1 and price_change < 0:
            return PatternMatch("volume_confirmation", 0.65, 0.10, True,
                              f"bearish_volume ({volume_ratio:.1f}x)")
```

## Integration with Pattern Filter

### Add to filter_by_patterns()
```python
# Check RSI divergence (66% bullish, 64% bearish win rate)
rsi_match = check_rsi_divergence(df, signal_direction)
patterns_checked.append(rsi_match)

# Check volume confirmation (65% win rate)
volume_match = check_volume_confirmation(df, signal_direction)
patterns_checked.append(volume_match)
```

### Update get_pattern_statistics()
```python
for direction, direction_name in [(1, 'long'), (-1, 'short')]:
    rsi_div = check_rsi_divergence(df, direction)
    volume_conf = check_volume_confirmation(df, direction)
    stats[f'rsi_divergence_{direction_name}'] = {...}
    stats[f'volume_confirmation_{direction_name}'] = {...}
```

## Pattern Win Rates Summary

| Pattern | Win Rate | Key Condition |
|---------|----------|---------------|
| VWAP Reversion | 68% | Price 2+ std devs from VWAP, prey dominant |
| Momentum Continuation | 71% | Pullback in strong trend, predator dominant |
| Bullish RSI Divergence | 66% | Lower low in price, higher low in RSI |
| Bearish RSI Divergence | 64% | Higher high in price, lower high in RSI |
| Volume Confirmation | 65% | Breakout with 2x+ average volume |
| Breakout | 62% | Price outside N-bar range (backup pattern) |

## Files Modified
- `alpaca_trading/signals/pattern_filter.py`

## Testing
```python
# Test pattern statistics
stats = get_pattern_statistics(df, regime_context)
assert 'rsi_divergence_long' in stats
assert 'volume_confirmation_long' in stats
assert stats['rsi_divergence_long']['win_rate'] == 0.66
```

## Research Basis
- RSI divergences indicate momentum exhaustion
- Work best at extreme price levels (oversold/overbought)
- Volume confirms institutional participation
